// Server-side rendering for crawlers and AI engines (Shifted Labs, SEO/GEO).
//
// Why this exists: the data pages ship as static shells and fill themselves in the browser from
// /data/*.json. Crawlers that don't run JavaScript (GPTBot, ClaudeBot, Bingbot, Applebot, Amazonbot,
// Meta, and Googlebot on its first pass) therefore see an empty page with none of the numbers that are
// the whole point of the site. This edge function reads the same committed JSON at the edge and injects
//   1. a server-rendered version of the page's key content into the containers the client later hydrates
//      (the browser overwrites these on load, so humans are unaffected and see no duplication), and
//   2. JSON-LD (schema.org) so Google can show rich results and AI engines can cite the data confidently.
//
// It never touches site-hits.js (the traffic counter) or canonical.js; it only reads the HTML response
// and the public data files. If anything is missing or errors, it returns the original response unchanged
// (fail-open). Mirrors canonical.js: context.next(), rewrite HTML, re-emit.

const ORIGIN = 'https://tienelicencia.com';

// Clean path, same rules as canonical.js (strip index.html / .html / trailing slash).
function cleanPath(pathname) {
  let path = pathname.replace(/\/index\.html$/, '/').replace(/\.html$/, '');
  if (path.length > 1) path = path.replace(/\/+$/, '');
  return path || '/';
}

// ---- tiny formatting helpers (Spanish is the site's primary language; crawlers get the es fallback) ----
const esNum = (x, d = 0) =>
  x == null ? '—' : Number(x).toLocaleString('es-ES', { maximumFractionDigits: d });
