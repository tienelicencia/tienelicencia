// Canonical address for every page: its own path on https://tienelicencia.com, with no query string,
// trailing slash or ".html", the same form as site/sitemap.xml. Added here, not in the HTML files,
// because one file serves many addresses (site/_redirects: /malaga, /sevilla … all serve area.html).
// It keeps search engines on the clean URL when shared links carry ?sh=… share codes (Shifted Labs
// traffic counter) or any other query string, and folds /malaga/ and /ranking.html into /malaga and /ranking.
// Sent twice: a <link rel="canonical"> in <head> and a Link header (Google reads both).

const ORIGIN = 'https://tienelicencia.com';
// Template files with no address of their own (/area.html, /zonas.html opened directly): no canonical
const NO_CANONICAL = new Set(['/area', '/zonas']);

export function canonicalPath(pathname) {
  let path = pathname.replace(/\/index\.html$/, '/').replace(/\.html$/, '');
  if (path.length > 1) path = path.replace(/\/+$/, '');
  return path || '/';
}

export default async (request, context) => {
  const res = await context.next();
  if (request.method !== 'GET' || res.status !== 200 || !(res.headers.get('content-type') ?? '').includes('text/html')) return res;
  const path = canonicalPath(new URL(request.url).pathname);
  if (NO_CANONICAL.has(path)) return res;
  const html = await res.text();
  const headers = new Headers(res.headers);
  headers.delete('content-length');
  if (/<link[^>]+rel=["']?canonical/i.test(html)) return new Response(html, { status: res.status, headers });
  const href = ORIGIN + path; // pathname is already percent-encoded
  headers.set('Link', `<${href}>; rel="canonical"`);
  const tag = `<link rel="canonical" href="${href.replace(/"/g, '%22')}">`;
  const out = html.includes('</head>') ? html.replace('</head>', `${tag}\n</head>`) : html;
  return new Response(out, { status: res.status, headers });
};

export const config = {
  path: '/*',
  excludedPath: ['/data/*', '/assets/*', '/__sl/*', '/*.json', '/*.js', '/*.css', '/*.png', '/*.ico', '/*.svg', '/*.xml', '/*.txt', '/*.webmanifest'],
};
