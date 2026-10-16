// node netlify/functions/test.mjs — parser parity tests + saved-page checks against the Python verdicts
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { parse, variants } from "./lib/codes.mjs";
import { extractPage, assess, assessCat, extractListingId, parseAdvertUrl, coverage, otherRegion } from "./check-listing.mjs";
import { findCode, findAddress, building, lookup, suggest } from "./lib/register-data.mjs";
import { looksLikeCode } from "./search.mjs";

const MAX = { "VUT/MA": 102876 };
const keys = (t) => parse(t, MAX).junta.map((j) => j.key);
for (const raw of ["VUT/MA/08150", "VUT-MA-08150", "vut/ma/08150", "VFT/MA/08150", "VFT MA 08150", "VUTMA08150", "Vft/ma/8150", "VTF/MA/08150"])
  assert.deepEqual(keys(raw), ["VUT/MA/8150"], raw);
assert.equal(parse("ESFCTU0000290270005174700000000000000000VUT/MA/117055").national[0].embedded_regional, "VUT/MA/117055");
assert.equal(parse("CTC-2018150102").other[0].kind, "CTC_procedure_ref");
assert.ok(parse("VFT-AB-54678", MAX).junta[0].malformed);
assert.deepEqual(variants(parse("VUT/MA/062057", MAX).junta[0])[1], ["VUT/MA/6205", "exact+check_digit_stripped"]);
assert.equal(extractListingId("https://www.airbnb.co.uk/rooms/1000000000000000001?source=x"), "1000000000000000001");
assert.equal(parseAdvertUrl("https://www.booking.com/hotel/es/casa-x.en-gb.html?aid=1").id, "es/casa-x");
assert.equal(parseAdvertUrl("https://www.airbnb.es/rooms/12345678").platform, "airbnb");
assert.equal(parseAdvertUrl("https://example.com/x"), null);
console.log("parser tests ok");

