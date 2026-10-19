// Loads the function data written by pipeline/site_build.py and answers register queries.
//   lookup.json.gz — every tourist-accommodation code in Andalucía (municipality, coords, group)
//   search.json.gz — every tourist-accommodation record in Málaga province, with address fields
// Both are read once per function instance (~100 ms) and kept in memory; no database needed.
import { existsSync, readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parse, variants, normaliseKey } from "./codes.mjs";

// Netlify bundles each function into one file, so this module's own location differs between local runs
// (netlify/functions/lib/) and production (the bundle). included_files keep their repo-relative path, so try both.
const HERE = dirname(fileURLToPath(import.meta.url));
const DATA = [join(HERE, "..", "data"), join(HERE, "data"), join(process.cwd(), "netlify", "functions", "data"),
  "/var/task/netlify/functions/data"].find((d) => existsSync(join(d, "lookup.json.gz"))) || join(HERE, "..", "data");
const gz = (f) => JSON.parse(gunzipSync(readFileSync(join(DATA, f))).toString("utf8"));

let LOOKUP, SEARCH;
export function lookup() {
  if (!LOOKUP) LOOKUP = gz("lookup.json.gz");
  return LOOKUP;
}

export const norm = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase()
  .replace(/[^A-Z0-9]+/g, " ").trim();
const STREET_TYPES = new Set(["C", "CL", "CALLE", "AV", "AVD", "AVDA", "AVENIDA", "PZA", "PL", "PLAZA", "PASEO", "PSO", "PS",
  "URB", "URBANIZACION", "CTRA", "CARRETERA", "CAMINO", "PASAJE", "ALAMEDA", "N", "NO", "NUM", "NUMERO"]);
const STOP = new Set(["DE", "DEL", "LA", "LAS", "EL", "LOS", "Y", "THE"]);
const AREA_MUNI = { malaga: "MALAGA", marbella: "MARBELLA", sevilla: "SEVILLA", granada: "GRANADA", cordoba: "CORDOBA", cadiz: "CADIZ",
  barcelona: "BARCELONA", bilbao: "BILBAO", donostia: "DONOSTIA SAN SEBASTIAN", valencia: "VALENCIA",
  laspalmas: "LAS PALMAS DE GRAN CANARIA", murcia: "MURCIA", zaragoza: "ZARAGOZA", madrid: "MADRID", palma: "PALMA" };
const AREA_PROV = { provincia: "MA", "provincia-sevilla": "SE", "provincia-cadiz": "CA", "provincia-granada": "GR",
  "provincia-almeria": "AL", "provincia-cordoba": "CO", "provincia-huelva": "HU", "provincia-jaen": "JA", mallorca: "IB" };   // "andalucia" = everything
/** Does a register row (or street/barrio entry with _muni/prov) belong to this area? */
const inArea = (r, area) => AREA_MUNI[area] ? r._muni === AREA_MUNI[area]
  : AREA_PROV[area] && r.prov ? r.prov === AREA_PROV[area] : true;   // (data built before "prov" existed: no filter)
