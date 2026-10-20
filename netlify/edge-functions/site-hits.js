/**
 * site-hits: Shifted Labs' shared traffic counter.
 *
 * ONE IDENTICAL COPY lives in every site repo (netlify/edge-functions/site-hits.js).
 * Master copy + installer: ~/.config/shiftedlabs/site-hits/ on Babac's Mac. Edit
 * there and re-run install.sh rather than editing a single site's copy.
 *
 * Why: Google Analytics only counts visitors who accept cookies and don't block
 * trackers, and never sees bots. This runs on Netlify's edge for every page
 * request, before any banner, and labels who asked for the page:
 *   human | suspect | ai_assistant | ai_crawler | search_crawler | seo_tool |
 *   link_preview | monitor | script | other_bot
 * It writes one row per HTML page served to Supabase (project
 * dpbqttplugxcuuuzxgfk, schema site_analytics) after the response has gone
 * out, so visitors never wait on it. If the database is down, nothing breaks.
 *
 * Stored: site, path, status, label, bot name / browser family, entry flag,
 * referring site, utm_source/medium/campaign, country/region/city (Netlify geo),
 * device, OS, first language, and for people a daily visitor code.
 * NOT stored: IP, full user agent, cookies, query strings.
 *
 * Unique visitors: for page views by people, the IP and user agent are sent
 * (over HTTPS) to log_site_hit, which turns them into a 16-character code with a
 * random salt that changes every day and never leaves the database, and stores
 * only the code. Finished days are rolled up into daily counts and their codes
 * and salts deleted (see dashboard.sql). No cookie, nothing on the device, so
 * no consent banner is needed; a person counts once per site per day.
 *
 * The key below is the project's PUBLISHABLE key: public by design, and in this
 * project it can only call log_site_hit (insert-only). It cannot read anything.
 *
 * Exclude your own browser on a site: open any page with ?count=off (undo: ?count=on).
 */

const ENDPOINT = 'https://dpbqttplugxcuuuzxgfk.supabase.co/rest/v1/rpc/log_site_hit';
const KEY = 'sb_publishable_45PHPHXAlqQl-LB4PNc8ag_KqXhqHio';
const OPT_OUT = 'sl_count_off';

