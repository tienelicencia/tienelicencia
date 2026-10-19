/* Índice de presión de la vivienda turística: every Spanish municipality over 300,000 inhabitants, one composite index
   (housing 40% · concentration 35% · registration 25%) normalised against a fixed October 2026 baseline (100 points).
   Data: /data/ranking.json, built by pipeline/site_build.py with rta_audit/index.py and index_config.json.
   Method: /metodologia#indice */
(() => {
  const { esc, getJSON, areaHref, fmt } = TL;
  TL.init({ page: "ranking" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const $ = (s) => document.querySelector(s);
  const loc = () => (TL.lang() === "es" ? "es-ES" : "en-GB");
  const num = (x, d = 1) => (x == null ? "—" : Number(x).toLocaleString(loc(), { maximumFractionDigits: d }));
  const fix = (x, d = 1) => (x == null ? "—" : Number(x).toLocaleString(loc(), { maximumFractionDigits: d, minimumFractionDigits: d }));
  const pc = (x, d = 1) => (x == null ? "—" : `${num(x, d)}${TL.lang() === "es" ? " %" : "%"}`);
  const NA = () => `<span class="ix-na">${L("sin datos", "no data")}</span>`;
  const titleCase = (s) => (/[a-z]/.test(s) ? s : s.toLowerCase().replace(/(^|[\s'-])\p{L}/gu, (m) => m.toUpperCase()));
  const COMP = { housing: { cls: "c-a", es: "Viviendas anunciadas", en: "Homes advertised" },
    concentration: { cls: "c-b", es: "Concentración", en: "Concentration" },
    registration: { cls: "c-c", es: "Discrepancias de registro", en: "Registration discrepancies" } };
  let R;

  getJSON("/data/ranking.json").then((d) => { R = d; paint(); TL.onLang(paint); })
    .catch(() => { $("#ix").innerHTML = `<li class="empty">${L("No se han podido cargar los datos.", "The data could not be loaded.")}</li>`; });

  const basePeriod = () => TL.date(`${R.baseline.period}-01`, { month: "long", year: "numeric" });
  const baseLabel = () => (R.baseline.frozen ? L(`base ${basePeriod()}`, `${basePeriod()} base`)
    : L(`base ${basePeriod()} (provisional)`, `${basePeriod()} base (provisional)`));

  function paint() {
    const ranked = R.cities.filter((c) => c.index != null), pending = R.cities.filter((c) => c.index == null);
    const n = R.cities.length, w = R.weights, sev = R.severity, co = R.cohort || {};
    const minPop = fmt(co.min_population || 300000);
    document.title = `${L(R.name.es, R.name.en)} | tienelicencia.com`;
    $("#ix-title").textContent = L(R.name.es, R.name.en);
    $("#ix-sub").textContent = L(`Ranking de las ciudades españolas de más de ${minPop} habitantes`, `Ranking of Spanish cities with more than ${minPop} inhabitants`);
    $("#ix-meta").innerHTML = [
      ranked.length === n ? L(`${n} ciudades`, `${n} cities`)
        : L(`${n} ciudades elegibles · ${ranked.length} con índice calculado`, `${n} eligible cities · ${ranked.length} with an index`),
      L(`Base ${basePeriod()}`, `${basePeriod()} base`) + (R.baseline.frozen ? "" : L(" (provisional)", " (provisional)")),
      L("Actualización mensual", "Updated monthly")].map((s) => `<span>${s}</span>`).join("");
    $("#ix-lede").innerHTML = L(`¿Qué ciudades soportan mayor presión de la vivienda turística? Comparamos el peso del alojamiento turístico sobre la vivienda residencial, su concentración y las discrepancias en los registros anunciados en todos los municipios de España con más de ${minPop} habitantes según el padrón (INE, 1 de enero de ${(co.population_date || "2025").slice(0, 4)}).`,
      `Which cities bear the most tourist-housing pressure? We compare how much residential housing goes to tourist accommodation, how concentrated it is, and discrepancies in advertised registrations, in every Spanish municipality with more than ${minPop} inhabitants on the official register (INE, 1 January ${(co.population_date || "2025").slice(0, 4)}).`);

    // ---- how it's calculated (above the ranking)
    $("#ix-how").innerHTML = `
      <h2 id="ix-how-h" class="ix-how-h">${L("¿Cómo calculamos el índice?", "How is the index calculated?")}</h2>
      <ul class="ix-weights">
        <li><i class="sw c-a"></i><b>${Math.round(w.housing * 100)}${L(" %", "%")}</b> ${L("Viviendas anunciadas para turistas", "Homes advertised to tourists")}</li>
        <li><i class="sw c-b"></i><b>${Math.round(w.concentration * 100)}${L(" %", "%")}</b> ${L("Concentración en zonas residenciales", "Concentration in residential areas")}</li>
        <li><i class="sw c-c"></i><b>${Math.round(w.registration * 100)}${L(" %", "%")}</b> ${L("Discrepancias en los registros anunciados", "Discrepancies in advertised registrations")}</li></ul>
      <p>${L(`La puntuación toma como referencia la ciudad con mayor índice en ${basePeriod()} (100 puntos). Las cifras posteriores pueden superar ese valor: 100 es la referencia, no el máximo posible ni un límite legal.`,
        `The score takes the city with the highest index in ${basePeriod()} as its reference (100 points). Later figures can exceed it: 100 is the reference, not the highest possible value or a legal limit.`)}
        ${R.baseline.frozen ? "" : `<b>${L("La base aún es provisional", "The baseline is still provisional")}</b>${L(": se fijará cuando las ciudades tengan datos comparables. Hasta entonces la referencia se recalcula con cada actualización.", ": it will be fixed once every city has comparable data. Until then the reference is recalculated with each update.")}`}</p>
      <details class="ix-formula"><summary>${L("Ver fórmula y metodología completa", "See the formula and full methodology")}</summary>
        <ol>
          <li>${L("<b>Viviendas anunciadas (A):</b> viviendas turísticas anunciadas en Airbnb, Booking y Vrbo según el INE (sin duplicados) ÷ total de viviendas del municipio.",
            "<b>Homes advertised (A):</b> tourist homes advertised on Airbnb, Booking and Vrbo according to the INE (de-duplicated) ÷ all homes in the municipality.")}</li>
          <li>${L(`<b>Concentración (B):</b> anuncios de Airbnb por cada 100 viviendas en el círculo de 1&nbsp;km más afectado del municipio (entre los que tienen al menos ${fmt(R.peak_min_homes)} viviendas). Son anuncios, no viviendas distintas: incluyen habitaciones y algún duplicado.`,
            `<b>Concentration (B):</b> Airbnb listings per 100 homes in the municipality's most affected 1 km circle (among circles with at least ${fmt(R.peak_min_homes)} homes). These are listings, not distinct homes: they include rooms and some duplicates.`)}</li>
          <li>${L(`<b>Registros (C):</b> R = 100 × (${fix(sev.invalid, 2)} × no válidos + ${fix(sev.unmatched, 2)} × sin coincidencia + ${fix(sev.missing, 2)} × sin número) ÷ anuncios evaluados. Los coeficientes son decisiones de diseño del índice, no probabilidades de ilegalidad. En Madrid, donde mostrar el número no es obligatorio, los anuncios sin número quedan fuera de este cálculo.`,
            `<b>Registration (C):</b> R = 100 × (${fix(sev.invalid, 2)} × invalid + ${fix(sev.unmatched, 2)} × unmatched + ${fix(sev.missing, 2)} × missing) ÷ assessed listings. The coefficients are design choices for the index, not probabilities of illegality. In Madrid, where showing the number isn't required, listings without one are left out of this calculation.`)}</li>
          <li>${L(`Cada medida se divide por su máximo en la base (A′ = 100 × A ÷ A<sub>máx</sub>, y lo mismo B′ y C′). Índice = 100 × (${w.housing} A′ + ${w.concentration} B′ + ${w.registration} C′) ÷ el mayor valor de la base.`,
            `Each measure is divided by its baseline maximum (A′ = 100 × A ÷ A<sub>max</sub>, likewise B′ and C′). Index = 100 × (${w.housing} A′ + ${w.concentration} B′ + ${w.registration} C′) ÷ the highest baseline value.`)}</li>
        </ol>
        <p>${L(`Una ciudad sin alguna de las tres medidas, o con menos de ${fmt(R.min_assessed)} anuncios evaluados, no recibe índice: nunca estimamos una medida ni repartimos su peso entre las otras. Versión ${esc(R.version)}.`,
          `A city missing any of the three measures, or with fewer than ${fmt(R.min_assessed)} assessed listings, gets no index: we never estimate a measure or share its weight among the others. Version ${esc(R.version)}.`)}
          <a href="/metodologia#indice">${L("Metodología completa →", "Full methodology →")}</a></p>
      </details>
      <div class="ix-legend" aria-hidden="true">${Object.values(COMP).map((c) => `<span><i class="sw ${c.cls}"></i>${L(c.es, c.en)}</span>`).join("")}
        <span><i class="tick100"></i>${L("100 = referencia", "100 = reference")}</span></div>`;

    const scale = Math.max(110, ...ranked.map((c) => c.index)) * 1.02;
    $("#ix").innerHTML = ranked.map((c) => row(c, scale)).join("") + pending.map(pendingRow).join("");

    $("#ix-notes").innerHTML = L(`<p><b>Cómo leerlo.</b> Un índice alto significa más presión de la vivienda turística combinada con más discrepancias visibles en los registros. <b>No demuestra</b> que haya alojamientos ilegales, que todos los anuncios sin número incumplan la ley, que un número sin coincidencia sea falso, ni que el ayuntamiento no actúe. En la Comunidad de Madrid no es obligatorio mostrar el número en los anuncios: allí los anuncios sin número no cuentan en la puntuación de registros, que se calcula solo con los números que sí se muestran.</p>
      <p>Ciudades: ${esc(co.source || "INE")}; revisamos la lista una vez al año. Datos: INE (${esc(R.ine_period || "")}), Inside Airbnb, nuestras comprobaciones en directo y muestras aleatorias, registros autonómicos y Catastro. Cada ciudad indica la fecha de sus datos. <a href="/metodologia#indice">Metodología completa</a>.</p>`,
      `<p><b>How to read it.</b> A high index means more tourist-housing pressure combined with more visible registration discrepancies. It <b>doesn't prove</b> illegal accommodation, that every listing without a number breaks the law, that an unmatched number is false, or that the council isn't acting. In the Comunidad de Madrid adverts don't have to show the number: there, listings without one don't count in the registration score, which is based only on the numbers that are shown.</p>
      <p>Cities: ${esc(co.source || "INE")}; we review the list once a year. Data: INE (${esc(R.ine_period || "")}), Inside Airbnb, our live checks and random samples, regional registers and the Catastro. Each city gives the date of its data. <a href="/metodologia#indice">Full methodology</a>.</p>`);
  }

  function bar(c, scale) {
    const seg = Object.entries(COMP).map(([k, m]) =>
      `<i class="${m.cls}" style="width:${(100 * c.contributions[k] / scale).toFixed(2)}%" title="${esc(`${L(m.es, m.en)}: ${fix(c.contributions[k])}`)}"></i>`).join("");
    const label = Object.entries(COMP).map(([k, m]) => `${L(m.es, m.en)} ${fix(c.contributions[k])}`).join(", ");
    return `<div class="ix-bar" role="img" aria-label="${esc(label)}">${seg}<span class="ix-100" style="left:${(10000 / scale).toFixed(2)}%"></span></div>`;
  }

  function headline(c) {
    const v = c.verification || {};
    const nov = v.no_verifiable_pct != null
      ? `${pc(v.no_verifiable_pct, 0)}${v.source === "sample" ? `<small>${L(`muestra de ${fmt(v.assessed)} anuncios`, `sample of ${fmt(v.assessed)} listings`)}</small>` : ""}${c.number_required === false ? `<small>${L("mostrarlo no es obligatorio", "showing it isn't required")}</small>` : ""}`
      : NA();
    return `<dl class="ix-head">
      <div><dt>${L("de las viviendas, anunciadas para turistas", "of homes advertised to tourists")}</dt><dd>${c.housing != null ? pc(c.housing, 2) : NA()}</dd></div>
      <div><dt>${L("anuncios por cada 100 viviendas en su km más afectado", "listings per 100 homes in its most affected km")}</dt><dd>${c.concentration != null ? num(c.concentration) : NA()}${c.peak_place ? `<small>${esc(titleCase(c.peak_place))}</small>` : ""}</dd></div>
      <div><dt>${L("de los anuncios sin número verificable públicamente", "of listings without a publicly verifiable number")}</dt><dd>${nov}</dd></div></dl>`;
  }

  const nameOf = (c) => (c.slug ? `<a href="${areaHref(c.slug)}">${esc(c.name)}</a>` : c.area ? `<a href="${areaHref(c.area)}">${esc(c.name)}</a>` : esc(c.name));

  function row(c, scale) {
    const v = c.verification || {};
    const prov = c.status === "provisional" && v.source === "sample" && v.checked < v.target
      ? `<span class="ix-prov">${L(`provisional · muestra de ${fmt(v.checked)} de ${fmt(v.target)}`, `provisional · sample of ${fmt(v.checked)} of ${fmt(v.target)}`)}</span>` : "";
    return `<li class="ix-row">
      <div class="ix-pos">${c.rank}</div>
      <div class="ix-main">
        <h2 class="ix-name">${nameOf(c)} ${prov}</h2>
        ${bar(c, scale)}
        ${headline(c)}
        <details class="ix-more"><summary>${L("Ver todos los datos", "See all the data")}</summary>${details(c)}</details>
      </div>
      <div class="ix-score"><b>${fix(c.index)}</b><span>${L("puntos", "points")} · ${baseLabel()}</span></div></li>`;
  }

  function pendingRow(c) {
    const v = c.verification;
    const miss = (c.missing_components || []).map((k) => L(COMP[k].es, COMP[k].en).toLowerCase());
    const why = v && !v.sufficient ? L(`solo ${fmt(v.assessed)} anuncios evaluados (mínimo ${fmt(R.min_assessed)})`, `only ${fmt(v.assessed)} listings assessed (minimum ${fmt(R.min_assessed)})`)
      : L(`falta: ${miss.join(", ")}`, `missing: ${miss.join(", ")}`);
    return `<li class="ix-row ix-pending">
      <div class="ix-pos">–</div>
      <div class="ix-main"><h2 class="ix-name">${nameOf(c)} <span class="pill">${L("Índice pendiente", "Index pending")}</span></h2>
        <p class="small muted">${L(`Aún no tiene índice (${why}). No calculamos el índice con medidas incompletas.`, `No index yet (${why}). We don't calculate the index with incomplete measures.`)}</p>
        ${headline(c)}
        <details class="ix-more"><summary>${L("Ver todos los datos", "See all the data")}</summary>${details(c)}</details></div>
      <div class="ix-score"><b>—</b><span>${L("pendiente", "pending")}</span></div></li>`;
  }

  function details(c) {
    const v = c.verification, k = (v || {}).counts || {};
    const tr = (label, value) => `<tr><th scope="row">${label}</th><td>${value ?? NA()}</td></tr>`;
    const share = (x) => (v && v.assessed ? ` <span class="muted">(${pc(100 * (x || 0) / v.assessed)})</span>` : "");
    const housing = [
      tr(L("Población (INE)", "Population (INE)"), c.population != null ? fmt(c.population) : null),
      tr(L("Viviendas del municipio (censo)", "Homes in the municipality (census)"), c.census_homes != null ? fmt(c.census_homes) : null),
      tr(L("Viviendas turísticas anunciadas, sin duplicados (INE)", "Tourist homes advertised, de-duplicated (INE)"), c.advertised_homes != null ? fmt(c.advertised_homes) : null),
      tr(L("% de viviendas anunciadas", "% of homes advertised"), c.housing != null ? `${pc(c.housing, 2)} <span class="muted">(INE ${esc(c.ine_period || "")})</span>` : null),
      tr(L("Viviendas turísticas registradas", "Registered tourist flats"), c.registered != null ? fmt(c.registered) : null),
      tr(L("% de viviendas con registro turístico", "% of homes with a tourist registration"), c.registered_pct != null ? pc(c.registered_pct, 2) : null)].join("");
    const conc = [
      tr(L("Zona más afectada", "Most affected area"), c.peak_place ? esc(titleCase(c.peak_place)) : c.concentration != null ? L("círculo de 1 km", "1 km circle") : null),
      tr(L("Anuncios de Airbnb en la zona", "Airbnb listings in the area"), c.peak_listings != null ? fmt(c.peak_listings) : null),
      tr(L("Viviendas en la zona", "Homes in the area"), c.peak_homes != null ? fmt(c.peak_homes) : null),
      tr(L("Anuncios por cada 100 viviendas", "Listings per 100 homes"), c.concentration != null ? num(c.concentration) : null),
      tr(L("% de viviendas con registro turístico en la zona", "% of homes with a tourist registration in the area"), c.peak_registered_pct != null ? pc(c.peak_registered_pct) : null),
      tr(L(`Edificios de pisos con un ${R.building_share} % o más de viviendas turísticas registradas`, `Apartment buildings with ${R.building_share}%+ registered tourist flats`),
        c.buildings_over_share != null ? `${fmt(c.buildings_over_share)} <span class="muted">(${pc(c.buildings_over_share_pct)} ${L(`de ${fmt(c.apartment_buildings)}`, `of ${fmt(c.apartment_buildings)}`)})</span>` : null)].join("");
    const method = !v ? "" : v.source === "sample"
      ? L(`Muestra aleatoria simple de los ${fmt(v.frame)} anuncios de Airbnb encontrados en el municipio (orden fijo y reproducible). Evaluados: ${fmt(v.checked)} de ${fmt(v.target)} previstos (${pc(100 * v.checked / v.target, 0)}).`,
        `Simple random sample of the ${fmt(v.frame)} Airbnb listings found in the municipality (fixed, reproducible order). Assessed: ${fmt(v.checked)} of a planned ${fmt(v.target)} (${pc(100 * v.checked / v.target, 0)}).`)
      : L(`Todos los anuncios de la ciudad en Inside Airbnb (${fmt(v.assessed)}), con ${fmt(v.live_checked)} revisados en directo.`,
        `Every listing in the city in Inside Airbnb (${fmt(v.assessed)}), with ${fmt(v.live_checked)} re-checked live.`);
    const reg = !v ? `<p class="small muted">${L("Aún no hay anuncios evaluados: la muestra de esta ciudad está en curso.", "No listings assessed yet: this city's sample is under way.")}</p>` : `<p class="small muted">${method}</p><table class="ix-t"><tbody>
      ${tr(L("Número válido", "Valid number"), fmt(k.valid) + share(k.valid))}
      ${tr(L(`Sin número (gravedad ${fix(R.severity.missing, 2)})`, `No number (severity ${fix(R.severity.missing, 2)})`), fmt(k.missing) + share(k.missing) + (c.number_required === false ? ` <span class="muted">${L("· en Madrid mostrarlo no es obligatorio, así que no cuentan en la puntuación de registros", "· in Madrid showing it isn't required, so they don't count in the registration score")}</span>` : ""))}
      ${tr(L(`Número sin coincidencia en el registro (gravedad ${fix(R.severity.unmatched, 2)})`, `Number not matched in the register (severity ${fix(R.severity.unmatched, 2)})`), fmt(k.unmatched) + share(k.unmatched))}
      ${tr(L(`Número de otro municipio (gravedad ${fix(R.severity.invalid, 2)})`, `Another municipality's number (severity ${fix(R.severity.invalid, 2)})`), fmt(k.invalid_other_town) + share(k.invalid_other_town))}
      ${tr(L(`Número cancelado, con documento oficial (gravedad ${fix(R.severity.invalid, 2)})`, `Cancelled number, with an official document (severity ${fix(R.severity.invalid, 2)})`), fmt(k.invalid_cancelled) + share(k.invalid_cancelled))}
      ${tr(L("Posiblemente exentos (gravedad 0, incluidos en el total)", "Possibly exempt (severity 0, included in the total)"), fmt(k.exempt) + share(k.exempt))}
      ${tr(L("Otras señales (sin efecto en el índice)", "Other signals (no effect on the index)"), L(`licencia compartida ${fmt(v.flags.shared)} · lejos de su dirección ${fmt(v.flags.far)} · habitación con licencia de vivienda ${fmt(v.flags.room_with_flat_licence)}`,
        `shared licence ${fmt(v.flags.shared)} · far from its address ${fmt(v.flags.far)} · room with a whole-home licence ${fmt(v.flags.room_with_flat_licence)}`))}
      ${tr(L("Sin número verificable públicamente", "Without a publicly verifiable number"), v.no_verifiable_pct != null ? `${pc(v.no_verifiable_pct)}${v.no_verifiable_ci ? ` <span class="muted">(${L("IC 95 %", "95% CI")} ${pc(v.no_verifiable_ci[0])}–${pc(v.no_verifiable_ci[1])})</span>` : ""}` : null)}
      ${tr(L("Puntuación de registros (R)", "Registration score (R)"), v.R != null ? `${fix(v.R, 2)} <span class="muted">= ${fix(v.contributions.invalid, 2)} + ${fix(v.contributions.unmatched, 2)} + ${fix(v.contributions.missing, 2)}${v.missing_excluded ? L(`, sobre ${fmt(v.r_assessed)} anuncios con número o posiblemente exentos`, `, over ${fmt(v.r_assessed)} listings with a number or possibly exempt`) : ""}</span>` : null)}
      ${tr(L("Fecha de los datos", "Data date"), v.date ? esc(v.date) : null)}</tbody></table>`;
    const comp = c.index == null ? "" : `<table class="ix-t ix-calc"><thead><tr><th scope="col">${L("Componente", "Component")}</th><th scope="col">${L("Medida", "Measure")}</th><th scope="col">${L("Normalizada", "Normalised")}</th><th scope="col">${L("Peso", "Weight")}</th><th scope="col">${L("Puntos", "Points")}</th></tr></thead><tbody>
      ${Object.entries(COMP).map(([kk, m]) => `<tr><th scope="row"><i class="sw ${m.cls}"></i> ${L(m.es, m.en)}</th>
        <td>${kk === "housing" ? pc(c.housing, 2) : kk === "concentration" ? num(c.concentration) : fix(c.verification.R, 2)}</td>
        <td>${fix(c.normalised[kk])}</td><td>${Math.round(R.weights[kk] * 100)}${L(" %", "%")}</td><td>${fix(c.contributions[kk])}</td></tr>`).join("")}
      <tr class="ix-total"><th scope="row" colspan="4">${L("Índice", "Index")} (${baseLabel()}, v${esc(R.version)})</th><td>${fix(c.index)}</td></tr></tbody></table>`;
    return `<div class="ix-sections">
      <section><h3>${L("Vivienda", "Housing")}</h3><table class="ix-t"><tbody>${housing}</tbody></table></section>
      <section><h3>${L("Concentración", "Concentration")}</h3><table class="ix-t"><tbody>${conc}</tbody></table></section>
      <section><h3>${L("Registros", "Registration")}</h3>${reg}</section>
      ${comp ? `<section><h3>${L("Cálculo del índice", "Index calculation")}</h3>${comp}</section>` : ""}</div>`;
  }
})();