const POSTCODE = /^(04|07|08|11|14|18|20|21|23|28|29|30|35|41|46|48|50)\d{3}$/;   // provinces we cover
const BARRIO_ALIASES = { SOHO: "ENSANCHE CENTRO" };
const codeKey = (code) => {
  const c = String(code || "").trim().toUpperCase();
  const m = /^([A-Z]+)\/([A-Z]{2})\/(\d+)$/.exec(c);
  if (m) return normaliseKey(m[1], m[2], m[3]);
  const k = /^(HUTB|HB|ATB)-?0*(\d{1,6})$/.exec(c);   // Catalonia (Barcelona): HUTB-012345
  if (k) return `${k[1]}-${k[2].padStart(6, "0")}`;
  const b = /^(ETV60|ETVPL|ETV|VT|ABT|AG|AT|TI|HA|HR|HO|HS|H|CA)\/0*(\d{1,6})$/.exec(c);   // Mallorca: ETV/1234
  if (b) return `${b[1]}/${+b[2]}`;
  const e = /^([ELHPTBKXC])(BI|SS|VI)0*(\d{1,5})$/.exec(c);   // Euskadi (EBI00123)
  if (e) return `${e[1]}${e[2]}${e[3].padStart(5, "0")}`;
  const v = /^CV-VUT0*(\d{1,7})-(A|V|CS)$/.exec(c);   // Comunitat Valenciana
  if (v) return `CV-VUT${v[1].padStart(7, "0")}-${v[2]}`;
  if (/^(VV|VT|EMR|CR|HR|H|A|E|AT)-(\d{2})?-(\d)?-\d{7}$/.test(c)) return c;   // Canarias (VV-35-1-0012345)
  const u = /^(VV|A|AR|H|CT|ALB)\.MU\.0*(\d+)(?:-(\d+))?$/.exec(c);   // Región de Murcia (VV.MU.6415-1)
  if (u) return `${u[1]}.MU.${+u[2]}${u[3] ? `-${+u[3]}` : ""}`;
  const z = /^VUT?-(HU|TE|ZA)-(\d{2})-0*(\d+)$/.exec(c);   // Aragón: VU-ZA-18-101 → ZA-18-101
  if (z) return `${z[1]}-${z[2]}-${+z[3]}`;
  const md = /^(VT|HM|AM|TR|HH|HR|AR|CM|CH|HS)-0*(\d{1,6})$/.exec(c);   // Comunidad de Madrid (VT-12345)
  if (md) return `${md[1]}-${+md[2]}`;
  const cl = /^(05|09|24|34|37|40|42|47|49)\/0*(\d{1,6})$/.exec(c);   // Castilla y León (47/000547 → 47/547)
  return cl ? `${cl[1]}/${+cl[2]}` : null;
};
/** A Mallorca number typed in (ETV/1234, ETVPL 12345, H/123…) → its key, else null. */
export const balKey = (q) => {
  const m = /(?<![A-Z0-9])(ETV60|ETVPL|ETV|ET|VT|ABT|AG|AT|TI|HA|HR|HO|HS|H|CA)[\s\-_.]*\/\s*0*(\d{1,6})(?![0-9])|(?<![A-Z0-9])(ETV60|ETVPL|ETV)[\s\-_.]*0*(\d{1,6})(?![0-9])/i
    .exec(String(q || ""));
  if (!m) return null;
  const p = (m[1] || m[3]).toUpperCase();
  return `${p === "ET" ? "ETV" : p}/${+(m[2] || m[4])}`;
};
/** A Basque number typed in (EBI00123, ESS-123, LBI 00456…) → its key, else null. */
export const eusKey = (q) => {
  const m = /(?<![A-Z0-9])([ELHPTBKXC])[\s\-_./]*(BI|SS|VI)[\s\-_./]*(\d{1,6})(?![0-9])/i.exec(String(q || ""));
  if (!m) return null;
  const n = m[3].length === 6 ? m[3].slice(0, 5) : m[3];
  return `${m[1].toUpperCase()}${m[2].toUpperCase()}${String(+n).padStart(5, "0")}`;
};
/** A Valencian number typed in (CV-VUT0012345-V, VT-12345-V, VT12345V) → its key (province V if left out), else null. */
export const vlcKey = (q) => {
  const m = /(?<![A-Z0-9])(?:CV[\s\-_]*)?(VUT|VT)[\s\-_/.]*0*(\d{1,7})(?:[\s\-_/.]*(CS|V|A)(?![A-Z]))?/i.exec(String(q || ""));
  if (!m || (m[1].toUpperCase() === "VT" && !m[3] && !/CV/i.test(q))) return null;   // a bare VT-123 could be Madrid's
  return `CV-VUT${m[2].padStart(7, "0")}-${(m[3] || "V").toUpperCase()}`;
};
/** A Canarian number typed in (VV-35-1-0012345, VV3510012345, VV-35-10012345) → its key, else null. */
export const canKey = (q) => {
  const m = /(?<![A-Z0-9])(VV)((?:[\s\-_./]*\d){7,12})(?![0-9])/i.exec(String(q || ""));
  if (!m) return null;
  const d = m[2].replace(/\D/g, "");
  return d.length >= 10 ? `VV-${d.slice(0, 2)}-${d[2]}-${d.slice(3, 10)}` : `VV---${d.slice(-7)}`;
};
/** A Murcian number typed in (VV.MU.6415-1, VV MU 6415-1, VVMU6415.1) → its key, else null. */
export const murKey = (q) => {
  const m = /(?<![A-Z0-9])(VV|AR|ALB|CT|A|H)[\s.\-_]*MU[\s.\-_]*0*(\d{1,5})(?:[\s.\-_]+(\d{1,4}))?(?![0-9])/i.exec(String(q || ""));
  return m ? `${m[1].toUpperCase()}.MU.${+m[2]}${m[3] ? `-${+m[3]}` : ""}` : null;
};
export const catKey = (q) => { const m = /(?<![A-Z0-9])(HUTB|HB|ATB)[\s\-_/.]*0*(\d{1,6})(?![0-9])/i.exec(String(q || "")); return m ? `${m[1].toUpperCase()}-${m[2].padStart(6, "0")}` : null; };
const cleanNum = (n) => String(n || "").toUpperCase().replace(/^0+(?=\w)/, "");

