/* Ranking of Spain's ten largest cities by tourist-housing pressure. Data: /data/ranking.json (built by pipeline/site_build.py) */
(() => {
  const { esc, getJSON, areaHref } = TL;
  TL.init({ page: "ranking" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const $ = (s) => document.querySelector(s);
  const pc = (x, d = 1) => (x == null ? "—" : `${Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: d })}${TL.lang() === "es" ? " %" : "%"}`);
  let R;

  getJSON("/data/ranking.json").then((d) => { R = d; paint(); TL.onLang(paint); })
    .catch(() => { $("#rk").innerHTML = `<li class="empty">${L("No se han podido cargar los datos.", "The data could not be loaded.")}</li>`; });

  function paint() {
    document.title = `${L("Ranking de ciudades", "City ranking")} | tienelicencia.com`;
    const C = R.cities, max = Math.max(...C.map((c) => Math.max(c.advertised_pct, c.registered_pct || 0))) * 1.08;
    const w = (x) => `${(100 * x / max).toFixed(2)}%`;
    const period = R.ine_period ? TL.date(`${R.ine_period}-01`, { month: "long", year: "numeric" }) : "";
    $("#rk-legend").innerHTML = `
      <span><i style="background:var(--brand-2)"></i>${L("Anunciadas con número válido", "Advertised with a valid number")}</span>
      <span><i class="unl"></i>${L("Anunciadas sin número válido", "Advertised without a valid number")}</span>
      <span><i style="background:var(--line-2)"></i>${L("Anunciadas (aún sin comprobar)", "Advertised (not checked yet)")}</span>
      <span><i class="tick"></i>${L("Licencias registradas", "Licences registered")}</span>`;
    $("#rk").innerHTML = C.map((c, i) => {
      const split = c.no_valid_number_pct != null;
      const bar = split
        ? `<i class="lic" style="width:${w(c.advertised_with_number_pct)}"></i><i class="unl" style="width:${w(c.advertised_no_number_pct)}"></i>`
        : `<i class="pend" style="width:${w(c.advertised_pct)}"></i>`;
      const name = c.slug ? `<a href="${areaHref(c.slug)}">${esc(c.name)}</a>` : c.area ? `<a href="${areaHref(c.area)}">${esc(c.name)}</a>` : esc(c.name);
      const facts = [
        `<span><b>${pc(c.advertised_pct, 2)}</b> ${L("de las viviendas, anunciadas como turísticas", "of homes advertised for tourist stays")}</span>`,
        split ? `<span><b>${pc(c.no_valid_number_pct, 0)}</b> ${L("de los anuncios sin número válido", "of listings without a valid number")}${c.no_valid_number_source === "sample" ? ` <span class="muted">(${L("muestra", "sample")})</span>` : ""}</span>`
          : `<span class="muted">${L("Anuncios sin número válido: pendiente", "Listings without a valid number: pending")}</span>`,
        c.registered_pct != null ? `<span><b>${pc(c.registered_pct, 2)}</b> ${L("con licencia registrada", "with a registered licence")}</span>` : "",
        c.concentration_pct != null ? `<span><b>${pc(c.concentration_pct)}</b> ${L("de las viviendas en zonas con más del 10 % turísticas", "of homes in areas over 10% tourist flats")}${c.concentration_basis === "barrio" ? ` <span class="muted">(${L("por barrio", "by barrio")})</span>` : ""}</span>` : "",
      ].filter(Boolean).join("");
      return `<li class="rk-row">
        <div class="rk-pos">${i + 1}</div>
        <div><h2 class="rk-name">${name}</h2>
          <div class="rk-bar" role="img" aria-label="${esc(`${c.name}: ${pc(c.advertised_pct, 2)}`)}">${bar}${c.registered_pct != null ? `<span class="reg" style="left:${w(c.registered_pct)}"></span>` : ""}</div>
          <div class="rk-facts">${facts}</div></div>
        <div class="rk-score"><b>${c.score}</b><span>${L("de 100", "of 100")}</span></div></li>`;
    }).join("");
    $("#rk-notes").innerHTML = L(`
      <p><b>Cómo leerlo.</b> La puntuación compara la parte de las viviendas anunciadas como turísticas con la de la ciudad más alta (100). Anunciadas: viviendas turísticas en Airbnb, Booking y Vrbo según el INE (${period}), sin duplicados, sobre el total de viviendas del censo. El reparto con y sin número válido sale de nuestras comprobaciones de anuncios de Airbnb en cada ciudad; donde aún no hemos llegado, se marca como pendiente.</p>
      <p>Licencias registradas: viviendas turísticas inscritas en el registro autonómico sobre el total de viviendas (Catastro o censo). Una vivienda registrada puede no estar anunciándose. Zonas: áreas de unos 150 m (o barrios donde no hay Catastro) en las que las viviendas turísticas registradas superan el 10&nbsp;% de las viviendas.</p>
      <p>No anunciar un número válido es una discrepancia con el registro: <b>no demuestra por sí solo que una vivienda no tenga permiso</b>. <a href="/metodologia">Metodología y fuentes</a>.</p>`,
      `
      <p><b>How to read it.</b> The score compares the share of homes advertised for tourist stays with the highest city (100). Advertised: tourist homes on Airbnb, Booking and Vrbo counted by the INE (${period}), de-duplicated, as a share of all census homes. The split with and without a valid number comes from our checks of Airbnb listings in each city; where we haven't got to yet, it's marked as pending.</p>
      <p>Licences registered: tourist flats in the regional register as a share of all homes (Catastro or census). A registered flat may not be advertised. Areas: ~150 m areas (or barrios where there is no Catastro) where registered tourist flats exceed 10% of homes.</p>
      <p>Not displaying a valid number is a mismatch with the register: <b>it doesn't on its own show that a home lacks a permit</b>. <a href="/metodologia">Methodology and sources</a>.</p>`);
  }
})();
