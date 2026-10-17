// GET /api/check?url=<Airbnb or Booking.com link>   or   /api/check?code=<number shown in the advert>
// Fetches the public advert page once, reads the registration number it displays and checks it against the
// Junta de Andalucía open register (data built by pipeline/site_build.py). No login, no CAPTCHA handling;
// results cached for 6 h per advert; per-IP rate limit. The response carries reason codes, not prose, so the
// site can phrase the answer in Spanish or English.
import { parse, variants, haversine } from "./lib/codes.mjs";
import { lookup, search, publicRow, norm } from "./lib/register-data.mjs";
import { json, rateLimited, clientIp } from "./lib/http.mjs";

const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36";
const CACHE = new Map(); // advert -> {at, body}
// Same location rule as the city figures (pipeline/rta_audit/classify.py, LOCATION_THRESHOLD_M):
//   within 800 m → matches; further away in the same municipality → valid but "far";
//   further away in another municipality → belongs somewhere else.
// The advert's municipality comes from its location line; without one, fall back to 3 km.
const THRESHOLD_M = 800;    // platform pin shift (up to ~150 m) + register geocoding error
const OTHER_PLACE_M = 3000; // only used when the advert doesn't say which town it's in
const HOTELISH = /hotel|hostel|aparthotel|boutique|bed and breakfast|guesthouse|pension/i;
const RURAL = /rural|cortijo|finca|farm/i;
let LONG_STAY;

export const config = { path: "/api/check" };

export function extractListingId(input) {
  if (!input) return null;
  const s = String(input).trim();
  const m = s.match(/airbnb\.[a-z.]+\/rooms\/(?:plus\/)?(\d{5,20})/i) || s.match(/^(\d{5,20})$/);
  return m ? m[1] : null;
}

export function parseAdvertUrl(input) {
  const s = String(input || "").trim();
  const id = extractListingId(s);
  if (id) return { platform: "airbnb", id, url: `https://www.airbnb.co.uk/rooms/${id}` };
  const b = s.match(/booking\.com\/hotel\/([a-z]{2})\/([a-z0-9\-_.]+?)(?:\.[a-z]{2}(?:-[a-z]{2})?)?\.html/i);
  if (b) return { platform: "booking", id: `${b[1]}/${b[2]}`, url: `https://www.booking.com/hotel/${b[1]}/${b[2]}.es.html` };
  return null;
}

function* walk(o) {
  if (o && typeof o === "object") {
    yield o;
    for (const v of Array.isArray(o) ? o : Object.values(o)) yield* walk(v);
  }
}

export function extractPage(html) {
  const out = { registration_raw: null, lat: null, lon: null, room_type: null, property_type: null, title: null, location: null };
  const reg = [];
  for (const m of html.matchAll(/<script[^>]*id="data-(?:deferred-state|injector-instances)[^"]*"[^>]*>([\s\S]*?)<\/script>/g)) {
    let blob;
    try { blob = JSON.parse(m[1]); } catch { continue; }
    for (const d of walk(blob)) {
      if (typeof d.title === "string" && /^(registration details|detalles del registro|licen[cs]e)/i.test(d.title)
          && d.html && d.html.htmlText) reg.push(d.html.htmlText);
      if (d.__typename === "DemandStayListingLocation" && d.coordinate) {
        out.lat = d.coordinate.latitude; out.lon = d.coordinate.longitude;
      }
      if (d.__typename === "StaysPdpLocation" && d.subtitle) out.location = d.subtitle;
      if (d.__typename === "PdpSharingConfig" && d.title && !out.title) out.title = d.title;
    }
  }
  const rt = html.match(/"listingLat":[^}]*?"roomType":"([^"]+)"/);
  if (rt) out.room_type = rt[1];
  const pt = [...html.matchAll(/"propertyType":"([^"]{1,60})"/g)].map((m) => m[1]).find((x) => x !== "OTHER");
  if (pt) out.property_type = pt;
  if (out.lat == null) {
    const la = html.match(/"listingLat":(-?[\d.]+)/), lo = html.match(/"listingLng":(-?[\d.]+)/);
    if (la && lo) { out.lat = +la[1]; out.lon = +lo[1]; }
  }
  out.registration_raw = [...new Set(reg)].join("\n") || null;
  out.page_ok = out.lat != null;
  return out;
}

/** Booking.com property page: the licence number sits in the fine print / "Número de licencia". */
export function extractBooking(html) {
  const out = { registration_raw: null, lat: null, lon: null, room_type: null, title: null, location: null };
  const ll = html.match(/data-atlas-latlng="(-?[\d.]+),(-?[\d.]+)"/);
  if (ll) { out.lat = +ll[1]; out.lon = +ll[2]; }
  const t = html.match(/<meta property="og:title" content="([^"]{1,200})"/);
  if (t) out.title = t[1];
  const text = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/g, " ").replace(/\s+/g, " ");
  const bits = [...text.matchAll(/(n[uú]mero de (licencia|registro)|licen[cs]e number|registration (number|details)|licencia)[^.]{0,160}/gi)]
    .map((m) => m[0]);
  out.registration_raw = [...new Set(bits)].join(" | ") || null;
  out.page_ok = !!(out.title && (out.lat != null || /hp_hotel_name|hotel_name/.test(html)));
  return out;
}

const licenceOf = (key) => {
  const rows = search().byKey.get(key);
  return rows ? publicRow(rows[0]) : null;
};