export function search() {
  if (SEARCH) return SEARCH;
  const raw = gz("search.json.gz");
  const F = raw.fields;
  const rows = raw.rows.map((r) => Object.fromEntries(F.map((f, i) => [f, r[i]])));
  const byKey = new Map(), byBuilding = new Map();
  for (const r of rows) {
    r._key = codeKey(r.code);
    r._muni = norm(r.muni);
    r._street = norm(r.street).split(" ").filter((w) => !STOP.has(w) && !STREET_TYPES.has(w)).join(" ");
    r._hay = ` ${norm([r.street, r.complement, r.locality, r.barrio, r.muni, r.postcode].join(" "))} `;
    if (r._key) (byKey.get(r._key) || byKey.set(r._key, []).get(r._key)).push(r);
    (byBuilding.get(r.building) || byBuilding.set(r.building, []).get(r.building)).push(r);
  }
  // Street index for autocomplete: one entry per (street, municipality), named by its most common spelling.
  const streets = new Map();
  for (const r of rows) {
    if (!r._street) continue;
    const k = `${r._street}|${r._muni}`;
    let s = streets.get(k);
    if (!s) streets.set(k, (s = { key: r._street, words: r._street.split(" "), muni: r.muni, _muni: r._muni, prov: r.prov, forms: new Map(), vut: 0, b: new Set() }));
    s.forms.set(r.street, (s.forms.get(r.street) || 0) + 1);
    if (r.kind === "VUT") s.vut++;
    s.b.add(r.building);
  }
  for (const s of streets.values()) {
    s.name = [...s.forms.entries()].sort((a, b) => b[1] - a[1])[0][0];
    s.messy = /\d|[,()/;:]|\s-\s|\. /.test(s.name) || s.words.length > 5;   // free-text addresses typed into the street field
    s.buildings = s.b.size;
    delete s.forms; delete s.b;
  }
  // Official barrios (Málaga and Sevilla cities), so a neighbourhood name works too. Ids are per city.
  const barrios = new Map();
  for (const r of rows) {
    if (r.barrio_id == null) continue;
    const bk = `${r._muni}:${r.barrio_id}`;
    let b = barrios.get(bk);
    if (!b) barrios.set(bk, (b = { id: r.barrio_id, name: r.barrio, muni: r.muni, _muni: r._muni, prov: r.prov, vut: 0,
      words: norm(r.barrio).split(" ").filter((w) => !STOP.has(w)) }));
    if (r.kind === "VUT") b.vut++;
  }
  // Everyday names for official barrios.
  for (const [alias, official] of Object.entries(BARRIO_ALIASES)) {
    const b = [...barrios.values()].find((x) => norm(x.name) === official);
    if (b) barrios.set(`${b.id}:${alias}`, { ...b, name: `${alias[0] + alias.slice(1).toLowerCase()} (${b.name})`, words: [alias] });
  }
  SEARCH = { built_at: raw.built_at, register_date: raw.register_lastUpdateData, rows, byKey, byBuilding, streets: [...streets.values()],
    barrios: [...barrios.values()] };
  return SEARCH;
}