const esPc = (x, d = 1) => (x == null ? '—' : `${esNum(x, d)} %`);
const esc = (s) =>
  String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const titleCase = (s) =>
  !s ? '' : /[a-z]/.test(s) ? s : s.toLowerCase().replace(/(^|[\s'-])\p{L}/gu, (m) => m.toUpperCase());

// Replace an empty element <tag ... id="ID"></tag> with the same open tag + inner HTML.
// Targeted and reversible: if the element isn't found or isn't empty, the HTML is left as-is.
function fillEmpty(html, id, inner) {
  const re = new RegExp(`(<[a-zA-Z0-9]+[^>]*\\bid=["']${id}["'][^>]*>)\\s*(</[a-zA-Z0-9]+>)`);
  return html.replace(re, (m, open, close) => `${open}${inner}${close}`);
}

// Insert markup just before </head> (JSON-LD) or </main> (fallbacks the client won't hydrate).
const beforeHead = (html, markup) => (html.includes('</head>') ? html.replace('</head>', `${markup}\n</head>`) : html);

// ===================== /ranking =====================
function rankingContent(d) {
  const ranked = d.cities.filter((c) => c.index != null);
  const pending = d.cities.filter((c) => c.index == null);
  const n = d.cities.length;
  const leader = ranked[0];
  const minPop = esNum(d.cohort?.min_population || 300000);

  const sub = `Ranking de las ciudades españolas de más de ${minPop} habitantes`;
  const meta = [`${n} ciudades`, 'Actualización mensual', 'Consulta gratuita']
    .map((s) => `<span>${esc(s)}</span>`).join('');
  // Quotable intro sentence — this is the line an AI answer or a Google snippet is likely to lift.
  const lede =
    `Consulta gratis qué ciudades españolas soportan más presión de la vivienda turística. ` +
    (leader
      ? `${esc(leader.name)} encabeza el índice con ${esNum(leader.index, 1)} puntos de 100. `
      : '') +
    `Comparamos el peso del alojamiento turístico sobre la vivienda residencial, su concentración y las ` +
    `discrepancias en los registros anunciados en todos los municipios de más de ${minPop} habitantes, ` +
    `con datos oficiales actualizados cada mes. Gratis y sin registro.`;

  const headline = (c) => {
    const v = c.verification || {};
    const parts = [];
    if (c.housing != null) parts.push(`${esPc(c.housing, 2)} de las viviendas anunciadas para turistas`);
    if (c.concentration != null)
      parts.push(
        `${esNum(c.concentration, 1)} anuncios por cada 100 viviendas en su km más afectado` +
          (c.peak_place ? ` (${esc(titleCase(c.peak_place))})` : ''),
      );
    if (v.no_verifiable_pct != null)
      parts.push(`${esPc(v.no_verifiable_pct, 0)} de los anuncios sin número verificable públicamente`);
    if (c.registered != null) parts.push(`${esNum(c.registered)} viviendas turísticas registradas`);
    return parts.map((p) => `<li>${p}</li>`).join('');
  };

  const row = (c) => `<li class="ix-row">
      <div class="ix-pos">${esc(c.rank)}</div>
      <div class="ix-main">
        <h2 class="ix-name"><a href="/${esc(c.slug || c.area)}">${esc(c.name)}</a></h2>
        <ul class="ssr-figs">${headline(c)}</ul>
      </div>
      <div class="ix-score"><b>${esNum(c.index, 1)}</b><span>puntos de 100</span></div></li>`;

  const pendingRow = (c) => `<li class="ix-row ix-pending">
      <div class="ix-pos">–</div>
      <div class="ix-main"><h2 class="ix-name"><a href="/${esc(c.slug || c.area)}">${esc(c.name)}</a> — índice pendiente</h2>
        <ul class="ssr-figs">${headline(c)}</ul></div>
      <div class="ix-score"><b>—</b><span>pendiente</span></div></li>`;

  const list = ranked.map(row).join('') + pending.map(pendingRow).join('');
  return { sub, meta, lede, list, ranked, pending, n, leader };
}

function rankingJsonLd(d, c) {
  const url = `${ORIGIN}/ranking`;
  const itemList = {
    '@type': 'ItemList',
    name: 'Índice de presión de la vivienda turística — ranking de ciudades',
    numberOfItems: c.ranked.length,
    itemListOrder: 'https://schema.org/ItemListOrderDescending',
    itemListElement: c.ranked.map((city) => ({
      '@type': 'ListItem',
      position: city.rank,
      url: `${ORIGIN}/${city.slug || city.area}`,
      name: city.name,
      description: `Índice ${esNum(city.index, 1)}/100 · ${esNum(city.registered)} viviendas turísticas registradas`,
    })),
  };
  const dataset = {
    '@type': 'Dataset',
    name: d.name?.es || 'Índice de presión de la vivienda turística',
    alternateName: d.name?.en,
    description:
      'Ranking gratuito de las ciudades españolas de más de 300.000 habitantes por presión de la vivienda ' +
      'turística: viviendas anunciadas, concentración y discrepancias con los registros oficiales. Datos ' +
      'oficiales actualizados cada mes. Free, no sign-up required.',
    url,
    inLanguage: ['es', 'en'],
    isAccessibleForFree: true,
    license: `${ORIGIN}/metodologia`,
    creator: { '@type': 'Organization', name: 'tienelicencia.com', url: ORIGIN },
    dateModified: d.built_at,
    temporalCoverage: d.baseline?.period,
    keywords: [
      'vivienda turística', 'viviendas turísticas', 'licencia turística', 'Airbnb', 'registro turístico',
      'España', 'ranking', 'gratis',
    ],
    variableMeasured: ['viviendas anunciadas', 'concentración', 'discrepancias de registro', 'índice de presión'],
    distribution: {
      '@type': 'DataDownload',
      encodingFormat: 'application/json',
      contentUrl: `${ORIGIN}/data/ranking.json`,
    },
  };
  const breadcrumb = {
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Inicio', item: ORIGIN + '/' },
      { '@type': 'ListItem', position: 2, name: 'Índice', item: url },
    ],
  };
  return JSON.stringify({ '@context': 'https://schema.org', '@graph': [dataset, itemList, breadcrumb] });
}

// Build the transform for a given clean path. Returns a function (html) => html, or null if unhandled.
// Exported pure so it can be unit-tested in Node against the real HTML + JSON (see scripts/ tests).
export function rankingTransform(data) {
  const c = rankingContent(data);
  return (html) => {
    if (html.includes('id="ssr-ld-ranking"')) return html; // idempotent
    let out = html;
    out = fillEmpty(out, 'ix-sub', c.sub);
    out = fillEmpty(out, 'ix-meta', c.meta);
    out = fillEmpty(out, 'ix-lede', c.lede);
    out = fillEmpty(out, 'ix', c.list);
    out = beforeHead(
      out,
      `<script type="application/ld+json" id="ssr-ld-ranking">${rankingJsonLd(data, c)}</script>`,
    );
    return out;
  };
}

// ---- data fetch, cached per edge isolate (matches /data/* Cache-Control: max-age=300) ----
const cache = new Map(); // path -> { at, json }
const TTL_MS = 5 * 60 * 1000;
async function loadData(requestUrl, dataPath) {
  const hit = cache.get(dataPath);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.json;
  try {
    const res = await fetch(new URL(dataPath, requestUrl));
    if (!res.ok) return null;
    const json = await res.json();
    cache.set(dataPath, { at: Date.now(), json });
    return json;
  } catch {
    return null;
  }
}

// Map a clean path to { dataPath, build } ; add city/map handlers here next.
function handlerFor(path) {
  if (path === '/ranking') return { dataPath: '/data/ranking.json', build: rankingTransform };
  return null;
}

export default async (request, context) => {
  const res = await context.next();
  if (request.method !== 'GET' || res.status !== 200) return res;
  if (!(res.headers.get('content-type') ?? '').includes('text/html')) return res;

  const path = cleanPath(new URL(request.url).pathname);
  const h = handlerFor(path);
  if (!h) return res;

  const data = await loadData(request.url, h.dataPath);
  if (!data) return res; // fail-open: no data, serve the page untouched

  const html = await res.text();
  let out;
  try {
    out = h.build(data)(html);
  } catch {
    return new Response(html, { status: res.status, headers: res.headers });
  }
  const headers = new Headers(res.headers);
  headers.delete('content-length');
  return new Response(out, { status: res.status, headers });
};

export const config = {
  path: '/*',
  excludedPath: [
    '/data/*', '/assets/*', '/__sl/*', '/*.json', '/*.js', '/*.css', '/*.png', '/*.ico', '/*.svg',
    '/*.xml', '/*.txt', '/*.webmanifest',
  ],
};
