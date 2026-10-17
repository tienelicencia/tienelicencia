// GET /api/search?q=<licence number or address>&area=malaga|marbella|provincia
// Answers from the Junta register (Málaga province). A licence number is looked up exactly (allowing the usual
// formatting differences); anything else is treated as an address and grouped by building.
import { findCode, findAddress, search, suggest } from "./lib/register-data.mjs";
import { json, rateLimited, clientIp } from "./lib/http.mjs";

export const config = { path: "/api/search" };

export function looksLikeCode(q) {
  return /^\s*(HUTB|ATB|VUT|VFT|VTF|VTAR|CTR|CR|A|H)\s*[-/_.\s]*[A-Z]{0,2}\s*[-/_.\s]*\d/i.test(q) || /^\s*\d{1,6}\s*$/.test(q)
    || /^\s*(ETV60|ETVPL|ETV|VT|ABT|AG|AT|TI|HA|HR|HO|HS)\s*[-/_.\s]*\d/i.test(q)   // Mallorca
    || /^\s*[ELHPTBKXC]\s*[-/_.\s]*(BI|SS|VI)\s*[-/_.\s]*\d/i.test(q)   // Euskadi
    || /^\s*(CV\s*[-_\s]*)?VUT?\s*[-_\s]*\d/i.test(q)   // Comunitat Valenciana
    || /^\s*VV\s*[-_\s]*\d/i.test(q)   // Canarias
    || /^\s*(VV|AR|ALB|CT|A|H)[\s.\-_]*MU[\s.\-_]*\d/i.test(q);   // Región de Murcia
}

export default async (req, context) => {
  const url = new URL(req.url);
  const q = (url.searchParams.get("q") || "").slice(0, 120).trim();
  const area = url.searchParams.get("area") || "provincia";
  if (q.length < 2) return json(400, { error: "short_query" });
  if (rateLimited(clientIp(req, context), 120)) return json(429, { error: "rate_limited" });
  const S = search();
  const base = { q, area, register_date: S.register_date };
  if (looksLikeCode(q)) {
    const r = findCode(q);
    if (r.rows.length || r.elsewhere || !/^\s*\d+\s*$/.test(q)) return json(200, { ...base, kind: "code", ...r }, 300);
  }
  let buildings = findAddress(q, area);
  // Nothing found: probably a typo. Retry with the closest street name (keeping any number typed) and say so.
  if (!buildings.length) {
    const s = suggest(q, area, 1);
    if (s.streets.length) {
      const fix = `${s.streets[0].name}${s.number ? " " + s.number : ""}${area === "provincia" ? " " + s.streets[0].muni : ""}`;
      buildings = findAddress(fix, area);
      if (buildings.length) return json(200, { ...base, kind: "address", corrected: fix, buildings }, 300);
    }
  }
  return json(200, { ...base, kind: "address", buildings }, 300);
};