/** Optimal string alignment distance (Levenshtein + adjacent swaps), stopping early above `max`. */
function dist(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev2 = null, prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      let v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (prev2 && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, prev2[j - 2] + 1);
      cur.push(v);
      best = Math.min(best, v);
    }
    if (best > max) return max + 1;
    prev2 = prev; prev = cur;
  }
  return prev[b.length];
}
const allowed = (w) => (w.length <= 3 ? 0 : w.length <= 5 ? 1 : 2);

/** Cost of matching one typed word against a street's words (prefix match is free; the last word may be half-typed). */
function wordCost(q, words, partial) {
  let best = 9;
  for (const w of words) {
    if (w.startsWith(q)) return 0;
    const max = allowed(q);
    if (!max) continue;
    const d = Math.min(dist(q, w, max), partial && w.length > q.length ? dist(q, w.slice(0, q.length), max) : 9);
    if (d <= max) best = Math.min(best, d);
  }
  return best;
}

/** Street suggestions for what's typed so far: accent-insensitive, partial words, small typos. */
export function suggest(q, area, limit = 8) {
  const S = search();
  const toks = norm(q).split(" ").filter(Boolean);
  const words = toks.filter((t) => !/^\d/.test(t) && !STREET_TYPES.has(t) && !STOP.has(t));
  const nums = toks.filter((t) => /^\d{1,4}[A-Z]?$/.test(t) && !POSTCODE.test(t));
  if (!words.length || words.join("").length < 3) return { streets: [], number: nums[0] || null };
  const out = [];
  for (const s of S.streets) {
    if (!inArea(s, area)) continue;
    let cost = 0;
    for (let i = 0; i < words.length && cost < 9; i++) cost += wordCost(words[i], s.words, i === words.length - 1);
    if (cost >= 9) continue;
    out.push({ s, cost, first: s.words[0].startsWith(words[0]) ? 0 : 1 });
  }
  out.sort((a, b) => a.s.messy - b.s.messy || a.cost - b.cost || a.first - b.first || b.s.vut - a.s.vut);
  // Barrios: only when every typed word matches (no number), listed before streets of equal quality.
  const bs = [];
  if (!nums.length) for (const b of S.barrios) {
    if (!inArea(b, area)) continue;
    let cost = 0;
    for (let i = 0; i < words.length && cost < 9; i++) cost += wordCost(words[i], b.words, i === words.length - 1);
    if (cost < 9 && cost <= (out[0]?.cost ?? 9)) bs.push({ b, cost });
  }
  bs.sort((a, b) => a.cost - b.cost || b.b.vut - a.b.vut);
  return { number: nums[0] || null,
    barrios: bs.slice(0, 3).map(({ b, cost }) => ({ type: "barrio", id: b.id, name: b.name, muni: b.muni, vut: b.vut, exact: cost === 0 })),
    streets: out.slice(0, limit).map(({ s, cost }) => ({ name: s.name, muni: s.muni, vut: s.vut, buildings: s.buildings, exact: cost === 0 })) };
}

/** Public shape of a register row (no internal fields). */
export const publicRow = (r) => Object.fromEntries(Object.entries(r).filter(([k]) => !k.startsWith("_")));