/**
 * Assess what an advert shows. page: {registration_raw, lat, lon, room_type, location}. Returns
 * {verdict, reason, shown, key, licence, ...}. Verdicts: VALID, VALID_CODE_SHARED, VALID_LOCATION_MISMATCH, NOT_VALID.
 * Reasons: valid, shared, far, other_place, cancelled, not_in_register, malformed, no_number.
 */
// ---- Coverage: we only check numbers against registers we have (today: Andalucía).
// Where a listing is: Airbnb's location line names the region ("Málaga, Andalucía, España"); else the map pin.
const COVERED = [
  // Mallorca only: the location line says "Illes Balears" for Menorca and Ibiza too, so the pin decides when there is one
  { id: "mallorca", name: "Mallorca", words: /mallorca|balear/i, pinOnly: true, inside: (la, lo) => la > 39.2 && la < 40.0 && lo > 2.3 && lo < 3.5 },
  { id: "murcia", name: "Murcia", region: "Región de Murcia", words: /^\s*murcia\b/i, inside: (la, lo) => la > 37.80 && la < 38.10 && lo > -1.35 && lo < -0.95 },
  { id: "laspalmas", name: "Las Palmas de Gran Canaria", region: "Canarias", words: /^\s*las palmas( de gran canaria)?\b/i, inside: (la, lo) => la > 28.03 && la < 28.18 && lo > -15.52 && lo < -15.38 },
  { id: "valencia", name: "Valencia", region: "Comunitat Valenciana", words: /^\s*val(e|è)ncia\b/i, inside: (la, lo) => la > 39.40 && la < 39.52 && lo > -0.43 && lo < -0.30 },
  { id: "bilbao", name: "Bilbao", region: "Euskadi", words: /^\s*bilbao\b/i, inside: (la, lo) => la > 43.21 && la < 43.29 && lo > -3.00 && lo < -2.87 },
  { id: "donostia", name: "San Sebastián", region: "Euskadi", words: /^\s*(donostia|san sebasti)/i, inside: (la, lo) => la > 43.27 && la < 43.34 && lo > -2.05 && lo < -1.92 },
  { id: "barcelona", name: "Barcelona", words: /^\s*barcelona\b/i, inside: (la, lo) => la > 41.32 && la < 41.47 && lo > 2.05 && lo < 2.23 },
  { id: "andalucia", name: "Andalucía", words: /andaluc/i,
  // rough outline of Andalucía (lat/lon box minus Murcia/Extremadura corners is close enough as a fallback)
  inside: (la, lo) => la > 35.9 && la < 38.75 && lo > -7.6 && lo < -1.6 && !(lo > -2.0 && la > 37.6) && !(lo < -5.6 && la > 38.2) }];
// Other regions' number formats, so a typed number from elsewhere gets "not covered yet" rather than "invalid"
const OTHER_FORMATS = [
  [/(?<![A-Z0-9])HUT[A-Z]{1,2}[\s\-_/.]*\d/i, "Catalunya"], [/(?<![A-Z0-9])VT-?\d{2,7}-?[VACS](?![A-Z0-9])/i, "Comunitat Valenciana"],
  [/(?<![A-Z0-9])E?[BLV]I\d{3,6}|(?<![A-Z0-9])ESS\d{4,6}/i, "Euskadi"],
  [/(?<![A-Z0-9])VT-\d{1,6}(?![A-Z0-9-])/i, "Comunidad de Madrid"]];
export function coverage(page) {
  const loc = page.location || "";
  if (loc) {
    const c = COVERED.find((r) => r.words.test(loc) && !(r.pinOnly && page.lat != null && !r.inside(page.lat, page.lon)));
    return c ? { covered: true, region: c.name, id: c.id } : { covered: false, place: loc.split(",")[0].trim(), region: loc.split(",").slice(-2, -1)[0]?.trim() || null };
  }
  if (page.lat != null) {
    const c = COVERED.find((r) => r.inside(page.lat, page.lon));
    return c ? { covered: true, region: c.name, id: c.id } : { covered: false, place: null, region: null };
  }
  return { covered: true };   // nothing to go on: check as usual
}
export function otherRegion(text) {
  const f = OTHER_FORMATS.find(([re]) => re.test(text || ""));
  return f ? f[1] : null;
}

