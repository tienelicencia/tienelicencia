/**
 * site-hits v2: Shifted Labs' shared traffic & signals counter.
 *
 * ONE IDENTICAL COPY lives in every site repo (netlify/edge-functions/site-hits.js).
 * Master copy + installer: ~/.config/shiftedlabs/site-hits/ on Babac's Mac. Edit
 * there and re-run install.sh rather than editing a single site's copy.
 *
 * Why: Google Analytics only counts people who accept cookies and don't block
 * trackers, and never sees bots, AI assistants or link shares. This runs on
 * Netlify's edge for every page request, before any banner, and records who
 * asked for the page. The database (signals.sql) turns that into signals:
 *   Recommended  something sent a person here (AI chat, search, a link, a share)
 *   Considered   an AI assistant read the page for someone; a link was shared
 *   Discovered   AI / search crawlers indexing pages (+ robots.txt, llms.txt, sitemaps)
 *   Noise        impostors, scrapers, monitors, SEO tools, scripts
 *
 * Labels (kind): human | suspect | ai_assistant | ai_crawler | search_crawler |
 *   seo_tool | link_preview | monitor | script | other_bot
 * Bots are VERIFIED where their operator publishes how: official IP lists
 * (Google, Bing, OpenAI, Perplexity, Apple) or reverse+forward DNS (Google,
 * Bing, Apple, Yandex, Baidu, Meta, Ahrefs, Semrush, Petal, Amazon).
 * verified = 'verified' | 'impostor' | 'unverifiable'. The IP is used for this
 * check and then dropped.
 *
 * Stored: site, path, status, label, agent/platform, verification, entry flag,
 * referring site, utm_source/medium/campaign, country/region/city (Netlify
 * geo), device, OS, first language, and for people a daily visitor code.
 * NOT stored: IP, full user agent, cookies, query strings.
 *
 * Unique visitors: for page views by people, the IP and user agent are sent
 * (over HTTPS) to log_site_hit, which turns them into a 16-character code with a
 * random salt that changes every day and never leaves the database, and stores
 * only the code. Finished days are rolled up and their codes and salts deleted.
 * No cookie, nothing on the device, so no consent banner is needed.
 *
 * Key: the project's PUBLISHABLE key, from the Netlify env var SITE_HITS_KEY if
 * set, else the copy embedded below by install.sh. install.sh embeds it ONLY in
 * private repos: a public repo (tienelicencia) gets no key in code and must set
 * SITE_HITS_KEY in its Netlify site. The analytics schema is insert-only for this
 * key, but the key is the whole project's public key, so never publish it in a
 * public repo (that happened once, 20 Oct 2026, and the key was revoked).
 * No key → nothing is logged; the site is unaffected.
 *
 * Exclude your own browser on a site: open any page with ?count=off (undo: ?count=on).
 */

const ENDPOINT = 'https://dpbqttplugxcuuuzxgfk.supabase.co/rest/v1/rpc/log_site_hit';
const EMBEDDED_KEY = '';
const OPT_OUT = 'sl_count_off';

const siteHitsKey = () => {
  const fromEnv = globalThis.Netlify?.env?.get('SITE_HITS_KEY') ?? '';
  if (fromEnv.startsWith('sb_publishable_')) return fromEnv;
  return EMBEDDED_KEY.startsWith('sb_publishable_') ? EMBEDDED_KEY : '';
};