/** Look a registration number up. Returns {query, key, variant, rows (Málaga province), elsewhere:[{key, muni}]}. */
export function findCode(q) {
  const S = search(), L = lookup();
  const ck = catKey(q);   // a Catalan number: look it up directly (no Andalusian variants)
  if (ck) return { query: q, key: ck, variant: "exact", rows: (S.byKey.get(ck) || []).map(publicRow) };
  const bk = !/^\s*[A-Z]+\s*\/\s*[A-Z]{2}\s*\//i.test(q) && balKey(q);   // Mallorca (not a Junta code like H/MA/123)
  if (bk) return { query: q, key: bk, variant: "exact", rows: (S.byKey.get(bk) || []).map(publicRow) };
  // Aragón (VU-ZA-18-101); Andalusian codes like VUT/HU/01234 use slashes, so a slash means it isn't one
  const az = /(?<![A-Z0-9])VUT?[\s\-_./]*(HU|TE|ZA)[\s\-_./]*(\d{2})[\s\-_./]*0*(\d{1,5})(?![0-9])/i.exec(String(q || ""));
  if (az && !String(q).includes("/")) { const k = `${az[1].toUpperCase()}-${az[2]}-${+az[3]}`; return { query: q, key: k, variant: "exact", rows: (S.byKey.get(k) || []).map(publicRow) }; }
  const cl = /^\s*(?:VUT?[\s\-_.:]*)?(05|09|24|34|37|40|42|47|49)\s*\/\s*0*(\d{1,6})\s*$/i.exec(String(q || ""));   // Castilla y León: 47/000547
  if (cl) { const k = `${cl[1]}/${+cl[2]}`; return { query: q, key: k, variant: "exact", rows: (S.byKey.get(k) || []).map(publicRow) }; }
  const md = /^\s*(VT|HM|AM|TR|HH)[\s\-_.]*0*(\d{1,6})\s*$/i.exec(String(q || ""));   // Madrid's bare VT-12345
  if (md) { const k = `${md[1].toUpperCase()}-${+md[2]}`; return { query: q, key: k, variant: "exact", rows: (S.byKey.get(k) || []).map(publicRow) }; }
  const uk = murKey(q);
  if (uk) return { query: q, key: uk, variant: "exact", rows: (S.byKey.get(uk) || []).map(publicRow) };
  const gk = canKey(q);
  if (gk) { const L2 = lookup(); const k2 = S.byKey.has(gk) ? gk : (L2.can_short || {})[`VV-${gk.slice(-7)}`] || gk;
    return { query: q, key: k2, variant: "exact", rows: (S.byKey.get(k2) || []).map(publicRow) }; }
  const vk = !/^\s*VUT\s*\/\s*[A-Z]{2}\s*\//i.test(q) && vlcKey(q);   // (not a Junta VUT/MA/… code)
  if (vk) return { query: q, key: vk, variant: "exact", rows: (S.byKey.get(vk) || []).map(publicRow) };
  const ek = eusKey(q);
  if (ek) return { query: q, key: ek, variant: "exact", rows: (S.byKey.get(ek) || []).map(publicRow) };
  const p = parse(q, L.max_issued);
  let items = p.junta;
  const bare = String(q).trim().match(/^(\d{1,6})$/);
  if (!items.length && bare) items = ["VUT", "A", "H", "VTAR", "CR"].map((pre) => parse(`${pre}/MA/${bare[1]}`).junta[0]);
  for (const j of items) {
    for (const [key, variant] of variants(j)) {
      const rows = S.byKey.get(key);
      if (rows) return { query: j.raw, key, variant, rows: rows.map(publicRow) };
      const rec = L.codes[key];
      if (rec) return { query: j.raw, key, variant, rows: [], elsewhere: { key, muni: rec[0], lat: rec[1], lon: rec[2] } };
    }
  }
  return { query: items[0]?.raw || String(q).trim(), key: items[0]?.key || null, rows: [], malformed: !!items[0]?.malformed,
    looks_like_code: items.length > 0 };
}

