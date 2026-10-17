/* Ranking of Spain's ten largest cities: tourist-housing pressure (how much + how concentrated) and compliance.
   Data: /data/ranking.json (built by pipeline/site_build.py). Method: /metodologia#ranking */
(() => {
  const { esc, getJSON, areaHref, fmt } = TL;
  TL.init({ page: "ranking" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const $ = (s) => document.querySelector(s);
  const pc = (x, d = 1) => (x == null ? "—" : `${Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: d })}${TL.lang() === "es" ? " %" : "%"}`);
  const num = (x, d = 1) => Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: d });
  const titleCase = (s) => (/[a-z]/.test(s) ? s : s.toLowerCase().replace(/(^|[\s'-])\p{L}/gu, (m) => m.toUpperCase()));
  let R, sort = "pressure";

  getJSON("/data/ranking.json").then((d) => { R = d; paint(); TL.onLang(paint); })
    .catch(() => { $("#rk").innerHTML = `<li class="empty">${L("No se han podido cargar los datos.", "The data could not be loaded.")}</li>`; });

  function paint() {
    document.title = `${L("Ranking de ciudades", "City ranking")} | tienelicencia.com`;
    const C = [...R.cities].sort(sort === "pressure" ? (a, b) => b.score - a.score
      : (a, b) => (b.no_valid_number_pct ?? -1) - (a.no_valid_number_pct ?? -1));
    const advMax = Math.max(...C.map((c) => Math.max(c.advertised_pct, c.registered_pct || 0))) * 1.08;
    const w = (x, m) => `${Math.min(100, 100 * x / m).toFixed(2)}%`;
    const period = R.ine_period ? TL.date(`${R.ine_period}-01`, { month: "long", year: "numeric" }) : "";

    $("#rk-tools").innerHTML = `<div class="seg" role="group" aria-label="${L("Ordenar", "Sort")}">
        <button type="button" data-s="pressure" aria-pressed="${sort === "pressure"}">${L("Presión turística", "Tourist pressure")}</button>
        <button type="button" data-s="compliance" aria-pressed="${sort === "compliance"}">${L("Anuncios sin número válido", "Listings without a valid number")}</button></div>`;
    $("#rk-tools").querySelectorAll("[data-s]").forEach((b) => b.addEventListener("click", () => { sort = b.dataset.s; paint(); }));
    $("#rk-legend").innerHTML = `
      <span><i style="background:var(--brand-2)"></i>${L("Anunciadas con número válido", "Advertised with a valid number")}</span>
      <span><i class="unl"></i>${L("Anunciadas sin número válido", "Advertised without a valid number")}</span>
      <span><i style="background:var(--line-2)"></i>${L("Anunciadas (aún sin comprobar)", "Advertised (not checked yet)")}</span>
      <span><i class="tick"></i>${L("Licencias registradas", "Licences registered")}</span>`;

    $("#rk").innerHTML = C.map((c, i) => {
      const split = c.no_valid_number_pct != null;
      const bar = split
        ? `<i class="lic" style="width:${w(c.advertised_with_number_pct, advMax)}"></i><i class="unl" style="width:${w(c.advertised_no_number_pct, advMax)}"></i>`
        : `<i class="pend" style="width:${w(c.advertised_pct, advMax)}"></i>`;
      const href = c.slug || c.area;
      const name = href ? `<a href="${areaHref(href)}">${esc(c.name)}</a>` : esc(c.name);
      const where = c.peak_place ? ` <span class="muted">(${esc(titleCase(c.peak_place))})</span>` : "";
      const lines = [
        `<span><b>${pc(c.advertised_pct, 2)}</b> ${L("de todas las viviendas se anuncian como turísticas", "of all homes are advertised for tourist stays")}</span>`,
        c.peak_listings_per_100_homes != null
          ? `<span><b>${num(c.peak_listings_per_100_homes)}</b> ${L("anuncios por cada 100 viviendas en su kilómetro más afectado", "listings per 100 homes in its most affected kilometre")}${where}${c.peak_registered_pct != null ? `, ${L("donde el", "where")} <b>${pc(c.peak_registered_pct)}</b> ${L("de las viviendas tiene licencia turística", "of homes hold a tourist licence")}` : ""}</span>`
          : `<span class="muted">${L("Zona más afectada: pendiente", "Most affected area: pending")}</span>`,
        split ? `<span><b>${pc(c.no_valid_number_pct, 0)}</b> ${L("de los anuncios sin número válido", "of listings without a valid number")}${c.no_valid_number_source === "sample" ? ` <span class="muted">(${L("muestra", "sample")})</span>` : ""}${c.number_required === false ? ` <span class="muted">(${L("no es obligatorio mostrarlo", "showing it isn't required")})</span>` : ""}</span>`
          : `<span class="muted">${L("Anuncios sin número válido: pendiente", "Listings without a valid number: pending")}</span>`,
        c.registered_pct != null ? `<span><b>${pc(c.registered_pct, 2)}</b> ${L("de las viviendas con licencia turística", "of homes hold a tourist licence")}</span>` : "",
        c.buildings_over_share != null ? `<span><b>${fmt(c.buildings_over_share)}</b> ${L(`edificios de pisos con un ${R.building_share} % o más de viviendas turísticas`, `apartment buildings where ${R.building_share}%+ of homes are tourist flats`)} <span class="muted">(${pc(c.buildings_over_share_pct, 1)})</span></span>` : "",
      ].filter(Boolean).join("");
      const parts = c.score_parts || {};
      return `<li class="rk-row">
        <div class="rk-pos">${i + 1}</div>
        <div><h2 class="rk-name">${name}</h2>
          <div class="rk-bar" role="img" aria-label="${esc(`${c.name}: ${pc(c.advertised_pct, 2)}`)}">${bar}${c.registered_pct != null ? `<span class="reg" style="left:${w(c.registered_pct, advMax)}"></span>` : ""}</div>
          <div class="rk-facts">${lines}</div></div>
        <div class="rk-score"><b>${c.score}</b><span>${L("de 100", "of 100")}${c.score_partial ? "*" : ""}</span>
          <span class="rk-parts">${L("cantidad", "amount")} ${parts.advertised_pct ?? "—"}<br>${L("concentración", "concentration")} ${parts.peak_listings_per_100_homes ?? "—"}</span></div></li>`;
    }).join("");

    $("#rk-notes").innerHTML = L(`
      <p><b>Cómo se calcula.</b> La puntuación de presión turística es la media de dos medidas, cada una respecto a la ciudad más alta (100):
        <b>cantidad</b>, la parte de todas las viviendas que se anuncian como turísticas (INE, ${period}, sin duplicados entre Airbnb, Booking y Vrbo), y
        <b>concentración</b>, los anuncios de Airbnb por cada 100 viviendas en el círculo de ${num(R.peak_radius_m / 1000)}&nbsp;km más afectado de la ciudad
        (entre los que tienen al menos ${fmt(R.peak_min_homes)} viviendas). Debajo de cada puntuación, las dos partes.
        ${C.some((c) => c.score_partial) ? "* Aún sin la medida de concentración: puntuación solo con la cantidad." : ""}</p>
      <p>El reparto con y sin número válido sale de nuestras comprobaciones de anuncios en cada ciudad (en Zaragoza, Murcia y Las Palmas, de una muestra aleatoria).
        Las licencias registradas y los edificios con muchas viviendas turísticas solo se muestran donde el registro permite situar la mayoría de las viviendas.
        <a href="/metodologia#ranking">Metodología completa del ranking</a>.</p>
      <p>No anunciar un número válido es una discrepancia con el registro: <b>no demuestra por sí solo que una vivienda no tenga permiso</b>.</p>`,
      `
      <p><b>How it's calculated.</b> The tourist-pressure score is the average of two measures, each relative to the highest city (100):
        <b>amount</b>, the share of all homes advertised for tourist stays (INE, ${period}, de-duplicated across Airbnb, Booking and Vrbo), and
        <b>concentration</b>, Airbnb listings per 100 homes in the city's most affected ${num(R.peak_radius_m / 1000)} km circle
        (among circles with at least ${fmt(R.peak_min_homes)} homes). The two parts are shown under each score.
        ${C.some((c) => c.score_partial) ? "* Concentration not available yet: scored on amount alone." : ""}</p>
      <p>The split with and without a valid number comes from our checks of listings in each city (in Zaragoza, Murcia and Las Palmas, a random sample).
        Licences registered and buildings with many tourist flats are shown only where the register lets us place most flats.
        <a href="/metodologia#ranking">Full ranking methodology</a>.</p>
      <p>Not displaying a valid number is a mismatch with the register: <b>it doesn't on its own show that a home lacks a permit</b>.</p>`);
  }
})();
