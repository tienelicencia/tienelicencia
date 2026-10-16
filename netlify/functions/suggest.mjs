// GET /api/suggest?q=<what's typed so far>&area=malaga|marbella|provincia
// Street autocomplete from the Junta register: accent-insensitive, partial words, small typos.
import { suggest } from "./lib/register-data.mjs";
import { json, rateLimited, clientIp } from "./lib/http.mjs";
import { looksLikeCode } from "./search.mjs";

export const config = { path: "/api/suggest" };

export default async (req, context) => {
  const url = new URL(req.url);
  const q = (url.searchParams.get("q") || "").slice(0, 80);
  if (looksLikeCode(q)) return json(200, { q, streets: [] }, 300);
  if (rateLimited(clientIp(req, context), 600)) return json(429, { error: "rate_limited" });
  return json(200, { q, ...suggest(q, url.searchParams.get("area") || "provincia") }, 300);
};
