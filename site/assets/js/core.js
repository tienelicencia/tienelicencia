/* tienelicencia.com — shared front-end: language, header/footer, formatting, register search widget.
   Pages call TL.init({page, area}) and then use TL.t(), TL.fmt(), TL.searchWidget(), etc.
   Static text lives in the HTML as lang="es" / lang="en" pairs; dynamic text comes from STR below. */
(() => {
  const SHIFTED_LABS = "https://shiftedlabs.ai";
  const STR = {
    es: {
      nav_areas: "Zonas", nav_rank: "Ranking", nav_check: "Comprobar anuncio", nav_method: "Metodología", nav_faq: "Preguntas", menu: "Menú", city_label: "Elige tu zona", city_all: "Toda España", city_avail: "Disponibles", city_soon: "Próximamente", soon: "próximamente",
      privacy: "Privacidad y cookies", legal: "Aviso legal", cookies: "Preferencias de cookies",
      strip: "Servicio de información independiente con datos abiertos oficiales.",
      strip_b: "No es una web oficial de ninguna administración.",
      foot_about: "Un recurso gratuito para vecinos y vecinas de toda España: qué viviendas turísticas están registradas y qué anuncios no muestran un número válido, con datos abiertos y verificables. Sin publicidad ni fines comerciales.",
      foot_registers: "Registros de turismo:", foot_all_sources: "Todas las fuentes y licencias →",
      foot_contact: "Contacto y correcciones", foot_code: "Código abierto (GitHub)", foot_press: "Prensa y datos",
      foot_areas: "Zonas", foot_tools: "Herramientas", foot_sources: "Fuentes de datos",
      foot_built: "Desarrollado y mantenido sin coste por", foot_updated: "Datos actualizados el",
      foot_disclaimer: "Un número no válido es una discrepancia con el registro: no demuestra por sí solo que la vivienda no tenga permiso.",
      map: "Mapa", summary: "Resumen", check: "Comprobar anuncio", method: "Metodología",
      search_ph: "Número de licencia o dirección, p. ej. Calle Feria 70 Sevilla",
      search_ph_short: "Licencia o dirección", search_btn: "Buscar", filter_ph: "Filtrar por nombre", search_try: "Prueba:", searching: "Buscando en el registro…",
      search_error: "No se ha podido completar la búsqueda. Inténtalo de nuevo.",
      search_short: "Escribe al menos 2 caracteres.",
      res_code_found: "Registrada en el Registro de Turismo de Andalucía",
      res_code_elsewhere: "Registrada en otra provincia",
      res_code_none: "Este número no figura en el registro abierto",
      res_code_none_p: "Hemos buscado el número exacto y sus variantes habituales (VFT/VUT, ceros, dígito de control). Los registros cancelados desaparecen del registro abierto; unos pocos registros válidos tampoco se publican.",
      res_corrected: "Leído como {key}",
      res_addr_none: "No hay viviendas turísticas registradas que coincidan con esa dirección en esta zona.",
      res_addr_none_p: "Prueba solo con el nombre de la calle, sin el tipo de vía, o busca en toda la provincia.",
      res_addr_count: "{n} edificios coinciden", res_addr_count_1: "1 edificio coincide",
      res_addr_other_nums: "No hay registros en ese número exacto; se muestran los de la calle.",
      search_province: "Buscar en toda la provincia",
      res_addr_fixed: "Mostrando resultados para «{q}»", barrio: "Barrio", searching_2: "Agrupando las viviendas por edificio…", sug_flats: "{n} viv. turísticas", sug_flats_1: "1 viv. turística",
      building: "Edificio", flats_n: "{n} viviendas turísticas", flat_1: "1 vivienda turística",
      places_n: "{n} plazas", other_n: "{n} otros alojamientos", other_1: "1 otro alojamiento",
      at_number: "{n} en este número",
      see_map: "Ver en el mapa", show_all: "Ver los {n} registros", show_less: "Ver menos", loading: "Cargando…",
      th_licence: "Licencia", th_unit: "Vivienda", th_places: "Plazas", th_since: "Alta", th_type: "Tipo",
      no_unit: "Sin piso/puerta en el registro",
      u_block: "Bloque", u_portal: "Portal", u_stair: "Esc.", u_floor: "Planta", u_door: "Puerta",
      k_VUT: "Vivienda turística", k_AT: "Apartamento turístico", k_H: "Hotel / hostal", k_VTAR: "Vivienda turística rural",
      k_CR: "Casa rural", k_CTR: "Complejo rural", k_CAMP: "Camping", "k_?": "Otro",
      g_C: "Completa", g_H: "Por habitaciones",
      registered_on: "Fecha de alta", municipality: "Municipio", address: "Dirección", unit: "Vivienda", places: "Plazas",
      type: "Tipo", building_label: "Edificio",
      map_report: "¿Algo mal?", more_soon: "Más zonas próximamente", more_ask: "¿Quieres la tuya? Pídenosla",
      area_kind_city: "Municipio", area_kind_province: "Provincia", area_kind_region: "Comunidad autónoma", area_kind_island: "Isla",
      regs: "viviendas turísticas registradas", listings_bad: "de los anuncios de Airbnb no muestran un número válido",
      view_data: "Ver los datos",
    },
    en: {
      nav_areas: "Areas", nav_rank: "Ranking", nav_check: "Check an advert", nav_method: "Methodology", nav_faq: "FAQ", menu: "Menu", city_label: "Choose your area", city_all: "All of Spain", city_avail: "Available", city_soon: "Coming soon", soon: "coming soon",
      privacy: "Privacy & cookies", legal: "Legal notice", cookies: "Cookie settings",
      strip: "An independent public-information service built on official open data.",
      strip_b: "Not an official website of any administration.",
      foot_about: "A free resource for residents across Spain: which tourist flats are registered and which adverts don't display a valid number, from open, verifiable data. No advertising, no commercial purpose.",
      foot_registers: "Tourism registers:", foot_all_sources: "All sources and licences →",
      foot_contact: "Contact and corrections", foot_code: "Open source (GitHub)", foot_press: "Press and data",
      foot_areas: "Areas", foot_tools: "Tools", foot_sources: "Data sources",
      foot_built: "Built and maintained free of charge by", foot_updated: "Data updated",
      foot_disclaimer: "An invalid number is a mismatch with the register: on its own it doesn't show that a flat lacks a permit.",
      map: "Map", summary: "Summary", check: "Check an advert", method: "Methodology",
      search_ph: "Licence number or address, e.g. Calle Feria 70 Sevilla",
      search_ph_short: "Licence number or address", search_btn: "Search", filter_ph: "Filter by name", search_try: "Try:", searching: "Searching the register…",
      search_error: "The search didn't complete. Please try again.",
      search_short: "Type at least 2 characters.",
      res_code_found: "Registered in the Andalusian Tourism Register",
      res_code_elsewhere: "Registered in another province",
      res_code_none: "This number is not in the open register",
      res_code_none_p: "We searched for the exact number and its usual variants (VFT/VUT, zeros, check digit). Cancelled registrations disappear from the open register; a few valid ones are also unpublished.",
      res_corrected: "Read as {key}",
      res_addr_none: "No registered tourist flats match that address in this area.",
      res_addr_none_p: "Try just the street name, without “Calle” or “Avenida”, or search the whole province.",
      res_addr_count: "{n} buildings match", res_addr_count_1: "1 building matches",
      res_addr_other_nums: "Nothing registered at that exact number; showing the street.",
      search_province: "Search the whole province",
      res_addr_fixed: "Showing results for “{q}”", barrio: "Barrio", searching_2: "Grouping the flats by building…", sug_flats: "{n} tourist flats", sug_flats_1: "1 tourist flat",
      building: "Building", flats_n: "{n} tourist flats", flat_1: "1 tourist flat",
      places_n: "{n} guest places", other_n: "{n} other establishments", other_1: "1 other establishment",
      at_number: "{n} at this number",
      see_map: "View on map", show_all: "Show all {n} records", show_less: "Show fewer", loading: "Loading…",
      th_licence: "Licence", th_unit: "Flat", th_places: "Places", th_since: "Registered", th_type: "Type",
      no_unit: "No floor/door in the register",
      u_block: "Block", u_portal: "Entrance", u_stair: "Stair", u_floor: "Floor", u_door: "Door",
      k_VUT: "Tourist flat", k_AT: "Tourist apartment", k_H: "Hotel / hostel", k_VTAR: "Rural tourist home",
      k_CR: "Rural house", k_CTR: "Rural complex", k_CAMP: "Campsite", "k_?": "Other",
      g_C: "Whole home", g_H: "Rooms",
      registered_on: "Registered", municipality: "Municipality", address: "Address", unit: "Flat", places: "Guest places",
      type: "Type", building_label: "Building",
      map_report: "Something wrong?", more_soon: "More areas coming soon", more_ask: "Want yours? Ask us",
      area_kind_city: "Municipality", area_kind_province: "Province", area_kind_region: "Region", area_kind_island: "Island",
      regs: "registered tourist flats", listings_bad: "of Airbnb listings don't display a valid number",
      view_data: "View the data",
    },
  };

  // ---------------------------------------------------------------- language
  const qs = new URLSearchParams(location.search);
  let lang = qs.get("lang");
  if (lang === "es" || lang === "en") {
    try { localStorage.setItem("tl-lang", lang); } catch { /* private mode */ }
  } else {
    try { lang = localStorage.getItem("tl-lang"); } catch { lang = null; }
  }
  if (lang !== "es" && lang !== "en") lang = "es";
  const root = document.documentElement;
  root.dataset.lang = lang;
  root.lang = lang;
  const listeners = [];

  function t(key, vars) {
    let s = STR[lang][key] ?? STR.es[key] ?? key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
    return s;
  }
  function setLang(l) {
    if (l === lang) return;
    lang = l;
    root.dataset.lang = l;
    root.lang = l;
    try { localStorage.setItem("tl-lang", l); } catch { /* private mode */ }
    const u = new URL(location.href);
    if (u.searchParams.has("lang")) { u.searchParams.set("lang", l); history.replaceState(null, "", u); }
    applyStatic();
    listeners.forEach((f) => f(l));
    track("language_change", { to: l });
  }
  function applyStatic() {
    document.querySelectorAll("[data-t]").forEach((el) => (el.textContent = t(el.dataset.t)));
    document.querySelectorAll("[data-t-ph]").forEach((el) => (el.placeholder = t(el.dataset.tPh)));
    document.querySelectorAll("[data-t-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.tAria)));
    document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.l === lang));
    const tt = document.querySelector(`meta[name="title-${lang}"]`);
    if (tt) document.title = tt.content;
    const dd = document.querySelector(`meta[name="description-${lang}"]`);
    if (dd) document.querySelector('meta[name="description"]')?.setAttribute("content", dd.content);
  }

  // ---------------------------------------------------------------- formatting
  const loc = () => (lang === "es" ? "es-ES" : "en-GB");
  const fmt = (n) => Number(n || 0).toLocaleString(loc(), { useGrouping: "always" });
  const pct = (a, b, d = 0) => (b ? (100 * a / b).toFixed(d) : "0");
  const pctStr = (a, b, d = 0) => `${Number(pct(a, b, d)).toLocaleString(loc())}%`;
  const date = (iso, opts = { day: "numeric", month: "long", year: "numeric" }) =>
    iso ? new Date(iso).toLocaleDateString(loc(), opts) : "";
  const ymd = (s) => (s && s.length >= 8 ? date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`, { day: "numeric", month: "short", year: "numeric" }) : "");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const name = (n) => (typeof n === "string" ? n : n?.[lang] ?? n?.es ?? "");

  // ---------------------------------------------------------------- data
  const cache = {};
  const getJSON = (url) => (cache[url] ||= fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  }));
  const api = (path, params) => fetch(`/api/${path}?${new URLSearchParams(params)}`).then(async (r) => {
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(j.error || r.status), { code: j.error, status: r.status });
    return j;
  });
  const areaHref = (slug, sub = "") => `/${slug}${sub ? "/" + sub : ""}`;
  const currentArea = () => location.pathname.split("/").filter(Boolean)[0] || qs.get("area") || null;

  // ---------------------------------------------------------------- icons
  const ICON = {
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
    map: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2-6-2Z"/><path d="M9 4v14M15 6v14"/></svg>',
    menu: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 7v6M12 17v.5"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 11v6M12 7v.5"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    share: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/></svg>',
  };
  const LOGO = '<svg class="brand-mark" viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="10" fill="#0d5a46"/><path d="M8.5 19.2 20 9.6l11.5 9.6" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M12.4 17v11.6c0 1 .8 1.8 1.8 1.8h11.6c1 0 1.8-.8 1.8-1.8V17" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><path d="m15.6 23.4 3.1 3.1 5.8-6" fill="none" stroke="#e2b54a" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const WORD = '<span class="brand-word">tiene<span class="q">licencia</span><span class="tld">.com</span></span>';

  // ---------------------------------------------------------------- city picker (header)
  // Cities we're working on: shown as "coming soon" until their area exists in areas.json, then they move to the list.
  const COMING = [["barcelona", "Barcelona"], ["madrid", "Madrid"], ["valencia", "Valencia"], ["bilbao", "Bilbao"],
    ["donostia", "San Sebastián"], ["zaragoza", "Zaragoza"], ["murcia", "Murcia"], ["laspalmas", "Las Palmas de Gran Canaria"]];
  function cityPicker(A) {
    const sel = document.getElementById("city-pick");
    if (!sel) return;
    const have = new Set(A.areas.map((a) => a.slug));
    const live = A.areas.filter((a) => a.kind === "city" || a.kind === "region" || a.kind === "island");
    const cur = currentArea();
    const paint = () => {
      sel.innerHTML = `<option value="">${t("city_all")}</option>
        <optgroup label="${t("city_avail")}">${live.map((a) => `<option value="${a.slug}" ${a.slug === cur ? "selected" : ""}>${esc(name(a.name))}</option>`).join("")}</optgroup>
        <optgroup label="${t("city_soon")}">${COMING.filter(([s]) => !have.has(s)).map(([, n]) => `<option disabled>${esc(n)} · ${t("soon")}</option>`).join("")}</optgroup>`;
      if (cur && !live.some((a) => a.slug === cur)) {   // a province page: show it as the current choice
        const a = A.areas.find((x) => x.slug === cur);
        if (a) sel.insertAdjacentHTML("afterbegin", `<option value="${a.slug}" selected>${esc(name(a.name))}</option>`);
      }
    };
    paint();
    listeners.push(paint);
    sel.addEventListener("change", () => {
      track("city_pick", { area: sel.value || "spain" });
      location.href = !sel.value ? "/" : areaHref(sel.value, /\/mapa$/.test(location.pathname) ? "mapa" : /\/zonas$/.test(location.pathname) ? "zonas" : undefined);
    });
  }

  // ---------------------------------------------------------------- header / footer
  function chrome(page) {
    const h = document.getElementById("site-header");
    if (h) {
      h.outerHTML = `<a class="skip" href="#main">${lang === "es" ? "Saltar al contenido" : "Skip to content"}</a>
      <div class="gov-strip"><div class="wrap"><span data-t="strip"></span> <span class="hide-sm" data-t="strip_b"></span></div></div>
      <header class="site-header"><div class="wrap">
        <a class="brand" href="/" aria-label="tienelicencia.com — inicio">${LOGO}${WORD}</a>
        <nav class="site-nav" id="site-nav" aria-label="Principal">
          <label class="city-pick"><span class="sr-only" data-t="city_label"></span><select id="city-pick" data-t-aria="city_label"></select></label>
          <a href="/#zonas" data-t="nav_areas" ${page === "home" || page === "area" || page === "map" ? 'aria-current="page"' : ""}></a>
          <a href="/ranking" data-t="nav_rank" ${page === "ranking" ? 'aria-current="page"' : ""}></a>
          <a href="/comprobar" data-t="nav_check" ${page === "check" ? 'aria-current="page"' : ""}></a>
          <a href="/metodologia" data-t="nav_method" ${page === "method" ? 'aria-current="page"' : ""}></a>
          <a href="/preguntas" data-t="nav_faq" ${page === "faq" ? 'aria-current="page"' : ""}></a>
        </nav>
        <div class="lang" role="group" aria-label="Idioma / Language">
          <button type="button" data-l="es" aria-pressed="false" title="Español">ES</button>
          <button type="button" data-l="en" aria-pressed="false" title="English">EN</button>
        </div>
        <button class="menu-btn" type="button" aria-controls="site-nav" aria-expanded="false" data-t-aria="menu">${ICON.menu}</button>
      </div></header>`;
      document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.l)));
      const mb = document.querySelector(".menu-btn"), nav = document.getElementById("site-nav");
      mb.addEventListener("click", () => {
        const open = !nav.classList.contains("open");
        nav.classList.toggle("open", open);
        mb.setAttribute("aria-expanded", open);
      });
    }
    const f = document.getElementById("site-footer");
    if (f) {
      f.outerHTML = `<footer class="site-footer"><div class="wrap">
        <div class="foot-grid">
          <div><a class="brand" href="/">${LOGO}${WORD}</a><p data-t="foot_about"></p><p class="tiny" data-t="foot_disclaimer"></p></div>
          <div><h2 data-t="foot_areas"></h2><ul class="foot-areas" id="foot-areas"></ul></div>
          <div><h2 data-t="foot_tools"></h2>
            <ul><li><a href="/ranking" data-t="nav_rank"></a></li><li><a href="/comprobar" data-t="nav_check"></a></li>
              <li><a href="/metodologia" data-t="nav_method"></a></li><li><a href="/preguntas" data-t="nav_faq"></a></li>
              <li><a href="/metodologia#prensa" data-t="foot_press"></a></li><li><a href="/contacto" data-t="foot_contact"></a></li>
              <li><a href="https://github.com/tienelicencia/tienelicencia" target="_blank" rel="noopener" data-t="foot_code"></a></li></ul>
            <h2 style="margin-top:26px" data-t="foot_sources"></h2>
            <p class="foot-sources"><span data-t="foot_registers"></span>
              <a href="https://www.juntadeandalucia.es/organismos/turismojusticiadesregulacionyadministracionlocal/areas/turismo/registro-turismo/open-rta.html" target="_blank" rel="noopener">Andalucía</a> ·
              <a href="https://datos.comunidad.madrid/dataset/alojamientos_turisticos" target="_blank" rel="noopener">Madrid</a> ·
              <a href="https://analisi.transparenciacatalunya.cat/" target="_blank" rel="noopener">Catalunya</a> ·
              <a href="https://intranet.caib.es/opendatacataleg/" target="_blank" rel="noopener">Mallorca</a> ·
              <a href="https://dadesobertes.gva.es/" target="_blank" rel="noopener">C. Valenciana</a> ·
              <a href="https://opendata.euskadi.eus/" target="_blank" rel="noopener">Euskadi</a> ·
              <a href="https://aplicaciones.aragon.es/wturpub/" target="_blank" rel="noopener">Aragón</a> ·
              <a href="https://www.turismoregiondemurcia.es/" target="_blank" rel="noopener">Murcia</a> ·
              <a href="https://datos.canarias.es/" target="_blank" rel="noopener">Canarias</a>.
              <a href="https://insideairbnb.com/" target="_blank" rel="noopener">Inside Airbnb</a> ·
              <a href="https://www.sedecatastro.gob.es/" target="_blank" rel="noopener">© Catastro</a> ·
              <a href="https://www.ine.es/" target="_blank" rel="noopener">INE</a> ·
              <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a>.
              <a href="/metodologia#fuentes" data-t="foot_all_sources"></a></p></div>
        </div>
        <div class="foot-base">
          <span class="built-by"><span data-t="foot_built"></span> <a href="${SHIFTED_LABS}" target="_blank" rel="noopener">Shifted Labs</a></span>
          <span class="foot-legal"><a href="/privacidad" data-t="privacy"></a> · <a href="/aviso-legal" data-t="legal"></a> ·
            <a href="#" data-cookie-settings data-t="cookies"></a></span>
          <span id="foot-updated"></span>
        </div>
      </div></footer>`;
      getJSON("/data/areas.json").then((A) => {
        cityPicker(A);
        const paint = () => {
          document.getElementById("foot-areas").innerHTML = A.areas.filter((a) => a.kind !== "province")
            .map((a) => `<li><a href="${areaHref(a.slug)}">${esc(name(a.name).replace(/ \((ciudad|city)\)$/, ""))}</a></li>`).join("");
          document.getElementById("foot-updated").textContent = `${t("foot_updated")} ${date(A.built_at)}`;
        };
        paint();
        listeners.push(paint);
      }).catch(() => {});
    }
  }

  // ---------------------------------------------------------------- register rows → text
  const unit = (r) => {
    const parts = [];
    if (r.block) parts.push(`${t("u_block")} ${r.block}`);
    if (r.portal) parts.push(`${t("u_portal")} ${r.portal}`);
    if (r.stair) parts.push(`${t("u_stair")} ${r.stair}`);
    if (r.floor) parts.push(`${t("u_floor")} ${r.floor}`);
    if (r.door) parts.push(`${t("u_door")} ${r.door}`);
    return parts.join(" · ");
  };
  const addr = (r) => [r.street, r.num].filter(Boolean).join(" ");
  const kind = (r) => t(`k_${r.kind}`) + (r.kind === "VUT" && r.group === "H" ? ` (${t("g_H").toLowerCase()})` : "");
  const plural = (n, one, many) => (n === 1 ? t(one) : t(many, { n: fmt(n) }));

  /** Table of register records, grouped by street number when a building spans several. */
  function flatsTable(rows, { limit = 12, showType = false } = {}) {
    const sorted = [...rows].sort((a, b) => (!a.num - !b.num) || addr(a).localeCompare(addr(b), "es", { numeric: true })
      || String(a.block + a.portal + a.stair).localeCompare(String(b.block + b.portal + b.stair), "es", { numeric: true })
      || String(a.floor).localeCompare(String(b.floor), "es", { numeric: true })
      || String(a.door).localeCompare(String(b.door), "es", { numeric: true }));
    const groups = new Set(sorted.map(addr)).size > 1;
    const id = "ft" + Math.random().toString(36).slice(2, 8);
    let last = null, i = 0, body = "";
    for (const r of sorted) {
      const hidden = i >= limit ? " hidden" : "";
      if (groups && addr(r) !== last) {
        body += `<tr class="group"${hidden} data-row="${i}"><td colspan="${showType ? 5 : 4}">${esc(addr(r) || "—")}</td></tr>`;
        last = addr(r);
      }
      body += `<tr${hidden} data-row="${i}"><td><code>${esc(r.code)}</code></td>
        <td>${esc(unit(r)) || `<span class="muted">${t("no_unit")}</span>`}${showType || r.kind !== "VUT" ? `<div class="tiny muted">${esc(kind(r))}</div>` : ""}</td>
        <td class="n">${r.places ? fmt(r.places) : "—"}</td><td class="n hide-sm">${(r.registered || "").slice(0, 4) || "—"}</td></tr>`;
      i++;
    }
    const more = rows.length > limit ? `<button class="more" type="button" data-more="${id}" data-limit="${limit}" data-n="${rows.length}">${t("show_all", { n: fmt(rows.length) })}</button>` : "";
    return `<table class="flats" id="${id}"><thead><tr><th>${t("th_licence")}</th><th>${t("th_unit")}</th><th class="n">${t("th_places")}</th><th class="n hide-sm">${t("th_since")}</th></tr></thead>
      <tbody>${body}</tbody></table>${more}`;
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-more]");
    if (!b) return;
    const tb = document.getElementById(b.dataset.more);
    const open = b.dataset.open !== "1";
    tb.querySelectorAll("tr[data-row]").forEach((tr) => (tr.hidden = !open && +tr.dataset.row >= +b.dataset.limit));
    b.dataset.open = open ? "1" : "0";
    b.textContent = open ? t("show_less") : t("show_all", { n: fmt(+b.dataset.n) });
  });

  // ---------------------------------------------------------------- search widget
  /**
   * Mounts the licence/address search into `el`. opts: {area, onShowOnMap(result), compact}
   * Renders results under the form; "View on map" links to /<area>/mapa?b=<building id>.
   */
  function searchWidget(el, opts = {}) {
    const area = opts.area || "provincia";
    const uid = "s" + Math.random().toString(36).slice(2, 8);
    el.classList.add("search");
    el.innerHTML = `<form role="search">
        <label class="field"><span class="sr-only" data-t="search_ph"></span>${ICON.search}
          <input type="search" name="q" autocomplete="off" spellcheck="false" enterkeyhint="search" data-t-ph="${opts.compact || innerWidth < 640 ? "search_ph_short" : "search_ph"}"
            role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${uid}-list">
          <ul class="suggest" id="${uid}-list" role="listbox" hidden></ul></label>
        <button class="btn btn-primary" type="submit" data-t="search_btn"></button>
      </form>
      ${opts.compact ? "" : `<div class="hint"><span data-t="search_try"></span> ${(opts.examples || []).map((x) => `<button type="button" data-ex="${esc(x)}">${esc(x)}</button>`).join(" · ")}</div>`}
      <div class="results" aria-live="polite"></div>`;
    const form = el.querySelector("form"), input = el.querySelector("input"), out = el.querySelector(".results");
    let last = null;
    const run = async (q, a = area) => {
      q = q.trim();
      if (q.length < 2) { out.innerHTML = `<div class="empty">${t("search_short")}</div>`; return; }
      const btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      btn.classList.add("busy");
      const stop = loading(out, [t("searching"), t("searching_2")]);
      try {
        const j = await api("search", { q, area: a });
        last = { j, a };
        render();
        if (!opts.compact) {   // keep the address bar shareable too
          const u = new URL(location.href);
          u.searchParams.set("q", q);
          if (a !== area) u.searchParams.set("zona", a); else u.searchParams.delete("zona");
          history.replaceState(null, "", u);
        }
        track("search", { search_kind: j.kind, area: a, town: (j.kind === "code" ? j.rows?.[0]?.muni || j.elsewhere?.muni : j.buildings?.[0]?.muni) || "", results: j.kind === "code" ? (j.rows.length ? "found" : j.elsewhere ? "elsewhere" : "none")
          : Math.min((j.buildings || []).length, 15), corrected: !!j.corrected });
      } catch {
        out.innerHTML = `<div class="empty">${t("search_error")}</div>`;
      } finally {
        stop();
        btn.disabled = false;
        btn.classList.remove("busy");
      }
    };
    const render = () => {
      if (!last) return;
      const { j, a } = last;
      out.innerHTML = (opts.compact ? "" : shareBar(j, a)) + (j.kind === "code" ? codeResult(j, a) : addressResults(j, a));
      out.querySelector("[data-province]")?.addEventListener("click", () => run(j.q, "provincia"));
      out.querySelectorAll("[data-onmap]").forEach((b) => b.addEventListener("click", (e) => {
        if (opts.onShowOnMap && opts.onShowOnMap(JSON.parse(b.dataset.onmap))) e.preventDefault();
      }));
      opts.onResults?.(j);
    };
    // Share a search: the link re-runs it (?q=) and scrolls to this search box.
    const shareBar = (j, a) => {
      const es = lang === "es", B = j.buildings || [], r = j.rows?.[0];
      const p = new URLSearchParams({ q: j.q });
      if (a !== area) p.set("zona", a);
      const url = `https://tienelicencia.com${location.pathname}?${p}${el.id ? `#${el.id}` : ""}`;
      const where = (x) => [addr(x), x.muni].filter(Boolean).join(", ");
      const text = j.kind === "code"
        ? (r ? (es ? `${r.code} está en el Registro de Turismo de Andalucía: ${where(r)}` : `${r.code} is in the Andalusian Tourism Register: ${where(r)}`)
          : (es ? `${j.key || j.q} no aparece en el Registro de Turismo de Andalucía` : `${j.key || j.q} isn't in the Andalusian Tourism Register`))
        : B.length === 1
          ? (es ? `${B[0].vut} viviendas turísticas registradas en ${B[0].addresses[0]} (${B[0].muni})` : `${B[0].vut} registered tourist flats at ${B[0].addresses[0]} (${B[0].muni})`)
          : (es ? `Viviendas turísticas registradas: «${j.q}»` : `Registered tourist flats: “${j.q}”`);
      return `<div class="check-share" style="margin:0 0 10px">${shareButton({ url, text: `${text} · tienelicencia.com`, content: `search_${j.kind}` })}</div>`;
    };
    const mapLink = (r, a) => {
      if (r.lat == null || !r.building) return "";
      const target = a === "provincia" ? "provincia" : areaOfMuni(r.muni, r.prov);
      if (!target) return "";
      return `<a class="btn btn-ghost" href="${areaHref(target, "mapa")}?b=${encodeURIComponent(r.building)}" data-onmap='${esc(JSON.stringify({ building: r.building, lat: r.lat, lon: r.lon }))}'>${ICON.map}<span>${t("see_map")}</span></a>`;
    };
    function codeResult(j, a) {
      if (j.rows.length) {
        const r = j.rows[0];
        return `<article class="result">
          <div class="result-head"><div><span class="pill ok">${ICON.check.replace("<svg", '<svg width="12" height="12"')}${t("res_code_found")}</span>
            <div class="licence-big" style="margin-top:10px">${esc(r.code)}</div>
            ${j.variant && j.variant !== "exact" ? `<div class="meta">${t("res_corrected", { key: esc(j.key) })}</div>` : ""}</div>
            <div class="result-actions">${mapLink(r, a)}</div></div>
          <dl class="kv">
            <dt>${t("address")}</dt><dd>${esc(addr(r))}${r.postcode ? `, ${esc(r.postcode)}` : ""} ${esc(r.muni)}</dd>
            ${unit(r) ? `<dt>${t("unit")}</dt><dd>${esc(unit(r))}</dd>` : ""}
            ${r.complement ? `<dt></dt><dd class="small muted">${esc(r.complement)}</dd>` : ""}
            <dt>${t("type")}</dt><dd>${esc(kind(r))}</dd>
            <dt>${t("places")}</dt><dd>${fmt(r.places)}</dd>
            <dt>${t("registered_on")}</dt><dd>${ymd(r.registered)}</dd>
          </dl></article>`;
      }
      if (j.elsewhere) return `<article class="result"><div class="result-head"><div><span class="pill warn">${t("res_code_elsewhere")}</span>
          <div class="licence-big" style="margin-top:10px">${esc(j.elsewhere.key)}</div></div></div>
          <dl class="kv"><dt>${t("municipality")}</dt><dd>${esc(j.elsewhere.muni)}</dd></dl></article>`;
      return `<div class="empty"><b>${t("res_code_none")}</b>${j.key ? ` · <code>${esc(j.key)}</code>` : ""}<p class="small" style="margin:8px 0 0">${t("res_code_none_p")}</p></div>`;
    }
    function addressResults(j, a) {
      const B = j.buildings || [];
      if (!B.length) return `<div class="empty"><b>${t("res_addr_none")}</b><p class="small" style="margin:8px 0 0">${t("res_addr_none_p")}</p>
        ${a !== "provincia" ? `<button class="more" type="button" data-province>${t("search_province")} →</button>` : ""}</div>`;
      return (j.corrected ? `<p class="small" style="margin:0 0 4px"><b>${t("res_addr_fixed", { q: esc(j.corrected) })}</b></p>` : "")
        + `<p class="small muted" style="margin:0">${plural(B.length, "res_addr_count_1", "res_addr_count")}</p>` + B.map((b) => `<article class="result">
        <div class="result-head"><div><h3>${esc(b.addresses.slice(0, 2).join(" · ") || "—")}${b.addresses.length > 2 ? ` <span class="muted">+${b.addresses.length - 2}</span>` : ""}</h3>
          <div class="meta">${esc([b.postcode, b.muni].filter(Boolean).join(" "))} · ${plural(b.vut, "flat_1", "flats_n")}${b.places ? ` · ${t("places_n", { n: fmt(b.places) })}` : ""}${b.other ? ` · ${plural(b.other, "other_1", "other_n")}` : ""}</div></div>
          <div class="result-actions">${mapLink(b, a)}</div></div>
        ${b.number_match && b.matched < b.vut + b.other ? `<p class="small muted" style="margin:10px 0 0">${t("at_number", { n: fmt(b.matched) })}</p>` : ""}
        ${b.flats.length < b.vut + b.other
          ? `${flatsTable(b.flats.slice(0, 6), { limit: 6 })}<button class="more" type="button" data-building="${esc(b.building)}">${t("show_all", { n: fmt(b.vut + b.other) })}</button>`
          : flatsTable(b.flats, { limit: 6 })}
      </article>`).join("");
    }
    out.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-building]");
      if (!b) return;
      b.textContent = t("loading");
      track("building_show_all", { area });
      const d = await api("building", { id: b.dataset.building });
      const art = b.closest("article");
      art.querySelectorAll(".flats, .more, p.small").forEach((x) => x.remove());
      art.insertAdjacentHTML("beforeend", flatsTable(d.flats, { limit: 400 }));
    });
    // ---- street autocomplete (/api/suggest): debounced, keyboard-navigable, ignores licence numbers
    const list = el.querySelector(".suggest");
    let items = [], active = -1, seq = 0, timer = null;
    const CODE_RE = /^\s*(HUTB|ATB|VUT|VFT|VTF|VTAR|CTR|CR|A|H)\s*[-/_.\s]*[A-Z]{0,2}\s*[-/_.\s]*\d|^\s*\d+\s*$/i;
    const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
    const paintList = () => {
      list.innerHTML = items.map((it, i) => `<li role="option" id="${uid}-o${i}" aria-selected="${i === active}" data-i="${i}">
          <span class="s-name">${esc(it.name)}${it.number ? ` <span class="s-num">${esc(it.number)}</span>` : ""}</span>
          <span class="s-meta">${it.type === "barrio" ? `${t("barrio")} · ` : ""}${esc(it.muni)} · ${plural(it.vut, "sug_flats_1", "sug_flats")}</span></li>`).join("");
      list.hidden = !items.length;
      input.setAttribute("aria-expanded", String(!!items.length));
      if (active >= 0) input.setAttribute("aria-activedescendant", `${uid}-o${active}`); else input.removeAttribute("aria-activedescendant");
    };
    const choose = (i) => {
      const it = items[i];
      if (!it) return;
      track("suggestion_select", { suggestion_type: it.type || "street", area });
      if (it.type === "barrio") {      // a neighbourhood: open it on the map
        input.value = it.name;
        close();
        if (!(opts.onBarrio && opts.onBarrio(it.id, it.muni))) location.href = `${areaHref(AREA_OF_MUNI[it.muni] || "malaga", "mapa")}?barrio=${it.id}`;
        return;
      }
      const q = `${it.name}${it.number ? " " + it.number : ""}${area === "provincia" ? " " + it.muni : ""}`;
      input.value = q;
      close();
      run(q);
    };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value;
      if (CODE_RE.test(q) || q.replace(/[^a-záéíóúüñ]/gi, "").length < 3) { items = []; close(); return; }
      timer = setTimeout(async () => {
        const my = ++seq;
        try {
          const j = await api("suggest", { q, area });
          if (my !== seq) return;
          items = [...(j.barrios || []), ...(j.streets || []).map((x) => ({ ...x, number: j.number }))].slice(0, 8);
          active = -1;
          paintList();
        } catch { /* autocomplete is best-effort */ }
      }, 140);
    });
    input.addEventListener("keydown", (e) => {
      if (list.hidden || !items.length) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        paintList();
      } else if (e.key === "Enter" && active >= 0) { e.preventDefault(); choose(active); }
      else if (e.key === "Escape") close();
    });
    list.addEventListener("mousedown", (e) => { const li = e.target.closest("[data-i]"); if (li) { e.preventDefault(); choose(+li.dataset.i); } });
    input.addEventListener("blur", () => setTimeout(close, 120));
    form.addEventListener("submit", (e) => { e.preventDefault(); close(); clearTimeout(timer); seq++; run(input.value); });
    el.querySelectorAll("[data-ex]").forEach((b) => b.addEventListener("click", () => { input.value = b.dataset.ex; close(); run(b.dataset.ex); }));
    listeners.push(render);
    applyStatic();
    if (!opts.compact && qs.get("q")) {   // opened from a shared search link
      input.value = qs.get("q");
      run(qs.get("q"), qs.get("zona") || area);
      requestAnimationFrame(() => el.scrollIntoView({ block: "start" }));
    }
    return { run, input };
  }
  const AREA_OF_MUNI = { "Málaga": "malaga", "Marbella": "marbella", "Sevilla": "sevilla", "Granada": "granada", "Córdoba": "cordoba", "Cádiz": "cadiz",
    "Barcelona": "barcelona", "Bilbao": "bilbao", "Donostia / San Sebastián": "donostia", "Valencia": "valencia",
    "Murcia": "murcia", "Las Palmas de Gran Canaria": "laspalmas", "Madrid": "madrid" };
  /** Which area's map shows a register row's building: its city, else Málaga province; null elsewhere in Andalucía
      (the Andalucía map shows density only). Data built before "prov" existed is all Málaga province. */
  const AREA_OF_PROV = { MA: "provincia", SE: "provincia-sevilla", CA: "provincia-cadiz", GR: "provincia-granada", AL: "provincia-almeria",
    CO: "provincia-cordoba", HU: "provincia-huelva", JA: "provincia-jaen", IB: "mallorca" };   // (Bizkaia, Gipuzkoa: only their cities)
  const areaOfMuni = (muni, prov) => AREA_OF_MUNI[muni] || AREA_OF_PROV[prov || "MA"] || null;

  // ---------------------------------------------------------------- tooltip for charts
  let tipEl;
  function tip(el, html) {
    tipEl ||= Object.assign(document.createElement("div"), { className: "tip", role: "tooltip" });
    if (!tipEl.isConnected) document.body.appendChild(tipEl);
    const show = (x, y) => {
      tipEl.innerHTML = typeof html === "function" ? html() : html;
      tipEl.classList.add("on");
      const w = tipEl.offsetWidth;
      tipEl.style.left = `${Math.min(innerWidth - w - 8, Math.max(8, x - w / 2))}px`;
      tipEl.style.top = `${y - tipEl.offsetHeight - 12}px`;
    };
    el.addEventListener("pointermove", (e) => show(e.clientX, e.clientY));
    el.addEventListener("pointerleave", () => tipEl.classList.remove("on"));
    el.addEventListener("focus", () => { const r = el.getBoundingClientRect(); show(r.left + r.width / 2, r.top); });
    el.addEventListener("blur", () => tipEl.classList.remove("on"));
  }

  // ---------------------------------------------------------------- dot-density preview (cards, teasers)
  /** Draws preview.json points into a canvas filling `host`. mode: "licences" | "problems". */
  function preview(host, pts, { mode = "licences", pad = 14, q: Q = [.01, .99] } = {}) {
    const c = document.createElement("canvas");
    host.prepend(c);
    const draw = () => {
      const w = host.clientWidth, h = host.clientHeight, dpr = devicePixelRatio || 1;
      if (!w || !h) return;
      c.width = w * dpr; c.height = h * dpr; c.style.width = w + "px"; c.style.height = h + "px";
      const g = c.getContext("2d");
      g.scale(dpr, dpr);
      const lats = pts.map((p) => p[1]).sort((a, b) => a - b), lons = pts.map((p) => p[0]).sort((a, b) => a - b);
      const q = (arr, f) => arr[Math.floor(f * (arr.length - 1))];
      const [x0, x1, y0, y1] = [q(lons, Q[0]), q(lons, Q[1]), q(lats, Q[0]), q(lats, Q[1])];
      const k = Math.cos((y0 + y1) / 2 * Math.PI / 180);
      const s = Math.min((w - 2 * pad) / ((x1 - x0) * k || 1), (h - 2 * pad) / ((y1 - y0) || 1));
      const ox = (w - (x1 - x0) * k * s) / 2, oy = (h - (y1 - y0) * s) / 2;
      const max = Math.max(...pts.map((p) => p[2]));
      // hex spacing in px (median nearest-neighbour over a sample) sets the dot size
      const smp = pts.filter((_, i) => i % Math.ceil(pts.length / 150) === 0), nn = [];
      for (const a of smp) {
        let best = Infinity;
        for (const b of pts) if (b !== a) best = Math.min(best, Math.hypot((a[0] - b[0]) * k, a[1] - b[1]));
        nn.push(best);
      }
      nn.sort((a, b) => a - b);
      const cell = Math.max(2, nn[Math.floor(nn.length / 2)] * s);
      const css = getComputedStyle(document.documentElement);
      const green = css.getPropertyValue("--brand-2").trim() || "#128062";
      const RAMP = ["#f6c9a8", "#ee9a6a", "#e0713f", "#c2412a", "#93231b"];
      for (const [lon, lat, reg, pc] of pts) {
        const x = ox + (lon - x0) * k * s, y = h - (oy + (lat - y0) * s);
        if (x < -4 || y < -4 || x > w + 4 || y > h + 4) continue;
        if (mode === "problems" && pc >= 0) {
          g.fillStyle = RAMP[Math.min(4, Math.floor(pc / 15))];
          g.globalAlpha = .9;
          g.beginPath(); g.arc(x, y, Math.min(5, cell * .45), 0, 7); g.fill();
        } else if (reg) {
          g.fillStyle = green;
          const f = Math.sqrt(reg / max);
          g.globalAlpha = .45 + .5 * f;
          g.beginPath(); g.arc(x, y, Math.min(6, Math.max(1.3, cell * (.18 + .5 * f))), 0, 7); g.fill();
        }
      }
    };
    draw();
    new ResizeObserver(draw).observe(host);
  }

  // ---------------------------------------------------------------- analytics (Google Analytics 4, only after consent)
  // "Basic" consent: gtag.js isn't even loaded until the visitor accepts. Events never carry what was typed
  // (an address search can reveal where someone lives): only the kind of action, the area and coarse outcomes.
  const GA_ID = "G-CDN5F0PS92";
  const consentKey = "tl-consent";
  let consent = null;
  try { consent = localStorage.getItem(consentKey); } catch { /* private mode */ }
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  let gaLoaded = false;
  function loadGA() {
    if (gaLoaded) return;
    gaLoaded = true;
    gtag("js", new Date());
    gtag("config", GA_ID, { page_title: document.title, language: lang });
    const s = document.createElement("script");
    s.async = true;
    s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
    document.head.appendChild(s);
  }
  function track(name, params = {}) {
    if (consent === "granted") gtag("event", name, { language: lang, ...params });
  }
  function setConsent(v) {
    consent = v;
    try { localStorage.setItem(consentKey, v); } catch { /* private mode */ }
    document.querySelector(".consent")?.remove();
    if (v === "granted") loadGA();
  }
  function consentBanner(force) {
    if ((consent && !force) || document.querySelector(".consent")) return;
    const el = document.createElement("div");
    el.className = "consent";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", lang === "es" ? "Cookies" : "Cookies");
    el.innerHTML = `<p>${lang === "es"
      ? "Usamos cookies analíticas de Google Analytics para saber cómo se usa la web (páginas visitadas y acciones como buscar o usar el mapa, nunca lo que escribes). Solo si aceptas."
      : "We use Google Analytics cookies to see how the site is used (pages and actions such as searching or using the map, never what you type). Only if you accept."}
      <a href="/privacidad">${lang === "es" ? "Más información" : "More information"}</a></p>
      <div class="consent-actions"><button type="button" class="btn btn-ghost" data-c="denied">${lang === "es" ? "Rechazar" : "Reject"}</button>
      <button type="button" class="btn btn-primary" data-c="granted">${lang === "es" ? "Aceptar" : "Accept"}</button></div>`;
    el.querySelectorAll("[data-c]").forEach((b) => b.addEventListener("click", () => setConsent(b.dataset.c)));
    document.body.appendChild(el);
  }
  if (consent === "granted") loadGA();
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-cookie-settings]")) { e.preventDefault(); consentBanner(true); }
    const out = e.target.closest("a[href^='http']");   // outbound links (official sources, reporting channels)
    if (out && !out.href.includes(location.host)) track("outbound_click", { link_domain: new URL(out.href).hostname });
  });

  // ---------------------------------------------------------------- sharing
  /** A share button. opts: {url, text, content} — content names what is shared, for analytics. */
  function shareButton(opts = {}) {
    const url = opts.url || location.href;
    return `<button type="button" class="share-btn" data-share-url="${esc(url)}" data-share-text="${esc(opts.text || document.title)}"
      data-share-content="${esc(opts.content || "page")}" aria-haspopup="menu">${ICON.share}<span>${lang === "es" ? "Compartir" : "Share"}</span></button>`;
  }
  document.addEventListener("click", async (e) => {
    const b = e.target.closest(".share-btn");
    const menu = document.querySelector(".share-menu");
    if (!b) { if (menu && !e.target.closest(".share-menu")) menu.remove(); return; }
    e.preventDefault();
    menu?.remove();
    const url = b.dataset.shareUrl, text = b.dataset.shareText, content = b.dataset.shareContent;
    if (navigator.share && matchMedia("(pointer: coarse)").matches) {   // phones: the system share sheet
      try { await navigator.share({ title: text, text, url }); track("share", { method: "native", content }); } catch { /* cancelled */ }
      return;
    }
    const enc = encodeURIComponent;
    const items = [
      ["whatsapp", "WhatsApp", `https://wa.me/?text=${enc(`${text} ${url}`)}`],
      ["x", "X", `https://twitter.com/intent/tweet?text=${enc(text)}&url=${enc(url)}`],
      ["email", lang === "es" ? "Correo" : "Email", `mailto:?subject=${enc(text)}&body=${enc(`${text}\n\n${url}`)}`],
      ["copy", lang === "es" ? "Copiar enlace" : "Copy link", ""],
    ];
    const m = document.createElement("div");
    m.className = "share-menu";
    m.setAttribute("role", "menu");
    m.innerHTML = items.map(([k, label, href]) => href
      ? `<a role="menuitem" href="${href}" target="_blank" rel="noopener" data-m="${k}">${label}</a>`
      : `<button role="menuitem" type="button" data-m="${k}">${label}</button>`).join("");
    document.body.appendChild(m);
    const r = b.getBoundingClientRect();
    m.style.top = `${r.bottom + window.scrollY + 6}px`;
    m.style.left = `${Math.min(window.scrollX + r.left, window.scrollX + innerWidth - m.offsetWidth - 12)}px`;
    m.addEventListener("click", async (ev) => {
      const it = ev.target.closest("[data-m]");
      if (!it) return;
      track("share", { method: it.dataset.m, content });
      if (it.dataset.m === "copy") {
        try { await navigator.clipboard.writeText(url); it.textContent = lang === "es" ? "¡Copiado!" : "Copied!"; } catch { prompt("", url); }
        setTimeout(() => m.remove(), 900);
      } else m.remove();
    });
  });

  // ---------------------------------------------------------------- loading state
  /** Pulsing card with an indeterminate progress bar and step messages that advance while waiting. */
  function loading(el, steps) {
    let i = 0;
    el.innerHTML = `<div class="loading" role="status" aria-live="polite"><div class="loading-bar"><span></span></div>
      <p><span class="spinner" aria-hidden="true"></span><span class="loading-msg">${esc(steps[0])}</span></p></div>`;
    const msg = el.querySelector(".loading-msg");
    const iv = setInterval(() => {
      if (!msg.isConnected) return clearInterval(iv);
      i = Math.min(i + 1, steps.length - 1);
      msg.textContent = steps[i];
    }, 1400);
    return () => clearInterval(iv);
  }

  function init({ page } = {}) {
    chrome(page);
    applyStatic();
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => consentBanner(false));
    else consentBanner(false);
  }

  window.TL = { init, t, lang: () => lang, setLang, onLang: (f) => listeners.push(f), fmt, pct, pctStr, date, ymd, esc, name,
    getJSON, api, areaHref, areaOfMuni, AREA_OF_PROV, COMING, currentArea, ICON, searchWidget, flatsTable, unit, addr, kind, plural, tip, preview, applyStatic,
    track, shareButton, loading };
})();
