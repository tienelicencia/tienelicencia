// Local preview: serves site/, the functions in netlify/functions (by their config.path) and the page
// rewrites from site/_redirects, like Netlify does.
//   node dev.mjs            → http://127.0.0.1:8791
import { createServer } from "node:http";
import { readFile, readdir } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = join(process.cwd(), "site");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".geojson": "application/geo+json", ".svg": "image/svg+xml", ".png": "image/png",
  ".ico": "image/x-icon", ".webmanifest": "application/manifest+json", ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml", ".csv": "text/csv; charset=utf-8" };
const PORT = +process.env.PORT || 8791;

const FUNCS = {};
for (const f of await readdir("netlify/functions")) {
  if (!f.endsWith(".mjs") || f === "test.mjs") continue;
  const m = await import(pathToFileURL(join(process.cwd(), "netlify/functions", f)).href);
  if (m.config?.path) FUNCS[m.config.path] = m.default;
}
// site/_redirects: "/x  /y.html  200" → rewrite table
const REWRITES = {};
for (const line of (await readFile("site/_redirects", "utf8")).split("\n")) {
  const [from, to, status] = line.trim().split(/\s+/);
  if (from && !from.startsWith("#") && to && status === "200") REWRITES[from.replace(/\/$/, "")] = to;
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const fn = FUNCS[url.pathname];
  if (fn) {
    const r = await fn(new Request(url), { ip: req.socket.remoteAddress });
    res.writeHead(r.status, Object.fromEntries(r.headers));
    return res.end(await r.text());
  }
  const path = REWRITES[url.pathname.replace(/\/$/, "")] || (url.pathname === "/" ? "/index.html" : url.pathname);
  const p = normalize(join(ROOT, path));
  if (!p.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  try {
    const body = await readFile(p);
    res.writeHead(200, { "content-type": TYPES[extname(p)] || "application/octet-stream", "cache-control": "no-cache" });
    res.end(body);
  } catch {
    res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
    res.end(await readFile(join(ROOT, "404.html")).catch(() => "Not found"));
  }
}).listen(PORT, "127.0.0.1", () => console.log(`http://127.0.0.1:${PORT}`));
