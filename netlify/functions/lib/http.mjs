// Small helpers shared by the functions.
export function json(status, body, maxAge = 0) {
  return new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json; charset=utf-8",
      "cache-control": maxAge ? `public, max-age=${maxAge}` : "no-store" } });
}

const HITS = new Map(); // ip -> [timestamps]
export function rateLimited(ip, max, windowMs = 10 * 60 * 1000) {
  const now = Date.now();
  const arr = (HITS.get(ip) || []).filter((t) => now - t < windowMs);
  arr.push(now);
  HITS.set(ip, arr);
  return arr.length > max;
}

export const clientIp = (req, context) => context?.ip || req.headers.get("x-nf-client-connection-ip") || "anon";