// ---------------------------------------------------------------------------
// Who is asking. First match wins; [kind, pattern, display name].
// Link previews are named by platform. iMessage and WhatsApp build previews on
// the sharer's own phone, so their location is the sharer's.
// ---------------------------------------------------------------------------
const AGENTS = [
  ['link_preview', /facebookexternalhit.*Twitterbot|Twitterbot.*facebookexternalhit/i, 'iMessage'],
  ['ai_assistant', /ChatGPT-User/i, 'ChatGPT-User'],
  ['ai_assistant', /Perplexity-User/i, 'Perplexity-User'],
  ['ai_assistant', /Claude-User/i, 'Claude-User'],
  ['ai_assistant', /MistralAI-User/i, 'MistralAI-User'],
  ['ai_assistant', /DuckAssistBot/i, 'DuckAssistBot'],
  ['ai_assistant', /Meta-ExternalFetcher/i, 'Meta-ExternalFetcher'],
  ['ai_assistant', /Google-NotebookLM/i, 'Google-NotebookLM'],
  ['ai_assistant', /Gemini-Deep-Research/i, 'Gemini-Deep-Research'],
  ['ai_crawler', /OAI-SearchBot/i, 'OAI-SearchBot'],
  ['ai_crawler', /GPTBot/i, 'GPTBot'],
  ['ai_crawler', /Claude-SearchBot/i, 'Claude-SearchBot'],
  ['ai_crawler', /ClaudeBot|anthropic-ai/i, 'ClaudeBot'],
  ['ai_crawler', /PerplexityBot/i, 'PerplexityBot'],
  ['ai_crawler', /Applebot-Extended/i, 'Applebot-Extended'],
  ['ai_crawler', /meta-externalagent/i, 'meta-externalagent'],
  ['ai_crawler', /Amazonbot/i, 'Amazonbot'],
  ['ai_crawler', /CCBot/i, 'CCBot'],
  ['ai_crawler', /Bytespider/i, 'Bytespider'],
  ['ai_crawler', /cohere-ai|cohere-training/i, 'cohere-ai'],
  ['ai_crawler', /Diffbot/i, 'Diffbot'],
  ['ai_crawler', /YouBot/i, 'YouBot'],
  ['ai_crawler', /Timpibot|ImagesiftBot|AI2Bot|Kangaroo Bot|PanguBot|Brightbot/i, null],
  ['search_crawler', /Google-InspectionTool/i, 'Google-InspectionTool'],
  ['search_crawler', /Storebot-Google/i, 'Storebot-Google'],
  ['search_crawler', /AdsBot-Google/i, 'AdsBot-Google'],
  ['search_crawler', /GoogleOther/i, 'GoogleOther'],
  ['search_crawler', /Googlebot/i, 'Googlebot'],
  ['search_crawler', /bingbot|BingPreview|msnbot/i, 'Bingbot'],
  ['search_crawler', /Applebot/i, 'Applebot'],
  ['search_crawler', /YandexBot|YandexMobileBot/i, 'YandexBot'],
  ['search_crawler', /DuckDuckBot/i, 'DuckDuckBot'],
  ['search_crawler', /Baiduspider/i, 'Baiduspider'],
  ['search_crawler', /PetalBot/i, 'PetalBot'],
  ['search_crawler', /Qwantbot|SeznamBot|Sogou|Yeti|MojeekBot|Bravebot|coccocbot/i, null],
  ['seo_tool', /AhrefsBot|AhrefsSiteAudit/i, 'AhrefsBot'],
  ['seo_tool', /SemrushBot|SiteAuditBot/i, 'SemrushBot'],
  ['seo_tool', /MJ12bot|DotBot|DataForSeoBot|BLEXBot|Screaming Frog|serpstatbot|SEOkicks|Barkrowler|rogerbot|Sitebulb|SeobilityBot|SERankingBacklinksBot|Seekport/i, null],
  ['link_preview', /WhatsApp/i, 'WhatsApp'],
  ['link_preview', /SkypeUriPreview/i, 'Teams/Skype'],
  ['link_preview', /Microsoft Office|Outlook|MicrosoftPreview/i, 'Outlook/Office'],
  ['link_preview', /Slackbot|Slack-ImgProxy/i, 'Slack'],
  ['link_preview', /TelegramBot/i, 'Telegram'],
  ['link_preview', /Discordbot/i, 'Discord'],
  ['link_preview', /LinkedInBot/i, 'LinkedIn'],
  ['link_preview', /Twitterbot/i, 'X'],
  ['link_preview', /facebookexternalhit|facebookcatalog|Facebot/i, 'Facebook/Instagram'],
  ['link_preview', /Pinterestbot/i, 'Pinterest'],
  ['link_preview', /redditbot/i, 'Reddit'],
  ['link_preview', /Viber/i, 'Viber'],
  ['link_preview', /Snapchat/i, 'Snapchat'],
  ['link_preview', /Google-PageRenderer/i, 'Google (Chat/Docs)'],
  ['link_preview', /Mastodon/i, 'Mastodon'],
  ['link_preview', /Bluesky|Cardyb/i, 'Bluesky'],
  ['link_preview', /vkShare/i, 'VK'],
  ['link_preview', /Iframely|Embedly|Notion/i, 'Embed (Notion, Medium…)'],
  ['monitor', /UptimeRobot|Pingdom|StatusCake|Better ?Uptime|BetterStack|Site24x7|Netlify|checkly|Datadog|NewRelic|GTmetrix|Chrome-Lighthouse|Google Page Speed|PageSpeed|Uptime-Kuma|Freshping|HetrixTools/i, null],
  ['script', /HeadlessChrome|PhantomJS|Puppeteer|Playwright|curl\/|Wget|python-requests|python-httpx|python-urllib|aiohttp|Go-http-client|node-fetch|undici|axios|okhttp|Java\/|libwww|Scrapy|httpclient|PostmanRuntime|Deno\/|Bun\//i, null],
  ['other_bot', /bot\b|bot\/|crawl|spider|slurp|scrape|fetcher|archiver/i, null],
];

// ---------------------------------------------------------------------------
// Verification. Lists are cached per edge isolate for 12 h.
// ---------------------------------------------------------------------------
const G = 'https://developers.google.com/static/search/apis/ipranges/';
const GOOGLE = { lists: [`${G}googlebot.json`, `${G}special-crawlers.json`, `${G}user-triggered-fetchers.json`, `${G}user-triggered-fetchers-google.json`], dns: ['googlebot.com', 'google.com', 'googleusercontent.com'] };
const META = { dns: ['fbsv.net', 'tfbnw.net', 'facebook.com'], dnsStrict: false };
const VERIFY = {
  Googlebot: GOOGLE, 'Google-InspectionTool': GOOGLE, GoogleOther: GOOGLE, 'Storebot-Google': GOOGLE, 'AdsBot-Google': GOOGLE,
  'Google (Chat/Docs)': GOOGLE, 'Google-NotebookLM': GOOGLE,
  Bingbot: { lists: ['https://www.bing.com/toolbox/bingbot.json'], dns: ['search.msn.com'] },
  GPTBot: { lists: ['https://openai.com/gptbot.json'] },
  'ChatGPT-User': { lists: ['https://openai.com/chatgpt-user.json'] },
  'OAI-SearchBot': { lists: ['https://openai.com/searchbot.json'] },
  PerplexityBot: { lists: ['https://www.perplexity.com/perplexitybot.json'] },
  'Perplexity-User': { lists: ['https://www.perplexity.com/perplexity-user.json'] },
  Applebot: { lists: ['https://search.developer.apple.com/applebot.json'], dns: ['applebot.apple.com'] },
  'Applebot-Extended': { lists: ['https://search.developer.apple.com/applebot.json'], dns: ['applebot.apple.com'] },
  YandexBot: { dns: ['yandex.ru', 'yandex.net', 'yandex.com'] },
  Baiduspider: { dns: ['baidu.com', 'baidu.jp'] },
  PetalBot: { dns: ['petalsearch.com', 'aspiegel.com'] },
  AhrefsBot: { dns: ['ahrefs.com', 'ahrefs.net'] },
  SemrushBot: { dns: ['semrush.com'] },
  Amazonbot: { dns: ['amazonbot.amazon', 'amazon.com'] },
  'Facebook/Instagram': META,
  'meta-externalagent': META,
};

const listCache = new Map(); // url -> { at, nets: [{ v, base, bits }] }
const verdictCache = new Map(); // `${agent}|${ip}` -> verdict
const LIST_TTL = 12 * 3600e3;

export function parseIp(ip) {
  if (!ip) return null;
  if (ip.includes('.') && !ip.includes(':')) {
    const p = ip.split('.').map(Number);
    if (p.length !== 4 || p.some((x) => !Number.isInteger(x) || x < 0 || x > 255)) return null;
    return { v: 4, n: (BigInt(p[0]) << 24n) + (BigInt(p[1]) << 16n) + (BigInt(p[2]) << 8n) + BigInt(p[3]) };
  }
  const s = ip.toLowerCase().split('%')[0];
  if (!s.includes(':') || s.includes('.')) return null;
  const [head, tail] = s.split('::');
  const h = head ? head.split(':') : [];
  const t = tail !== undefined && tail ? tail.split(':') : [];
  const groups = tail !== undefined ? [...h, ...Array(Math.max(0, 8 - h.length - t.length)).fill('0'), ...t] : h;
  if (groups.length !== 8 || groups.some((g) => !/^[0-9a-f]{1,4}$/.test(g))) return null;
  let n = 0n;
  for (const g of groups) n = (n << 16n) + BigInt(parseInt(g, 16));
  return { v: 6, n };
}

function inNet(ip, net) {
  if (ip.v !== net.v) return false;
  const shift = BigInt((ip.v === 4 ? 32 : 128) - net.bits);
  return ip.n >> shift === net.base >> shift;
}

async function loadList(url) {
  const hit = listCache.get(url);
  if (hit && Date.now() - hit.at < LIST_TTL) return hit.nets;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(2500) });
    if (!res.ok) throw new Error(String(res.status));
    const nets = [];
    for (const p of (await res.json()).prefixes ?? []) {
      const cidr = p.ipv4Prefix ?? p.ipv6Prefix;
      if (!cidr) continue;
      const [addr, bits] = cidr.split('/');
      const parsed = parseIp(addr);
      if (parsed) nets.push({ v: parsed.v, base: parsed.n, bits: Number(bits) });
    }
    listCache.set(url, { at: Date.now(), nets });
    return nets;
  } catch {
    return hit?.nets ?? null; // stale list beats no list; null = couldn't check
  }
}

