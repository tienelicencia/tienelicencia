/* One map of Spain: registered tourist flats from the whole country down to each building, plus, where we have Airbnb
   data, problem hexes and barrios. /<slug>/mapa opens it framed on that area, /mapa on all of Spain; as you zoom and pan
   the title, layers and legend follow the area in the middle of the screen.
   Data: /data/spain/* (pipeline/site_build.py write_spain_map): hexagons at four sizes, one per zoom band; buildings and
   the 90 m hexagons in tiles, fetched for what is on screen; each area's own layers when it is in view; plus
   /data/<slug>/barrios.geojson and dots.json. Clicking a building lists every registered flat in it (/api/building).
   Deep links: ?b=<building id>[&lat=&lon=], ?barrio=<id>, ?lat=&lon=&z=, ?capa=, ?circle=<lat>,<lon>,<radius m>[&label=]. */
(() => {
  const { t, fmt, esc, name, getJSON, areaHref, ICON } = TL;
  const first = TL.currentArea();   // "mapa" on /mapa: all of Spain
  TL.init({ page: "map" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const $ = (s) => document.querySelector(s);
  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => TL.setLang(b.dataset.l)));
  TL.applyStatic();

  const DENS = ["#dcefe5", "#a9d7bf", "#6dbb95", "#2c956b", "#0b6a4e"];
  const RAMP = ["#fde7d6", "#f7b98e", "#ec8452", "#cf4a2c", "#9a2318"];
  const SHARE = ["#eceffb", "#c3caf0", "#8b97df", "#4f5fc4", "#26318f"];   // % of homes (indicative)
  const SHARE_STOPS = [2, 5, 8, 15], PCT_STOPS = [15, 30, 45, 60];
  let measure = "share";   // share layer: "share" = registered, "ashare" = Airbnb entire-home listings (cities with Airbnb data)
  const BLD = "#11805d", OTHER = "#2f62b5";
  const pc = (x) => `${Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 })}${TL.lang() === "es" ? " %" : "%"}`;
  const isMobile = () => matchMedia("(max-width: 760px)").matches;
  const params = new URLSearchParams(location.search);
  if (!["licences", "share", "problems", "barrios"].includes(params.get("capa") || "licences")) params.delete("capa");

  // ---------------------------------------------------------------- hexagons
  // The pipeline's grid (rta_audit/geo.py Hex: pointy-top, in a fixed local projection), rebuilt here from each cell's
  // (q, r) so the files carry two numbers per hexagon instead of seven corners.
  const MX = 111320 * Math.cos(36.72 * Math.PI / 180), MY = 110574, R3 = Math.sqrt(3);
  function hexRing(s, q, r) {
    const cx = s * R3 * (q + r / 2), cy = s * 1.5 * r, out = [];
    for (let i = 0; i < 7; i++) {
      const a = (60 * (i % 6) - 30) * Math.PI / 180;
      out.push([(cx + s * Math.cos(a)) / MX, (cy + s * Math.sin(a)) / MY]);
    }
    return out;
  }
  function hexCell(s, lat, lon) {
    const x = lon * MX, y = lat * MY, q = (R3 / 3 * x - y / 3) / s, r = (2 / 3 * y) / s;
    let rx = Math.round(q), rz = Math.round(r);
    const ry = Math.round(-q - r), dx = Math.abs(rx - q), dy = Math.abs(ry + q + r), dz = Math.abs(rz - r);
    if (dx > dy && dx > dz) rx = -ry - rz;
    else if (dy <= dz) rz = -rx - ry;
    return [rx, rz];
  }
  const hexFeat = (s, q, r, properties) => ({ type: "Feature", properties, geometry: { type: "Polygon", coordinates: [hexRing(s, q, r)] } });
  const across = (s) => { const m = s * R3; return m >= 1000 ? `${(Math.round(m / 500) / 2).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB")} km` : `${fmt(Math.round(m / 10) * 10)} m`; };

  // Zoom bands: hexagon level k (6 km, 2 km, 400 m, 90 m circumradius) gives way to k+1 at BAND[k], crossfading over ±FADE.
  const BAND = [6.3, 8.8, 11.3], FADE = 0.3, BMIN = 12.3;   // buildings from BMIN
  const levelAt = (z) => BAND.filter((b) => z >= b).length;
  const SPAIN = { center: [-3.6, 40.1], zoom: 5.3 };
  // When an area takes over the title and layer buttons (zf), and when its own layers load instead of a whole-city circle (zt)
  const zf = (a) => a.zoom - ({ city: 2.2, island: 1.6, province: 0.9, region: 1.3 }[a.kind] ?? 2);
  const zt = (a) => a.zoom - (a.kind === "city" ? 3 : 1.5);

  let A, AREA = {}, AIDX = {}, M, OWN = new Map(), focus = null, pin = null, view = params.get("capa") || "licences", selected = null;
  let B = [], byId = new Map(), pendingB = null, H3T, BT, layersReady = false, framing = false;
  const DATA = { h0: [], h1: [], h2: [], h3: [], buildings: [], ahex: [], barrios: [], dots: [], bub: [] };
  const themeOn = new Set(), barOn = new Set();
  const circle = parseCircle();

  const map = new maplibregl.Map({ container: "map", style: "https://tiles.openfreemap.org/styles/positron",
    center: SPAIN.center, zoom: SPAIN.zoom, minZoom: 4, maxZoom: 19, attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "top-right");
  // Our layers only need the style to be parsed, not every basemap tile and glyph ("load"/"idle"),
  // so wait for "style.load" and fetch our data in parallel with it.
  const styleReady = new Promise((r) => map.once("style.load", r));
  const loadingEl = $("#map-loading");
  let inflight = 0, firstPaint = false;
  const busy = (d) => { inflight += d; if (firstPaint) loadingEl.classList.toggle("done", inflight <= 0); };
  const loaded = () => { firstPaint = true; busy(0); };

  Promise.all([getJSON("/data/areas.json"), getJSON("/data/spain/map.json")]).then(async ([AA, MM]) => {
    A = AA; M = MM;
    A.areas.forEach((a, i) => { AREA[a.slug] = a; AIDX[a.slug] = i + 1; });
    if (first && first !== "mapa" && !AREA[first]) { location.replace("/mapa"); return; }
    for (const [q, r, , o] of M.levels[1].c) OWN.set(`${q},${r}`, M.owners[o]);
    H3T = new Set(M.levels[3].tiles); BT = new Set(M.bld.tiles);
    DATA.h0 = M.levels[0].c.map(([q, r, n]) => hexFeat(M.levels[0].s, q, r, { n }));
    DATA.h1 = M.levels[1].c.filter((c) => c[2]).map(([q, r, n]) => hexFeat(M.levels[1].s, q, r, { n }));
    frame();
    refresh();   // starts fetching what's on screen while the basemap style loads
    TL.onLang(() => { bubbles(); chrome(true); if (selected) reselect(); });
    await styleReady;
    addLayers();
    map.once("render", loaded);   // first frame with our layers drawn
  }).catch(() => map.once("idle", loaded));
  map.once("idle", () => { if (!layersReady) loaded(); });   // fallback, e.g. if our data failed to load

  /** Initial camera: a ?circle=, then ?lat=&lon=, then the area in the address, else all of Spain. */
  function frame() {
    const a = AREA[first], pl = +params.get("lat"), pn = +params.get("lon"), pz = +params.get("z");
    framing = true;   // no refresh() from these jumps' "moveend" until the pin below is set
    if (circle) map.fitBounds(circle.bounds, { padding: padding(), maxZoom: 16, duration: 0 });
    else if (pl && pn) map.jumpTo({ center: [pn, pl], zoom: pz || (params.get("b") ? 17 : 15) });
    else if (a) map.jumpTo({ center: a.center, zoom: isMobile() ? a.zoom - 0.6 : a.zoom });
    else map.jumpTo(isMobile() ? { center: SPAIN.center, zoom: SPAIN.zoom - 0.9 } : SPAIN);
    if (a) pin = { slug: a.slug, z: map.getZoom() };
    framing = false;
    const b = params.get("b");
    if (b && pl && pn) pendingB = b;
    else if (b && a) {   // an older link with only the building id: find it in that area's building list
      getJSON(`/data/${a.slug}/buildings.json`).then((d) => {
        const r = d.rows.find((x) => x[8] === b);
        if (!r) return;
        pendingB = b;
        map.jumpTo({ center: [r[1], r[0]], zoom: 17 });
        refresh();
      }).catch(() => {});
    }
  }

  // ---------------------------------------------------------------- what is on screen: data and the area in focus
  const LOADS = new Map();
  function load(url, use) {
    if (!LOADS.has(url)) {
      busy(1);
      LOADS.set(url, getJSON(url).then(use).catch(() => {}).finally(() => busy(-1)));
    }
    return LOADS.get(url);
  }
  function tilesInView(z) {
    const b = map.getBounds(), n = 2 ** z, out = [];
    const tx = (lon) => Math.floor((lon + 180) / 360 * n);
    const ty = (lat) => Math.floor((1 - Math.asinh(Math.tan(Math.max(-85, Math.min(85, lat)) * Math.PI / 180)) / Math.PI) / 2 * n);
    for (let x = tx(b.getWest()); x <= tx(b.getEast()); x++) for (let y = ty(b.getNorth()); y <= ty(b.getSouth()); y++) out.push(`${x}-${y}`);
    return out.length > 48 ? [] : out;
  }
  const box = (s) => M.areas[s]?.bbox;
  const inBox = (s, c) => { const b = box(s); return b && c.lng >= b[0] && c.lng <= b[2] && c.lat >= b[1] && c.lat <= b[3]; };
  function areasInView() {
    const b = map.getBounds();
    return A.areas.filter((a) => { const x = box(a.slug); return a.has_map !== false && x && !(x[2] < b.getWest() || x[0] > b.getEast() || x[3] < b.getSouth() || x[1] > b.getNorth()); });
  }
  const hasShare = (a) => a.homes && !a.census && M.areas[a.slug]?.theme;
  const ownerAt = (lat, lon) => OWN.get(hexCell(M.levels[1].s, lat, lon).join(","));

  /** The area the screen is about: the one the URL or the switcher chose until the view leaves it; else the finest area
      owning the 2 km cell in the middle that is zoomed in enough; else (no registered flats there) the smallest area
      whose box holds the middle. null = Spain. */
  function findFocus() {
    const z = map.getZoom(), c = map.getCenter();
    if (selected?.type === "barrio" && inBox(selected.area, c)) return AREA[selected.area];
    if (pin) {
      if (Math.abs(z - pin.z) < 0.8 && inBox(pin.slug, c)) return AREA[pin.slug];
      pin = null;
    }
    const o = ownerAt(c.lat, c.lng);
    if (o) {
      for (let s = o; s; s = M.areas[s]?.parent) if (AREA[s] && z >= zf(AREA[s])) return AREA[s];
      return null;
    }
    const area_ = (s) => { const b = box(s); return (b[2] - b[0]) * (b[3] - b[1]); };
    return A.areas.filter((a) => inBox(a.slug, c) && z >= zf(a)).sort((a, b) => area_(a.slug) - area_(b.slug))[0] || null;
  }

  function refresh() {
    if (!M || framing) return;
    const z = map.getZoom();
    if (z >= BAND[1] - FADE && z < BAND[2] + FADE) load("/data/spain/h2.json", (cs) => { DATA.h2 = cs.map(([q, r, n]) => hexFeat(M.levels[2].s, q, r, { n })); touch("h2"); });
    if (z >= BAND[2] - FADE) for (const k of tilesInView(M.levels[3].tz)) if (H3T.has(k)) load(`/data/spain/h3/${k}.json`, (cs) => {
      for (const [q, r, n] of cs) DATA.h3.push(hexFeat(M.levels[3].s, q, r, { n }));
      touch("h3");
    });
    if (z >= BMIN - 0.5) for (const k of tilesInView(M.bld.tz)) if (BT.has(k)) load(`/data/spain/b/${k}.json`, addBuildings);
    for (const a of areasInView()) {
      if ((view === "share" || view === "problems") && M.areas[a.slug].theme && z >= zt(a)) loadTheme(a.slug);
      if (view === "barrios" && a.has_barrios && z >= zt(a)) loadBarrios(a.slug);
      if (view === "problems" && a.has_listings && z >= 13) loadDots(a.slug);
    }
    const f = findFocus();
    if (f !== focus || !location.pathname.endsWith("mapa")) {
      focus = f;
      const u = new URL(location.href);
      u.pathname = focus ? areaHref(focus.slug, "mapa") : "/mapa";
      if (u.pathname !== location.pathname && selected?.type !== "barrio") u.searchParams.delete("barrio");   // its id is that city's
      if (u.href !== location.href) history.replaceState(null, "", u);
    }
    if (!viewsAvail().includes(view)) showLayers("licences");   // e.g. "% homes" after leaving every area that has it
    bubbles();
    chrome();
  }
  map.on("moveend", refresh);

  function addBuildings(rows) {
    for (const r of rows) {
      if (byId.has(r[6])) continue;
      byId.set(r[6], B.length);
      DATA.buildings.push({ type: "Feature", id: B.length, properties: { vut: r[3], other: r[5], n: r[3] + r[5] }, geometry: { type: "Point", coordinates: [r[1], r[0]] } });
      B.push(r);
    }
    touch("buildings");
    if (layersReady && pendingB && byId.has(pendingB)) { select(pendingB, true); pendingB = null; }
  }
  function loadTheme(s) {
    return load(`/data/spain/a/${s}.json`, (d) => {
      const F = d.fields;
      for (const c of d.c) {
        const p = { a: s };
        F.forEach((k, i) => { if (i > 1 && c[i] != null) p[k] = c[i]; });
        DATA.ahex.push(hexFeat(d.s, c[0], c[1], p));
      }
      themeOn.add(s);
      shareFilter();
      touch("ahex");
    });
  }
  function loadBarrios(s) {
    return load(`/data/${s}/barrios.geojson`, (g) => {
      for (const f of g.features) DATA.barrios.push({ ...f, properties: { ...f.properties, area: s, uid: AIDX[s] * 100000 + f.properties.id } });
      barOn.add(s);
      touch("barrios");
      if (view === "barrios" && !selected && focus?.slug === s && !isMobile()) barrioList();
    });
  }
  function loadDots(s) {
    return load(`/data/${s}/dots.json`, (D) => {
      for (const [lo, la, v] of D) DATA.dots.push({ type: "Feature", properties: { v }, geometry: { type: "Point", coordinates: [lo, la] } });
      touch("dots");
    });
  }
  // Sources are redrawn once per frame however many files arrive in it
  const dirty = new Set();
  function touch(src) {
    if (!layersReady) return;
    if (!dirty.size) requestAnimationFrame(() => {
      for (const s of dirty) map.getSource(s)?.setData({ type: "FeatureCollection", features: DATA[s] });
      dirty.clear();
    });
    dirty.add(src);
  }

  // ---------------------------------------------------------------- chrome (title, switcher, layers, legend, search)
  let search, searchArea, sig = "";
  const SUB = (a = focus) => a?.subareas === "municipality"
    ? { one: L("Municipio", "Municipality"), many: L("Municipios", "Municipalities"), the: L("del municipio", "in this municipality") }
    : { one: "Barrio", many: "Barrios", the: L("del barrio", "in this barrio") };
  function viewsAvail() {
    const inV = areasInView(), vs = ["licences"];
    if (inV.some(hasShare)) vs.push("share");
    if (inV.some((a) => a.has_listings && a.has_barrios)) vs.push("problems", "barrios");
    return vs;
  }
  const circlesOn = () => DATA.bub.length > 0;
  function chrome(force) {
    if (!A) return;
    const vs = viewsAvail();
    const s = [focus?.slug, vs.join(), view, levelAt(map.getZoom()), map.getZoom() >= BMIN, circlesOn(), TL.lang()].join("|");
    if (!force && s === sig) return;
    sig = s;
    const nm = focus ? name(focus.name) : L("España", "Spain");
    document.title = `${L("Mapa", "Map")} · ${nm} | tienelicencia.com`;
    $("#map-title").innerHTML = `${esc(nm)}<small>${L("Viviendas turísticas registradas", "Registered tourist flats")}</small>`;
    $("#back").href = focus ? areaHref(focus.slug) : "/";
    $("#area-switch").innerHTML = `<option value="" ${focus ? "" : "selected"}>${L("España", "Spain")}</option>` +
      A.areas.map((a) => `<option value="${a.slug}" ${a.slug === focus?.slug ? "selected" : ""}>${esc(name(a.name))}</option>`).join("");
    $("#area-switch").onchange = (e) => goTo(e.target.value);
    $("#map-share").innerHTML = TL.shareButton({ url: viewUrl(), text: L(`Mapa de viviendas turísticas · ${nm}`, `Tourist-flat map · ${nm}`) + " · tienelicencia.com", content: "map_view" });
    const btn = (v, es, en) => vs.includes(v) ? `<button type="button" data-v="${v}" aria-pressed="${view === v}">${L(es, en)}</button>` : "";
    $("#layers").innerHTML = `<div class="seg" role="group">${btn("licences", "Licencias", "Licences")}${btn("share", "% viviendas", "% homes")}
        ${btn("problems", "Sin nº", "No number")}${btn("barrios", SUB().many, SUB().many)}</div>
        <p class="layer-help">${help()}</p>`;
    document.querySelectorAll("#layers [data-v]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.v)));
    $("#legend").innerHTML = `<button class="legend-btn" type="button"><i></i>${L("Leyenda", "Legend")}</button><div class="legend-body">${legend()}</div>`;
    $("#legend .legend-btn").onclick = () => $("#legend").classList.toggle("open");
    wireMeasure();
    // the search looks in the area on screen (its register); remounted only while it's empty
    const sa = focus?.slug || searchArea || (AREA[first] ? first : "provincia");
    if (!search || (sa !== searchArea && !search.input.value && document.activeElement !== search.input)) {
      searchArea = sa;
      search = TL.searchWidget($("#p-search"), { area: sa, compact: true, onBarrio: (id, muni) => {
        const s_ = TL.areaOfMuni(muni);
        if (!AREA[s_]?.has_barrios) return false;
        loadBarrios(s_).then(() => showBarrio(s_, id));
        return true;
      }, onShowOnMap: (r) => {
        if (byId.has(r.building)) { select(r.building, true); return true; }
        if (r.lat == null) return false;
        pendingB = r.building;   // its tile loads when the map gets there
        map.flyTo({ center: [r.lon, r.lat], zoom: 17, speed: 1.6, padding: padding() });
        return true;
      } });
    }
    if (!selected) emptyDetail();
  }
  function emptyDetail() {
    const note = focus && focus.has_map === false
      ? L(`El registro de ${esc(name(focus.name))} no da la ubicación de las viviendas, así que no podemos situarlas en el mapa. Puedes buscarlas por dirección o número de licencia, o <a href="${areaHref(focus.slug)}">ver los datos de la ciudad</a>.`,
        `${esc(name(focus.name))}'s register doesn't give the flats' locations, so we can't place them on the map. You can search by address or licence number, or <a href="${areaHref(focus.slug)}">see the city's figures</a>.`)
      : L("Pulsa un edificio del mapa para ver sus viviendas turísticas registradas, o busca una dirección o un número de licencia.",
        "Tap a building on the map to see its registered tourist flats, or search for an address or licence number.");
    $("#p-detail").innerHTML = `${circle ? `<div class="detail-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2.4"><circle cx="12" cy="12" r="8"/></svg><span>${circle.label ? `<b>${esc(circle.label)}</b> · ` : ""}${L(`círculo de ${fmtM(circle.r)} de radio`, `circle of ${fmtM(circle.r)} radius`)}</span></div>` : ""}
      <div class="detail-empty">${ICON.info}<span>${note}</span></div>`;
  }
  const fmtM = (m) => (m >= 1000 ? `${(m / 1000).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 })} km` : `${fmt(Math.round(m))} m`);
  function goTo(s) {
    const a = AREA[s];
    TL.track("map_area", { area: s || "spain" });
    const to = a ? { center: a.center, zoom: isMobile() ? a.zoom - 0.6 : a.zoom } : isMobile() ? { center: SPAIN.center, zoom: SPAIN.zoom - 0.9 } : SPAIN;
    pin = a ? { slug: s, z: to.zoom } : null;
    map.flyTo({ ...to, speed: 1.4 });
  }
  function help() {
    const far = circlesOn() ? L(" Cada círculo da el dato de toda una ciudad o isla; acércate para verlo por zonas.", " Each circle gives the figure for a whole city or island; zoom in to see it by area.") : "";
    return {
      licences: map.getZoom() >= BMIN
        ? L("Cada punto es un edificio con viviendas turísticas registradas. El sombreado indica cuántas hay en cada zona.",
          "Each dot is a building with registered tourist flats. Shading shows how many there are in each area.")
        : L("El sombreado indica cuántas viviendas turísticas registradas hay en cada zona; acércate para verlas edificio a edificio. Sin color: zonas sin viviendas registradas o cuyo registro aún no tenemos.",
          "Shading shows how many registered tourist flats there are in each area; zoom in to see them building by building. No colour: areas with no registered flats or whose register we don't have yet."),
      share: L("Viviendas turísticas registradas como porcentaje de todas las viviendas de cada zona (Catastro). Dato indicativo.",
        "Registered tourist flats as a share of all homes in each area (Catastro). Indicative.") + far,
      problems: L("Porcentaje de anuncios de Airbnb que no muestran un número válido, por zona. Solo zonas con 10 anuncios o más; nunca anuncios individuales.",
        "Share of Airbnb listings not showing a valid number, by area. Only areas with 10+ listings; never individual listings.") + far,
      barrios: (focus?.subareas === "municipality"
        ? L("Porcentaje de anuncios sin número válido por municipio. Pulsa un municipio para ver sus datos.",
          "Share of listings without a valid number by municipality. Tap a municipality for its figures.")
        : L("Porcentaje de anuncios sin número válido por barrio oficial. Pulsa un barrio para ver sus datos.",
          "Share of listings without a valid number by official barrio. Tap a barrio for its figures.")) + far,
    }[view];
  }
  function legend() {
    const ramp = (cols, labels) => `<div class="ramp">${cols.map((c) => `<span style="background:${c}"></span>`).join("")}</div>
      <div class="ramp-labels">${labels.map((l) => `<span>${l}</span>`).join("")}</div>`;
    const lv = M.levels[levelAt(map.getZoom())], st = lv.stops;
    const far = circlesOn() ? `<p class="tiny muted" style="margin:6px 0 0">${L("Círculos: dato de toda la ciudad o isla.", "Circles: the figure for the whole city or island.")}</p>` : "";
    if (view === "licences") return `<div class="legend-title">${L(`Viviendas por zona de ~${across(lv.s)}`, `Flats per ~${across(lv.s)} area`)}</div>
      ${ramp(DENS, ["1", ...st.map(fmt).slice(0, 3), `${fmt(st[3])}+`])}
      <div class="legend-row"><span class="sw" style="background:${BLD}"></span>${L("Edificio con viviendas turísticas (tamaño = número)", "Building with tourist flats (size = number)")}</div>
      <div class="legend-row"><span class="sw" style="background:${OTHER}"></span>${L("Hotel, apartamento turístico u otro alojamiento", "Hotel, tourist apartment or other establishment")}</div>`;
    if (view === "share") return `${focus?.has_listings ? `<div class="seg mini" role="group" style="margin-bottom:10px">
        <button type="button" data-m="share" aria-pressed="${measure === "share"}">${L("Registradas", "Registered")}</button>
        <button type="button" data-m="ashare" aria-pressed="${measure === "ashare"}">${L("Anunciadas en Airbnb", "On Airbnb")}</button></div>` : ""}
      <div class="legend-title">${measure === "share" ? L("% de viviendas que son turísticas registradas", "% of homes that are registered tourist flats")
        : L("Anuncios de vivienda completa en Airbnb, % de viviendas", "Entire-home Airbnb listings, % of homes")}</div>
      ${ramp(SHARE, ["0", "2%", "5%", "8%", "15%+"])}<p class="tiny muted" style="margin:6px 0 0">${L("Indicativo · solo zonas con al menos 30 viviendas", "Indicative · only areas with at least 30 homes")}</p>${far}`;
    if (view === "problems") return `<div class="legend-title">${L("Anuncios sin número válido", "Listings without a valid number")}</div>${ramp(RAMP, ["0%", "15%", "30%", "45%", "60%+"])}
      <div class="legend-items" style="margin-top:10px"><span><i style="background:#b3261e"></i>${L("Sin número válido", "No valid number")}</span>
        <span><i style="background:#2e7d5b"></i>${L("Número válido", "Valid number")}</span><span><i style="background:#9aa3b0"></i>${L("Posiblemente exento", "Possibly exempt")}</span></div>
      <p class="tiny muted" style="margin:6px 0 0">${L("Al acercarte, cada punto es un anuncio, colocado al azar dentro de su zona de ~150 m: no marca dónde está.",
        "Zoom in and each dot is a listing, placed at random inside its ~150 m area: it doesn't mark where the listing is.")}</p>${far}`;
    return `<div class="legend-title">${focus?.subareas === "municipality" ? L("Anuncios sin número válido, por municipio", "Listings without a valid number, by municipality") : L("Anuncios sin número válido, por barrio", "Listings without a valid number, by barrio")}</div>${ramp(RAMP, ["0%", "15%", "25%", "35%", "45%+"])}${far}`;
  }

  /** Link to exactly what's on screen: position, zoom, layer, selection, circle. */
  function viewUrl() {
    const c = map.getCenter(), s = selected?.type === "barrio" ? selected.area : focus?.slug;
    const u = new URL(`https://tienelicencia.com${s ? areaHref(s, "mapa") : "/mapa"}`);
    u.searchParams.set("lat", c.lat.toFixed(5)); u.searchParams.set("lon", c.lng.toFixed(5)); u.searchParams.set("z", map.getZoom().toFixed(1));
    if (view !== "licences") u.searchParams.set("capa", view);
    if (selected?.type === "building") u.searchParams.set("b", selected.id);
    if (selected?.type === "barrio") u.searchParams.set("barrio", selected.id);
    if (circle) { u.searchParams.set("circle", params.get("circle")); if (circle.label) u.searchParams.set("label", circle.label); }
    return u.toString();
  }
  map.on("moveend", () => { const b = document.querySelector("#map-share .share-btn"); if (b) b.dataset.shareUrl = viewUrl(); });
  // "Something wrong?": open the contact form with the current view (and selected building) attached
  document.getElementById("map-report").addEventListener("click", (e) => {
    e.preventDefault();
    TL.track("map_report", { area: focus?.slug || "spain" });
    location.href = `/contacto?${new URLSearchParams({ tipo: "correccion", ref: viewUrl() })}`;
  });
  document.addEventListener("click", (e) => {   // keep the view link current at the moment of sharing
    const b = e.target.closest("#map-share .share-btn");
    if (b) b.dataset.shareUrl = viewUrl();
  }, true);

  // ---------------------------------------------------------------- ?circle=<lat>,<lon>,<radius m>[&label=]: an outline to point at
  function parseCircle() {
    const [la, lo, r] = (params.get("circle") || "").split(",").map(Number);
    if (!(la > 27 && la < 44.5 && lo > -19 && lo < 5 && r >= 20 && r <= 50000)) return null;
    const ring = [];
    for (let i = 0; i <= 96; i++) {
      const a = 2 * Math.PI * i / 96;
      ring.push([lo + r * Math.sin(a) / (111320 * Math.cos(la * Math.PI / 180)), la + r * Math.cos(a) / 110574]);
    }
    const label = (params.get("label") || "").trim().slice(0, 80);
    return { lat: la, lon: lo, r, label, ring, bounds: [[Math.min(...ring.map((p) => p[0])), Math.min(...ring.map((p) => p[1]))], [Math.max(...ring.map((p) => p[0])), Math.max(...ring.map((p) => p[1]))]] };
  }

  // ---------------------------------------------------------------- whole-city circles, for the area layers when zoomed out
  function bubbles() {
    if (!A) return;
    const z = map.getZoom(), lang = TL.lang() === "es" ? "es-ES" : "en-GB";
    const prop = view === "share" ? (measure === "share" ? "share" : null) : view === "problems" || view === "barrios" ? "pct" : null;
    DATA.bub = !prop ? [] : areasInView().filter((a) => z < zt(a) && (prop === "share" ? hasShare(a) && a.kind !== "province" && a.vut_share != null : a.has_listings && a.listings))
      .map((a) => {
        const v = prop === "share" ? a.vut_share : 100 * a.not_valid / a.listings;
        const cols = prop === "share" ? SHARE : RAMP, stops = prop === "share" ? SHARE_STOPS : PCT_STOPS;
        const k = stops.filter((s) => v >= s).length;
        return { type: "Feature", properties: { slug: a.slug, color: cols[k], tc: k >= 3 ? "#ffffff" : "#142036",
          label: `${v.toLocaleString(lang, { maximumFractionDigits: prop === "share" ? 1 : 0 })}${TL.lang() === "es" ? " %" : "%"}`,
          name: name(a.name).replace(/ \((ciudad|city)\)$/, "") }, geometry: { type: "Point", coordinates: a.center } };
      });
    touch("bub");
  }

  // ---------------------------------------------------------------- layers
  const VIEWS = { licences: ["dens0", "dens1", "dens2", "dens3", "bld", "sel-halo", "sel"], share: ["share", "bld", "bub", "bub-t", "bub-n", "sel-halo", "sel"],
    problems: ["prob", "dots", "bub", "bub-t", "bub-n", "sel-halo", "sel"], barrios: ["bar-fill", "bar-line", "bub", "bub-t", "bub-n", "sel-halo", "sel"] };
  function addLayers() {
    const fc = (s) => ({ type: "FeatureCollection", features: DATA[s] });
    for (const s of ["h0", "h1", "h2", "h3", "ahex", "dots", "bub"]) map.addSource(s, { type: "geojson", data: fc(s) });
    map.addSource("buildings", { type: "geojson", data: fc("buildings") });
    map.addSource("barrios", { type: "geojson", data: fc("barrios"), promoteId: "uid" });
    map.addSource("sel", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    const step = (prop, colors, stops) => ["step", ["get", prop], colors[0], ...stops.flatMap((s, i) => [s, colors[i + 1]])];
    const zi = (...stops) => ["interpolate", ["linear"], ["zoom"], ...stops];
    // registered flats, four hexagon sizes crossfading into each other
    const op = [zi(BAND[0] - FADE, 0.75, BAND[0] + FADE, 0),
      zi(BAND[0] - FADE, 0, BAND[0] + FADE, 0.75, BAND[1] - FADE, 0.75, BAND[1] + FADE, 0),
      zi(BAND[1] - FADE, 0, BAND[1] + FADE, 0.75, BAND[2] - FADE, 0.75, BAND[2] + FADE, 0),
      zi(BAND[2] - FADE, 0, BAND[2] + FADE, 0.75, BMIN, 0.75, BMIN + 3, 0.18)];
    M.levels.forEach((lv, k) => map.addLayer({ id: `dens${k}`, type: "fill", source: `h${k}`,
      ...(k ? { minzoom: BAND[k - 1] - FADE } : {}), ...(k < 3 ? { maxzoom: BAND[k] + FADE } : {}),
      paint: { "fill-color": step("n", DENS, lv.stops), "fill-opacity": op[k] } }));
    map.addLayer({ id: "share", type: "fill", source: "ahex", filter: ["has", "share"],
      paint: { "fill-color": step("share", SHARE, SHARE_STOPS), "fill-opacity": zi(BMIN - 0.3, 0.78, BMIN + 3.7, 0.35), "fill-outline-color": "rgba(255,255,255,.5)" } });
    map.addLayer({ id: "prob", type: "fill", source: "ahex", filter: ["has", "pct"],
      paint: { "fill-color": step("pct", RAMP, PCT_STOPS), "fill-opacity": zi(14, 0.75, 16, 0.22), "fill-outline-color": "rgba(255,255,255,.6)" } });
    map.addLayer({ id: "bar-fill", type: "fill", source: "barrios",
      paint: { "fill-color": ["case", ["has", "not_valid_pct"], step("not_valid_pct", RAMP, [15, 25, 35, 45]), "rgba(0,0,0,0)"],
        "fill-opacity": ["case", ["boolean", ["feature-state", "sel"], false], 0.9, 0.62] } });
    map.addLayer({ id: "bar-line", type: "line", source: "barrios",
      paint: { "line-color": "#3b4558", "line-width": ["case", ["boolean", ["feature-state", "sel"], false], 2.5, 0.5], "line-opacity": 0.55 } });
    map.addLayer({ id: "bld", type: "circle", source: "buildings", minzoom: BMIN,
      paint: {
        "circle-radius": zi(BMIN, ["min", ["+", 1.4, ["*", 0.5, ["sqrt", ["get", "n"]]]], 5],
          15, ["min", ["+", 3, ["sqrt", ["get", "n"]]], 12],
          17.5, ["min", ["+", 5, ["*", 2, ["sqrt", ["get", "n"]]]], 26]),
        "circle-color": ["case", [">", ["get", "vut"], 0], BLD, OTHER],
        "circle-opacity": zi(BMIN, 0.55, 15, 0.85),
        "circle-stroke-color": "#ffffff", "circle-stroke-width": zi(BMIN, 0.4, 16, 1.5) } });
    // Dot density: one dot per listing at a random spot inside its hexagon (not where the listing is). Zoomed in only.
    map.addLayer({ id: "dots", type: "circle", source: "dots", minzoom: 14,
      paint: { "circle-radius": zi(14, 1.8, 17, 4),
        "circle-color": ["match", ["get", "v"], 0, "#b3261e", 1, "#2e7d5b", "#9aa3b0"],
        "circle-opacity": zi(14, 0, 14.6, 0.9),
        "circle-stroke-color": "#ffffff", "circle-stroke-width": zi(14, 0, 16, 0.8) } });
    map.addLayer({ id: "bub", type: "circle", source: "bub",
      paint: { "circle-radius": zi(4, 13, 9, 19), "circle-color": ["get", "color"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 2, "circle-opacity": 0.95 } });
    map.addLayer({ id: "bub-t", type: "symbol", source: "bub",
      layout: { "text-field": ["get", "label"], "text-font": ["Noto Sans Bold"], "text-size": 11, "text-allow-overlap": true, "text-ignore-placement": true },
      paint: { "text-color": ["get", "tc"] } });
    map.addLayer({ id: "bub-n", type: "symbol", source: "bub",
      layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": 11.5, "text-offset": [0, 2.1], "text-anchor": "top", "text-optional": true },
      paint: { "text-color": "#142036", "text-halo-color": "#ffffff", "text-halo-width": 1.6 } });
    if (circle) {
      map.addSource("circle", { type: "geojson", data: { type: "FeatureCollection", features: [
        { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [circle.ring] } },
        { type: "Feature", properties: { label: circle.label }, geometry: { type: "Point", coordinates: circle.ring[0] } }] } });
      map.addLayer({ id: "circ-fill", type: "fill", source: "circle", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "#142036", "fill-opacity": 0.05 } });
      map.addLayer({ id: "circ-line", type: "line", source: "circle", filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "line-color": "#142036", "line-width": 2.5, "line-dasharray": [2, 1.4], "line-opacity": 0.85 } });
      if (circle.label) map.addLayer({ id: "circ-t", type: "symbol", source: "circle", filter: ["==", ["geometry-type"], "Point"],
        layout: { "text-field": ["get", "label"], "text-font": ["Noto Sans Bold"], "text-size": 13, "text-anchor": "bottom", "text-offset": [0, -0.5], "text-allow-overlap": true },
        paint: { "text-color": "#142036", "text-halo-color": "#ffffff", "text-halo-width": 2 } });
    }
    map.addLayer({ id: "sel-halo", type: "circle", source: "sel", paint: { "circle-radius": 18, "circle-color": "#e2b54a", "circle-opacity": 0.28 } });
    map.addLayer({ id: "sel", type: "circle", source: "sel", paint: { "circle-radius": 7, "circle-color": "#e2b54a", "circle-stroke-color": "#142036", "circle-stroke-width": 2.5 } });
    layersReady = true;   // (the sources above already hold whatever arrived while the style loaded)
    shareFilter();

    map.on("click", "share", (e) => {
      if (view !== "share" || map.queryRenderedFeatures(e.point, { layers: ["bld"] }).length) return;
      const p = e.features[0].properties;
      new maplibregl.Popup({ closeButton: false, maxWidth: "260px" }).setLngLat(e.lngLat)
        .setHTML(`<b>${pc(p.share)}</b> ${L("registradas", "registered")}${p.ashare != null ? ` · <b>${pc(p.ashare)}</b> ${L("en Airbnb", "on Airbnb")}` : ""}<br>${fmt(p.reg)} ${L("turísticas registradas de", "registered tourist flats of")} ${fmt(p.homes)} ${L("viviendas", "homes")}`).addTo(map);
    });
    map.on("click", "bld", (e) => select(B[e.features[0].id][6], false));
    map.on("click", "prob", (e) => { if (view === "problems") hexDetail(e.features[0].properties, e.lngLat); });
    map.on("click", "bar-fill", (e) => { if (view === "barrios") barrioDetail(e.features[0].properties); });
    map.on("click", "bub", (e) => { const a = AREA[e.features[0].properties.slug]; if (a) goTo(a.slug); });
    // Building dots are hard to hit at low zoom: also pick the nearest dot within 14 px.
    map.on("click", (e) => {
      if ((view !== "licences" && view !== "share") || map.getZoom() < BMIN) return;
      if (map.queryRenderedFeatures(e.point, { layers: ["bld"] }).length) return;
      const near = map.queryRenderedFeatures([[e.point.x - 14, e.point.y - 14], [e.point.x + 14, e.point.y + 14]], { layers: ["bld"] });
      if (near.length) select(B[near[0].id][6], false);
    });
    const hover = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, maxWidth: "280px" });
    for (const l of ["bld", "prob", "bar-fill", "share", "bub"]) {
      map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; hover.remove(); });
    }
    map.on("mousemove", "bld", (e) => {
      if (isMobile()) return;
      const r = B[e.features[0].id];
      hover.setLngLat([r[1], r[0]]).setHTML(`<b>${esc(r[2] || "—")}</b><br>${r[3] ? TL.plural(r[3], "flat_1", "flats_n") : TL.plural(r[5], "other_1", "other_n")}`).addTo(map);
    });
    showLayers(view);
    refresh();
    if (pendingB && byId.has(pendingB)) { select(pendingB, true); pendingB = null; }
    const br = +params.get("barrio");
    if (br && AREA[first]?.has_barrios) loadBarrios(first).then(() => showBarrio(first, br));
  }

  /** Province hexagons inside a city whose own, finer hexagons are loaded give way to those. */
  function shareFilter() {
    if (!layersReady) return;
    map.setFilter("share", ["all", ["has", measure], ["!", ["in", ["coalesce", ["get", "o"], ""], ["literal", [...themeOn]]]]]);
  }
  function wireMeasure() {
    document.querySelectorAll("#legend [data-m]").forEach((b) => (b.onclick = () => {
      measure = b.dataset.m;
      TL.track("map_layer", { layer: `share_${measure}`, area: focus?.slug || "spain" });
      if (layersReady) map.setPaintProperty("share", "fill-color", ["step", ["get", measure], SHARE[0], ...SHARE_STOPS.flatMap((x, i) => [x, SHARE[i + 1]])]);
      shareFilter();
      bubbles();
      chrome(true);
    }));
  }
  function showLayers(v) {
    view = v;
    if (!layersReady) return;
    for (const ls of Object.values(VIEWS)) for (const l of ls) if (map.getLayer(l)) map.setLayoutProperty(l, "visibility", "none");
    for (const l of VIEWS[v]) if (map.getLayer(l)) map.setLayoutProperty(l, "visibility", "visible");
  }
  function setView(v) {
    if (v !== view) TL.track("map_layer", { layer: v, area: focus?.slug || "spain" });
    showLayers(v);
    refresh();   // the new layer's data for what's on screen, its circles, the buttons and legend
    if (v === "barrios" && !selected && !isMobile()) barrioList();
  }

  // ---------------------------------------------------------------- selection: building
  let reqId = 0;
  function select(id, fly) {
    const i = byId.get(id);
    if (i == null) return;
    const r = B[i];
    selected = { type: "building", id };
    if (view !== "licences" && view !== "share") setView("licences");
    map.getSource("sel").setData({ type: "Feature", geometry: { type: "Point", coordinates: [r[1], r[0]] } });
    const u = new URL(location.href);
    u.searchParams.set("b", id); u.searchParams.set("lat", r[0]); u.searchParams.set("lon", r[1]); u.searchParams.delete("z");
    history.replaceState(null, "", u);
    if (fly) map.flyTo({ center: [r[1], r[0]], zoom: Math.max(map.getZoom(), 17), speed: 1.6, padding: padding() });
    else if (isMobile()) map.easeTo({ center: [r[1], r[0]], padding: padding(), duration: 300 });
    const own = M.areas[ownerAt(r[0], r[1])] || M.areas[focus?.slug], reg = own?.register || { es: "Registro de Turismo de Andalucía", en: "Andalusian Tourism Register" };
    const where = focus?.slug || "mapa";
    const head = `<div class="detail">
        <div class="eyebrow"><span>${t("building_label")}</span><button class="x" type="button" data-close aria-label="Cerrar">${ICON.close}</button></div>
        <h2>${esc(r[2] || "—")}</h2>
        <div class="figs">
          ${r[3] ? `<div><b>${fmt(r[3])}</b><span>${L("viviendas turísticas", "tourist flats")}</span></div><div><b>${fmt(r[4])}</b><span>${L("plazas", "guest places")}</span></div>` : ""}
          ${r[5] ? `<div><b>${fmt(r[5])}</b><span>${L("otros alojamientos", "other establishments")}</span></div>` : ""}
          ${r[7] ? `<div><b>${fmt(r[7])}</b><span>${L("viviendas en el edificio", "homes in the building")}</span></div>` : ""}
        </div>
        ${r[7] && r[3] ? `<p class="sub" style="margin-top:10px">${L(`<b>${fmt(r[3])} de ${fmt(r[7])}</b> viviendas del edificio (${Math.round(100 * Math.min(1, r[3] / r[7]))}%) están registradas como turísticas.`,
          `<b>${fmt(r[3])} of ${fmt(r[7])}</b> homes in the building (${Math.round(100 * Math.min(1, r[3] / r[7]))}%) are registered as tourist flats.`)}
          <span class="tiny muted">${L("Viviendas según el Catastro; indicativo.", "Homes per the Catastro; indicative.")}</span></p>` : ""}
        <div class="point-share">${TL.shareButton({ url: `https://tienelicencia.com${where === "mapa" ? "/mapa" : areaHref(where, "mapa")}?b=${encodeURIComponent(id)}&lat=${r[0]}&lon=${r[1]}`,
          text: L(`${r[2] || "Edificio"}: ${r[3]} viviendas turísticas registradas${r[7] ? ` de ${r[7]} viviendas` : ""}`, `${r[2] || "Building"}: ${r[3]} registered tourist flats${r[7] ? ` out of ${r[7]} homes` : ""}`) + " · tienelicencia.com",
          content: "map_building" })}</div>
        <div id="flats"><p class="small muted" style="margin-top:12px">${t("loading")}</p></div></div>`;
    $("#p-detail").innerHTML = head;
    sheet(true, "detail");
    const my = ++reqId;
    TL.api("building", { id }).then((d) => {
      TL.track("map_select", { select_type: "building", area: focus?.slug || "spain", town: d.muni || "", place: barrioAt(r[0], r[1]) || d.muni || "" });
      if (my !== reqId) return;
      $("#p-detail h2").innerHTML = `${esc(d.addresses.slice(0, 3).join(" · "))}${d.addresses.length > 3 ? ` <span class="muted">+${d.addresses.length - 3}</span>` : ""}`;
      $("#p-detail .figs").insertAdjacentHTML("afterend", `<p class="sub" style="margin-top:10px">${esc([d.postcode, d.muni].filter(Boolean).join(" "))}</p>`);
      $("#flats").innerHTML = TL.flatsTable(d.flats, { limit: 10 }) +
        `<p class="note info small">${L(`Datos del ${esc(reg.es)}. Una vivienda registrada puede no estar anunciándose; una anunciada sin registro no aparece aquí.`,
          `From the ${esc(reg.en)}. A registered flat may not be advertised; an unregistered one being advertised won't appear here.`)}</p>`;
    }).catch(() => { if (my === reqId) $("#flats").innerHTML = `<p class="small muted">${t("search_error")}</p>`; });
  }
  function reselect() { if (selected?.type === "building") select(selected.id, false); }

  // Barrio at a point (cities with barrios loaded), for analytics: we record the barrio, never the building.
  function barrioAt(lat, lon) {
    const inRing = (ring) => {
      let inside = false;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
      }
      return inside;
    };
    for (const f of DATA.barrios) {
      const g = f.geometry, polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
      if (polys.some((p) => inRing(p[0]))) return f.properties.name;
    }
    return null;
  }

  // ---------------------------------------------------------------- selection: hex / barrio
  function hexDetail(p, lngLat) {
    selected = { type: "hex" };
    TL.track("map_select", { select_type: "area_hex", area: p.a, place: barrioAt(lngLat.lat, lngLat.lng) || "" });
    map.getSource("sel").setData({ type: "Feature", geometry: { type: "Point", coordinates: [lngLat.lng, lngLat.lat] } });
    $("#p-detail").innerHTML = `<div class="detail"><div class="eyebrow"><span>${L("Zona de ~150 m", "~150 m area")}</span><button class="x" type="button" data-close aria-label="Cerrar">${ICON.close}</button></div>
      <h2>${p.pct}% ${L("sin número válido", "without a valid number")}</h2>
      <p class="sub">${L(`${fmt(p.nv)} de ${fmt(p.n)} anuncios de Airbnb en esta zona no muestran un número válido del registro.`, `${fmt(p.nv)} of ${fmt(p.n)} Airbnb listings in this area don't display a valid register number.`)}</p>
      <div class="figs"><div><b>${fmt(p.n)}</b><span>${L("anuncios", "listings")}</span></div><div><b>${fmt(p.reg)}</b><span>${L("viviendas registradas", "registered flats")}</span></div></div>
      <p class="note small">${L("Mostramos zonas, nunca anuncios concretos. Las ubicaciones de Airbnb son aproximadas.", "We show areas, never individual listings. Airbnb locations are approximate.")}</p></div>`;
    sheet(true, "detail");
  }
  function barrioDetail(p) {
    if (selected?.type === "barrio") map.setFeatureState({ source: "barrios", id: selected.uid }, { sel: false });
    const a = AREA[p.area];
    selected = { type: "barrio", id: p.id, uid: p.uid, area: p.area };
    map.setFeatureState({ source: "barrios", id: p.uid }, { sel: true });
    map.getSource("sel").setData({ type: "FeatureCollection", features: [] });
    const has = p.not_valid_pct != null, an = name(a.name).replace(/ \(.*\)/, "");
    TL.track("map_select", { select_type: "barrio", area: p.area, place: p.name });
    $("#p-detail").innerHTML = `<div class="detail"><div class="eyebrow"><span>${SUB(a).one}</span><button class="x" type="button" data-close aria-label="Cerrar">${ICON.close}</button></div>
      <h2>${esc(p.name)}</h2>
      <div class="point-share" style="margin:4px 0 10px">${TL.shareButton({ url: `https://tienelicencia.com/${p.area}/mapa?barrio=${p.id}`,
        text: L(`${p.name} (${an}): ${p.vut_share != null ? `el ${pc(p.vut_share)} de las viviendas son turísticas registradas` : `${p.vut} viviendas turísticas registradas`}`,
          `${p.name} (${an}): ${p.vut_share != null ? `${pc(p.vut_share)} of homes are registered tourist flats` : `${p.vut} registered tourist flats`}`) + " · tienelicencia.com",
        content: "map_barrio" })}</div>
      ${p.vut_share != null ? `<p class="sub">${L(`<b>${pc(p.vut_share)}</b> de las viviendas ${SUB(a).the} son turísticas registradas (${fmt(p.vut)} de ${fmt(p.homes)}; indicativo)${a.cap && p.vut_share > a.cap ? `, por encima del límite del ${a.cap}&nbsp;% que usa el Ayuntamiento` : ""}.`,
        `<b>${pc(p.vut_share)}</b> of homes ${SUB(a).the} are registered tourist flats (${fmt(p.vut)} of ${fmt(p.homes)}; indicative)${a.cap && p.vut_share > a.cap ? `, above the ${a.cap}% limit the council uses` : ""}.`)}</p>` : ""}
      <div class="figs"><div><b>${fmt(p.vut)}</b><span>${L("viviendas registradas", "registered flats")}</span></div><div><b>${fmt(p.listings)}</b><span>${L("anuncios", "listings")}</span></div>
        ${has ? `<div><b style="color:var(--bad)">${Math.round(p.not_valid_pct)}%</b><span>${L("sin número válido", "no valid number")}</span></div>` : ""}</div>
      ${has ? `<table class="flats"><tbody>
        <tr><td>${L("No muestran número", "No number shown")}</td><td class="n">${fmt(p.no_number)} <span class="muted">(${Math.round(100 * p.no_number / p.listings)}%)</span></td></tr>
        <tr><td>${L("Número erróneo o inexistente", "Wrong or non-existent number")}</td><td class="n">${fmt(p.bad_number)} <span class="muted">(${Math.round(100 * p.bad_number / p.listings)}%)</span></td></tr>
        <tr><td>${L("Licencia compartida en varios anuncios", "Licence shared across listings")}</td><td class="n">${fmt(p.shared)}</td></tr>
        <tr><td>${L("Posiblemente exentos", "Possibly exempt")}</td><td class="n">${fmt(p.exempt)}</td></tr></tbody></table>`
        : `<p class="small muted">${L("Muy pocos anuncios para dar un porcentaje fiable.", "Too few listings for a reliable percentage.")}</p>`}
      ${p.rent1 != null ? `<p class="sub" style="margin-top:12px">${L(`Alquiler mediano: <b>${p.rent1.toLocaleString("es-ES", { minimumFractionDigits: 2 })} €/m²</b> (+${Math.round(p.rent_growth)}% desde 2015; indicativo).`,
        `Median rent: <b>€${p.rent1.toLocaleString("en-GB", { minimumFractionDigits: 2 })}/m²</b> (+${Math.round(p.rent_growth)}% since 2015; indicative).`)}</p>` : ""}</div>`;
    sheet(true, "detail");
  }
  function fitFeature(f, pad) {
    const pts = f.geometry.coordinates.flat(2), lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: pad, maxZoom: 16 });
  }
  function showBarrio(s, id) {
    const f = DATA.barrios.find((x) => x.properties.area === s && x.properties.id === id);
    if (!f) return;
    if (view !== "barrios") setView("barrios");
    fitFeature(f, isMobile() ? { top: 60, bottom: innerHeight * 0.62, left: 20, right: 20 } : 40);
    barrioDetail(f.properties);
  }
  function barrioList() {
    if (!focus?.has_barrios || !barOn.has(focus.slug)) return;
    const s = focus.slug, feats = DATA.barrios.filter((f) => f.properties.area === s);
    const top = feats.map((f) => f.properties).filter((p) => p.not_valid_pct != null).sort((a, b) => b.listings - a.listings).slice(0, 10);
    $("#p-detail").innerHTML = `<div class="detail"><div class="legend-title">${focus.subareas === "municipality" ? L("Municipios con más anuncios", "Municipalities with most listings") : L("Barrios con más anuncios", "Barrios with most listings")}</div>
      <table class="flats"><thead><tr><th>${SUB().one}</th><th class="n">${L("Anuncios", "Listings")}</th><th class="n">${L("Sin nº", "No no.")}</th></tr></thead><tbody>
      ${top.map((p) => `<tr><td><a href="#" data-bar="${p.id}">${esc(p.name)}</a></td><td class="n">${fmt(p.listings)}</td><td class="n">${Math.round(p.not_valid_pct)}%</td></tr>`).join("")}</tbody></table></div>`;
    document.querySelectorAll("[data-bar]").forEach((a) => (a.onclick = (e) => {
      e.preventDefault();
      const f = feats.find((x) => x.properties.id === +a.dataset.bar);
      fitFeature(f, 40);
      barrioDetail(f.properties);
    }));
  }

  function clearSelection() {
    if (selected?.type === "barrio") map.setFeatureState({ source: "barrios", id: selected.uid }, { sel: false });
    selected = null;
    map.getSource("sel")?.setData({ type: "FeatureCollection", features: [] });
    const u = new URL(location.href);
    for (const k of ["b", "lat", "lon", "z", "barrio"]) u.searchParams.delete(k);
    history.replaceState(null, "", u);
    chrome(true);
    sheet(false);
  }
  document.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) clearSelection(); });

  // ---------------------------------------------------------------- mobile bottom sheet
  const sh = $("#sheet");
  function padding() { return isMobile() ? { top: 50, bottom: Math.round(innerHeight * 0.62), left: 0, right: 0 } : { top: 40, bottom: 40, left: 40, right: 40 }; }
  function sheet(open, mode) {
    if (!isMobile()) return;
    if (mode) sh.dataset.mode = mode;
    sh.classList.toggle("open", open);
    document.body.classList.toggle("sheet-open", open);
    if (open) sh.querySelector(".sheet-body").scrollTop = 0;
  }
  $("#search-fab").addEventListener("click", () => { sheet(true, "search"); setTimeout(() => search?.input.focus(), 280); });
  $("#sheet-close").addEventListener("click", () => { if (sh.dataset.mode === "detail") clearSelection(); else sheet(false); });
  let y0 = null;
  sh.querySelector(".sheet-head").addEventListener("pointerdown", (e) => { y0 = e.clientY; sh.classList.add("dragging"); sh.setPointerCapture?.(e.pointerId); });
  sh.addEventListener("pointermove", (e) => { if (y0 != null) sh.style.transform = `translateY(${Math.max(0, e.clientY - y0)}px)`; });
  const end = (e) => {
    if (y0 == null) return;
    const dy = e.clientY - y0;
    y0 = null; sh.classList.remove("dragging"); sh.style.transform = "";
    if (dy > 70) { if (sh.dataset.mode === "detail") clearSelection(); else sheet(false); }
  };
  sh.addEventListener("pointerup", end);
  sh.addEventListener("pointercancel", end);
  addEventListener("keydown", (e) => { if (e.key === "Escape" && selected) clearSelection(); });
})();