/** Address search within an area. Groups matches by building. */
export function findAddress(q, area) {
  const S = search();
  const toks = norm(q).split(" ").filter(Boolean);
  const postcode = toks.find((t) => POSTCODE.test(t));
  const nums = toks.filter((t) => /^\d{1,4}[A-Z]?$/.test(t) && t !== postcode).map(cleanNum);
  const words = toks.filter((t) => !/^\d/.test(t) && !STREET_TYPES.has(t) && !STOP.has(t) && t.length > 1);
  if (!words.length && !postcode) return [];
  const groups = new Map();
  for (const r of S.rows) {
    if (!inArea(r, area)) continue;
    if (postcode && r.postcode !== postcode) continue;
    if (!words.every((w) => r._hay.includes(` ${w}`))) continue;
    const streetNum = nums.length > 0 && nums.some((n) => cleanNum(r.num) === n);
    const numHit = streetNum || (nums.length > 0 && nums.some((n) => cleanNum(r.portal) === n));
    let g = groups.get(r.building);
    if (!g) groups.set(r.building, (g = { building: r.building, rows: [], hits: 0, streetHits: 0, inStreet: 0 }));
    g.rows.push(r);
    if (numHit) g.hits++;
    if (streetNum) g.streetHits++;
    if (words.every((w) => ` ${r._street} `.includes(` ${w}`))) g.inStreet++;
  }
  const out = [...groups.values()].map((g) => {
    const all = S.byBuilding.get(g.building) || g.rows;
    const vut = all.filter((r) => r.kind === "VUT");
    const at = g.rows.find((r) => r.lat != null) || all.find((r) => r.lat != null) || g.rows[0];
    return {
      building: g.building, number_match: g.hits > 0, score: (g.streetHits ? 2000 : g.hits ? 1000 : 0) + (g.inStreet ? 100 : 0) + Math.min(vut.length, 99),
      addresses: addressList(all), muni: at.muni, postcode: at.postcode, lat: at.lat, lon: at.lon,
      vut: vut.length, other: all.length - vut.length, places: vut.reduce((s, r) => s + (r.places || 0), 0),
      // the flats that matched (at that number, if a number was given), to show without a second request
      flats: (g.hits ? g.rows.filter((r) => nums.some((n) => cleanNum(r.num) === n || cleanNum(r.portal) === n)) : g.rows)
        .slice(0, 60).map(publicRow),
      matched: g.hits || g.rows.length,
    };
  });
  // If a number was given and some building has it, drop buildings that only matched the street.
  const anyHit = out.some((g) => g.number_match);
  return out.filter((g) => !anyHit || g.number_match).sort((a, b) => b.score - a.score).slice(0, 15);
}

/** "Street 19-21, 24, 27" strings for a set of rows: one per street (accent/"De"-insensitive), most common first. */
export function addressList(rows) {
  const streets = new Map();
  for (const r of rows) {
    if (!r.street) continue;
    const k = r._street || norm(r.street);
    let s = streets.get(k);
    if (!s) streets.set(k, (s = { n: 0, forms: new Map(), nums: new Set() }));
    s.n++;
    s.forms.set(r.street, (s.forms.get(r.street) || 0) + 1);
    const num = cleanNum(r.num).replace(/\.$/, "");
    if (num && !/^S\s*\/?\s*N$|^0+$|^-$/.test(num)) s.nums.add(num);
  }
  const nk = (x) => [parseInt(x, 10) || 1e6, x];
  return [...streets.values()].sort((a, b) => b.n - a.n).map((s) => {
    const name = [...s.forms.entries()].sort((a, b) => b[1] - a[1])[0][0];
    const nums = [...s.nums].sort((a, b) => nk(a)[0] - nk(b)[0] || a.localeCompare(b));
    return `${name} ${nums.slice(0, 6).join(", ")}${nums.length > 6 ? " …" : ""}`.trim();
  });
}

export function building(id) {
  const rows = search().byBuilding.get(id);
  if (!rows) return null;
  const vut = rows.filter((r) => r.kind === "VUT");
  const at = rows.find((r) => r.lat != null) || rows[0];
  return { building: id, addresses: addressList(rows), muni: at.muni, postcode: at.postcode, lat: at.lat, lon: at.lon,
    vut: vut.length, other: rows.length - vut.length, places: vut.reduce((s, r) => s + (r.places || 0), 0),
    flats: rows.map(publicRow) };
}

export { codeKey };
