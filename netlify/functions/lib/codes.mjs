// JS port of pipeline/rta_audit/codes.py — keep the two in step (tests in netlify/functions/test.mjs).
export const ANDALUSIAN_PROVINCES = new Set(["AL", "CA", "CO", "GR", "HU", "JA", "MA", "SE"]);
const PREFIXES = { VUT: "VUT", VFT: "VUT", VTF: "VUT", VTAR: "VTAR", A: "A", H: "H", CR: "CR", CTR: "CTR", CM: "CM" };
const PREFIX_RE = Object.keys(PREFIXES).sort((a, b) => b.length - a.length).join("|");
const SEP = "[\\s/\\-_.\\\\]*";
const JUNTA_RE = new RegExp(
  `(?<![A-Z0-9])(${PREFIX_RE})${SEP}(?:([A-Z]{2})${SEP})?(\\d{1,8})([A-Z])?(?![0-9])`, "gi");
const NATIONAL_RE = /(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*/gi;
const CTC_RE = /(?<![A-Z0-9])CTC[\s\-_/]*(\d{6,12})(?![0-9])/gi;
const EXEMPT_RE = /\b(exempt|exento|exenta)\b[^|\n]*/i;
const LABEL_RE = /(Andaluc[ií]a|Spain|Espa[ñn]a)\s*[–-]\s*(Regional|National|Nacional|Auton[oó]mic\w*)\s+registration\s+number/gi;

export function cleanText(raw) {
  if (!raw) return "";
  let s = raw.replace(/<br\s*\/?>/gi, " | ").replace(/<[^>]+>/g, " ");
  s = s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/ /g, " ");
  return s.replace(/[ \t]+/g, " ").trim();
}

export const normaliseKey = (prefix, prov, num) =>
  `${PREFIXES[prefix.toUpperCase()] || prefix.toUpperCase()}/${(prov || "??").toUpperCase()}/${parseInt(num, 10)}`;

export function parse(rawText, maxIssued = {}) {
  const text = cleanText(rawText);
  const out = { clean: text, junta: [], national: [], other: [], exempt_text: null };
  let work = text;
  for (const m of text.matchAll(NATIONAL_RE)) {
    const t = m[0].toUpperCase();
    const e = t.match(/(VUT|VFT|VTAR|CR|A|H)\/[A-Z]{2}\/\d+$/);
    out.national.push({ raw: m[0], type: t.slice(2, 6), embedded_regional: e ? e[0] : null });
    work = work.replace(m[0], " ");
  }
  for (const m of work.matchAll(CTC_RE)) {
    out.other.push({ raw: m[0], kind: "CTC_procedure_ref", value: m[1] });
    work = work.replace(m[0], " ");
  }
  work = work.replace(LABEL_RE, " ");
  const seen = new Set();
  for (const m of work.matchAll(JUNTA_RE)) {
    const [raw, prefix, prov, num, suffix] = m;
    const canon = PREFIXES[prefix.toUpperCase()];
    if (prefix.length === 1 && !prov) continue;
    const problems = [];
    const P = prov ? prov.toUpperCase() : null;
    if (P && !ANDALUSIAN_PROVINCES.has(P)) {
      if (canon !== "VUT") { out.other.push({ raw, kind: "non_andalusian_province", value: P }); continue; }
      problems.push(`invalid_province_${P}`);
    }
    if (prefix.toUpperCase() === "VTF") problems.push("prefix_typo_VTF");
    if (!P) problems.push("missing_province");
    if (suffix) problems.push("letter_suffix");
    if (num.length > 6) problems.push("too_many_digits");
    if (num.length < 5) problems.push("short_unpadded");
    if (P && maxIssued[`${canon}/${P}`] && parseInt(num, 10) > maxIssued[`${canon}/${P}`]) problems.push("exceeds_highest_issued");
    const hard = ["missing_province", `invalid_province_${P}`, "letter_suffix", "too_many_digits", "exceeds_highest_issued"];
    const key = (P || canon === "VUT") ? normaliseKey(prefix, P && ANDALUSIAN_PROVINCES.has(P) ? P : "MA", num) : null;
    const k = key || raw;
    if (seen.has(k)) continue;
    seen.add(k);
    out.junta.push({ raw: raw.trim(), prefix: prefix.toUpperCase(), canonical_prefix: canon, prov: P, num, suffix: suffix || null,
      key, problems, malformed: problems.some((p) => hard.includes(p)) });
  }
  const e = text.match(EXEMPT_RE);
  if (e) out.exempt_text = e[0].trim();
  return out;
}

export function variants(item) {
  const c = [];
  const { num, prov, canonical_prefix: canon, prefix } = item;
  const valid = prov && ANDALUSIAN_PROVINCES.has(prov);
  const p = valid ? prov : "MA";
  let base = valid ? "exact" : (prov ? "province_replaced_MA" : "province_inferred_MA");
  if (prefix === "VFT") base = base === "exact" ? "prefix_swap_VFT_to_VUT" : base + "+prefix_swap_VFT_to_VUT";
  if (prefix === "VTF") base = base === "exact" ? "prefix_typo_VTF_to_VUT" : base + "+prefix_typo_VTF_to_VUT";
  if (num.length < 5) base += "+zero_pad";
  c.push([normaliseKey(canon, p, num), base]);
  if (num.length >= 6) c.push([normaliseKey(canon, p, num.slice(0, -1)), base + "+check_digit_stripped"]);
  if (canon === "VUT") c.push([normaliseKey("VTAR", p, num), base + "+prefix_swap_VUT_to_VTAR"]);
  return c;
}

export function haversine(lat1, lon1, lat2, lon2) {
  const r = 6371008.8, rad = Math.PI / 180;
  const dp = (lat2 - lat1) * rad, dl = (lon2 - lon1) * rad;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}
