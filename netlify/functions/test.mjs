// node netlify/functions/test.mjs — parser parity tests + saved-page checks against the Python verdicts
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { parse, variants } from "./lib/codes.mjs";
import { extractPage, assess, assessCat, assessBal, assessEus, assessVlc, assessCan, assessMur, assessMad, extractListingId, parseAdvertUrl, coverage, otherRegion } from "./check-listing.mjs";
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
  if (Object.keys(lookup().cat || {}).length) {   // (skipped when this region's data didn't download)
    // Barcelona: HUTB numbers against the Generalitat register
    const bcn = lookup().cat["HUTB-002062"];
    assert.equal(assessCat({ registration_raw: "HUTB-002062", lat: bcn[1], lon: bcn[2], room_type: "Entire home/apt", location: "Barcelona" }, lookup()).reason, "valid");
    assert.equal(assessCat({ registration_raw: "HUTB-002062", lat: bcn[1], lon: bcn[2], room_type: "Private room", location: "Barcelona" }, lookup()).reason, "type_mismatch");
    assert.equal(assessCat({ registration_raw: "HUTB-000000" }, lookup()).reason, "not_in_register");
    assert.equal(assessCat({ registration_raw: "ESFCTU000008058000039706000000000000000HUTB-002062349" }, lookup()).key, "HUTB-002062");
  }
  assert.equal(coverage({ lat: 37.39, lon: -5.99 }).covered, true);
  // Mallorca: ETV numbers against the Consell de Mallorca registers; Menorca and Ibiza aren't covered
  assert.equal(coverage({ location: "Sóller, Illes Balears, España", lat: 39.77, lon: 2.71 }).id, "mallorca");
  assert.equal(coverage({ location: "Eivissa, Illes Balears, España", lat: 38.91, lon: 1.43 }).covered, false);
  assert.equal(coverage({ location: "Maó, Illes Balears, España", lat: 39.89, lon: 4.26 }).covered, false);
  if (lookup().bal?.["ETV/10070"]) {   // (skipped when this region's data didn't download)
    const etv = lookup().bal["ETV/10070"];
    assert.equal(assessBal({ registration_raw: "Mallorca - Regional registration number<br />ETV/10070", lat: etv[1], lon: etv[2], room_type: "Entire home/apt", location: "Alcúdia" }, lookup()).verdict.startsWith("VALID"), true);
    assert.equal(assessBal({ registration_raw: "ETV/10070", lat: etv[1], lon: etv[2], room_type: "Private room", location: "Alcúdia" }, lookup()).reason, "type_mismatch");
    assert.equal(assessBal({ registration_raw: "ETV/10070", lat: 39.57, lon: 2.65, room_type: "Entire home/apt", location: "Palma" }, lookup()).reason, "other_place");
    assert.equal(assessBal({ registration_raw: "ETV/999999" }, lookup()).reason, "not_in_register");
    assert.equal(assessBal({ registration_raw: "ESFCTU00000703500012345600000000000000000ETV/100700" }, lookup()).key, "ETV/10070");
    assert.equal(assessBal({ registration_raw: "" }, lookup()).reason, "no_number");
    assert.ok(looksLikeCode("ETV/10070") && findCode("ETV/10070").rows.length > 0);
    assert.ok(findAddress("Carrer Miramar 10", "mallorca").length > 0);
  }
  // Bilbao, Donostia: Basque numbers against the REATE; the rest of Euskadi isn't covered yet
  assert.equal(coverage({ location: "Bilbao, País Vasco, España", lat: 43.26, lon: -2.93 }).id, "bilbao");
  assert.equal(coverage({ location: "Donostia-San Sebastián, Gipuzkoa, España" }).id, "donostia");
  assert.equal(coverage({ location: "Getxo, País Vasco, España" }).covered, false);
  if (lookup().eus?.["EBI00003"]) {   // (skipped when this region's data didn't download)
    const ebi = lookup().eus["EBI00003"];
    assert.ok(ebi);   // (its coordinates come from the councils' address points, when those downloaded)
    assert.equal(assessEus({ registration_raw: "Basque Country - Regional registration number<br />EBI00003", lat: ebi[1], lon: ebi[2], room_type: "Entire home/apt", location: "Bilbao" }, lookup(), null, "Bilbao").verdict.startsWith("VALID"), true);
    assert.equal(assessEus({ registration_raw: "EBI00003", lat: ebi[1], lon: ebi[2], room_type: "Private room" }, lookup(), null, "Bilbao").reason, "type_mismatch");
    if (ebi[1] != null) assert.equal(assessEus({ registration_raw: "EBI00003", lat: 43.32, lon: -1.98, room_type: "Entire home/apt" }, lookup(), null, "Donostia / San Sebastián").reason, "other_place");
    assert.equal(assessEus({ registration_raw: "ESS99999" }, lookup()).reason, "not_in_register");
    assert.equal(assessEus({ registration_raw: "ESFCTU0000480200000123450000000000000000EBI000034" }, lookup()).key, "EBI00003");
    assert.ok(looksLikeCode("EBI00003") && findCode("EBI00003").rows.length > 0);
    assert.ok(findAddress("Bidebarrieta 7", "bilbao").length > 0);
  }
  // Valencia, Murcia, Las Palmas
  assert.equal(coverage({ location: "València, Comunidad Valenciana, España" }).id, "valencia");
  assert.equal(coverage({ location: "Murcia, Región de Murcia, España" }).id, "murcia");
  assert.equal(coverage({ location: "Las Palmas de Gran Canaria, Canarias, España" }).id, "laspalmas");
  if (Object.values(lookup().vlc || {}).some((v) => v[1] != null)) {   // (skipped when this region's data didn't download)
    const vk = Object.keys(lookup().vlc).find((k) => lookup().vlc[k][0] && /VAL/i.test(lookup().vlc[k][0]) && lookup().vlc[k][1]);
    const vr = lookup().vlc[vk];
    assert.equal(assessVlc({ registration_raw: vk.replace(/^CV-VUT0*(\d+)-V$/, "VT-$1-V"), lat: vr[1], lon: vr[2], room_type: "Entire home/apt" }, lookup()).verdict.startsWith("VALID"), true);
    assert.equal(assessVlc({ registration_raw: "VT-9999999-V" }, lookup()).reason, "not_in_register");
    assert.equal(assessVlc({ registration_raw: "HV-1234" }, lookup()).reason, "possibly_exempt");
  }
  if (lookup().mur?.["VV.MU.6254-1"]) {   // (skipped when this region's data didn't download)
    assert.equal(assessMur({ registration_raw: "VV MU 6254-1" }, lookup()).key, "VV.MU.6254-1");
    assert.equal(assessMur({ registration_raw: "VV.MU.6254" }, lookup()).key, "VV.MU.6254-1");   // the filing alone
  }
  if (Object.keys(lookup().can || {}).length) {   // (skipped when this region's data didn't download)
    assert.equal(assessCan({ registration_raw: "VV-35-10022236" }, lookup()).key, "VV-35-1-0022236");
  }
  if (lookup().mur?.["VV.MU.6254-1"] && lookup().can?.["VV-35-1-0000750"]) {   // (skipped when this region's data didn't download)
    assert.ok(findCode("VV.MU.6254-1").rows.length > 0 && findCode("VV-35-1-0000750").rows.length > 0 && findAddress("Luis Morote 42", "laspalmas").length > 0 && findAddress("Sucina", "murcia").length > 0);
  }
  if (Object.keys(lookup().mad || {}).length) {   // Madrid: showing the number isn't required, and the result says so
    assert.equal(coverage({ location: "Madrid, Comunidad de Madrid, España" }).id, "madrid");
    const mk = Object.keys(lookup().mad).find((k) => k.startsWith("VT-") && lookup().mad[k][0] === "Madrid" && lookup().mad[k][1] != null);
    const mr = lookup().mad[mk];
    assert.equal(assessMad({ registration_raw: `Madrid - Regional registration number<br />${mk}`, lat: mr[1], lon: mr[2], room_type: "Entire home/apt" }, lookup()).verdict.startsWith("VALID"), true);
    const none = assessMad({ registration_raw: "" }, lookup());
    assert.equal(none.reason, "no_number"); assert.equal(none.number_required, false);
    assert.equal(assessVlc({ registration_raw: "VT-12345-V" }, lookup()).region, "Comunitat Valenciana");   // Valencia's VT- keeps its -V
  }
  assert.equal(otherRegion("VT-12345-V"), "Comunitat Valenciana");   // Valencia's VT- isn't read as Balearic
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
