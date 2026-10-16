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

  Promise.all([getJSON("/data/areas.json"), getJSON("/data/malaga/summary.json"), getJSON("/data/meta.json"),
    getJSON("/data/sevilla/summary.json").catch(() => null)]).then(([A, MS, M, SS]) => {
    const paint = () => {
      stats(A, MS, M, SS);
      cards(A);
    };
    paint();
    TL.onLang(paint);
  });

  function stats(A, MS, M, SS) {
    const by = Object.fromEntries(A.areas.map((a) => [a.slug, a]));
    const LS = MS.listings, n = LS.listings, b = LS.not_valid_breakdown;
    const wrong = b.not_in_register + b.other_town + (b.cancelled || 0);
    const rows = MS.subareas.rows.filter((r) => r.vut_share != null);
    const over8 = rows.filter((r) => r.vut_share > 8).length;
    const overS = SS ? SS.subareas.rows.filter((r) => r.vut_share != null && r.vut_share > (SS.cap || 10)).length : 0;
    const SL = SS?.listings;
    const top = rows.reduce((x, y) => (y.vut_share > x.vut_share ? y : x), rows[0]);
    const mb = by.marbella, mg = by.malaga;
    const pc = (x) => `${Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 })}${TL.lang() === "es" ? " %" : "%"}`;
    const base = "https://tienelicencia.com";
    // Across every city we analyse (full lists + town samples with enough checks). Never "in Spain": only where we look.
    const full = A.areas.filter((a) => a.has_listings), samp = A.areas.filter((a) => !a.has_listings && a.sample_pct != null && a.sample_checked >= 300);
    const totL = full.reduce((x, a) => x + a.listings, 0), totNV = full.reduce((x, a) => x + a.not_valid, 0);
    const cityPcts = [...full.map((a) => `${esc(name(a.name).replace(/ \(.*\)/, ""))} ${pctStr(a.not_valid, a.listings)}`),
      ...samp.map((a) => `${esc(name(a.name).replace(/ \(.*\)/, ""))} ~${Math.round(a.sample_pct)}%`)].join(" · ");
    const nCities = full.length + samp.length;
    const SB = SS?.listings?.not_valid_breakdown;
    const wrongAll = wrong + (SB ? SB.not_in_register + SB.other_town + (SB.cancelled || 0) : 0);
    const S = [
      ["bad", pctStr(totNV, totL), L(`de los anuncios de Airbnb en las <b>${nCities} ciudades que analizamos</b> no muestran un número de registro válido`,
          `of Airbnb listings in the <b>${nCities} cities we analyse</b> don't display a valid registration number`),
        cityPcts, "/#zonas",
        L(`El ${pctStr(totNV, totL)} de los anuncios de Airbnb en las ciudades que analiza tienelicencia.com no muestran un número de registro válido`,
          `${pctStr(totNV, totL)} of Airbnb listings in the cities tienelicencia.com analyses don't display a valid registration number`)],
      ["", fmt(totL + samp.reduce((x, a) => x + a.sample_checked, 0)), L("anuncios de Airbnb analizados, uno a uno, con el registro oficial", "Airbnb listings checked one by one against the official register"),
        L(`${fmt(full.reduce((x, a) => x + (a.live_checked || 0), 0) + samp.reduce((x, a) => x + a.sample_checked, 0))} de ellos revisados en directo en la página del anuncio.`,
          `${fmt(full.reduce((x, a) => x + (a.live_checked || 0), 0) + samp.reduce((x, a) => x + a.sample_checked, 0))} of them re-checked live on the listing page.`), "/metodologia#comprobacion",
        L(`tienelicencia.com ha comprobado ${fmt(totL)} anuncios de Airbnb con el registro oficial de turismo`, `tienelicencia.com has checked ${fmt(totL)} Airbnb listings against the official tourism register`)],
      ["bad", fmt(wrongAll), L("anuncios en Málaga y Sevilla muestran <b>un número que no está en el registro</b> o que es de otro municipio", "listings in Málaga and Seville show <b>a number that isn't in the register</b> or belongs to another town"),
        L("No sabemos por qué: puede ser una baja, una errata o un número de otra vivienda.", "We don't know why: a closed registration, a typo or another flat's number."), "/malaga#sin-numero",
        L(`${fmt(wrongAll)} anuncios de Airbnb en Málaga y Sevilla muestran un número de registro que no existe o es de otro municipio`, `${fmt(wrongAll)} Airbnb listings in Málaga and Seville show a registration number that doesn't exist or belongs to another town`)],
      overS ? ["gold", fmt(over8 + overS), L(`barrios superan el <b>límite de viviendas turísticas</b> de su ayuntamiento: ${fmt(over8)} en Málaga (8&nbsp;%) y ${fmt(overS)} en Sevilla (10&nbsp;%)`,
          `barrios are above their council's <b>tourist-flat limit</b>: ${fmt(over8)} in Málaga (8%) and ${fmt(overS)} in Seville (10%)`),
        L("Indicativo: sobre las viviendas del Catastro.", "Indicative: against Catastro homes."), "/sevilla/zonas",
        L(`${fmt(over8 + overS)} barrios de Málaga y Sevilla superan el límite de viviendas turísticas de su ayuntamiento`, `${fmt(over8 + overS)} barrios in Málaga and Seville are above their council's tourist-flat limit`)] :
      ["gold", fmt(over8), L("barrios de Málaga superan el <b>8&nbsp;% de viviendas turísticas</b> registradas, el límite que usa el Ayuntamiento", "Málaga barrios are above <b>8% registered tourist flats</b>, the limit the council uses"),
        L("Indicativo: sobre las viviendas del Catastro.", "Indicative: against Catastro homes."), "/malaga/zonas",
        L(`${fmt(over8)} barrios de Málaga superan el 8 % de viviendas turísticas registradas`, `${fmt(over8)} Málaga barrios are above 8% registered tourist flats`)],
      ["gold", pc(top.vut_share), L(`de las viviendas de <b>${esc(top.name)}</b> son viviendas turísticas registradas`, `of homes in <b>${esc(top.name)}</b> are registered tourist flats`),
        L("El estudio municipal da una cifra parecida.", "The council's own study gives a similar figure."), `/malaga/mapa?barrio=${top.id}`,
        L(`El ${pc(top.vut_share)} de las viviendas de ${top.name} (Málaga) son viviendas turísticas registradas`, `${pc(top.vut_share)} of homes in ${top.name} (Málaga) are registered tourist flats`)],
      ["", pc(mb.vut_share), L(`de las viviendas de <b>Marbella</b> están registradas como turísticas, frente al ${pc(mg.vut_share)} en Málaga capital`, `of homes in <b>Marbella</b> are registered as tourist flats, against ${pc(mg.vut_share)} in Málaga city`),
        L(`Pero solo el ${pc(mb.ine_pct)} se anuncia en las grandes plataformas (INE).`, `But only ${pc(mb.ine_pct)} is advertised on the big platforms (INE).`), "/marbella",
        L(`El ${pc(mb.vut_share)} de las viviendas de Marbella están registradas como turísticas`, `${pc(mb.vut_share)} of homes in Marbella are registered as tourist flats`)],
    ];
    document.getElementById("bigstats").innerHTML = S.map(([cls, big, txt, small, href, share]) => `<div class="stat">
        <b class="${cls}">${big}</b><span>${txt}</span><small>${small} <a href="${href}" style="color:#7fd3b3">${L("Ver datos", "See data")} →</a></small>
        ${TL.shareButton({ url: base + href, text: `${share} · tienelicencia.com`, content: "home_stat" })}</div>`).join("");
    document.getElementById("bigstats-src").textContent = L(
      `Anuncios: Airbnb (Inside Airbnb, ${TL.date(M.snapshot_date)}${SS?.snapshot_date ? ` y ${TL.date(SS.snapshot_date)}` : ""}) verificados uno a uno por tienelicencia.com; ${fmt(LS.live_checked + (SL?.live_checked || 0))} revisados en directo en los últimos 45 días. Registro de Turismo de Andalucía (${TL.date(M.register_lastUpdateData)}), Catastro e INE.`,
      `Listings: Airbnb (Inside Airbnb, ${TL.date(M.snapshot_date)}${SS?.snapshot_date ? ` and ${TL.date(SS.snapshot_date)}` : ""}) checked one by one by tienelicencia.com; ${fmt(LS.live_checked + (SL?.live_checked || 0))} re-checked live in the last 45 days. Andalusian Tourism Register (${TL.date(M.register_lastUpdateData)}), Catastro and INE.`);
  }

  function cards(A) {
    document.getElementById("areas").innerHTML = A.areas.filter((a) => a.kind !== "province").map((a) => `
      <a class="card area-card" href="${areaHref(a.slug)}">
        <div class="art" data-preview="${a.slug}"></div>
        <div class="body">
          <span class="kind">${t(`area_kind_${["province", "region", "island"].includes(a.kind) ? a.kind : "city"}`)}</span>
          <h3>${esc(name(a.name))}</h3>
          <div class="stats">
            <div><b>${fmt(a.vut)}</b><span>${t("regs")}</span></div>
            ${a.has_listings ? `<div><b class="bad">${pctStr(a.not_valid, a.listings)}</b><span>${L("anuncios sin número válido", "listings without a valid number")}</span></div>`
              : a.sample_pct != null && a.sample_checked >= 300 ? `<div><b class="bad">~${Math.round(a.sample_pct)}%</b><span>${L("anuncios sin número válido (muestra)", "listings without a valid number (sample)")}</span></div>`
              : `<div><b>${fmt(a.vut_places)}</b><span>${L("plazas turísticas", "guest places")}</span></div>`}
          </div>
          <span class="go">${t("view_data")} ${ICON.arrow.replace("<svg", '<svg width="18" height="18"')}</span>
        </div>
      </a>`).join("");
    // Cities we're working on, after the live ones
    const have = new Set(A.areas.map((a) => a.slug));
    document.getElementById("areas").insertAdjacentHTML("beforeend", TL.COMING.filter(([s]) => !have.has(s)).map(([s, n]) => `
      <div class="card area-card soon">
        <div class="body">
          <span class="kind">${L("Próximamente", "Coming soon")}</span>
          <h3>${esc(n)}</h3>
          <p class="small muted">${L("Estamos preparando sus datos: registro oficial y anuncios.", "We're preparing its data: official register and listings.")}</p>
          <a class="go" href="/contacto?${new URLSearchParams({ tipo: "zona", ref: n })}">${L("Avísame / pídela", "Tell me / ask for it")} ${ICON.arrow.replace("<svg", '<svg width="18" height="18"')}</a>
        </div>
      </div>`).join(""));
    const live = A.areas.filter((a) => a.kind === "city" || a.kind === "island").map((a) => esc(name(a.name).replace(/ \(.*\)/, "")));
    const soon = TL.COMING.filter(([s]) => !have.has(s)).map(([, n]) => esc(n));
    document.getElementById("coverage-line").innerHTML = L(`<b>Disponible:</b> ${live.join(", ")} y toda Andalucía. <b>Próximamente:</b> ${soon.join(", ")}.`,
      `<b>Available:</b> ${live.join(", ")} and all of Andalucía. <b>Coming soon:</b> ${soon.join(", ")}.`);
    document.querySelectorAll("[data-preview]").forEach((el) =>
      getJSON(`/data/${el.dataset.preview}/preview.json`).then((pts) => TL.preview(el, pts, { pad: 10 })));
  }
})();