function ptrName(ip, parsed) {
  if (parsed.v === 4) return `${ip.split('.').reverse().join('.')}.in-addr.arpa`;
  return `${parsed.n.toString(16).padStart(32, '0').split('').reverse().join('.')}.ip6.arpa`;
}

async function doh(name, type) {
  const res = await fetch(`https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(name)}&type=${type}`, {
    headers: { accept: 'application/dns-json' },
    signal: AbortSignal.timeout(1500),
  });
  if (!res.ok) throw new Error(String(res.status));
  return ((await res.json()).Answer ?? []).map((a) => String(a.data).replace(/\.$/, '').toLowerCase());
}

// Reverse DNS must end in an operator domain AND resolve forward to the same IP.
async function dnsVerdict(ip, parsed, domains, strict) {
  try {
    const hosts = await doh(ptrName(ip, parsed), 'PTR');
    if (!hosts.length) return strict === false ? 'unverifiable' : 'impostor';
    const host = hosts.find((h) => domains.some((d) => h === d || h.endsWith(`.${d}`)));
    if (!host) return 'impostor';
    const back = await doh(host, parsed.v === 4 ? 'A' : 'AAAA');
    return back.some((a) => parseIp(a)?.n === parsed.n) ? 'verified' : 'impostor';
  } catch {
    return 'unverifiable';
  }
}

