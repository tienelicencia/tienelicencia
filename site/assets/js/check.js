/* Check an advert: /api/check?url= (Airbnb / Booking.com) or ?code= (number typed by hand). The API returns reason
   codes; the wording lives here so it follows the language toggle. */
(() => {
  const { fmt, esc, ICON, areaHref } = TL;
  TL.init({ page: "check" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const $ = (s) => document.querySelector(s);
  let mode = new URLSearchParams(location.search).get("code") ? "code" : "url", last = null;

  const JUNTA_BUZON = "ma.buzonclandestinidadturistica.ctjdal@juntadeandalucia.es";
  const REPORT = {
    airbnb: "https://www.airbnb.com/neighbors",
    booking: "https://www.booking.com/content-moderation-policy/reporting-content-on-booking.html",
  };

  function setMode(m) {
    mode = m;
    document.querySelectorAll(".check-tabs [data-mode]").forEach((b) => b.setAttribute("aria-selected", b.dataset.mode === m));
    const inp = $("#check-input");
    inp.type = m === "url" ? "url" : "text";
    inp.inputMode = m === "url" ? "url" : "text";
    inp.placeholder = m === "url" ? "https://www.airbnb.es/rooms/…  ·  https://www.booking.com/hotel/es/…" : "VUT/MA/12345";
    $("#check-hint").textContent = m === "url"
      ? L("Airbnb: leemos el número automáticamente. Booking.com: te pediremos que escribas el número que muestra.", "Airbnb: we read the number automatically. Booking.com: we'll ask you to type the number it shows.")
      : L("Escribe el número tal como aparece en el anuncio. Comprobaremos también las variantes habituales (VFT/VUT, ceros).",
        "Type the number exactly as the advert shows it. We'll also try the usual variants (VFT/VUT, zeros).");
  }
  document.querySelectorAll(".check-tabs [data-mode]").forEach((b) => b.addEventListener("click", () => { setMode(b.dataset.mode); $("#check-input").focus(); }));

  $("#check-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const v = $("#check-input").value.trim();
    if (!v) return;
    const btn = e.target.querySelector("button[type=submit]"), out = $("#check-result");
    // Booking.com blocks automatic reading (bot check), so go straight to "type the number" instead of a doomed request.
    if (mode === "url" && /booking\.com/i.test(v)) {
      TL.track("check_advert", { check_mode: "url", platform: "booking", result: "needs_number" });
      setMode("code");
      $("#check-input").value = "";
      out.innerHTML = `<div class="note" style="margin-top:22px">${L("<b>Booking.com no permite leer sus anuncios automáticamente.</b> Abre el anuncio, busca el número en «Letra pequeña» o «Información legal» (empieza por VUT/MA/…) y escríbelo aquí.",
        "<b>Booking.com doesn't allow its adverts to be read automatically.</b> Open the advert, find the number under “Fine print” or “Legal information” (it starts VUT/MA/…) and type it here.")}</div>`;
      $("#check-input").focus();
      return;
    }
    btn.disabled = true;
    btn.classList.add("busy");
    const box = document.createElement("div");
    box.style.marginTop = "22px";
    out.replaceChildren(box);
    const stop = TL.loading(box, mode === "url"
      ? [L("Abriendo el anuncio en Airbnb…", "Opening the advert on Airbnb…"), L("Leyendo el número de registro que muestra…", "Reading the registration number it shows…"),
        L("Buscándolo en el registro oficial…", "Looking it up in the official register…"), L("Comparando la ubicación…", "Comparing the location…")]
      : [L("Buscando el número en el registro…", "Looking the number up in the register…"), L("Probando variantes de formato…", "Trying format variants…")]);
    try {
      last = await TL.api("check", mode === "url" ? { url: v } : { code: v });
      render();
      // Town only (the licence's, else the advert's own location line), never the advert or the number
      const town = last.licence?.muni || last.licence_muni || (last.location || "").split(",")[0].trim();
      TL.track("check_advert", { check_mode: mode, platform: last.platform || "none", result: last.reason || last.verdict, town });
    } catch (err) {
      last = null;
      const msg = { bad_url: L("Pega un enlace de un anuncio de Airbnb (…/rooms/123…) o de Booking.com (…/hotel/es/…).", "Paste an Airbnb listing link (…/rooms/123…) or a Booking.com link (…/hotel/es/…)."),
        rate_limited: L("Demasiadas comprobaciones seguidas. Espera unos minutos.", "Too many checks in a row. Please wait a few minutes."),
        unreachable: L("No hemos podido conectar con la plataforma. Inténtalo más tarde.", "We couldn't reach the platform. Please try later.") }[err.code]
        || L("No se ha podido completar la comprobación.", "The check didn't complete.");
      out.innerHTML = `<div class="empty" style="margin-top:22px">${msg}</div>`;
      TL.track("check_advert", { check_mode: mode, result: `error_${err.code || "unknown"}` });
    } finally { stop(); btn.disabled = false; btn.classList.remove("busy"); }
  });

  function render() {
    if (!last) return;
    const j = last, out = $("#check-result");
    const code = `<b>${esc(j.code || "")}</b>`;
    const d = j.distance_m != null ? fmt(Math.round(j.distance_m / 10) * 10) : null;
    // The register the number was checked against (Andalucía unless the result says otherwise)
    const RG = { Catalunya: { reg_es: "Registre de Turisme de Catalunya", reg_en: "Catalan Tourism Register", of_es: "de la Generalitat", of_en: "Generalitat",
        example: "HUTB-012345", search: "/barcelona", search_es: "nuestro buscador de Barcelona", search_en: "our Barcelona search" },
      "Illes Balears": { reg_es: "registro turístico del Consell de Mallorca", reg_en: "Consell de Mallorca tourism register", of_es: "del Consell de Mallorca", of_en: "Consell de Mallorca",
        example: "ETV/1234", search: "/mallorca", search_es: "nuestro buscador de Mallorca", search_en: "our Mallorca search" },
      "Comunitat Valenciana": { reg_es: "Registro de Turismo de la Comunitat Valenciana", reg_en: "Valencian Tourism Register", of_es: "de la Generalitat Valenciana", of_en: "Generalitat Valenciana",
        example: "CV-VUT0012345-V", search: "/valencia", search_es: "nuestro buscador de Valencia", search_en: "our Valencia search" },
      "Aragón": { reg_es: "Registro de Turismo de Aragón", reg_en: "Aragón Tourism Register", of_es: "del Gobierno de Aragón", of_en: "Government of Aragón",
        example: "VU-ZA-18-101", search: "/zaragoza", search_es: "nuestro buscador de Zaragoza", search_en: "our Zaragoza search" },
      Canarias: { reg_es: "Registro General Turístico de Canarias", reg_en: "Canary Islands tourism register", of_es: "del Gobierno de Canarias", of_en: "Canary Islands",
        example: "VV-35-1-0012345", search: "/laspalmas", search_es: "nuestro buscador de Las Palmas", search_en: "our Las Palmas search" },
      "Región de Murcia": { reg_es: "registro turístico de la Región de Murcia", reg_en: "Region of Murcia tourism register", of_es: "de la Región de Murcia", of_en: "Region of Murcia",
        example: "VV.MU.1234-1", search: "/murcia", search_es: "nuestro buscador de Murcia", search_en: "our Murcia search" },
      "Comunidad de Madrid": { reg_es: "registro de empresas turísticas de la Comunidad de Madrid", reg_en: "Comunidad de Madrid tourism register", of_es: "de la Comunidad de Madrid", of_en: "Comunidad de Madrid",
        example: "VT-12345", search: "/madrid", search_es: "nuestro buscador de Madrid", search_en: "our Madrid search" },
      "Castilla y León": { reg_es: "Registro de Turismo de Castilla y León", reg_en: "Castilla y León Tourism Register", of_es: "de la Junta de Castilla y León", of_en: "Junta de Castilla y León",
        example: "VUT 47/000123", search: "/valladolid", search_es: "nuestro buscador de Valladolid", search_en: "our Valladolid search" },
      Euskadi: { reg_es: "Registro de Empresas y Actividades Turísticas de Euskadi", reg_en: "Basque tourism register (REATE)", of_es: "del Gobierno Vasco", of_en: "Basque Government",
        example: "EBI01234", search: "/bilbao", search_es: "nuestro buscador de Bilbao", search_en: "our Bilbao search" } }[j.region]
      || { reg_es: "Registro de Turismo de Andalucía", reg_en: "Andalusian Tourism Register", of_es: "de la Junta", of_en: "Junta", andalucia: true,
        example: "VUT/MA/12345", search: "/provincia", search_es: "nuestro buscador de la provincia", search_en: "our province search" };
    const typed = j.mode === "code";
    const V = {
      valid: ["ok", ICON.check, typed ? L(`${code} está en el registro`, `${code} is in the register`) : L(`${code} está en el registro y coincide con la ubicación`, `${code} is in the register and matches the location`),
        typed ? L("Comprueba que la dirección de abajo coincide con la del anuncio.", "Check that the address below matches the advert.")
          : L(`La vivienda registrada está a unos ${d ?? "?"} m de la ubicación del anuncio (las ubicaciones de las plataformas son aproximadas).`, `The registered flat is about ${d ?? "?"} m from the advert's location (platform locations are approximate).`)],
      shared: ["shared", ICON.info, j.region === "Illes Balears" ? L(`${code} es real, pero aparece en anuncios de ${fmt(j.shared_count)} lugares distintos`, `${code} is real, but appears on listings in ${fmt(j.shared_count)} different places`)
        : L(`${code} es real, pero la usan ${fmt(j.shared_count)} anfitriones distintos`, `${code} is real, but ${fmt(j.shared_count)} different hosts use it`),
        L("Es la licencia de una sola vivienda completa y aparece en anuncios de vivienda completa de varios anfitriones, así que no puede ser válida para todos. Este anuncio puede ser el legítimo.",
          "It's the licence for a single whole dwelling and appears on entire-home listings from several hosts, so it can't be valid for all of them. This listing may be the genuine one.")],
      type_mismatch: ["warn", ICON.warn, L(`${code} existe, pero es una licencia para la vivienda completa`, `${code} exists, but it's a whole-home licence`),
        RG.andalucia ? L("Este anuncio alquila una habitación. Para alquilar habitaciones hace falta una inscripción «por habitaciones»: la licencia mostrada no encaja con lo que se anuncia.",
          "This advert lets a room. Letting rooms needs a “by rooms” registration: the licence shown doesn't fit what's advertised.")
          : L("Este anuncio alquila una habitación, y aquí la normativa no permite alquilar habitaciones con una licencia de vivienda turística: la licencia mostrada no encaja con lo que se anuncia.",
            "This advert lets a room, and the rules here don't allow letting rooms under a tourist-let licence: the licence shown doesn't fit what's advertised.")],
      far: ["warn", ICON.warn, L(`${code} existe, pero está registrada a ${d} m del anuncio`, `${code} exists, but is registered ${d} m from the advert`),
        L("Las plataformas muestran una ubicación aproximada y algunas direcciones del registro están mal situadas en el mapa, así que dejamos 800 m de margen. Más allá, la licencia puede ser de otra vivienda del mismo municipio, o la ubicación puede estar mal.",
          "Platforms show an approximate location and some register addresses are misplaced on the map, so we allow 800 m. Beyond that, the licence may belong to another flat in the same town, or a location may be wrong.")],
      other_place: ["bad", ICON.x, L(`${code} está registrada en ${esc(j.licence_muni)}, no donde está el anuncio`, `${code} is registered in ${esc(j.licence_muni)}, not where the advert is`),
        L(`El número existe, pero corresponde a una vivienda ${d ? `a ${fmt(Math.round(j.distance_m / 1000))} km` : "en otro lugar"}.`, `The number exists, but it belongs to a flat ${d ? `${fmt(Math.round(j.distance_m / 1000))} km away` : "elsewhere"}.`)],
      cancelled: ["bad", ICON.x, L(`${code} fue cancelada`, `${code} has been cancelled`),
        L(`Un documento oficial de la Junta recoge su cancelación el ${esc(j.cancel_date)}.`, `An official Junta document records its cancellation on ${esc(j.cancel_date)}.`)],
      not_in_register: ["bad", ICON.x, L(`${code} no está en el registro actual`, `${code} is not in the current register`),
        L("Hemos buscado el número exacto y sus variantes habituales. No sabemos por qué no aparece: solo vemos lo que publica hoy el registro. Puede que la inscripción se diera de baja o se cancelara, que el número del anuncio tenga una errata o que sea muy reciente.",
          "We searched for the exact number and its usual variants. We don't know why it's missing: we only see what the register publishes today. The registration may have been closed or cancelled, the number in the advert may have a typo, or it may be very recent.")],
      malformed: ["bad", ICON.x, L(`${code} no es un número de registro válido`, `${code} is not a valid registration number`),
        L("Tiene un formato incorrecto y ninguna corrección razonable coincide con el registro.", "It's malformed and no reasonable correction matches the register.")],
      possibly_exempt: ["neutral", ICON.info, L(`El anuncio no muestra un número ${RG.of_es}, pero puede no necesitarlo`, `The advert shows no ${RG.of_en} number, but may not need one`),
        [L("Parece estar en uno de los casos que no cuentan como viviendas turísticas o tienen otro registro:", "It looks like one of the cases that don't count as tourist flats or have a different registration:"),
          (j.exempt || []).map((x) => ({
            hotel: L("es un hotel u hostal (tienen otro tipo de registro)", "it's a hotel or hostel (they have a different registration)"),
            long_stay: (() => { const n = { Catalunya: 32, "Illes Balears": 31, Euskadi: 32, "Comunitat Valenciana": 11, "Comunidad de Madrid": 32, Canarias: 32, "Región de Murcia": 32, "Aragón": 32, "Castilla y León": 32 }[j.region] || 60;
              return L(`su estancia mínima es de ${n} noches o más (alquiler de temporada)`, `its minimum stay is ${n} nights or more (a seasonal let)`); })(),
            national_only: L("muestra solo un número nacional (ES…)", "it shows only a national (ES…) number"),
            seasonal_claim: L("dice ser un alquiler de temporada", "it says it's a seasonal let"),
            rural: L("es un alojamiento rural", "it's a rural property") }[x])).filter(Boolean).join("; ") + ".",
          L("No lo contamos como «sin número válido». Si crees que sí debería tenerlo, puedes comunicarlo.", "We don't count it as “no valid number”. If you think it should have one, you can still report it.")].join(" ")],
      no_number: ["bad", ICON.x, L(`El anuncio no muestra ningún número de registro ${RG.of_es}`, `The advert doesn't display any ${RG.of_en} registration number`),
        [j.number_required === false
          ? L("En la Comunidad de Madrid no es obligatorio mostrar el número en los anuncios (el Tribunal Supremo anuló esa obligación en 2018), así que esto no es un incumplimiento. Mostrarlo es buena práctica: permite comprobar que la vivienda está registrada.",
            "In the Comunidad de Madrid adverts don't have to show the number (the Supreme Court annulled that duty in 2018), so this isn't a breach. Showing it is good practice: it lets anyone check the flat is registered.")
          : L(`Las viviendas turísticas deben mostrar su número de registro (p. ej. ${RG.example}) en todos los anuncios.`, `Tourist flats must show their registration number (e.g. ${RG.example}) in every advert.`),
          j.ctc ? L("Muestra una referencia «CTC», que es de un trámite, no un número de registro.", "It shows a 'CTC' reference, which is an application number, not a registration.") : "",
          j.national_numbers?.length ? L(`Muestra un número nacional (ES…), pero no el ${RG.of_es}. El registro nacional fue anulado por el Tribunal Supremo en mayo de 2026.`, `It shows a national (ES…) number but no ${RG.of_en} number. The national register was annulled by the Supreme Court in May 2026.`) : "",
          L("Algunos alojamientos están exentos (hoteles, o alquileres de temporada largos según el plazo de cada comunidad): compruébalo antes de comunicarlo.", "Some lets are exempt (hotels, or long seasonal lets, with each region setting its own length): check before reporting.")].filter(Boolean).join(" ")],
      not_covered: ["neutral", ICON.info,
        j.place || j.region ? L(`Todavía no cubrimos ${esc(j.place || j.region)}`, `We don't cover ${esc(j.place || j.region)} yet`) : L("Todavía no cubrimos esta zona", "We don't cover this area yet"),
        [L(`Solo podemos comprobar números con el registro oficial de las zonas que ya cubrimos (de momento, Andalucía, Madrid, Barcelona, Mallorca, Valencia, Alicante, Bilbao, San Sebastián, Zaragoza, Murcia, Las Palmas de Gran Canaria y Valladolid${j.region ? `; esto parece ${esc(j.region)}` : ""}).`,
            `We can only check numbers against the official register of the areas we cover (so far, Andalucía, Madrid, Barcelona, Mallorca, Valencia, Alicante, Bilbao, San Sebastián, Zaragoza, Murcia, Las Palmas de Gran Canaria and Valladolid${j.region ? `; this looks like ${esc(j.region)}` : ""}).`),
          j.shown_text ? L(`El anuncio muestra: <code>${esc(j.shown_text)}</code>.`, `The advert shows: <code>${esc(j.shown_text)}</code>.`) : "",
          `<a href="/contacto?${new URLSearchParams({ tipo: "zona", ref: j.place || j.region || j.code || "" })}">${L("Pídenos que lleguemos a esta zona →", "Ask us to cover this area →")}</a>`].filter(Boolean).join(" ")],
      removed: ["neutral", ICON.info, L("Este anuncio ya no existe", "This advert no longer exists"), L("La plataforma devuelve que el anuncio ha sido retirado.", "The platform says the advert has been removed.")],
      blocked: ["neutral", ICON.info, L("No hemos podido leer este anuncio", "We couldn't read this advert"),
        j.platform === "booking"
          ? L("Booking.com no permite leer sus páginas de forma automática. Busca el número en la sección «Letra pequeña» o «Información legal» del anuncio, escríbelo aquí y lo comprobamos.",
            "Booking.com doesn't allow its pages to be read automatically. Find the number in the advert's “Fine print” or “Legal information” section, type it here and we'll check it.")
          : L("La plataforma no nos ha dejado ver la página. Escribe el número que aparece en el anuncio y lo comprobamos.", "The platform didn't let us see the page. Type the number shown in the advert and we'll check it.")],
      unreadable: ["neutral", ICON.info, L("No hemos podido leer este anuncio", "We couldn't read this advert"),
        L("No encontramos los datos del anuncio en la página. Escribe el número que aparece y lo comprobamos.", "We couldn't find the advert's details on the page. Type the number shown and we'll check it.")],
    };
    if (j.number_required === false && j.reason === "no_number") V.no_number[0] = "neutral";   // Madrid: not a breach
    const [tone, icon, title, body] = V[j.reason] || V.unreadable;
    const lic = j.licence;
    const where = lic ? `<h4 class="h3" style="font-size:16px;margin:4px 0 6px">${L("Dónde está registrada", "Where it is registered")}</h4>
      <dl class="kv" style="margin-top:6px">
        <dt>${L("Dirección", "Address")}</dt><dd>${esc(TL.addr(lic))}${lic.postcode ? `, ${esc(lic.postcode)}` : ""} ${esc(lic.muni)}</dd>
        ${TL.unit(lic) ? `<dt>${L("Vivienda", "Flat")}</dt><dd>${esc(TL.unit(lic))}</dd>` : ""}
        <dt>${L("Tipo", "Type")}</dt><dd>${esc(TL.kind(lic))}</dd>
        <dt>${L("Plazas", "Guest places")}</dt><dd>${fmt(lic.places)}</dd>
        <dt>${L("Alta", "Registered")}</dt><dd>${TL.ymd(lic.registered)}</dd>
      </dl>
      ${lic.lat != null && TL.areaOfMuni(lic.muni, lic.prov) ? `<p style="margin:14px 0 0"><a class="btn btn-ghost" href="${areaHref(TL.areaOfMuni(lic.muni, lic.prov), "mapa")}?b=${encodeURIComponent(lic.building)}">${ICON.map.replace("<svg", '<svg width="18" height="18"')} ${L("Ver el edificio en el mapa", "See the building on the map")}</a></p>` : ""}`
      : (j.licence_muni ? `<p class="small muted">${L("Registrada en", "Registered in")} ${esc(j.licence_muni)}.</p>` : "");
    // Report links only for a clear problem; shared and far licences may be the genuine flat.
    const bad = tone === "bad";
    const report = bad ? `<h4 class="h3" style="font-size:16px;margin:20px 0 6px">${L("Qué puedes hacer", "What you can do")}</h4>
      <ul>
        ${j.platform ? `<li>${L("Comunicarlo a la plataforma:", "Report it to the platform:")} <a href="${REPORT[j.platform]}" target="_blank" rel="noopener">${j.platform === "airbnb" ? "Airbnb" : "Booking.com"}</a>.</li>` : ""}
        ${RG.andalucia ? `<li>${L("Escribir al buzón contra la clandestinidad turística de la Junta en tu provincia", "Write to the Junta's tourism inbox for unregistered lets in your province")} (<a href="/metodologia#denunciar">${L("direcciones por provincia", "addresses by province")}</a>; ${L("Málaga", "Málaga")}: <a href="mailto:${JUNTA_BUZON}">${JUNTA_BUZON}</a>).</li>` : ""}
        <li>${L("Incluye el enlace, el número que muestra, la fecha de hoy y una captura de pantalla.", "Include the link, the number it shows, today's date and a screenshot.")}</li>
      </ul><p class="small"><a href="/metodologia#denunciar">${L("Todos los canales para comunicarlo →", "All the ways to report it →")}</a></p>` : "";
    const ctx = new URLSearchParams({ tipo: "correccion", ...(j.listing_url ? { anuncio: j.listing_url } : {}), ...(j.code ? { numero: j.code } : {}) });
    const host = ["bad", "warn", "shared", "neutral"].includes(tone) && !["removed", "blocked", "unreadable", "not_covered"].includes(j.reason)
      ? `<details class="host-help" style="margin-top:18px"><summary><b>${L("¿Es tu anuncio? Cómo resolverlo", "Is this your listing? How to fix it")}</b></summary>
        <ol style="margin:10px 0 0">
          <li>${L(`Busca tu número en el ${RG.reg_es} (`, `Look up your number in the ${RG.reg_en} (`)}<a href="${RG.search}">${L(RG.search_es, RG.search_en)}</a>${RG.andalucia ? `${L(" o el ", " or the ")}<a href="https://www.juntadeandalucia.es/organismos/turismojusticiadesregulacionyadministracionlocal/areas/turismo/registro-turismo/open-rta.html" target="_blank" rel="noopener">${L("registro abierto de la Junta", "Junta's open register")}</a>` : ""}).</li>
          <li>${L(`Compáralo con tu resolución de inscripción y corrige el número en la plataforma si no coincide (debe aparecer completo, p. ej. ${RG.example}).`, `Compare it with your registration decision (resolución de inscripción) and correct it on the platform if it differs (it must appear in full, e.g. ${RG.example}).`)}</li>
          ${RG.andalucia ? `<li>${L("Si tu vivienda ya no aparece en el registro, consulta su estado en la Delegación Territorial de Turismo de tu provincia.", "If your property no longer appears in the register, ask the Junta's tourism office in your province (Delegación Territorial de Turismo) about its status.")}</li>` : ""}
          <li>${L("Cuando el número correcto esté en el registro y en el anuncio, esta web se actualiza sola en unos días.", "Once the right number is in the register and on the advert, this site updates by itself within a few days.")}</li>
        </ol></details>` : "";
    // Share this result: the link re-runs the same check for whoever opens it (so it's always current).
    const q = j.mode === "code" ? { code: j.code || $("#check-input").value.trim() } : { url: j.listing_url };
    const shareUrl = `https://tienelicencia.com/comprobar?${new URLSearchParams(q)}`;
    const shareText = typed ? ({ ok: L(`${j.code} está en el ${RG.reg_es}`, `${j.code} is in the ${RG.reg_en}`),
      bad: L(`${j.code || q.code} no es un número válido del ${RG.reg_es}`, `${j.code || q.code} isn't a valid ${RG.reg_en} number`) }[tone]
      || L("He comprobado este número de registro", "I checked this registration number")) : { ok: L(`Este anuncio muestra un número que está en el ${RG.reg_es} (${j.code || ""})`, `This advert shows a number that's in the ${RG.reg_en} (${j.code || ""})`),
      bad: L(`Este anuncio no muestra un número de registro válido ${RG.of_es}`, `This advert doesn't show a valid ${RG.of_en} registration number`) }[tone]
      || L("He comprobado el número de registro de este anuncio", "I checked this advert's registration number");
    const share = !["removed", "blocked", "unreadable", "not_covered"].includes(j.reason) && (j.listing_url || q.code)
      ? `<div class="check-share">${TL.shareButton({ url: shareUrl, text: `${shareText} · tienelicencia.com`, content: `check_${j.reason}` })}
          <span class="tiny muted">${L("Quien abra el enlace verá la comprobación actualizada.", "Whoever opens the link sees an up-to-date check.")}</span></div>` : "";
    if (share) history.replaceState(null, "", `/comprobar?${new URLSearchParams(q)}`);
    const wrong = `<p class="small" style="margin:14px 0 0"><a href="/contacto?${ctx}">${L("¿Crees que este resultado es incorrecto? Cuéntanoslo →", "Think this result is wrong? Tell us →")}</a></p>`;
    const retry = ["blocked", "unreadable"].includes(j.reason) ? `<button class="btn btn-primary" type="button" id="to-code">${L("Escribir el número", "Type the number")}</button>` : "";
    out.innerHTML = `<div class="verdict ${tone}">
      <div class="verdict-head"><span class="icon">${icon}</span><div><h3>${title}</h3><p>${body}</p>
        ${j.corrected ? `<p class="small">${L(`Leído como ${esc(j.key)} (corrigiendo el formato).`, `Read as ${esc(j.key)} (format corrected).`)}</p>` : ""}</div></div>
      <div class="verdict-body">
        ${share}
        ${j.title ? `<p class="small muted" style="margin-bottom:12px">${esc(j.title)}${j.listing_url ? ` · <a href="${esc(j.listing_url)}" target="_blank" rel="noopener">${L("ver anuncio", "view advert")}</a>` : ""}</p>` : ""}
        ${j.shown?.length > 1 ? `<p class="small">${L("Números que muestra:", "Numbers shown:")} ${j.shown.map((c) => `<code>${esc(c)}</code>`).join(" ")}</p>` : ""}
        ${where}${report}${host}${retry}${wrong}
        <p class="tiny muted" style="margin:16px 0 0">${L("Comprobado el", "Checked")} ${new Date(j.checked_at || Date.now()).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB")} · ${L("registro del", "register of")} ${TL.date(j.register_date)}</p>
      </div></div>`;
    $("#to-code")?.addEventListener("click", () => { setMode("code"); $("#check-input").value = ""; $("#check-input").focus(); });
  }

  setMode(mode);
  const pre = new URLSearchParams(location.search);
  if (pre.get("code") || pre.get("url")) { $("#check-input").value = pre.get("code") || pre.get("url"); $("#check-form").requestSubmit(); }
  TL.onLang(() => { setMode(mode); render(); });
})();