// ---- Catalonia (Barcelona): HUTB-012345 numbers against the Generalitat register (same rules as pipeline/rta_audit/catalunya.py)
const CAT_RE = /(?<![A-Z0-9])(HUTB|HB|ATB|AJ|HSB|PB|HUT)[\s\-_/.]*0*(\d{1,6})(?![0-9])/gi;
const catKeyOf = (p, n) => `${p.toUpperCase() === "HUT" ? "HUTB" : p.toUpperCase()}-${String(+n).padStart(6, "0")}`;
export function assessCat(page, L, listingId = null) {
  const text = (page.registration_raw || "").replace(/<br\s*\/?>/gi, " | ");
  const national = [...text.matchAll(/(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*/gi)].map((m) => m[0]);
  const rest = text.replace(/(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*/gi, " ");
  let keys = [...new Set([...rest.matchAll(CAT_RE)].map((m) => catKeyOf(m[1], m[2])))];
  if (!keys.length) keys = [...new Set(national.flatMap((n) => [...n.matchAll(/HUTB-?(\d{6})/gi)].map((m) => `HUTB-${m[1]}`)))];
  const base = { shown: keys, national_numbers: national, register_date: L.register_lastUpdateData, region: "Catalunya" };
  const C = L.cat || {};
  if (!keys.length) {
    LONG_STAY ??= new Set(L.long_stay || []);
    const exempt = [];
    if (page.room_type === "Hotel room") exempt.push("hotel");
    if (listingId && LONG_STAY.has(String(listingId))) exempt.push("long_stay");
    if (national.length) exempt.push("national_only");
    if (/(exempt|exento)[^|]*(seasonal|temporada)/i.test(text)) exempt.push("seasonal_claim");
    return exempt.length ? { ...base, verdict: "POSSIBLY_EXEMPT", reason: "possibly_exempt", exempt } : { ...base, verdict: "NOT_VALID", reason: "no_number" };
  }
  let best = null;
  for (const k of keys) {
    const rec = C[k];
    let r;
    if (!rec) r = { k, v: 4 };
    else {
      const [mun, lat, lon, group] = rec;
      const dist = page.lat != null && lat != null ? Math.round(haversine(page.lat, page.lon, lat, lon)) : null;
      const other = mun && mun !== "Barcelona" && (page.lat != null || page.location);
      r = { k, mun, dist, group, v: other ? 2 : dist != null && dist > THRESHOLD_M ? 1 : 0 };
    }
    if (!best || r.v < best.v) best = r;
  }
  const res = { ...base, code: best.k, key: best.k, licence: licenceOf(best.k), licence_muni: best.mun || null, distance_m: best.dist ?? null };
  if (best.v === 0) {
    if (page.room_type && page.room_type !== "Entire home/apt" && best.group === "C") return { ...res, verdict: "VALID_TYPE_MISMATCH", reason: "type_mismatch" };
    const shared = (L.shared[best.k] || 0) > 1 && page.room_type === "Entire home/apt";
    return { ...res, verdict: shared ? "VALID_CODE_SHARED" : "VALID", reason: shared ? "shared" : "valid", shared_count: L.shared[best.k] || 0 };
  }
  if (best.v === 1) return { ...res, verdict: "VALID_LOCATION_MISMATCH", reason: "far" };
  if (best.v === 2) return { ...res, verdict: "NOT_VALID", reason: "other_place" };
  return { ...res, verdict: "NOT_VALID", reason: "not_in_register" };
}

// ---- Mallorca: ETV/1234, ETVPL/…, ETV60/…, VT/… (and hotel H/…, AT/…, AG/…) against the Consell de Mallorca registers
// (same rules as pipeline/rta_audit/baleares.py). The national number ends with the regional one plus a check digit.
const BAL_RE = /(?<![A-Z0-9])(ETV60|ETVPL|ETV|ET|VT|ABT|AG|AT|TI|HA|HR|HO|HS|H|CA|CE|EH)[\s\-_.]*\/\s*0*(\d{1,6})(?![0-9])|(?<![A-Z0-9])(ETV60|ETVPL|ETV)[\s\-_.]*0*(\d{1,6})(?![0-9])/gi;   // no bare "VT-12345": that's Valencia's format
const balKeyOf = (p, n) => `${p.toUpperCase() === "ET" ? "ETV" : p.toUpperCase()}/${+n}`;
const balMuni = (s) => norm(s).replace(/^PALMA DE MALLORCA$/, "PALMA");
export function assessBal(page, L, listingId = null) {
  const text = (page.registration_raw || "").replace(/<br\s*\/?>/gi, " | ");
  const NAT = /(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*/gi;
  const national = [...text.matchAll(NAT)].map((m) => m[0]);
  const rest = text.replace(NAT, " ");
  let keys = [...new Set([...rest.matchAll(BAL_RE)].map((m) => balKeyOf(m[1] || m[3], m[2] || m[4])))];
  if (!keys.length) keys = [...new Set(national.map((n) => /(ETV60|ETVPL|ETV|ET|VT)\/?(\d{2,7})$/i.exec(n.toUpperCase()))
    .filter(Boolean).map((m) => balKeyOf(m[1], m[2].slice(0, -1))))];
  const base = { shown: keys, national_numbers: national, register_date: L.register_lastUpdateData, region: "Illes Balears" };
  const B = L.bal || {};
  if (!keys.length) {
    LONG_STAY ??= new Set(L.long_stay || []);
    const exempt = [];
    if (page.room_type === "Hotel room") exempt.push("hotel");
    if (listingId && LONG_STAY.has(String(listingId))) exempt.push("long_stay");
    if (national.length) exempt.push("national_only");
    if (/(exempt|exento)[^|]*(seasonal|temporada)/i.test(text)) exempt.push("seasonal_claim");
    return exempt.length ? { ...base, verdict: "POSSIBLY_EXEMPT", reason: "possibly_exempt", exempt } : { ...base, verdict: "NOT_VALID", reason: "no_number" };
  }
  const place = balMuni((page.location || "").split(",")[0]);
  let best = null;
  for (const k of keys) {
    const rec = B[k];
    let r;
    if (!rec) r = { k, v: 4 };
    else {
      const [mun, lat, lon, group] = rec;
      const dist = page.lat != null && lat != null ? Math.round(haversine(page.lat, page.lon, lat, lon)) : null;
      // The location line names a town, which may be a village inside the municipality (Port de Pollença): only call it
      // another place when it is also well away from the registered point.
      const same = place ? place.includes(balMuni(mun)) || balMuni(mun).includes(place) : null;
      const v = /^(CE|EH)\//.test(k) || dist == null || dist <= THRESHOLD_M ? 0 : !same && dist > OTHER_PLACE_M ? 2 : 1;
      r = { k, mun, dist, group, v };
    }
    if (!best || r.v < best.v) best = r;
  }
  const res = { ...base, code: best.k, key: best.k, licence: licenceOf(best.k), licence_muni: best.mun || null, distance_m: best.dist ?? null };
  if (best.v === 0) {
    if (page.room_type && page.room_type !== "Entire home/apt" && best.group === "C") return { ...res, verdict: "VALID_TYPE_MISMATCH", reason: "type_mismatch" };
    const shared = (L.shared[best.k] || 0) > 1 && page.room_type === "Entire home/apt";
    return { ...res, verdict: shared ? "VALID_CODE_SHARED" : "VALID", reason: shared ? "shared" : "valid", shared_count: L.shared[best.k] || 0 };
  }
  if (best.v === 1) return { ...res, verdict: "VALID_LOCATION_MISMATCH", reason: "far" };
  if (best.v === 2) return { ...res, verdict: "NOT_VALID", reason: "other_place" };
  return { ...res, verdict: "NOT_VALID", reason: "not_in_register" };
}

// ---- Bilbao, Donostia: EBI00123 / ESS00123 (flats), LBI… (rooms), HBI… (hotels)… against the Basque register (REATE)
// (same rules as pipeline/rta_audit/euskadi.py). Six digits = five plus a check digit, as inside the national number.
const EUS_RE = /(?<![A-Z0-9])([ELHPTBKXC])[\s\-_./]*(BI|SS|VI)[\s\-_./]*(\d{1,6})(?![0-9])/gi;
const eusKeyOf = (l, p, n) => `${l.toUpperCase()}${p.toUpperCase()}${String(+(n.length === 6 ? n.slice(0, 5) : n)).padStart(5, "0")}`;
export function assessEus(page, L, listingId = null, home = null) {
  const text = (page.registration_raw || "").replace(/<br\s*\/?>/gi, " | ");
  const NAT = /(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*/gi;
  const national = [...text.matchAll(NAT)].map((m) => m[0]);
  const rest = text.replace(NAT, " ");
  let keys = [...new Set([...rest.matchAll(EUS_RE)].map((m) => eusKeyOf(m[1], m[2], m[3])))];
  if (!keys.length) keys = [...new Set(national.map((n) => /([ELHPTBKXC])(BI|SS|VI)(\d{5,6})$/i.exec(n.toUpperCase())).filter(Boolean).map((m) => eusKeyOf(m[1], m[2], m[3])))];
  const base = { shown: keys, national_numbers: national, register_date: L.register_lastUpdateData, region: "Euskadi" };
  const E = L.eus || {};
  if (!keys.length) {
    LONG_STAY ??= new Set(L.long_stay || []);
    const exempt = [];
    if (page.room_type === "Hotel room") exempt.push("hotel");
    if (listingId && LONG_STAY.has(String(listingId))) exempt.push("long_stay");
    if (national.length) exempt.push("national_only");
    if (/(exempt|exento)[^|]*(seasonal|temporada)/i.test(text)) exempt.push("seasonal_claim");
    return exempt.length ? { ...base, verdict: "POSSIBLY_EXEMPT", reason: "possibly_exempt", exempt } : { ...base, verdict: "NOT_VALID", reason: "no_number" };
  }
  let best = null;
  for (const k of keys) {
    const rec = E[k];
    let r;
    if (!rec) r = { k, v: 4 };
    else {
      const [mun, lat, lon, group] = rec;
      const dist = page.lat != null && lat != null ? Math.round(haversine(page.lat, page.lon, lat, lon)) : null;
      const other = home && mun && norm(mun) !== norm(home);   // the advert is in a city we cover; the number is registered elsewhere
      r = { k, mun, dist, group, v: other && (dist == null || dist > THRESHOLD_M) ? 2 : dist != null && dist > THRESHOLD_M ? 1 : 0 };
    }
    if (!best || r.v < best.v) best = r;
  }
  const res = { ...base, code: best.k, key: best.k, licence: licenceOf(best.k), licence_muni: best.mun || null, distance_m: best.dist ?? null };
  if (best.v === 0) {
    if (page.room_type && page.room_type !== "Entire home/apt" && best.group === "C") return { ...res, verdict: "VALID_TYPE_MISMATCH", reason: "type_mismatch" };
    const shared = (L.shared[best.k] || 0) > 1 && page.room_type === "Entire home/apt";
    return { ...res, verdict: shared ? "VALID_CODE_SHARED" : "VALID", reason: shared ? "shared" : "valid", shared_count: L.shared[best.k] || 0 };
  }
  if (best.v === 1) return { ...res, verdict: "VALID_LOCATION_MISMATCH", reason: "far" };
  if (best.v === 2) return { ...res, verdict: "NOT_VALID", reason: "other_place" };
  return { ...res, verdict: "NOT_VALID", reason: "not_in_register" };
}

// ---- Valencia: CV-VUT0012345-V / VT-12345-V against the Generalitat's register (same rules as pipeline/rta_audit/valencia.py).
// Hotel and tourist-apartment numbers (HV-, AT-) are in registers that aren't open: possibly exempt, not "invalid".
const VLC_RE = /(?<![A-Z0-9])(?:CV[\s\-_]*)?(VUT|VT)[\s\-_/.]*0*(\d{1,7})(?:[\s\-_/.]*(CS|V|A)(?![A-Z]))?/gi;
const VLC_OTHER = /(?<![A-Z0-9])(?:CV[\s\-_]*)?(AT|HV|HA|HCS|APT)[\s\-_/.]*0*\d{1,7}/i;
const vlcKeyOf = (n, p) => `CV-VUT${String(+n).padStart(7, "0")}-${p.toUpperCase()}`;
export function assessVlc(page, L, listingId = null) {
  const text = (page.registration_raw || "").replace(/<br\s*\/?>/gi, " | ");
  const NAT = /(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*/gi;
  const national = [...text.matchAll(NAT)].map((m) => m[0]);
  const rest = text.replace(NAT, " ");
  const V = L.vlc || {};
  let nums = [...rest.matchAll(VLC_RE)].map((m) => [m[2], m[3]]);
  if (!nums.length) nums = national.flatMap((n) => [...n.toUpperCase().matchAll(/(?:CV-?)?VU?T-?0*(\d{1,7})-?(CS|V|A)?/g)].map((m) => [m[1], m[2]]));
  const keys = [...new Set(nums.map(([n, p]) => p ? vlcKeyOf(n, p) : (["V", "A", "CS"].map((q) => vlcKeyOf(n, q)).find((k) => V[k]) || vlcKeyOf(n, "V"))))];
  const base = { shown: keys, national_numbers: national, register_date: L.register_lastUpdateData, region: "Comunitat Valenciana" };
  if (!keys.length) {
    LONG_STAY ??= new Set(L.long_stay || []);
    const exempt = [];
    if (page.room_type === "Hotel room" || VLC_OTHER.test(rest)) exempt.push("hotel");
    if (listingId && LONG_STAY.has(String(listingId))) exempt.push("long_stay");
    if (national.length) exempt.push("national_only");
    if (/(exempt|exento)[^|]*(seasonal|temporada)/i.test(text)) exempt.push("seasonal_claim");
    return exempt.length ? { ...base, verdict: "POSSIBLY_EXEMPT", reason: "possibly_exempt", exempt } : { ...base, verdict: "NOT_VALID", reason: "no_number" };
  }
  let best = null;
  for (const k of keys) {
    const rec = V[k];
    let r;
    if (!rec) r = { k, v: 4 };
    else {
      const [mun, lat, lon, group] = rec;
      const dist = page.lat != null && lat != null ? Math.round(haversine(page.lat, page.lon, lat, lon)) : null;
      const other = mun && norm(mun) !== "VALENCIA" && (page.lat != null || page.location);
      r = { k, mun, dist, group, v: other ? 2 : dist != null && dist > THRESHOLD_M ? 1 : 0 };
    }
    if (!best || r.v < best.v) best = r;
  }
  const res = { ...base, code: best.k, key: best.k, licence: licenceOf(best.k), licence_muni: best.mun || null, distance_m: best.dist ?? null };
  if (best.v === 0) {
    if (page.room_type && page.room_type !== "Entire home/apt" && best.group === "C") return { ...res, verdict: "VALID_TYPE_MISMATCH", reason: "type_mismatch" };
    const shared = (L.shared[best.k] || 0) > 1 && page.room_type === "Entire home/apt";
    return { ...res, verdict: shared ? "VALID_CODE_SHARED" : "VALID", reason: shared ? "shared" : "valid", shared_count: L.shared[best.k] || 0 };
  }
  if (best.v === 1) return { ...res, verdict: "VALID_LOCATION_MISMATCH", reason: "far" };
  if (best.v === 2) return { ...res, verdict: "NOT_VALID", reason: "other_place" };
  return { ...res, verdict: "NOT_VALID", reason: "not_in_register" };
}

// ---- Las Palmas de Gran Canaria: VV-35-1-0012345 against the Registro General Turístico de Canarias (pipeline/rta_audit/canarias.py).
// Hosts drop hyphens, leave out the province/island, or write VT for VV; the national number ends with the digits plus a check digit.
const CAN_RE = /(?<![A-Z0-9])(VV|VT|EMR|CR|HR|H|A|E|AT)((?:[\s\-_./]*\d){7,12})(?![0-9])/gi;
const canKeyOf = (typ, digits) => digits.length >= 10 ? `${typ.toUpperCase()}-${digits.slice(0, 2)}-${digits[2]}-${digits.slice(3, 10)}`
  : digits.length >= 7 ? `${typ.toUpperCase()}---${digits.slice(-7)}` : null;
export function assessCan(page, L, listingId = null) {
  const text = (page.registration_raw || "").replace(/<br\s*\/?>/gi, " | ");
  const NAT = /(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*/gi;
  const national = [...text.matchAll(NAT)].map((m) => m[0]);
  const rest = text.replace(NAT, " ");
  let keys = [...new Set([...rest.matchAll(CAN_RE)].map((m) => canKeyOf(m[1], m[2].replace(/\D/g, ""))).filter(Boolean))];
  if (!keys.length) keys = [...new Set(national.map((n) => /(VV|VT|EMR|CR|HR|H|A|E|AT)-?(\d{2})-?(\d)-?(\d{7})\d?$/i.exec(n.toUpperCase()))
    .filter(Boolean).map((m) => `${m[1]}-${m[2]}-${m[3]}-${m[4]}`))];
  const base = { shown: keys, national_numbers: national, register_date: L.register_lastUpdateData, region: "Canarias" };
  const C = L.can || {}, SH = L.can_short || {};
  const find = (k) => C[k] ? k : (() => { const typ = k.split("-")[0], num = k.slice(-7);
    for (const tt of typ === "VT" ? [typ, "VV"] : [typ]) if (SH[`${tt}-${num}`]) return SH[`${tt}-${num}`]; return null; })();
  if (!keys.length) {
    LONG_STAY ??= new Set(L.long_stay || []);
    const exempt = [];
    if (page.room_type === "Hotel room") exempt.push("hotel");
    if (listingId && LONG_STAY.has(String(listingId))) exempt.push("long_stay");
    if (national.length) exempt.push("national_only");
    if (/(exempt|exento)[^|]*(seasonal|temporada)/i.test(text)) exempt.push("seasonal_claim");
    return exempt.length ? { ...base, verdict: "POSSIBLY_EXEMPT", reason: "possibly_exempt", exempt } : { ...base, verdict: "NOT_VALID", reason: "no_number" };
  }
  let best = null;
  for (const k0 of keys) {
    const k = find(k0), rec = k && C[k];
    let r;
    if (!rec) r = { k: k0, v: 4 };
    else {
      const [mun, lat, lon] = rec;
      const dist = page.lat != null && lat != null ? Math.round(haversine(page.lat, page.lon, lat, lon)) : null;
      const other = mun && norm(mun) !== "LAS PALMAS DE GRAN CANARIA";
      r = { k, mun, dist, v: dist != null && dist <= THRESHOLD_M ? 0 : other ? 2 : dist != null ? 1 : 0 };
    }
    if (!best || r.v < best.v) best = r;
  }
  const res = { ...base, code: best.k, key: best.k, licence: licenceOf(best.k), licence_muni: best.mun || null, distance_m: best.dist ?? null };
  if (best.v === 0) {
    const shared = (L.shared[best.k] || 0) > 1 && page.room_type === "Entire home/apt";
    return { ...res, verdict: shared ? "VALID_CODE_SHARED" : "VALID", reason: shared ? "shared" : "valid", shared_count: L.shared[best.k] || 0 };
  }
  if (best.v === 1) return { ...res, verdict: "VALID_LOCATION_MISMATCH", reason: "far" };
  if (best.v === 2) return { ...res, verdict: "NOT_VALID", reason: "other_place" };
  return { ...res, verdict: "NOT_VALID", reason: "not_in_register" };
}

// ---- Murcia: VV.MU.6415-1 (and A.MU, H.MU, AR.MU…) against the ITREM register (pipeline/rta_audit/murcia.py).
const MUR_RE = /(?<![A-Z0-9])(VV|AR|ALB|CT|A|H)[\s.\-_]*MU[\s.\-_]*0*(\d{1,5})(?:[\s.\-_]+(\d{1,4}))?(?![0-9])/gi;
const murKeyOf = (p, n, k) => `${p.toUpperCase()}.MU.${+n}${k ? `-${+k}` : ""}`;
export function assessMur(page, L, listingId = null) {
  const text = (page.registration_raw || "").replace(/<br\s*\/?>/gi, " | ");
  const NAT = /(?<![A-Z0-9])ES[A-Z]{4}[0-9A-Z]{10,}[0-9A-Z/.\-]*/gi;
  const national = [...text.matchAll(NAT)].map((m) => m[0]);
  const rest = text.replace(NAT, " ");
  let keys = [...new Set([...rest.matchAll(MUR_RE)].map((m) => murKeyOf(m[1], m[2], m[3])))];
  if (!keys.length) keys = [...new Set(national.map((n) => /(VV|AR|A)[\s.\-_]*MU[\s.\-_]*0*(\d{1,5})(?:[\s.\-_]+(\d{1,4}))?$/i.exec(n.toUpperCase()))
    .filter(Boolean).map((m) => m[3] && m[3].length > 1 ? murKeyOf(m[1], m[2], m[3].slice(0, -1)) : !m[3] && m[2].length > 1 ? murKeyOf(m[1], m[2].slice(0, -1)) : murKeyOf(m[1], m[2], m[3])))];
  const base = { shown: keys, national_numbers: national, register_date: L.register_lastUpdateData, region: "Región de Murcia" };
  const M = L.mur || {}, F = L.mur_filing || {};
  // As pipeline/rta_audit/murcia.py: the filing alone, filing and flat run together, or a check digit on the flat
  const find = (k) => {
    if (M[k]) return k;
    const [base, flat] = k.split("-");
    if (flat && flat.length > 1 && M[`${base}-${flat.slice(0, -1)}`]) return `${base}-${flat.slice(0, -1)}`;
    if (!flat) { const i = base.lastIndexOf("."), pre = base.slice(0, i), num = base.slice(i + 1);
      for (const cut of [1, 2]) if (num.length > cut && M[`${pre}.${+num.slice(0, -cut)}-${+num.slice(-cut)}`]) return `${pre}.${+num.slice(0, -cut)}-${+num.slice(-cut)}`; }
    return F[base] || null;
  };
  if (!keys.length) {
    LONG_STAY ??= new Set(L.long_stay || []);
    const exempt = [];
    if (page.room_type === "Hotel room") exempt.push("hotel");
    if (listingId && LONG_STAY.has(String(listingId))) exempt.push("long_stay");
    if (national.length) exempt.push("national_only");
    if (/(exempt|exento)[^|]*(seasonal|temporada)/i.test(text)) exempt.push("seasonal_claim");
    return exempt.length ? { ...base, verdict: "POSSIBLY_EXEMPT", reason: "possibly_exempt", exempt } : { ...base, verdict: "NOT_VALID", reason: "no_number" };
  }
  let best = null;
  for (const k0 of keys) {
    const k = find(k0) || k0, rec = M[k];
    let r;
    if (!rec) r = { k, v: 4 };
    else {
      const [mun, lat, lon] = rec;
      const dist = page.lat != null && lat != null ? Math.round(haversine(page.lat, page.lon, lat, lon)) : null;
      r = { k, mun: mun || null, dist, v: !mun ? 2 : dist != null && dist > THRESHOLD_M ? 1 : 0 };
    }
    if (!best || r.v < best.v) best = r;
  }
  const res = { ...base, code: best.k, key: best.k, licence: licenceOf(best.k), licence_muni: best.mun || null, distance_m: best.dist ?? null };
  if (best.v === 0) {
    const shared = (L.shared[best.k] || 0) > 1 && page.room_type === "Entire home/apt";
    return { ...res, verdict: shared ? "VALID_CODE_SHARED" : "VALID", reason: shared ? "shared" : "valid", shared_count: L.shared[best.k] || 0 };
  }
  if (best.v === 1) return { ...res, verdict: "VALID_LOCATION_MISMATCH", reason: "far" };
  if (best.v === 2) return { ...res, verdict: "NOT_VALID", reason: "other_place", licence_muni: "Región de Murcia" };
  return { ...res, verdict: "NOT_VALID", reason: "not_in_register" };
}

export function assess(page, L, listingId = null) {
  const p = parse(page.registration_raw || "", L.max_issued);
  // Only a national number shown, with the Junta code at its tail (…0000VUT/MA/117055): check that code.
  if (!p.junta.length) p.junta = p.national.filter((n) => n.embedded_regional).flatMap((n) => parse(n.embedded_regional, L.max_issued).junta);
  const base = { shown: p.junta.map((j) => j.raw), national_numbers: p.national.map((n) => n.raw),
    ctc: p.other.some((o) => o.kind === "CTC_procedure_ref"), register_date: L.register_lastUpdateData };
  if (!p.junta.length) {
    // Same "possibly exempt" rules as the city figures (classify.py): don't call these "no number".
    LONG_STAY ??= new Set(L.long_stay || []);
    const exempt = [];
    if (page.room_type === "Hotel room" || HOTELISH.test(page.property_type || "")) exempt.push("hotel");
    if (listingId && LONG_STAY.has(String(listingId))) exempt.push("long_stay");
    if (p.national.length) exempt.push("national_only");
    if (p.exempt_text && /seasonal|temporada/i.test(p.exempt_text)) exempt.push("seasonal_claim");
    if (RURAL.test(page.property_type || "")) exempt.push("rural");
    if (exempt.length) return { ...base, verdict: "POSSIBLY_EXEMPT", reason: "possibly_exempt", exempt };
    return { ...base, verdict: "NOT_VALID", reason: "no_number" };
  }
  const place = norm(page.location || "");
  // Does the advert's location line name this municipality? null when the advert gives no location.
  const sameMuni = (mun) => (place ? place.includes(norm(mun)) : null);
  let best = null;
  for (const j of p.junta) {
    let hit = null;
    for (const [key, variant] of variants(j)) {
      if (L.cancelled[key]) { hit = { key, variant, cancelled: L.cancelled[key] }; break; }
      const rec = L.codes[key];
      if (!rec) continue;
      // Prefer a correction that lands where the advert is (by pin distance, else by the advert's stated town).
      const d = page.lat != null && rec[1] != null ? haversine(page.lat, page.lon, rec[1], rec[2]) : null;
      const here = d != null ? d <= THRESHOLD_M || (sameMuni(rec[0]) ?? d <= OTHER_PLACE_M) : sameMuni(rec[0]) === true;
      if (!hit || (here && !hit.here)) hit = { key, variant, rec, here };
      if (here) break;
    }
    const r = { j, hit };
    if (hit?.cancelled) r.v = 3;
    else if (hit?.rec) {
      const [mun, lat, lon, group] = hit.rec;
      r.dist = page.lat != null && lat != null ? Math.round(haversine(page.lat, page.lon, lat, lon)) : null;
      r.muni = mun;
      const same = sameMuni(mun);
      r.other_place = r.dist != null ? r.dist > THRESHOLD_M && !(same ?? r.dist <= OTHER_PLACE_M) : same === false;
      r.far = !r.other_place && r.dist != null && r.dist > THRESHOLD_M;
      r.shared = group === "C" ? (L.shared[hit.key] || 0) : 0; // only whole-dwelling ('Completa') VUTs
      r.group = group;
      r.v = r.other_place ? 2 : r.far ? 1 : 0;
    } else r.v = j.malformed ? 5 : 4;
    if (!best || r.v < best.v) best = r;
  }
  const { j, hit } = best;
  const res = { ...base, code: j.raw, key: hit?.key || j.key, corrected: !!(hit && hit.variant !== "exact"),
    licence: hit?.key ? licenceOf(hit.key) : null, licence_muni: best.muni || null, distance_m: best.dist ?? null };
  if (best.v === 0) {
    const shared = best.shared > 1 && page.room_type === "Entire home/apt";
    const room = page.room_type && page.room_type !== "Entire home/apt" && best.group === "C";   // room advert, whole-home licence
    if (room) return { ...res, verdict: "VALID_TYPE_MISMATCH", reason: "type_mismatch" };
    return { ...res, verdict: shared ? "VALID_CODE_SHARED" : "VALID", reason: shared ? "shared" : "valid", shared_count: best.shared };
  }
  if (best.v === 1) return { ...res, verdict: "VALID_LOCATION_MISMATCH", reason: "far" };
  if (best.v === 2) return { ...res, verdict: "NOT_VALID", reason: "other_place" };
  if (best.v === 3) return { ...res, verdict: "NOT_VALID", reason: "cancelled", cancel_date: hit.cancelled.date };
  if (best.v === 4) return { ...res, verdict: "NOT_VALID", reason: "not_in_register" };
  return { ...res, verdict: "NOT_VALID", reason: "malformed", problems: j.problems };
}

export default async (req, context) => {
  const url = new URL(req.url);
  const L = lookup();
  const ip = clientIp(req, context);

  // A number typed in by hand: no advert page, so no location checks.
  const code = (url.searchParams.get("code") || "").slice(0, 80);
  if (code) {
    if (rateLimited(ip, 60)) return json(429, { error: "rate_limited" });
    const isCat = CAT_RE.test(code); CAT_RE.lastIndex = 0;
    const isBal = !isCat && BAL_RE.test(code); BAL_RE.lastIndex = 0;
    const isEus = !isCat && !isBal && EUS_RE.test(code); EUS_RE.lastIndex = 0;
    const isMur = /(?<![A-Z0-9])(VV|AR|ALB|CT|A|H)[\s.\-_]*MU[\s.\-_]*\d/i.test(code);
    const isCan = !isMur && /(?<![A-Z0-9])VV[\s\-_./]*\d/i.test(code);
    const isVlc = !isCan && !isCat && !isBal && !isEus && /(?<![A-Z0-9])(?:CV[\s\-_]*)?VUT|(?<![A-Z0-9])VT[\s\-_]*\d{1,7}[\s\-_]*(CS|V|A)(?![A-Z0-9])/i.test(code);
    const res = isCat ? assessCat({ registration_raw: code }, L) : isBal ? assessBal({ registration_raw: code }, L)
      : isEus ? assessEus({ registration_raw: code }, L) : isMur ? assessMur({ registration_raw: code }, L) : isCan ? assessCan({ registration_raw: code }, L)
      : isVlc ? assessVlc({ registration_raw: code }, L) : assess({ registration_raw: code }, L);
    const other = !isCat && !isBal && !isEus && !isVlc && !isCan && !isMur && !res.shown.length && otherRegion(code);   // e.g. a Valencian VT- number typed in
    if (other) return json(200, { mode: "code", checked_at: new Date().toISOString(), verdict: "NOT_COVERED", reason: "not_covered",
      region: other, code, register_date: L.register_lastUpdateData });
    return json(200, { mode: "code", checked_at: new Date().toISOString(), ...res });
  }

  const ad = parseAdvertUrl(url.searchParams.get("url") || url.searchParams.get("id"));
  if (!ad) return json(400, { error: "bad_url" });
  const c = CACHE.get(ad.url);
  if (c && Date.now() - c.at < 6 * 3600 * 1000) return json(200, { ...c.body, cached: true });
  if (rateLimited(ip, 20)) return json(429, { error: "rate_limited" });
  let res;
  try {
    res = await fetch(ad.url, { headers: { "user-agent": UA, "accept-language": "es-ES,es;q=0.9,en;q=0.8" } });
  } catch {
    return json(502, { error: "unreachable", platform: ad.platform });
  }
  const meta = { mode: "url", platform: ad.platform, listing_url: ad.url, checked_at: new Date().toISOString() };
  if (res.status === 404 || res.status === 410) return json(200, { ...meta, verdict: "REMOVED", reason: "removed" });
  if (res.status !== 200) return json(200, { ...meta, verdict: "UNREADABLE", reason: "blocked", http: res.status });
  const html = await res.text();
  const page = ad.platform === "airbnb" ? extractPage(html) : extractBooking(html);
  if (!page.page_ok) return json(200, { ...meta, verdict: "UNREADABLE", reason: "unreadable" });
  const cov = coverage(page);
  const body = !cov.covered
    ? { ...meta, title: page.title, location: page.location, verdict: "NOT_COVERED", reason: "not_covered", place: cov.place,
        region: cov.region || otherRegion(page.registration_raw), shown_text: (page.registration_raw || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 200),
        register_date: L.register_lastUpdateData }
    : { ...meta, title: page.title, location: page.location, room_type: page.room_type,
        pin: page.lat != null ? [page.lat, page.lon] : null,
        ...({ barcelona: assessCat, mallorca: assessBal, bilbao: assessEus, donostia: assessEus, valencia: assessVlc, laspalmas: assessCan, murcia: assessMur }[cov.id] || assess)(page, L, ad.platform === "airbnb" ? ad.id : null,
          { bilbao: "Bilbao", donostia: "Donostia / San Sebastián" }[cov.id]) };
  CACHE.set(ad.url, { at: Date.now(), body });
  return json(200, body);
};