export async function verify(agent, ip) {
  const rule = VERIFY[agent];
  const parsed = parseIp(ip);
  if (!rule || !parsed) return 'unverifiable';
  const key = `${agent}|${ip}`;
  if (verdictCache.has(key)) return verdictCache.get(key);
  let verdict = null;
  if (rule.lists) {
    const lists = await Promise.all(rule.lists.map(loadList));
    if (lists.some((nets) => nets?.some((net) => inNet(parsed, net)))) verdict = 'verified';
    else if (!rule.dns) verdict = lists.every((l) => l === null) ? 'unverifiable' : 'impostor';
  }
  if (!verdict) verdict = await dnsVerdict(ip, parsed, rule.dns, rule.dnsStrict);
  if (verdictCache.size > 2000) verdictCache.clear();
  verdictCache.set(key, verdict);
  return verdict;
}

// ---------------------------------------------------------------------------
// Classification
// ---------------------------------------------------------------------------
export function classify(ua, headers) {
  for (const [kind, re, name] of AGENTS) {
    const m = ua.match(re);
    // Generic matches ("bot/", "crawl") say nothing; name those by the user agent's first word instead
    if (m) return { kind, agent: name ?? (kind === 'other_bot' ? productOf(ua) : m[0].replace(/\/$/, '')) };
  }
  const isBrowser = /Mozilla\/5\.0/.test(ua) && /(Chrome|CriOS|Safari|Firefox|FxiOS|Edg|OPR)\//.test(ua);
  if (!isBrowser) return { kind: ua ? 'other_bot' : 'script', agent: ua ? productOf(ua) : '(no user agent)' };
  // Real browsers always send Accept-Language, and modern ones mark top-level page loads.
  const dest = headers.get('sec-fetch-dest');
  const human = !!headers.get('accept-language') && (!dest || dest === 'document');
  return { kind: human ? 'human' : 'suspect', agent: browserOf(ua) };
}

