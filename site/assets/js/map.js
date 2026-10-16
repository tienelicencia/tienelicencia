/* Map: licensed buildings (+ problem hexes and barrios where we have Airbnb data). Data: /data/<slug>/*
   Clicking a building lists every registered flat in it (/api/building). Deep link: /<slug>/mapa?b=<building id>. */
(() => {
  const { t, fmt, esc, name, getJSON, areaHref, ICON } = TL;
  const slug = TL.currentArea();
  TL.init({ page: "map" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const $ = (s) => document.querySelector(s);
  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => TL.setLang(b.dataset.l)));
  TL.applyStatic();

  const DENS = ["#dcefe5", "#a9d7bf", "#6dbb95", "#2c956b", "#0b6a4e"];
  const RAMP = ["#fde7d6", "#f7b98e", "#ec8452", "#cf4a2c", "#9a2318"];
  const SHARE = ["#eceffb", "#c3caf0", "#8b97df", "#4f5fc4", "#26318f"];   // % of homes (indicative)
  const SHARE_STOPS = [2, 5, 8, 15];
  let measure = "share";   // share layer: "share" = registered, "ashare" = Airbnb entire-home listings (Málaga)
  const BLD = "#11805d", OTHER = "#2f62b5";
  const pc = (x) => `${Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 })}${TL.lang() === "es" ? "\u00a0%" : "%"}`;
  const isMobile = () => matchMedia("(max-width: 760px)").matches;
  const params = new URLSearchParams(location.search);

  let A, area, barData = null, B = [], byId = new Map(), view = params.get("capa") || "licences", selected = null, densStops = [3, 10, 25, 50];
  const map = new maplibregl.Map({ container: "map", style: "https://tiles.openfreemap.org/styles/positron",
    center: [-4.6, 36.68], zoom: 9, minZoom: 7, maxZoom: 19, attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "top-right");
  // Our layers only need the style to be parsed, not every basemap tile and glyph ("load"/"idle"),
  // so wait for "style.load" and fetch our data in parallel with it.
  const styleReady = new Promise((r) => map.once("style.load", r));
  const dataReady = slug ? Promise.all([getJSON(`/data/${slug}/buildings.json`), getJSON(`/data/${slug}/hex.geojson`)]) : null;
  dataReady?.catch(() => {});   // unknown slug: we redirect below instead
  const loaded = () => $("#map-loading").classList.add("done");

  getJSON("/data/areas.json").then(async (AA) => {
    A = AA;
    area = A.areas.find((a) => a.slug === slug);
    if (!area) { location.replace("/"); return; }
    if (!area.has_listings) view = "licences";
    const pl = +params.get("lat"), pn = +params.get("lon"), pz = +params.get("z");
    map.jumpTo(pl && pn ? { center: [pn, pl], zoom: pz || 15 } : { center: area.center, zoom: isMobile() ? area.zoom - 0.6 : area.zoom });
    const [[bld, hex], bar] = await Promise.all([dataReady, area.has_barrios ? getJSON(`/data/${slug}/barrios.geojson`) : null]);
    B = bld.rows;
    B.forEach((r, i) => byId.set(r[8], i));
    const regs = hex.features.map((f) => f.properties.reg).filter(Boolean).sort((a, b) => a - b);
    const qv = (f) => regs[Math.min(regs.length - 1, Math.floor(f * regs.length))];
    densStops = [...new Set([qv(.5), qv(.75), qv(.9), qv(.97)].map((x) => Math.max(2, x)))];
    while (densStops.length < 4) densStops.push(densStops[densStops.length - 1] + 1);
    chrome();
    TL.onLang(() => { chrome(); if (selected) reselect(); });
    await styleReady;
    addLayers(bld, hex, bar);
    map.once("render", loaded);   // first frame with our layers drawn
  });
  map.once("idle", loaded);   // fallback, e.g. if our data failed to load

  // ---------------------------------------------------------------- chrome (title, switcher, layers, legend, search)
  let search;
  function chrome() {
    document.title = `${L("Mapa", "Map")} · ${name(area.name)} | tienelicencia.com`;
    $("#map-title").innerHTML = `${esc(name(area.name))}<small>${L("Viviendas turísticas registradas", "Registered tourist flats")}</small>`;
    $("#back").href = areaHref(slug);
    $("#area-switch").innerHTML = A.areas.map((a) => `<option value="${a.slug}" ${a.slug === slug ? "selected" : ""}>${esc(name(a.name))}</option>`).join("");
    $("#area-switch").onchange = (e) => (location.href = areaHref(e.target.value, "mapa"));
    $("#map-share").innerHTML = TL.shareButton({ url: viewUrl(), text: L(`Mapa de viviendas turísticas · ${name(area.name)}`, `Tourist-flat map · ${name(area.name)}`) + " · tienelicencia.com", content: "map_view" });
    const btn = (v, es, en) => `<button type="button" data-v="${v}" aria-pressed="${view === v}">${L(es, en)}</button>`;
    $("#layers").innerHTML = `<div class="seg" role="group">${btn("licences", "Licencias", "Licences")}${area.homes && !area.census ? btn("share", "% viviendas", "% homes") : ""}
        ${area.has_listings ? btn("problems", "Sin nº", "No number") + btn("barrios", "Barrios", "Barrios") : ""}</div>
        <p class="layer-help">${help()}</p>`;
    document.querySelectorAll("#layers [data-v]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.v)));
    $("#legend").innerHTML = `<button class="legend-btn" type="button"><i></i>${L("Leyenda", "Legend")}</button><div class="legend-body">${legend()}</div>`;
    $("#legend .legend-btn").onclick = () => $("#legend").classList.toggle("open");
    wireMeasure();
    if (!search) {
      search = TL.searchWidget($("#p-search"), { area: slug, compact: true, onBarrio: (id, muni) => { if (TL.areaOfMuni(muni) !== slug) return false; showBarrio(id); return true; }, onShowOnMap: (r) => {
        if (!byId.has(r.building)) return false;      // outside this area: follow the link to the right map
        select(r.building, true);
        return true;
      } });
    }
    if (!selected) $("#p-detail").innerHTML = `<div class="detail-empty">${ICON.info}<span>${L(
      "Pulsa un edificio del mapa para ver sus viviendas turísticas registradas, o busca una dirección o un número de licencia.",
      "Tap a building on the map to see its registered tourist flats, or search for an address or licence number.")}</span></div>`;
  }
  function help() {
    return {
      licences: area.kind === "region"
        ? L("El sombreado indica cuántas viviendas turísticas registradas hay en cada zona. Para verlas edificio a edificio, abre el mapa de una ciudad o de la provincia de Málaga.",
          "Shading shows how many registered tourist flats there are in each area. To see them building by building, open a city map or the Málaga province map.")
        : L("Cada punto es un edificio con viviendas turísticas registradas. El sombreado indica cuántas hay en cada zona.",
          "Each dot is a building with registered tourist flats. Shading shows how many there are in each area."),
      share: L("Viviendas turísticas registradas como porcentaje de todas las viviendas de cada zona (Catastro). Dato indicativo.",
        "Registered tourist flats as a share of all homes in each area (Catastro). Indicative."),
      problems: L(`Porcentaje de anuncios de Airbnb que no muestran un número válido, por zona. Solo zonas con ${5} anuncios o más; nunca anuncios individuales.`,
        "Share of Airbnb listings not showing a valid number, by area. Only areas with 5+ listings; never individual listings."),
      barrios: L("Porcentaje de anuncios sin número válido por barrio oficial. Pulsa un barrio para ver sus datos.",
        "Share of listings without a valid number by official barrio. Tap a barrio for its figures."),
    }[view];
  }
  function legend() {
    const ramp = (cols, labels) => `<div class="ramp">${cols.map((c) => `<span style="background:${c}"></span>`).join("")}</div>
      <div class="ramp-labels">${labels.map((l) => `<span>${l}</span>`).join("")}</div>`;
    const across = Math.round(area.hex_m * Math.sqrt(3) / 10) * 10;
    if (view === "licences") return `<div class="legend-title">${L(`Viviendas por zona de ~${fmt(across)} m`, `Flats per ~${fmt(across)} m area`)}</div>
      ${ramp(DENS, ["1", ...densStops.map(fmt).slice(0, 3), `${fmt(densStops[3])}+`])}
      <div class="legend-row"><span class="sw" style="background:${BLD}"></span>${L("Edificio con viviendas turísticas (tamaño = número)", "Building with tourist flats (size = number)")}</div>
      <div class="legend-row"><span class="sw" style="background:${OTHER}"></span>${L("Hotel, apartamento turístico u otro alojamiento", "Hotel, tourist apartment or other establishment")}</div>`;
    if (view === "share") return `${area.has_listings ? `<div class="seg mini" role="group" style="margin-bottom:10px">
        <button type="button" data-m="share" aria-pressed="${measure === "share"}">${L("Registradas", "Registered")}</button>
        <button type="button" data-m="ashare" aria-pressed="${measure === "ashare"}">${L("Anunciadas en Airbnb", "On Airbnb")}</button></div>` : ""}
      <div class="legend-title">${measure === "share" ? L("% de viviendas que son turísticas registradas", "% of homes that are registered tourist flats")
        : L("Anuncios de vivienda completa en Airbnb, % de viviendas", "Entire-home Airbnb listings, % of homes")}</div>
      ${ramp(SHARE, ["0", "2%", "5%", "8%", "15%+"])}<p class="tiny muted" style="margin:6px 0 0">${L(`Indicativo · zonas de ~${fmt(across)} m con al menos 30 viviendas`, `Indicative · ~${fmt(across)} m areas with at least 30 homes`)}</p>`;
    if (view === "problems") return `<div class="legend-title">${L("Anuncios sin número válido", "Listings without a valid number")}</div>${ramp(RAMP, ["0%", "15%", "30%", "45%", "60%+"])}`;
    return `<div class="legend-title">${L("Anuncios sin número válido, por barrio", "Listings without a valid number, by barrio")}</div>${ramp(RAMP, ["0%", "15%", "25%", "35%", "45%+"])}`;
  }

  /** Link to exactly what's on screen: position, zoom, layer, selection. */
  function viewUrl() {
    const c = map.getCenter(), u = new URL(`https://tienelicencia.com/${slug}/mapa`);
    u.searchParams.set("lat", c.lat.toFixed(5)); u.searchParams.set("lon", c.lng.toFixed(5)); u.searchParams.set("z", map.getZoom().toFixed(1));
    if (view !== "licences") u.searchParams.set("capa", view);
    if (selected?.type === "building") u.searchParams.set("b", selected.id);
    if (selected?.type === "barrio" && selBarrio != null) u.searchParams.set("barrio", selBarrio);
    return u.toString();
  }
  map.on("moveend", () => { const b = document.querySelector("#map-share .share-btn"); if (b) b.dataset.shareUrl = viewUrl(); });
  // "Something wrong?": open the contact form with the current view (and selected building) attached
  document.getElementById("map-report").addEventListener("click", (e) => {
    e.preventDefault();
    TL.track("map_report", { area: slug });
    location.href = `/contacto?${new URLSearchParams({ tipo: "correccion", ref: viewUrl() })}`;
  });
  document.addEventListener("click", (e) => {   // keep the view link current at the moment of sharing
    const b = e.target.closest("#map-share .share-btn");
    if (b) b.dataset.shareUrl = viewUrl();
  }, true);

  // ---------------------------------------------------------------- layers
  const VIEWS = { licences: ["dens", "bld", "sel-halo", "sel"], share: ["share", "bld", "sel-halo", "sel"], problems: ["prob", "sel-halo", "sel"], barrios: ["bar-fill", "bar-line", "sel-halo", "sel"] };
  function addLayers(bld, hex, bar) {
    const feats = B.map((r, i) => ({ type: "Feature", id: i, properties: { vut: r[3], other: r[5], n: r[3] + r[5] },
      geometry: { type: "Point", coordinates: [r[1], r[0]] } }));
    map.addSource("buildings", { type: "geojson", data: { type: "FeatureCollection", features: feats } });
    map.addSource("hex", { type: "geojson", data: hex });
    map.addSource("sel", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    const step = (prop, colors, stops) => ["step", ["get", prop], colors[0], ...stops.flatMap((s, i) => [s, colors[i + 1]])];
    const bmin = slug === "provincia" ? 11.5 : slug === "marbella" ? 12.3 : 13;
    map.addLayer({ id: "dens", type: "fill", source: "hex", filter: [">", ["get", "reg"], 0],
      paint: { "fill-color": step("reg", DENS, densStops), "fill-opacity": area.kind === "region" ? 0.75   // region map: density only, no building layer
        : ["interpolate", ["linear"], ["zoom"], bmin - 1, 0.75, bmin + 3, 0.18] } });
    map.addLayer({ id: "bld", type: "circle", source: "buildings", minzoom: bmin,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"],
          bmin, ["min", ["+", 1.4, ["*", 0.5, ["sqrt", ["get", "n"]]]], 5],
          15, ["min", ["+", 3, ["sqrt", ["get", "n"]]], 12],
          17.5, ["min", ["+", 5, ["*", 2, ["sqrt", ["get", "n"]]]], 26]],
        "circle-color": ["case", [">", ["get", "vut"], 0], BLD, OTHER],
        "circle-opacity": ["interpolate", ["linear"], ["zoom"], bmin, 0.55, 15, 0.85],
        "circle-stroke-color": "#ffffff", "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], bmin, 0.4, 16, 1.5] } });
    map.addLayer({ id: "share", type: "fill", source: "hex", filter: ["has", "share"],
      paint: { "fill-color": step("share", SHARE, SHARE_STOPS), "fill-opacity": ["interpolate", ["linear"], ["zoom"], bmin - 1, 0.78, bmin + 3, 0.35],
        "fill-outline-color": "rgba(255,255,255,.5)" } }, "bld");
    map.on("click", "share", (e) => {
      if (view !== "share" || map.queryRenderedFeatures(e.point, { layers: ["bld"] }).length) return;
      const p = e.features[0].properties;
      new maplibregl.Popup({ closeButton: false, maxWidth: "260px" }).setLngLat(e.lngLat)
        .setHTML(`<b>${pc(p.share)}</b> ${L("registradas", "registered")}${p.ashare != null ? ` · <b>${pc(p.ashare)}</b> ${L("en Airbnb", "on Airbnb")}` : ""}<br>${fmt(p.reg)} ${L("turísticas registradas de", "registered tourist flats of")} ${fmt(p.homes)} ${L("viviendas", "homes")}`).addTo(map);
    });
    if (area.has_listings) {
      map.addLayer({ id: "prob", type: "fill", source: "hex", filter: ["has", "pct"],
        paint: { "fill-color": step("pct", RAMP, [15, 30, 45, 60]), "fill-opacity": 0.75, "fill-outline-color": "rgba(255,255,255,.6)" } });
    }
    barData = bar;
    if (bar) {
      map.addSource("barrios", { type: "geojson", data: bar, promoteId: "id" });
      map.addLayer({ id: "bar-fill", type: "fill", source: "barrios",
        paint: { "fill-color": ["case", ["has", "not_valid_pct"], step("not_valid_pct", RAMP, [15, 25, 35, 45]), "rgba(0,0,0,0)"],
          "fill-opacity": ["case", ["boolean", ["feature-state", "sel"], false], 0.9, 0.62] } });
      map.addLayer({ id: "bar-line", type: "line", source: "barrios",
        paint: { "line-color": "#3b4558", "line-width": ["case", ["boolean", ["feature-state", "sel"], false], 2.5, 0.5], "line-opacity": 0.55 } });
    }
    map.addLayer({ id: "sel-halo", type: "circle", source: "sel", paint: { "circle-radius": 18, "circle-color": "#e2b54a", "circle-opacity": 0.28 } });
    map.addLayer({ id: "sel", type: "circle", source: "sel", paint: { "circle-radius": 7, "circle-color": "#e2b54a", "circle-stroke-color": "#142036", "circle-stroke-width": 2.5 } });

    map.on("click", "bld", (e) => select(B[e.features[0].id][8], false));
    map.on("mouseenter", "share", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "share", () => (map.getCanvas().style.cursor = ""));
    map.on("click", "prob", (e) => { if (view === "problems") hexDetail(e.features[0].properties, e.lngLat); });
    map.on("click", "bar-fill", (e) => { if (view === "barrios") barrioDetail(e.features[0].properties); });
    // Building dots are hard to hit at low zoom: also pick the nearest dot within 14 px.
    map.on("click", (e) => {
      if ((view !== "licences" && view !== "share") || map.getZoom() < bmin) return;
      if (map.queryRenderedFeatures(e.point, { layers: ["bld"] }).length) return;
      const near = map.queryRenderedFeatures([[e.point.x - 14, e.point.y - 14], [e.point.x + 14, e.point.y + 14]], { layers: ["bld"] });
      if (near.length) select(B[near[0].id][8], false);
    });
    const hover = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, maxWidth: "280px" });
    for (const l of ["bld", "prob", "bar-fill"]) {
      map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; hover.remove(); });
    }
    map.on("mousemove", "bld", (e) => {
      if (isMobile()) return;
      const r = B[e.features[0].id];
      hover.setLngLat([r[1], r[0]]).setHTML(`<b>${esc(r[2] || "—")}</b><br>${r[3] ? TL.plural(r[3], "flat_1", "flats_n") : TL.plural(r[5], "other_1", "other_n")}`).addTo(map);
    });
    setView(view);
    const b = params.get("b"), br = +params.get("barrio");
    if (b && byId.has(b)) select(b, true);
    else if (br && barData) showBarrio(br);
  }

  function wireMeasure() {
    document.querySelectorAll("#legend [data-m]").forEach((b) => (b.onclick = () => {
      measure = b.dataset.m;
      TL.track("map_layer", { layer: `share_${measure}`, area: slug });
      const step = ["step", ["get", measure], SHARE[0], ...SHARE_STOPS.flatMap((x, i) => [x, SHARE[i + 1]])];
      map.setPaintProperty("share", "fill-color", step);
      map.setFilter("share", ["has", measure]);
      $("#legend .legend-body").innerHTML = legend();
      wireMeasure();
    }));
  }
  function setView(v) {
    if (v !== view) TL.track("map_layer", { layer: v, area: slug });
    view = v;
    for (const [k, ls] of Object.entries(VIEWS)) for (const l of ls) if (map.getLayer(l)) map.setLayoutProperty(l, "visibility", "none");
    for (const l of VIEWS[v]) if (map.getLayer(l)) map.setLayoutProperty(l, "visibility", "visible");
    document.querySelectorAll("#layers [data-v]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.v === v));
    const h = $("#layers .layer-help");
    if (h) h.textContent = help();
    $("#legend .legend-body") && ($("#legend .legend-body").innerHTML = legend());
    wireMeasure();
    if (v === "barrios" && selBarrio == null && !isMobile()) barrioList();
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
    const u = new URL(location.href); u.searchParams.set("b", id); history.replaceState(null, "", u);
    if (fly) map.flyTo({ center: [r[1], r[0]], zoom: Math.max(map.getZoom(), 17), speed: 1.6, padding: padding() });
    else if (isMobile()) map.easeTo({ center: [r[1], r[0]], padding: padding(), duration: 300 });
    const head = `<div class="detail">
        <div class="eyebrow"><span>${t("building_label")}</span><button class="x" type="button" data-close aria-label="Cerrar">${ICON.close}</button></div>
        <h2>${esc(r[2] || "—")}</h2>
        <div class="figs">
          ${r[3] ? `<div><b>${fmt(r[3])}</b><span>${L("viviendas turísticas", "tourist flats")}</span></div><div><b>${fmt(r[4])}</b><span>${L("plazas", "guest places")}</span></div>` : ""}
          ${r[5] ? `<div><b>${fmt(r[5])}</b><span>${L("otros alojamientos", "other establishments")}</span></div>` : ""}
          ${r[9] ? `<div><b>${fmt(r[9])}</b><span>${L("viviendas en el edificio", "homes in the building")}</span></div>` : ""}
        </div>
        ${r[9] && r[3] ? `<p class="sub" style="margin-top:10px">${L(`<b>${fmt(r[3])} de ${fmt(r[9])}</b> viviendas del edificio (${Math.round(100 * Math.min(1, r[3] / r[9]))}%) están registradas como turísticas.`,
          `<b>${fmt(r[3])} of ${fmt(r[9])}</b> homes in the building (${Math.round(100 * Math.min(1, r[3] / r[9]))}%) are registered as tourist flats.`)}
          <span class="tiny muted">${L("Viviendas según el Catastro; indicativo.", "Homes per the Catastro; indicative.")}</span></p>` : ""}
        <div class="point-share">${TL.shareButton({ url: `https://tienelicencia.com/${slug}/mapa?b=${encodeURIComponent(id)}`,
          text: L(`${r[2] || "Edificio"}: ${r[3]} viviendas turísticas registradas${r[9] ? ` de ${r[9]} viviendas` : ""}`, `${r[2] || "Building"}: ${r[3]} registered tourist flats${r[9] ? ` out of ${r[9]} homes` : ""}`) + " · tienelicencia.com",
          content: "map_building" })}</div>
        <div id="flats"><p class="small muted" style="margin-top:12px">${t("loading")}</p></div></div>`;
    $("#p-detail").innerHTML = head;
    sheet(true, "detail");
    const my = ++reqId;
    TL.api("building", { id }).then((d) => {
      TL.track("map_select", { select_type: "building", area: slug, town: d.muni || "", place: barrioAt(r[0], r[1]) || d.muni || "" });
      if (my !== reqId) return;
      $("#p-detail h2").innerHTML = `${esc(d.addresses.slice(0, 3).join(" · "))}${d.addresses.length > 3 ? ` <span class="muted">+${d.addresses.length - 3}</span>` : ""}`;
      $("#p-detail .figs").insertAdjacentHTML("afterend", `<p class="sub" style="margin-top:10px">${esc([d.postcode, d.muni].filter(Boolean).join(" "))}</p>`);
      $("#flats").innerHTML = TL.flatsTable(d.flats, { limit: 10 }) +
        `<p class="note info small">${L("Datos del Registro de Turismo de Andalucía. Una vivienda registrada puede no estar anunciándose; una anunciada sin registro no aparece aquí.",
          "From the Andalusian Tourism Register. A registered flat may not be advertised; an unregistered one being advertised won't appear here.")}</p>`;
    }).catch(() => { if (my === reqId) $("#flats").innerHTML = `<p class="small muted">${t("search_error")}</p>`; });
  }
  function reselect() { if (selected?.type === "building") select(selected.id, false); }

  // Barrio at a point (cities with barrios), for analytics: we record the barrio, never the building.
  function barrioAt(lat, lon) {
    if (!barData) return null;
    const inRing = (ring) => {
      let inside = false;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
      }
      return inside;
    };
    for (const f of barData.features) {
      const g = f.geometry, polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
      if (polys.some((p) => inRing(p[0]))) return f.properties.name;
    }
    return null;
  }

  // ---------------------------------------------------------------- selection: hex / barrio
  function hexDetail(p, lngLat) {
    selected = { type: "hex" };
    TL.track("map_select", { select_type: "area_hex", area: slug, place: barrioAt(lngLat.lat, lngLat.lng) || "" });
    map.getSource("sel").setData({ type: "Feature", geometry: { type: "Point", coordinates: [lngLat.lng, lngLat.lat] } });
    $("#p-detail").innerHTML = `<div class="detail"><div class="eyebrow"><span>${L("Zona de ~150 m", "~150 m area")}</span><button class="x" type="button" data-close aria-label="Cerrar">${ICON.close}</button></div>
      <h2>${p.pct}% ${L("sin número válido", "without a valid number")}</h2>
      <p class="sub">${L(`${fmt(p.nv)} de ${fmt(p.n)} anuncios de Airbnb en esta zona no muestran un número válido de la Junta.`, `${fmt(p.nv)} of ${fmt(p.n)} Airbnb listings in this area don't display a valid Junta number.`)}</p>
      <div class="figs"><div><b>${fmt(p.n)}</b><span>${L("anuncios", "listings")}</span></div><div><b>${fmt(p.reg)}</b><span>${L("viviendas registradas", "registered flats")}</span></div></div>
      <p class="note small">${L("Mostramos zonas, nunca anuncios concretos. Las ubicaciones de Airbnb son aproximadas.", "We show areas, never individual listings. Airbnb locations are approximate.")}</p></div>`;
    sheet(true, "detail");
  }
  let selBarrio = null;
  function barrioDetail(p) {
    if (selBarrio != null) map.setFeatureState({ source: "barrios", id: selBarrio }, { sel: false });
    selBarrio = p.id;
    selected = { type: "barrio" };
    map.setFeatureState({ source: "barrios", id: p.id }, { sel: true });
    map.getSource("sel").setData({ type: "FeatureCollection", features: [] });
    const has = p.not_valid_pct != null;
    TL.track("map_select", { select_type: "barrio", area: slug, place: p.name });
    $("#p-detail").innerHTML = `<div class="detail"><div class="eyebrow"><span>Barrio</span><button class="x" type="button" data-close aria-label="Cerrar">${ICON.close}</button></div>
      <h2>${esc(p.name)}</h2>
      <div class="point-share" style="margin:4px 0 10px">${TL.shareButton({ url: `https://tienelicencia.com/${slug}/mapa?barrio=${p.id}`,
        text: L(`${p.name} (${area.slug === "sevilla" ? "Sevilla" : "Málaga"}): ${p.vut_share != null ? `el ${pc(p.vut_share)} de las viviendas son turísticas registradas` : `${p.vut} viviendas turísticas registradas`}`,
          `${p.name} (${area.slug === "sevilla" ? "Sevilla" : "Málaga"}): ${p.vut_share != null ? `${pc(p.vut_share)} of homes are registered tourist flats` : `${p.vut} registered tourist flats`}`) + " · tienelicencia.com",
        content: "map_barrio" })}</div>
      ${p.vut_share != null ? `<p class="sub">${L(`<b>${pc(p.vut_share)}</b> de las viviendas del barrio son turísticas registradas (${fmt(p.vut)} de ${fmt(p.homes)}; indicativo)${p.vut_share > (area.cap || 8) ? `, por encima del límite del ${area.cap || 8}&nbsp;% que usa el Ayuntamiento` : ""}.`,
        `<b>${pc(p.vut_share)}</b> of homes in this barrio are registered tourist flats (${fmt(p.vut)} of ${fmt(p.homes)}; indicative)${p.vut_share > (area.cap || 8) ? `, above the ${area.cap || 8}% limit the council uses` : ""}.`)}</p>` : ""}
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
  function showBarrio(id) {
    const f = barData?.features.find((x) => x.properties.id === id);
    if (!f) return;
    setView("barrios");
    const pts = f.geometry.coordinates.flat(2);
    const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: isMobile() ? { top: 60, bottom: innerHeight * 0.62, left: 20, right: 20 } : 40, maxZoom: 16 });
    barrioDetail(f.properties);
  }
  function barrioList() {
    const feats = barData?.features || [];
    const top = feats.map((f) => f.properties).filter((p) => p.not_valid_pct != null).sort((a, b) => b.listings - a.listings).slice(0, 10);
    $("#p-detail").innerHTML = `<div class="detail"><div class="legend-title">${L("Barrios con más anuncios", "Barrios with most listings")}</div>
      <table class="flats"><thead><tr><th>Barrio</th><th class="n">${L("Anuncios", "Listings")}</th><th class="n">${L("Sin nº", "No no.")}</th></tr></thead><tbody>
      ${top.map((p) => `<tr><td><a href="#" data-bar="${p.id}">${esc(p.name)}</a></td><td class="n">${fmt(p.listings)}</td><td class="n">${Math.round(p.not_valid_pct)}%</td></tr>`).join("")}</tbody></table></div>`;
    document.querySelectorAll("[data-bar]").forEach((a) => (a.onclick = (e) => {
      e.preventDefault();
      const f = feats.find((x) => x.properties.id === +a.dataset.bar);
      const pts = f.geometry.coordinates.flat(2);
      const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 40, maxZoom: 16 });
      barrioDetail(f.properties);
    }));
  }

  function clearSelection() {
    selected = null;
    map.getSource("sel")?.setData({ type: "FeatureCollection", features: [] });
    if (selBarrio != null) { map.setFeatureState({ source: "barrios", id: selBarrio }, { sel: false }); selBarrio = null; }
    const u = new URL(location.href); u.searchParams.delete("b"); history.replaceState(null, "", u);
    chrome();
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