// Register search (needs netlify/functions/data/search.json.gz from the pipeline build)
assert.ok(looksLikeCode("VUT/MA/14434") && looksLikeCode("vut-ma-14434") && looksLikeCode("14434") && !looksLikeCode("Calle Bolivia 121"));
{
  const c = findCode("vft-ma-14434");
  assert.equal(c.key, "VUT/MA/14434");
  assert.equal(c.rows[0].street, "Bolivia");
  // Principal del Candado 5 and 9 is one cadastral parcel: searching either number must find it, labelled with both.
  for (const n of ["5", "9"]) {
    const g = findAddress(`Calle Principal del Candado ${n}`, "malaga").find((b) => b.building === "9549202UF7694N");
    assert.ok(g && g.number_match && g.flats.every((f) => f.num === n), n);
    assert.equal(g.addresses[0], "Principal del Candado 5, 9");
  }
  assert.equal(building("9549202UF7694N").vut, 17);
  assert.equal(findAddress("Calle Inventada Que No Existe 27", "malaga").length, 0);
  // Typed number, no page: valid with the licence's registered address
  const v = assess({ registration_raw: "VUT/MA/14434" }, lookup());
  assert.equal(v.verdict, "VALID");
  assert.equal(v.licence.num, "121");
  // Autocomplete tolerates typos and half-typed words
  assert.equal(suggest("calle bolivai", "malaga").streets[0].name, "Bolivia");
  assert.equal(suggest("principal del cand 9", "malaga").streets[0].name, "Principal del Candado");
  assert.equal(suggest("principal del cand 9", "malaga").number, "9");
  assert.equal(assess({ registration_raw: "" }, lookup()).reason, "no_number");
  // A Junta code only shown at the tail of the national number is still checked
  assert.equal(assess({ registration_raw: "ESFCTU00002906700012345600000000000000000VUT/MA/14434" }, lookup()).verdict, "VALID");
  // Same "possibly exempt" rules as the city figures
  assert.equal(assess({ registration_raw: "", room_type: "Hotel room" }, lookup()).reason, "possibly_exempt");
  assert.deepEqual(assess({ registration_raw: "ESFCTU0000290670001234560000000000000000" }, lookup()).exempt, ["national_only"]);
  // Location: same rule as classify.py — other municipality beyond 800 m is "other_place", same one is "far"
  const lic = lookup().codes["VUT/MA/14434"];
  const near = { registration_raw: "VUT/MA/14434", lat: lic[1] + 0.012, lon: lic[2] };   // ~1.3 km north
  assert.equal(assess({ ...near, location: "Málaga, Andalucía, España" }, lookup()).reason, "far");
  assert.equal(assess({ ...near, location: "Torremolinos, Andalucía, España" }, lookup()).reason, "other_place");
  assert.equal(assess({ ...near }, lookup()).reason, "far");   // no town given: 3 km fallback
  // A room advert showing a whole-home ('Completa') licence: real number, but it doesn't fit the listing
  assert.equal(assess({ registration_raw: "VUT/MA/14434", room_type: "Private room" }, lookup()).reason, "type_mismatch");
  // Sevilla: city search, province filter, barrio ids that don't clash with Málaga's
  assert.ok(findAddress("Calle Feria 70", "sevilla").length > 0);
  assert.equal(findAddress("Calle Feria 70", "provincia").filter((b) => b.muni === "Sevilla").length, 0);
  assert.ok(suggest("santa cruz", "sevilla").barrios.some((b) => b.muni === "Sevilla"));
  assert.ok(!suggest("santa cruz", "malaga").barrios.some((b) => b.muni === "Sevilla"));
  assert.equal(assess({ registration_raw: "VUT/SE/00624" }, lookup()).verdict, "VALID");
  // Coverage: listings outside Andalucía aren't judged; other regions' numbers are recognised
  assert.equal(coverage({ location: "Málaga, Andalucía, España" }).covered, true);
  assert.equal(coverage({ location: "Barcelona, Cataluña, España" }).id, "barcelona");
  assert.equal(coverage({ lat: 41.39, lon: 2.17 }).id, "barcelona");
  assert.equal(coverage({ location: "Girona, Cataluña, España" }).covered, false);
  // Barcelona: HUTB numbers against the Generalitat register
  const bcn = lookup().cat["HUTB-002062"];
  assert.equal(assessCat({ registration_raw: "HUTB-002062", lat: bcn[1], lon: bcn[2], room_type: "Entire home/apt", location: "Barcelona" }, lookup()).reason, "valid");
  assert.equal(assessCat({ registration_raw: "HUTB-002062", lat: bcn[1], lon: bcn[2], room_type: "Private room", location: "Barcelona" }, lookup()).reason, "type_mismatch");
  assert.equal(assessCat({ registration_raw: "HUTB-000000" }, lookup()).reason, "not_in_register");
  assert.equal(assessCat({ registration_raw: "ESFCTU000008058000039706000000000000000HUTB-002062349" }, lookup()).key, "HUTB-002062");
  assert.equal(coverage({ lat: 37.39, lon: -5.99 }).covered, true);
  assert.equal(otherRegion("HUTB-012345"), "Catalunya");
  assert.equal(otherRegion("VT-12345-V"), "Comunitat Valenciana");
  assert.equal(otherRegion("VUT/MA/12345"), null);
  console.log("search tests ok");
}

// Parity on saved pages (only runs where the evidence folder is present)
// AUD: the original audit's sample200 verdicts (outside this repo), e.g. AUD=".../malaga_rta_audit/output/sample200/audit_sample200.json"
const EV = "pipeline/evidence", AUD = process.env.AUD || "";
if (existsSync(EV) && existsSync(AUD)) {
  const L = JSON.parse(gunzipSync(readFileSync("netlify/functions/data/lookup.json.gz")).toString());
  const py = Object.fromEntries(JSON.parse(readFileSync(AUD)).map((r) => [r.listing_id, r.licence_verdict]));
  let n = 0, same = 0; const diff = [];
  for (const id of Object.keys(py)) {
    if (!existsSync(`${EV}/${id}`)) continue;
    const f = readdirSync(`${EV}/${id}`).filter((x) => x.startsWith("live_")).sort().pop();
    if (!f) continue;
    const page = extractPage(gunzipSync(readFileSync(`${EV}/${id}/${f}`)).toString());
    if (!page.page_ok) continue;
    const v = assess(page, L).verdict; n++;
    const pv = py[id] === "POSSIBLY_EXEMPT" ? "NOT_VALID" : py[id]; // JS shows no-code as not valid + exemption caveat
    if (v === pv) same++; else diff.push([id, py[id], v]);
  }
  console.log(`saved-page parity: ${same}/${n} match the Python verdicts`);
  diff.slice(0, 10).forEach((d) => console.log("  diff", d));
}
