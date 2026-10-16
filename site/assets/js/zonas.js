/* Full ranking of an area's barrios / municipalities / postcodes. Sortable, filterable. Data: /data/<slug>/summary.json */
(() => {
  const { fmt, esc, name, getJSON, areaHref } = TL;
  const slug = TL.currentArea();
  TL.init({ page: "area" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const $ = (s) => document.querySelector(s);
  const pc = (x) => (x == null ? "—" : `${Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 })}%`);
  let A, S, M, sortKey = "vut_share", dir = -1;

  Promise.all([getJSON("/data/areas.json"), getJSON(`/data/${slug}/summary.json`), getJSON("/data/meta.json")]).then(([AA, SS, MM]) => {
    A = AA.areas.find((a) => a.slug === slug);
    if (!A) { location.replace("/"); return; }
    S = SS; M = MM;
    for (const r of S.subareas.rows) if (r.listings && r.not_valid_pct != null) {
      r.no_number_pct = 100 * (r.no_number || 0) / r.listings;
      r.bad_number_pct = 100 * (r.bad_number || 0) / r.listings;
    }
    if (!S.subareas.rows.some((r) => r.vut_share != null)) sortKey = "vut";
    paint();
    TL.onLang(paint);
    $("#rank-filter").addEventListener("input", body);
  });

  function cols() {
    const k = S.subareas.kind;
    const withListings = S.subareas.rows.some((r) => r.listings);   // barrios, and Mallorca's municipalities
    const mapLink = A.has_barrios;
    const first = { barrio: L("Barrio", "Barrio"), municipality: L("Municipio", "Municipality"), locality: L("Código postal", "Postcode") }[k];
    const c = [
      { key: "name", label: first, text: true, cell: (r) => mapLink ? `<a href="${areaHref(slug, "mapa")}?barrio=${r.id}">${esc(r.name)}</a>`
          : esc(k === "locality" ? `${r.name}${r.locality ? " · " + r.locality : ""}` : r.name) },
      { key: "vut", label: L("Viviendas turísticas registradas", "Registered tourist flats"), cell: (r) => fmt(r.vut) },
    ];
    if (k !== "locality") {
      c.push({ key: "homes", label: L("Viviendas (Catastro)", "Homes (Catastro)"), cell: (r) => r.homes ? fmt(r.homes) : "—", sm: true });
      c.push({ key: "vut_share", label: L("% registradas", "% registered"), cell: (r) => pct(r.vut_share, "brand", k === "barrio") });
    } else c.push({ key: "places", label: L("Plazas", "Guest places"), cell: (r) => fmt(r.places) });
    if (k === "municipality" && S.subareas.rows.some((r) => r.ine_homes != null)) {
      c.push({ key: "ine_homes", label: L("Anunciadas (INE)", "Advertised (INE)"), cell: (r) => r.ine_homes != null ? fmt(r.ine_homes) : "—", sm: true });
      c.push({ key: "ine_pct", label: L("% anunciadas (INE)", "% advertised (INE)"), cell: (r) => pct(r.ine_pct, "adv") });
    }
    if (withListings) {
      c.push({ key: "airbnb_entire", label: L("Anuncios Airbnb (vivienda completa)", "Airbnb listings (entire home)"), cell: (r) => fmt(r.airbnb_entire || 0), sm: true });
      c.push({ key: "airbnb_share", label: L("% anunciadas en Airbnb", "% advertised on Airbnb"), cell: (r) => pct(r.airbnb_share, "adv") });
      c.push({ key: "not_valid_pct", label: L("Anuncios sin nº válido", "Listings with no valid no."), cell: (r) => r.not_valid_pct != null ? `${Math.round(r.not_valid_pct)}%` : "—" });
      c.push({ key: "no_number_pct", label: L("· sin número", "· no number"), cell: (r) => r.no_number_pct != null ? `${Math.round(r.no_number_pct)}%` : "—", sm: true });
      c.push({ key: "bad_number_pct", label: L("· número erróneo o inexistente", "· wrong or non-existent number"), cell: (r) => r.bad_number_pct != null ? `${Math.round(r.bad_number_pct)}%` : "—", sm: true });
      if (S.subareas.rows.some((r) => r.rent1 != null)) c.push({ key: "rent1", label: L("Alquiler €/m² (último año)", "Rent €/m² (latest)"), cell: (r) => r.rent1 != null ? r.rent1.toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { minimumFractionDigits: 2 }) : "—", sm: true });
      if (S.subareas.rows.some((r) => r.rent_growth != null)) c.push({ key: "rent_growth", label: L("Subida alquiler desde 2015", "Rent rise since 2015"), cell: (r) => r.rent_growth != null ? `+${Math.round(r.rent_growth)}%` : "—" });
    }
    return c;
  }
  function pct(x, cls, mark8) {
    if (x == null) return "—";
    const w = Math.min(100, x * 1.6);
    const cap = S.cap;   // the council's cap per barrio: 8% Málaga, 10% Sevilla; none in Barcelona
    mark8 = mark8 && !!cap;
    return `<span class="pct-cell"><span class="pct-bar ${cls}"><i style="width:${w}%"></i>${mark8 ? `<b style="left:${cap * 1.6}%"></b>` : ""}</span><span class="${mark8 && x > cap ? "over" : ""}">${pc(x)}</span></span>`;
  }

  function paint() {
    const k = S.subareas.kind;
    document.title = `${L("Clasificación", "Ranking")} · ${name(A.name)} | tienelicencia.com`;
    $("#crumb-area").textContent = name(A.name);
    $("#crumb-area").href = areaHref(slug);
    $("#rank-title").textContent = { barrio: L("Todos los barrios", "Every barrio"), municipality: L("Todos los municipios", "Every municipality"),
      locality: L("Todos los códigos postales", "Every postcode") }[k] + ` · ${name(A.name)}`;
    $("#rank-lede").innerHTML = k === "barrio"
      ? L("Viviendas turísticas registradas y anuncios de Airbnb como porcentaje de todas las viviendas de cada barrio. Pulsa una columna para ordenar; pulsa un barrio para verlo en el mapa.",
        "Registered tourist flats and Airbnb listings as a share of all homes in each barrio. Click a column to sort; click a barrio to see it on the map.")
      : k === "municipality" && A.has_listings
        ? L("Viviendas turísticas registradas y anuncios de Airbnb como porcentaje de todas las viviendas de cada municipio. Pulsa una columna para ordenar; pulsa un municipio para verlo en el mapa.",
          "Registered tourist flats and Airbnb listings as a share of all homes in each municipality. Click a column to sort; click a municipality to see it on the map.")
      : k === "municipality"
        ? L("Viviendas turísticas registradas en la Junta y anunciadas en plataformas (INE) como porcentaje de todas las viviendas de cada municipio. Pulsa una columna para ordenar.",
          "Tourist flats registered with the Junta and advertised on platforms (INE) as a share of all homes in each municipality. Click a column to sort.")
        : L("Viviendas turísticas registradas por código postal.", "Registered tourist flats by postcode.");
    $("#rank-notes").innerHTML = (k === "barrio" ? L(`${S.cap ? `La línea marca el ${S.cap}&nbsp;%, el límite que usa el Ayuntamiento sobre viviendas registradas (con su propio recuento de viviendas familiares; el suyo identifica ${{ malaga: 43, sevilla: 11 }[slug]} barrios). ` : ""}No damos porcentajes para barrios con menos de 100 viviendas ni porcentaje de anuncios sin número válido con menos de ${M.min_listings_area} anuncios. Airbnb puede tener varios anuncios para una misma vivienda. «Número erróneo o inexistente»: muestra un número que no está en el registro, que nunca se ha emitido o de otro municipio. Alquiler: mediana €/m² de pisos según declaraciones de la renta (Ministerio de Vivienda), solo barrios con al menos 40 pisos alquilados; indicativo.`,
      `${S.cap ? `The line marks ${S.cap}%, the limit the council applies to registered flats (on its own count of family homes; it identifies ${{ malaga: 43, sevilla: 11 }[slug]} barrios). ` : ""}No shares for barrios with fewer than 100 homes, and no "no valid number" share below ${M.min_listings_area} listings. Airbnb can have several listings for one flat. "Wrong or non-existent number": shows a number that isn't in the register, was never issued, or belongs to another town. Rent: median €/m² for flats from tax returns (Housing Ministry), barrios with at least 40 rented flats only; indicative.`) : "")
      + " " + L("Datos indicativos: el Catastro cuenta todas las viviendas, también vacías y segundas residencias.", "Indicative figures: the Catastro counts every home, including empty and second homes.")
      + (A.ine_period && k === "municipality" ? L(` INE: periodo ${A.ine_period}; Airbnb, Booking y Vrbo sin duplicados.`, ` INE: period ${A.ine_period}; Airbnb, Booking and Vrbo, de-duplicated.`) : "");
    const C = cols();
    $("#rank").innerHTML = `<thead><tr><th class="n rank-i">#</th>${C.map((c) => `<th class="${c.text ? "" : "n"} ${c.sm ? "hide-sm" : ""}"><button type="button" data-k="${c.key}" aria-sort="${c.key === sortKey ? (dir < 0 ? "descending" : "ascending") : "none"}">${c.label}${c.key === sortKey ? (dir < 0 ? " ↓" : " ↑") : ""}</button></th>`).join("")}</tr></thead><tbody></tbody>`;
    $("#rank").querySelectorAll("[data-k]").forEach((b) => b.addEventListener("click", () => {
      const k2 = b.dataset.k;
      dir = k2 === sortKey ? -dir : (k2 === "name" ? 1 : -1);
      TL.track("ranking_sort", { column: k2, area: slug });
      sortKey = k2;
      paint();
    }));
    TL.applyStatic();
    body();
  }
  function body() {
    const C = cols(), q = $("#rank-filter").value.trim();
    const norm = (x) => String(x ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    const rows = S.subareas.rows.filter((r) => (r.vut || r.listings) && (!q || norm(`${r.name} ${r.locality || ""}`).includes(norm(q))));
    rows.sort((a, b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y, "es") : x - y) * dir;
    });
    $("#rank tbody").innerHTML = rows.map((r, i) => `<tr><td class="n rank-i">${i + 1}</td>${C.map((c) => `<td class="${c.text ? "" : "n"} ${c.sm ? "hide-sm" : ""}">${c.cell(r)}</td>`).join("")}</tr>`).join("");
    $("#rank-count").textContent = L(`${fmt(rows.length)} filas`, `${fmt(rows.length)} rows`);
  }
})();
