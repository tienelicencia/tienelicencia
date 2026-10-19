/* Home: hero map preview, headline stats (from the live data), area cards, province-wide search. */
(() => {
  const { t, fmt, pctStr, esc, name, getJSON, areaHref, ICON } = TL;
  TL.init({ page: "home" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const search = TL.searchWidget(document.getElementById("home-search"), { area: "andalucia", examples: ["VUT/MA/86284", "Calle Bolivia 121 Málaga", "Calle Feria 70 Sevilla"] });

  getJSON("/data/andalucia/preview.json").then((pts) => TL.preview(document.getElementById("hero-map"), pts, { pad: 8, q: [.01, .99] }));

  // "Search an address" hero action: scroll to the search box and focus it
  document.querySelector('[data-track="hero_search"]')?.addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById("buscar").scrollIntoView({ behavior: "smooth" });
    setTimeout(() => search.input.focus({ preventScroll: true }), 400);
  });
  document.querySelectorAll("[data-track]").forEach((a) => a.addEventListener("click", () => TL.track("home_action", { action: a.dataset.track })));

  Promise.all([getJSON("/data/areas.json"), getJSON("/data/home.json"), getJSON("/data/meta.json")]).then(([A, H, M]) => {
    const paint = () => {
      stats(A, H, M);
      cards(A);
    };
    paint();
    TL.onLang(paint);
  });

  // The headline figures (data/home.json, built by site_build.py home_stats): across the index cities, or every area with
  // barrio maps. Each says where it comes from; never "in Spain" for what we only measure in some places.
  function stats(A, H, M) {
    const by = Object.fromEntries(A.areas.map((a) => [a.slug, a]));
    const loc = TL.lang() === "es" ? "es-ES" : "en-GB";
    const pc = (x, d = 1) => `${Number(x).toLocaleString(loc, { maximumFractionDigits: d })}${TL.lang() === "es" ? "\u00a0%" : "%"}`;
    const nm = (s) => esc(by[s] ? name(by[s].name) : s);
    const base = "https://tienelicencia.com";
    const n = H.cities, minPop = fmt(H.min_population);
    const [t1, t2, t3] = H.top;
    const nv = 100 * H.not_valid / H.assessed, wr = 100 * H.wrong_number / H.not_valid;
    const tb = H.top_barrio, hs = H.hotspot;
    const barrioCities = Object.entries(H.barrios_over_by_area).map(([s, k]) => `${nm(s)} ${fmt(k)}`).join(" · ");
    const S = [
      ["gold", esc(t1.name), L(`es la ciudad con <b>más presión de la vivienda turística</b> de España, seguida de ${esc(t2.name)} y ${esc(t3.name)}`,
          `is the city under <b>the most tourist-housing pressure</b> in Spain, followed by ${esc(t2.name)} and ${esc(t3.name)}`),
        L(`Índice de las ${n} ciudades de más de ${minPop} habitantes: viviendas anunciadas, concentración y registros.`,
          `Index of the ${n} cities over ${minPop} inhabitants: homes advertised, concentration and registrations.`), "/ranking",
        L(`${t1.name}, ${t2.name} y ${t3.name}: las ciudades españolas con más presión de la vivienda turística`, `${t1.name}, ${t2.name} and ${t3.name}: the Spanish cities under the most tourist-housing pressure`)],
      ["", pc(H.registered_pct, 2), L(`de las viviendas de las <b>${n} mayores ciudades</b> son viviendas turísticas registradas: ${fmt(H.registered)}`,
          `of homes in the <b>${n} largest cities</b> are registered tourist flats: ${fmt(H.registered)}`),
        L(`Del ${pc(H.registered_min[0], 2)} en ${esc(H.registered_min[1])} al ${pc(H.registered_max[0], 2)} en ${esc(H.registered_max[1])}.`,
          `From ${pc(H.registered_min[0], 2)} in ${esc(H.registered_min[1])} to ${pc(H.registered_max[0], 2)} in ${esc(H.registered_max[1])}.`), "/ranking",
        L(`${pc(H.registered_pct, 2)} de las viviendas de las ${n} mayores ciudades españolas son viviendas turísticas registradas`, `${pc(H.registered_pct, 2)} of homes in Spain's ${n} largest cities are registered tourist flats`)],
      ["bad", fmt(H.not_valid), L(`anuncios de Airbnb <b>no muestran un número de registro válido</b>: el ${pc(nv, 0)} de los ${fmt(H.assessed)} que hemos comprobado`,
          `Airbnb listings <b>don't display a valid registration number</b>: ${pc(nv, 0)} of the ${fmt(H.assessed)} we've checked`),
        L(`${fmt(H.wrong_number)} de ellos (${pc(wr, 0)}) muestran un número que no está en el registro o que es de otro municipio. Sin contar Madrid, donde mostrarlo no es obligatorio.`,
          `${fmt(H.wrong_number)} of them (${pc(wr, 0)}) show a number that isn't in the register or belongs to another town. Not counting Madrid, where showing it isn't required.`), "/ranking",
        L(`${fmt(H.not_valid)} anuncios de Airbnb en las mayores ciudades españolas no muestran un número de registro válido`, `${fmt(H.not_valid)} Airbnb listings in Spain's largest cities don't display a valid registration number`)],
      ["gold", fmt(H.barrios_over), L(`barrios tienen <b>más del ${H.barrio_share}\u00a0% de sus viviendas</b> registradas como turísticas; ${fmt(H.barrios_over_by_area[tb.area] || 0)} están en ${nm(tb.area)}`,
          `barrios have <b>more than ${H.barrio_share}% of their homes</b> registered as tourist flats; ${fmt(H.barrios_over_by_area[tb.area] || 0)} are in ${nm(tb.area)}`),
        L(`En ${esc(tb.name)} llegan al ${pc(tb.share)}. ${barrioCities}. Solo ciudades con mapa de barrios.`,
          `In ${esc(tb.name)} they reach ${pc(tb.share)}. ${barrioCities}. Only cities with barrio maps.`), `/${tb.area}/mapa?barrio=${tb.id}`,
        L(`${fmt(H.barrios_over)} barrios españoles tienen más del ${H.barrio_share} % de sus viviendas registradas como turísticas`, `${fmt(H.barrios_over)} Spanish barrios have more than ${H.barrio_share}% of their homes registered as tourist flats`)],
      ["", fmt(H.buildings_over), L(`edificios de pisos tienen <b>al menos una de cada cuatro viviendas</b> registrada como turística`,
          `apartment buildings have <b>at least one in four homes</b> registered as tourist flats`),
        L(`Edificios de 4 viviendas o más en ${H.building_cities.map(esc).join(", ")} (donde podemos situar la mayoría de las viviendas registradas).`,
          `Buildings of 4+ homes in ${H.building_cities.map(esc).join(", ")} (where we can place most registered flats).`), "/ranking",
        L(`${fmt(H.buildings_over)} edificios de pisos en las mayores ciudades españolas tienen al menos una de cada cuatro viviendas registrada como turística`, `${fmt(H.buildings_over)} apartment buildings in Spain's largest cities have at least one in four homes registered as tourist flats`)],
      ["bad", fmt(Math.round(hs.concentration)), L(`anuncios de Airbnb por cada 100 viviendas en <b>${esc(TL.titleCase ? TL.titleCase(hs.peak_place || "") : hs.peak_place || "")} (${esc(hs.name)})</b>, la zona más afectada de España`,
          `Airbnb listings for every 100 homes in <b>${esc(TL.titleCase ? TL.titleCase(hs.peak_place || "") : hs.peak_place || "")} (${esc(hs.name)})</b>, the most affected area in Spain`),
        L(`${fmt(hs.peak_listings)} anuncios y ${fmt(hs.peak_homes)} viviendas en un círculo de 1\u00a0km de diámetro.`, `${fmt(hs.peak_listings)} listings and ${fmt(hs.peak_homes)} homes in a circle 1 km across.`),
        `/${hs.area}/mapa?circle=${hs.peak_lat},${hs.peak_lon},${hs.peak_radius_m}`,
        L(`En la zona más afectada de España hay ${Math.round(hs.concentration)} anuncios de Airbnb por cada 100 viviendas`, `In Spain's most affected area there are ${Math.round(hs.concentration)} Airbnb listings for every 100 homes`)],
    ];
    document.getElementById("bigstats").innerHTML = S.map(([cls, big, txt, small, href, share]) => `<div class="stat">
        <b class="${cls}">${big}</b><span>${txt}</span><small>${small} <a href="${href}" style="color:#7fd3b3">${L("Ver datos", "See data")} →</a></small>
        ${TL.shareButton({ url: base + href, text: `${share} · tienelicencia.com`, content: "home_stat" })}</div>`).join("");
    document.getElementById("bigstats-src").textContent = L(
      `Ciudades de más de ${minPop} habitantes (INE). Anuncios: Airbnb (Inside Airbnb y nuestras muestras aleatorias), comprobados uno a uno con los registros oficiales de turismo; Catastro e INE. Datos al ${TL.date(H.built_at.slice(0, 10))}.`,
      `Cities over ${minPop} inhabitants (INE). Listings: Airbnb (Inside Airbnb and our random samples), checked one by one against the official tourism registers; Catastro and INE. Data as of ${TL.date(H.built_at.slice(0, 10))}.`);
  }

  function cards(A) {
    const list = [...TL.cityAreas(A), ...TL.wideAreas(A)];   // cities by population, then Mallorca and Andalucía
    document.getElementById("areas").innerHTML = list.map((a) => `
      <a class="card area-card" href="${areaHref(a.slug)}">
        <div class="art" data-preview="${a.slug}"></div>
        <div class="body">
          <span class="kind">${t(`area_kind_${["province", "region", "island"].includes(a.kind) ? a.kind : "city"}`)}</span>
          <h3>${esc(name(a.name))}</h3>
          <div class="stats">
            <div><b>${fmt(a.vut)}</b><span>${t("regs")}</span></div>
            ${a.has_listings ? `<div><b class="bad">${pctStr(a.not_valid, a.listings)}</b><span>${L("anuncios sin número válido", "listings without a valid number")}</span></div>`
              : a.sample_pct != null && a.sample_checked >= 250 ? `<div><b class="bad">~${Math.round(a.sample_pct)}%</b><span>${L("anuncios sin número válido (muestra)", "listings without a valid number (sample)")}</span></div>`
              : `<div><b>${fmt(a.vut_places)}</b><span>${L("plazas turísticas", "guest places")}</span></div>`}
          </div>
          <span class="go">${t("view_data")} ${ICON.arrow.replace("<svg", '<svg width="18" height="18"')}</span>
        </div>
      </a>`).join("");
    const cities = TL.cityAreas(A).map((a) => esc(name(a.name)));
    document.getElementById("coverage-line").innerHTML = L(`<b>Disponible:</b> ${cities.join(", ")}, la isla de Mallorca y toda Andalucía.`,
      `<b>Available:</b> ${cities.join(", ")}, the island of Mallorca and all of Andalucía.`);
    document.querySelectorAll("[data-preview]").forEach((el) =>
      getJSON(`/data/${el.dataset.preview}/preview.json`).then((pts) => TL.preview(el, pts, { pad: 10 })));
  }
})();