// First match wins. Order matters: AI assistants before generic bot words.
const AGENTS = [
  ['ai_assistant', /ChatGPT-User|Perplexity-User|Claude-User|MistralAI-User|Gemini-Deep-Research|DuckAssistBot|Meta-ExternalFetcher|Google-NotebookLM|NovaAct/i],
  ['ai_crawler', /GPTBot|OAI-SearchBot|ClaudeBot|Claude-SearchBot|anthropic-ai|PerplexityBot|CCBot|Bytespider|Amazonbot|meta-externalagent|Applebot-Extended|Google-Extended|cohere-ai|Diffbot|YouBot|PetalBot|Timpibot|ImagesiftBot|AI2Bot|Kangaroo Bot/i],
  ['search_crawler', /Googlebot|Google-InspectionTool|GoogleOther|Storebot-Google|AdsBot-Google|bingbot|BingPreview|YandexBot|DuckDuckBot|Baiduspider|Applebot|Qwantbot|SeznamBot|Sogou|Yeti|MojeekBot|Bravebot/i],
  ['seo_tool', /AhrefsBot|AhrefsSiteAudit|SemrushBot|SiteAuditBot|MJ12bot|DotBot|DataForSeoBot|BLEXBot|Screaming Frog|serpstatbot|SEOkicks|Barkrowler|rogerbot|Sitebulb|SeobilityBot|SERankingBacklinksBot/i],
  ['link_preview', /facebookexternalhit|facebookcatalog|WhatsApp|Twitterbot|Slackbot|Slack-ImgProxy|TelegramBot|LinkedInBot|Discordbot|Pinterestbot|SkypeUriPreview|redditbot|Iframely|Embedly|vkShare|Viber|Snapchat|Google-PageRenderer|Mastodon|Bluesky|Teams|Outlook-iOS|Microsoft Office/i],
  ['monitor', /UptimeRobot|Pingdom|StatusCake|Better ?Uptime|BetterStack|Site24x7|Netlify|checkly|Datadog|NewRelic|GTmetrix|Chrome-Lighthouse|Google Page Speed|PageSpeed|Uptime-Kuma/i],
  ['script', /HeadlessChrome|PhantomJS|Puppeteer|Playwright|curl\/|Wget|python-requests|python-httpx|python-urllib|aiohttp|Go-http-client|node-fetch|undici|axios|okhttp|Java\/|libwww|Scrapy|httpclient|PostmanRuntime|Deno\/|Bun\//i],
  ['other_bot', /bot\b|bot\/|crawl|spider|slurp|scrape|fetcher|archiver/i],
];

const STATIC = /\.(?!html?$)[a-z0-9]{1,8}$/i; // any file extension except .html

function classify(ua, headers) {
  for (const [kind, re] of AGENTS) {
    const m = ua.match(re);
    if (m) return { kind, agent: m[0].replace(/\/$/, '') };
  }
  const isBrowser = /Mozilla\/5\.0/.test(ua) && /(Chrome|CriOS|Safari|Firefox|FxiOS|Edg|OPR)\//.test(ua);
  if (!isBrowser) return { kind: ua ? 'other_bot' : 'script', agent: ua ? ua.split(/[\s/;(]/)[0].slice(0, 60) : '(no user agent)' };
  // Real browsers always send Accept-Language, and modern ones mark top-level page loads.
  const dest = headers.get('sec-fetch-dest');
  const human = !!headers.get('accept-language') && (!dest || dest === 'document');
  return { kind: human ? 'human' : 'suspect', agent: browserOf(ua) };
}

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

export default async (request, context) => {
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  const site = bareHost(url.hostname);
  // Real domains only: not deploy previews, branch deploys or local dev.
  if (!site.includes('.') || site.endsWith('.netlify.app') || site.endsWith('.netlify.live') || site === 'localhost') return;
  if (STATIC.test(url.pathname) || /^\/admin(\/|$)/.test(url.pathname)) return; // assets; your own admin pages
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
  if (optedOut || !(response.headers.get('content-type') ?? '').includes('text/html')) return response;

  const ua = request.headers.get('user-agent') ?? '';
  const { kind, agent } = classify(ua, request.headers);

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
    device: kind === 'human' || kind === 'suspect' ? deviceOf(ua) : null,
    browser: kind === 'human' || kind === 'suspect' ? agent : null,
    os: osOf(ua),
    lang: (request.headers.get('accept-language') ?? '').split(',')[0].trim() || null,
    // People only: hashed with a daily salt in the database, never stored (see header)
    ip: kind === 'human' || kind === 'suspect' ? context.ip ?? null : null,
    ua: kind === 'human' || kind === 'suspect' ? ua : null,
  };

  context.waitUntil(
    fetch(ENDPOINT, {
      method: 'POST',
      headers: { apikey: KEY, Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ hit }),
    })
      .then((r) => (r.ok ? null : r.text().then((t) => console.error('[site-hits]', r.status, t.slice(0, 200)))))
      .catch((e) => console.error('[site-hits]', e?.message ?? e)),
  );
  return response;
};

export const config = {
  path: '/*',
  excludedPath: [
    '/.netlify/*', '/api/*', '/_next/*', '/_astro/*', '/assets/*', '/static/*', '/fonts/*', '/images/*', '/img/*',
    '/*.js', '/*.mjs', '/*.css', '/*.map', '/*.json', '/*.xml', '/*.txt', '/*.ico', '/*.svg', '/*.png', '/*.jpg',
    '/*.jpeg', '/*.webp', '/*.avif', '/*.gif', '/*.woff', '/*.woff2', '/*.pdf', '/*.mp4', '/*.webmanifest',
  ],
};