const productOf = (ua) => (ua.split(/[\s;(]/)[0].split('/')[0] || ua).slice(0, 60);

function browserOf(ua) {
  if (/Edg(A|iOS)?\//.test(ua)) return 'Edge';
  if (/OPR\/|Opera/.test(ua)) return 'Opera';
  if (/SamsungBrowser/.test(ua)) return 'Samsung Internet';
  if (/Firefox\/|FxiOS/.test(ua)) return 'Firefox';
  if (/CriOS|Chrome\//.test(ua)) return 'Chrome';
  if (/Safari\//.test(ua)) return 'Safari';
  return 'Other';
}

function osOf(ua) {
  if (/iPhone|iPad|iPod/.test(ua)) return 'iOS';
  if (/Android/.test(ua)) return 'Android';
  if (/Windows/.test(ua)) return 'Windows';
  if (/CrOS/.test(ua)) return 'ChromeOS';
  if (/Mac OS X|Macintosh/.test(ua)) return 'macOS';
  if (/Linux/.test(ua)) return 'Linux';
  return null;
}

function deviceOf(ua) {
  if (/iPad|Tablet|(Android(?!.*Mobile))/i.test(ua)) return 'tablet';
  if (/Mobi|iPhone|iPod|Android/i.test(ua)) return 'mobile';
  return 'desktop';
}

const bareHost = (h) => h.toLowerCase().replace(/^www\./, '');
// Machine-readable files bots read to discover a site: always logged.
const DISCOVERY_FILE = /^\/(robots\.txt|llms(-full)?\.txt|ai\.txt|humans\.txt|sitemap[^/]*\.xml|feed(\.xml)?|rss(\.xml)?|atom\.xml|\.well-known\/[a-z0-9._-]+)$/i;
const STATIC = /\.(?!html?$)[a-z0-9]{1,8}$/i; // any other file extension except .html

export default async (request, context) => {
  if (request.method !== 'GET') return; // HEAD = link checkers, not page views
  const url = new URL(request.url);
  const site = bareHost(url.hostname);
  // Real domains only: not deploy previews, branch deploys or local dev.
  if (!site.includes('.') || site.endsWith('.netlify.app') || site.endsWith('.netlify.live') || site === 'localhost') return;
  const discoveryFile = DISCOVERY_FILE.test(url.pathname);
  if (!discoveryFile && (STATIC.test(url.pathname) || /^\/admin(\/|$)/.test(url.pathname))) return; // assets; your own admin pages
  // Browsers prefetching a link aren't page views.
  if (/prefetch|prerender/i.test(request.headers.get('sec-purpose') ?? request.headers.get('purpose') ?? '')) return;

  const toggle = url.searchParams.get('count');
  const optedOut = toggle === 'off' || (toggle !== 'on' && (request.headers.get('cookie') ?? '').includes(`${OPT_OUT}=1`));

  const response = await context.next();

  if (toggle === 'off' || toggle === 'on') {
    const res = new Response(response.body, response);
    res.headers.append(
      'set-cookie',
      toggle === 'off'
        ? `${OPT_OUT}=1; Path=/; Max-Age=63072000; SameSite=Lax; Secure`
        : `${OPT_OUT}=; Path=/; Max-Age=0; SameSite=Lax; Secure`,
    );
    return res;
  }
  if (optedOut) return response;
  if (!discoveryFile && !(response.headers.get('content-type') ?? '').includes('text/html')) return response;
  const KEY = siteHitsKey();
  if (!KEY) return response;

  const ua = request.headers.get('user-agent') ?? '';
  const { kind, agent } = classify(ua, request.headers);
  const person = kind === 'human' || kind === 'suspect';

  let refHost = null;
  try {
    const ref = request.headers.get('referer');
    if (ref) refHost = bareHost(new URL(ref).hostname);
  } catch {
    /* malformed referrer */
  }
  const internal = refHost === site;

  const hit = {
    site,
    path: url.pathname.slice(0, 300),
    status: response.status,
    kind,
    agent,
    entry: !internal,
    ref_host: internal ? null : refHost,
    utm_source: url.searchParams.get('utm_source'),
    utm_medium: url.searchParams.get('utm_medium'),
    utm_campaign: url.searchParams.get('utm_campaign'),
    country: context.geo?.country?.code ?? null,
    region: context.geo?.subdivision?.name ?? null,
    city: context.geo?.city ?? null,
    device: person ? deviceOf(ua) : null,
    browser: person ? agent : null,
    os: osOf(ua),
    lang: (request.headers.get('accept-language') ?? '').split(',')[0].trim() || null,
    // People only: hashed with a daily salt in the database, never stored (see header)
    ip: person ? context.ip ?? null : null,
    ua: person ? ua : null,
  };

  context.waitUntil(
    (person ? Promise.resolve(null) : verify(agent, context.ip))
      .then((verified) =>
        fetch(ENDPOINT, {
          method: 'POST',
          headers: { apikey: KEY, Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ hit: { ...hit, verified } }),
        }),
      )
      .then((r) => (r.ok ? null : r.text().then((t) => console.error('[site-hits]', r.status, t.slice(0, 200)))))
      .catch((e) => console.error('[site-hits]', e?.message ?? e)),
  );
  return response;
};

export const config = {
  path: '/*',
  excludedPath: [
    '/.netlify/*', '/api/*', '/_next/*', '/_astro/*', '/assets/*', '/static/*', '/fonts/*', '/images/*', '/img/*',
    '/*.js', '/*.mjs', '/*.css', '/*.map', '/*.json', '/*.ico', '/*.svg', '/*.png', '/*.jpg',
    '/*.jpeg', '/*.webp', '/*.avif', '/*.gif', '/*.woff', '/*.woff2', '/*.pdf', '/*.mp4', '/*.webmanifest',
  ],
};
