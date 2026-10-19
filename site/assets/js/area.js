/* Area summary: key figures one by one, register search, link to the map. Data: /data/<slug>/summary.json */
(() => {
  const { t, fmt, pctStr, esc, name, getJSON, areaHref, ICON } = TL;
  const slug = TL.currentArea();
  TL.init({ page: "area" });
  const L = (es, en) => (TL.lang() === "es" ? es : en);
  const $ = (s) => document.querySelector(s);

  const COLORS = { valid: "var(--ok)", shared: "var(--shared)", far: "var(--warn)", bad: "var(--bad)", exempt: "var(--line-2)",
    no_number: "#b3261e", not_in_register: "#e07a3f", other_town: "#8a5cc2" };

  // Short legal context per area (full, sourced version on /metodologia#ley).
  const JUNTA_LAW = () => L([
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de Andalucía y <b>mostrar su número en cualquier anuncio</b>.",
      "Desde 2024–2025 los ayuntamientos pueden limitar o suspender nuevas viviendas turísticas en su municipio (Decreto 31/2024 y Decreto-ley 1/2025).",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["Every tourist flat must be in the Andalusian Tourism Register and <b>display its number in every advert</b>.",
      "Since 2024–25 councils may limit or suspend new tourist flats in their municipality (Decreto 31/2024 and Decreto-ley 1/2025).",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]);
  const LAW = {
    malaga: () => L([
      "Desde el <b>23 de agosto de 2025</b> está <b>suspendida el alta de nuevas viviendas turísticas</b> en todo el municipio, durante un máximo de tres años.",
      "Desde enero de 2025, <b>43 barrios</b> que superan el 8&nbsp;% de viviendas turísticas no admiten nuevas altas; en los demás se exige acceso independiente.",
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de Andalucía y <b>mostrar su número en cualquier anuncio</b>.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["Since <b>23 August 2025</b>, <b>new tourist-flat registrations are suspended</b> across the whole municipality, for up to three years.",
      "Since January 2025, <b>43 barrios</b> above 8% tourist flats accept no new ones; elsewhere a separate entrance is required.",
      "Every tourist flat must be in the Andalusian Tourism Register and <b>display its number in every advert</b>.",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]),
    sevilla: () => L([
      "Desde el <b>29 de octubre de 2024</b>, las viviendas turísticas no pueden superar el <b>10&nbsp;% de las viviendas de cada barrio</b>. <b>11 barrios</b> del Casco Antiguo y Triana ya lo superan y no admiten nuevas.",
      "Además de inscribirse en la Junta, una vivienda turística necesita el <b>cambio de uso urbanístico</b> del ayuntamiento. Un número válido no garantiza que lo tenga.",
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de Andalucía y <b>mostrar su número en cualquier anuncio</b>.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["Since <b>29 October 2024</b>, tourist flats may not exceed <b>10% of the homes in each barrio</b>. <b>11 barrios</b> in the old town and Triana are already above it and accept no new ones.",
      "Besides registering with the Junta, a tourist flat needs the council's <b>planning change of use</b>. A valid number doesn't guarantee it has one.",
      "Every tourist flat must be in the Andalusian Tourism Register and <b>display its number in every advert</b>.",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]),
    barcelona: () => L([
      "Toda vivienda turística debe estar inscrita en el Registre de Turisme de Catalunya y <b>mostrar su número (HUTB-…) en cualquier anuncio</b> (Ley 13/2002, art. 73.5).",
      "El Ayuntamiento ha anunciado que <b>no renovará ninguna licencia de vivienda turística en noviembre de 2028</b>, al aplicar el Decreto-ley 3/2023 de la Generalitat (que permite una prórroga).",
      "El plan especial (PEUAT) <b>no permite que crezca el número de viviendas turísticas</b> y prohíbe alquilar habitaciones a turistas en la propia vivienda.",
      "Es vivienda turística toda estancia de <b>31 días o menos</b>; solo las de más de 31 días quedan fuera."],
    ["Every tourist flat must be in the Registre de Turisme de Catalunya and <b>display its number (HUTB-…) in every advert</b> (Law 13/2002, art. 73.5).",
      "The city council has announced it <b>won't renew any tourist-flat licence in November 2028</b>, applying the Generalitat's Decree-law 3/2023 (which allows one extension).",
      "The special plan (PEUAT) <b>doesn't allow the number of tourist flats to grow</b> and bans letting rooms to tourists in one's own home.",
      "Any stay of <b>31 days or less</b> counts as a tourist let; only stays of more than 31 days fall outside."]),
    mallorca: () => L([
      "Toda vivienda turística debe estar inscrita en el registro del Consell de Mallorca y <b>mostrar su número en toda la publicidad</b> (Ley 8/2012, art. 28.3.a). Las plataformas también responden si la anuncian sin él.",
      "Se alquila la <b>vivienda completa</b>: la ley no permite contratos por habitaciones (art. 50.15).",
      "Desde abril de 2025 no se admiten <b>nuevas viviendas turísticas en edificios de pisos</b> en las Baleares, y en Mallorca está congelada la compra de nuevas plazas (Decreto-ley 4/2025).",
      "Palma declaró en 2026 <b>todo el municipio zona no apta</b> para nuevas viviendas turísticas (BOIB núm. 81, 27 de junio de 2026); las ya inscritas siguen siendo válidas.",
      "Una estancia turística no puede superar las <b>30 noches</b>; las de 31 noches o más quedan fuera (art. 50.13)."],
    ["Every tourist let must be in the Consell de Mallorca's register and <b>display its number in all advertising</b> (Law 8/2012, art. 28.3.a). Platforms are also liable if they advertise it without one.",
      "The <b>whole home</b> is let: the law doesn't allow letting by the room (art. 50.15).",
      "Since April 2025 <b>no new tourist lets are accepted in apartment blocks</b> anywhere in the Balearics, and buying new tourist places is frozen in Mallorca (Decree-law 4/2025).",
      "In 2026 Palma declared <b>the whole municipality unsuitable</b> for new tourist lets (BOIB no. 81, 27 June 2026); existing registrations remain valid.",
      "A tourist stay can't exceed <b>30 nights</b>; stays of 31 nights or more fall outside (art. 50.13)."]),
    // Palma: Mallorca's rules, with Palma's own zoning first
    palma: () => { const m = LAW.mallorca(); return [m[3], m[0], m[1], m[2], m[4]]; },
    valencia: () => L([
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de la Comunitat Valenciana y <b>mostrar su número y su ubicación exacta en toda la publicidad</b> (Ley 15/2018, art. 19.1.b). Las plataformas deben pedir un número válido (art. 62.2).",
      "Una vivienda turística se alquila <b>por 10 días o menos</b> al mismo huésped; las estancias de 11 días o más no lo son (art. 65). No se puede alquilar por habitaciones.",
      "Desde mayo de 2026, el plan urbanístico limita las viviendas turísticas al <b>2&nbsp;% de las viviendas de cada barrio</b>, solo en planta baja o primera con acceso propio en edificios residenciales. Ciutat Vella tiene un régimen propio.",
      "Las inscripciones valen cinco años y requieren un informe municipal de compatibilidad urbanística."],
    ["Every tourist flat must be in the Valencian Tourism Register and <b>display its number and exact location in all advertising</b> (Law 15/2018, art. 19.1.b). Platforms must ask for a valid number (art. 62.2).",
      "A tourist flat is let <b>for 10 days or less</b> to the same guest; stays of 11 days or more aren't tourist lets (art. 65). Letting by the room isn't allowed.",
      "Since May 2026 the city plan caps tourist flats at <b>2% of homes in each barrio</b>, only on the ground or first floor with their own entrance in residential buildings. Ciutat Vella has its own rules.",
      "Registrations last five years and need a council planning-compatibility report."]),
    zaragoza: () => L([
      "Toda vivienda de uso turístico debe estar inscrita en el Registro de Turismo de Aragón y <b>mostrar su número en toda la publicidad</b> (Decreto 1/2023, art. 17.2).",
      "Se presume uso turístico si se anuncia en canales turísticos o la estancia es de <b>un mes o menos</b> (art. 4.3). No se puede alquilar por habitaciones.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística en un edificio con comunidad de propietarios necesita su aprobación expresa.",
      "El registro de Aragón no publica coordenadas y muchas direcciones no llevan número de portal, así que en Zaragoza no hay mapa de viviendas registradas; sí se pueden buscar por número o dirección."],
    ["Every tourist flat must be in the Aragón Tourism Register and <b>display its number in all advertising</b> (Decree 1/2023, art. 17.2).",
      "Tourist use is presumed if the home is advertised on tourist channels or the stay is <b>a month or less</b> (art. 4.3). Letting by the room isn't allowed.",
      "Since 3 April 2025, a new tourist flat in a building with an owners' community needs the community's express approval.",
      "Aragón's register has no coordinates and many addresses lack a street number, so there's no map of registered flats in Zaragoza; you can still search them by number or address."]),
    alicante: () => L([
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de la Comunitat Valenciana y <b>mostrar su número y su ubicación exacta en toda la publicidad</b> (Ley 15/2018, art. 19.1.b). Las plataformas deben pedir un número válido (art. 62.2).",
      "Una vivienda turística se alquila <b>por 10 días o menos</b> al mismo huésped; las estancias de 11 días o más no lo son (art. 65). No se puede alquilar por habitaciones.",
      "Desde el <b>13 de enero de 2025</b> el Ayuntamiento tiene <b>suspendidas las nuevas licencias</b> de viviendas turísticas, ampliado en julio de 2025 a bloques de apartamentos, pensiones y albergues (como máximo hasta enero de 2027). Una modificación del Plan General que fija un máximo de plazas turísticas por distrito censal está en tramitación.",
      "Las inscripciones valen cinco años y requieren un informe municipal de compatibilidad urbanística."],
    ["Every tourist flat must be in the Valencian Tourism Register and <b>display its number and exact location in all advertising</b> (Law 15/2018, art. 19.1.b). Platforms must ask for a valid number (art. 62.2).",
      "A tourist flat is let <b>for 10 days or less</b> to the same guest; stays of 11 days or more aren't tourist lets (art. 65). Letting by the room isn't allowed.",
      "Since <b>13 January 2025</b> the city council has <b>suspended new tourist-flat licences</b>, extended in July 2025 to apartment blocks, guesthouses and hostels (until January 2027 at the latest). A change to the city plan setting a maximum of tourist places per census district is going through approval.",
      "Registrations last five years and need a council planning-compatibility report."]),
    valladolid: () => L([
      "Toda vivienda de uso turístico debe estar inscrita en el Registro de Turismo de Castilla y León y <b>mostrar su número en toda la publicidad</b> (Decreto 3/2017, art. 35.1).",
      "Se puede alquilar por habitaciones: el Tribunal Superior de Justicia de Castilla y León anuló la prohibición (art. 3.2; Orden CYT/1318/2019).",
      "La normativa de Castilla y León no fija un número de noches: tratamos como posiblemente exentas las estancias mínimas de 32 noches o más (ley estatal). Desde el 3 de abril de 2025, una nueva vivienda turística en un edificio con comunidad de propietarios necesita su aprobación.",
      "El registro de la Junta de Castilla y León solo da coordenadas de unas pocas viviendas de Valladolid, así que no hay mapa de viviendas registradas; sí se pueden buscar por número o dirección. No hemos encontrado límites municipales en Valladolid (revisado el 19/10/2026)."],
    ["Every tourist flat must be in the Castilla y León Tourism Register and <b>display its number in all advertising</b> (Decree 3/2017, art. 35.1).",
      "Letting by the room is allowed: the Castilla y León High Court annulled the ban (art. 3.2; Order CYT/1318/2019).",
      "Castilla y León's rules set no number of nights: we treat minimum stays of 32 nights or more as possibly exempt (national law). Since 3 April 2025, a new tourist flat in a building with an owners' community needs the community's approval.",
      "The Junta's register gives coordinates for only a few of Valladolid's flats, so there's no map of registered flats; you can still search them by number or address. We found no city limits in Valladolid (checked 19/10/2026)."]),
    murcia: () => L([
      "Toda vivienda de uso turístico debe estar inscrita en el registro turístico de la Región de Murcia y <b>mostrar su número en toda la publicidad</b> (Decreto 256/2019, art. 6.6). Desde el 4 de noviembre de 2026, anunciar sin número es infracción grave (Ley 3/2026).",
      "Se permite alquilar por habitaciones si el titular vive en la vivienda.",
      "La ley murciana no fija un número de noches: tratamos como posiblemente exentas las estancias mínimas de 32 noches o más (alquiler de temporada según la ley estatal)."],
    ["Every tourist flat must be in the Region of Murcia tourism register and <b>display its number in all advertising</b> (Decree 256/2019, art. 6.6). From 4 November 2026, advertising without the number is a serious infringement (Law 3/2026).",
      "Letting by the room is allowed if the holder lives in the home.",
      "Murcian law sets no number of nights: we treat minimum stays of 32 nights or more as possibly exempt (seasonal lets under national law)."]),
    laspalmas: () => L([
      "Toda vivienda vacacional debe estar inscrita en el Registro General Turístico de Canarias y <b>mostrar su número en toda la publicidad</b> (Ley 6/2025, art. 8.6). Anunciar sin número es muy grave (Ley 7/1995, art. 75.16).",
      "Desde la Ley 6/2025, una nueva vivienda vacacional necesita que el planeamiento la permita expresamente; las existentes pueden seguir al menos cinco años.",
      "Se presume uso turístico si se anuncia en canales turísticos o la estancia es de <b>31 días o menos</b> (Ley 7/2026). El alquiler por habitaciones no está prohibido."],
    ["Every holiday home must be in the Canary Islands tourism register and <b>display its number in all advertising</b> (Law 6/2025, art. 8.6). Advertising without it is very serious (Law 7/1995, art. 75.16).",
      "Since Law 6/2025, a new holiday home needs express permission in the local plan; existing ones may continue for at least five years.",
      "Tourist use is presumed if the home is advertised on tourist channels or the stay is <b>31 days or less</b> (Law 7/2026). Letting by the room isn't banned."]),
    madrid: () => L([
      "En la Comunidad de Madrid <b>no es obligatorio mostrar el número de registro en los anuncios</b>: el Tribunal Supremo anuló esa obligación en 2018 (STS 1741/2018) porque inscribirse en el registro es voluntario.",
      "Lo obligatorio es presentar una <b>declaración responsable</b> antes de alquilar; operar sin ella es muy grave (de 30.001 a 300.000&nbsp;€).",
      "En la ciudad, el Plan Reside (BOCM 22/09/2025) solo admite viviendas turísticas en planta baja o primera con acceso propio, o en edificios completos en el centro. La licencia urbanística municipal es distinta del número autonómico.",
      "La normativa madrileña no fija un número de noches: tratamos como posiblemente exentas las estancias mínimas de 32 noches o más (ley estatal)."],
    ["In the Comunidad de Madrid <b>adverts don't have to show the registration number</b>: the Supreme Court annulled that duty in 2018 (STS 1741/2018) because joining the register is voluntary.",
      "What's compulsory is filing a <b>declaración responsable</b> before letting; operating without one is very serious (€30,001–300,000).",
      "In the city, Plan Reside (BOCM 22/09/2025) only allows tourist flats on the ground or first floor with their own entrance, or in whole buildings in the centre. The council's planning licence is separate from the regional number.",
      "Madrid's rules set no number of nights: we treat minimum stays of 32 nights or more as possibly exempt (national law)."]),
    bilbao: () => L([
      "Toda vivienda turística (E…) o habitación en vivienda particular (L…) debe estar inscrita en el registro turístico de Euskadi (REATE) y <b>mostrar su número en toda la publicidad</b> (Ley 13/2016, art. 24.7; Decreto 101/2018, art. 20). Las plataformas deben comprobarlo y mostrarlo.",
      "Desde el 30 de diciembre de 2025 <b>no se pueden inscribir nuevas viviendas ni habitaciones turísticas</b> en las zonas de mercado residencial tensionado (Ley 6/2025), y Bilbao lo es.",
      "Desde 2018 el plan urbanístico solo admite viviendas turísticas en planta baja o primera, salvo con acceso independiente. Una nueva modificación (zonas de alta concentración, una por edificio) tiene aprobación provisional desde junio de 2026; aún no está en vigor.",
      "Se presume uso turístico si la vivienda se anuncia en canales turísticos o acoge estancias de <b>31 días o menos</b> dos o más veces al año (Decreto 101/2018, art. 2.4)."],
    [
      "Every tourist flat (E…) or room in a private home (L…) must be in the Basque tourism register (REATE) and <b>display its number in all advertising</b> (Law 13/2016, art. 24.7; Decree 101/2018, art. 20). Platforms must check and display it.",
      "Since 30 December 2025 <b>no new tourist flats or rooms can be registered</b> in stressed housing-market zones (Law 6/2025), and Bilbao is one.",
      "Since 2018 the city plan only allows tourist flats on the ground or first floor, unless they have their own entrance. A new change (high-concentration zones, one per building) has had provisional approval since June 2026; it isn't in force yet.",
      "Tourist use is presumed if the home is advertised on tourist channels or hosts stays of <b>31 days or less</b> twice or more a year (Decree 101/2018, art. 2.4)."]),
    donostia: () => L([
      "Toda vivienda turística (E…) o habitación en vivienda particular (L…) debe estar inscrita en el registro turístico de Euskadi (REATE) y <b>mostrar su número en toda la publicidad</b> (Ley 13/2016, art. 24.7; Decreto 101/2018, art. 20). Las plataformas deben comprobarlo y mostrarlo.",
      "Desde el 30 de diciembre de 2025 <b>no se pueden inscribir nuevas viviendas ni habitaciones turísticas</b> en las zonas de mercado residencial tensionado (Ley 6/2025), y San Sebastián lo es.",
      "La Parte Vieja no admite nuevas viviendas turísticas desde 2020, y el Ayuntamiento suspendió las nuevas licencias en 2023 (prorrogado en 2024). La nueva regulación de usos de alojamiento se aprobó definitivamente el 29 de enero de 2026.",
      "Se presume uso turístico si la vivienda se anuncia en canales turísticos o acoge estancias de <b>31 días o menos</b> dos o más veces al año (Decreto 101/2018, art. 2.4)."],
    [
      "Every tourist flat (E…) or room in a private home (L…) must be in the Basque tourism register (REATE) and <b>display its number in all advertising</b> (Law 13/2016, art. 24.7; Decree 101/2018, art. 20). Platforms must check and display it.",
      "Since 30 December 2025 <b>no new tourist flats or rooms can be registered</b> in stressed housing-market zones (Law 6/2025), and San Sebastián is one.",
      "The old town (Parte Vieja) has accepted no new tourist flats since 2020, and the council suspended new licences in 2023 (extended in 2024). The new rules on lodging uses got final approval on 29 January 2026.",
      "Tourist use is presumed if the home is advertised on tourist channels or hosts stays of <b>31 days or less</b> twice or more a year (Decree 101/2018, art. 2.4)."]),
    granada: () => L([
      "Desde julio de 2025, las viviendas turísticas no pueden superar el <b>10&nbsp;% por zona</b>. En <b>Albaicín, Centro-Sagrario, Realejo-San Matías y Fígares</b>, que ya lo superan, no se autorizan nuevas.",
      "Desde enero de 2025 están suspendidas las licencias de <b>cambio de uso</b> para nuevas viviendas turísticas mientras se tramita un cambio del PGOU.",
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de Andalucía y <b>mostrar su número en cualquier anuncio</b>.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["Since July 2025, tourist flats may not exceed <b>10% per zone</b>. In <b>Albaicín, Centro-Sagrario, Realejo-San Matías and Fígares</b>, already above it, no new ones are authorised.",
      "Since January 2025, <b>change-of-use permits</b> for new tourist flats are suspended while a planning change is processed.",
      "Every tourist flat must be in the Andalusian Tourism Register and <b>display its number in every advert</b>.",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]),
    cordoba: () => L([
      "Desde el <b>2 de abril de 2025</b> no se admiten <b>nuevas viviendas turísticas en los distritos Centro y Sur</b> (22 barrios, incluido el Casco Histórico), durante un máximo de tres años.",
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de Andalucía y <b>mostrar su número en cualquier anuncio</b>.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["Since <b>2 April 2025</b>, <b>no new tourist flats are accepted in the Centro and Sur districts</b> (22 barrios, including the old town), for up to three years.",
      "Every tourist flat must be in the Andalusian Tourism Register and <b>display its number in every advert</b>.",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]),
    cadiz: () => L([
      "Desde el <b>6 de junio de 2025</b> está <b>suspendida el alta de nuevas viviendas turísticas</b> en toda la ciudad, durante un máximo de tres años.",
      "Desde 2022 no se admiten viviendas turísticas en edificios residenciales del <b>Casco Histórico</b>; en el Ensanche Moderno, solo hasta la segunda planta.",
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de Andalucía y <b>mostrar su número en cualquier anuncio</b>.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["Since <b>6 June 2025</b>, <b>new tourist-flat registrations are suspended</b> across the whole city, for up to three years.",
      "Since 2022, tourist flats aren't allowed in residential buildings in the <b>old town</b>; in the Ensanche Moderno, only up to the second floor.",
      "Every tourist flat must be in the Andalusian Tourism Register and <b>display its number in every advert</b>.",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]),
    andalucia: () => L([
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de Andalucía y <b>mostrar su número en cualquier anuncio</b>. Anunciarla sin inscripción es una infracción grave (hasta 18.000&nbsp;€).",
      "Desde 2024–2025 los ayuntamientos pueden limitar o suspender nuevas viviendas turísticas. Tienen límites en vigor, entre otros, <b>Málaga, Sevilla, Granada, Córdoba y Cádiz</b>.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["Every tourist flat must be in the Andalusian Tourism Register and <b>display its number in every advert</b>. Advertising one without registration is a serious infringement (up to €18,000).",
      "Since 2024–25 councils may limit or suspend new tourist flats. Cities with limits in force include <b>Málaga, Sevilla, Granada, Córdoba and Cádiz</b>.",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]),
    marbella: () => L([
      "No hemos encontrado <b>ninguna limitación municipal en vigor</b> para viviendas turísticas en Marbella (octubre de 2026). El ayuntamiento anunció en 2025 un registro municipal y nuevas normas que no constan aprobadas.",
      "Toda vivienda turística debe estar inscrita en el Registro de Turismo de Andalucía y <b>mostrar su número en cualquier anuncio</b>.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["We found <b>no municipal restriction in force</b> on tourist flats in Marbella (October 2026). The council announced a municipal register and new rules in 2025; we can't find that they were adopted.",
      "Every tourist flat must be in the Andalusian Tourism Register and <b>display its number in every advert</b>.",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]),
    provincia: () => L([
      "Las normas de la Junta se aplican en toda la provincia: inscripción en el Registro de Turismo de Andalucía y <b>número visible en cualquier anuncio</b>.",
      "Desde 2024–2025 los ayuntamientos pueden limitar o suspender nuevas viviendas turísticas. <b>Málaga capital</b> es el único municipio de la provincia con límites en vigor que hemos encontrado.",
      "Desde el 3 de abril de 2025, una nueva vivienda turística necesita el voto favorable de <b>3/5 de la comunidad de propietarios</b>."],
    ["Junta rules apply across the province: registration in the Andalusian Tourism Register and <b>the number shown in every advert</b>.",
      "Since 2024–25 councils may limit or suspend new tourist flats. <b>Málaga city</b> is the only municipality in the province with limits in force that we found.",
      "Since 3 April 2025, a new tourist flat needs the approval of <b>3/5 of the owners' community</b>."]),
  };

  Promise.all([getJSON("/data/areas.json"), getJSON(`/data/${slug}/summary.json`), getJSON("/data/meta.json")]).then(([A, S, M]) => {
    const area = A.areas.find((a) => a.slug === slug);
    if (!area) { location.replace("/"); return; }
    TL.searchWidget($("#area-search"), { area: slug, examples: {
      malaga: ["VUT/MA/14434", "Calle Bolivia 121", "Avenida Juan Sebastián Elcano"],
      marbella: ["VUT/MA/86284", "Duque de Ahumada 10", "Jardines de las Golondrinas"],
      sevilla: ["VUT/SE/00624", "Calle Feria 70", "Santa Cruz"],
      barcelona: ["HUTB-002062", "Carrer de Sants 387", "Sagrada Família"],
      mallorca: ["ETV/10070", "Carrer Miramar 10 Alcúdia", "Sóller"],
      palma: ["ETV/2215", "Carrer Jeroni Pou 35", "Santa Catalina"],
      valencia: ["CV-VUT0044553-V", "Calle Paz 29", "Russafa"],
      madrid: ["VT-1234", "Calle de Atocha 20", "Embajadores"],
      bilbao: ["EBI00003", "Bidebarrieta 7", "Abando"],
      zaragoza: ["VU-ZA-19-112", "César Augusto", "50004"],
      alicante: ["CV-VUT0012345-A", "Calle San Fernando", "03002"],
      valladolid: ["47/000453", "Calle Santiago", "47001"],
      murcia: ["VV.MU.6254-1", "Sucina", "30001"],
      laspalmas: ["VV-35-1-0000750", "Calle Luis Morote 42", "35007"],
      donostia: ["ESS00009", "Zarautz 27", "Gros"],
      granada: ["VUT/GR/00283", "Calle Reyes Católicos 13", "Albaicín"],
      cordoba: ["VUT/CO/01464", "Calle Cardenal González 8", "Judería"],
      cadiz: ["VUT/CA/00615", "Calle Sagasta 97", "La Viña"],
      andalucia: ["VUT/GR/00283", "Calle Sagasta 97 Cádiz", "Nerja"],
      provincia: ["VUT/MA/86284", "Avenida del Gamonal Benalmádena", "29780 Nerja"] }[slug] });
    for (const a of [$("#map-teaser"), $("#cta-map")]) a.href = areaHref(slug, "mapa");
    if (area.has_map === false) {   // a register without coordinates (Zaragoza): nothing to put on a map
      for (const el of [$("#map-teaser"), document.querySelector(".cta-band")]) el.style.display = "none";
    }
    getJSON(`/data/${slug}/preview.json`).then((pts) => TL.preview($("#map-teaser"), pts, { mode: area.has_listings ? "licences" : "licences", pad: 12,
      q: slug === "provincia" || slug === "andalucia" ? [.01, .99] : [.06, .94] }));
    const paint = () => render(area, S, M, A);
    paint();
    TL.onLang(paint);
  }).catch(() => { $("#points").innerHTML = `<div class="empty" style="margin-top:32px">${L("No se han podido cargar los datos.", "The data could not be loaded.")}</div>`; });

  function render(area, S, M, A) {
    // The official register behind this area (Junta de Andalucía, Generalitat de Catalunya…)
    const RG = S.register || { es: "Registro de Turismo de Andalucía", en: "Andalusian Tourism Register", by_es: "la Junta", by_en: "the Junta", src: "Open RTA", seasonal_nights: 60 };
    // The council's cap on tourist flats per barrio (% of homes) and how many barrios its own count puts over it
    const CAP = S.cap,   // null where the council has no % cap (e.g. Barcelona)
      COUNCIL_OVER = { malaga: 43, sevilla: 11 }[slug];
    const R = S.registered, LS = S.listings;
    document.title = `${name(area.name)} · ${L("Viviendas turísticas", "Tourist flats")} | tienelicencia.com`;
    $("#area-name").textContent = name(area.name);
    $("#crumb-area").textContent = name(area.name);
    $("#area-updated").innerHTML = `<span class="live"></span><span>${RG.src !== "Open RTA" ? `${RG.es}` : `${RG.es}: ${TL.date(M.register_lastUpdateData)}`}</span>` +
      (LS ? `<span aria-hidden="true">·</span><span>Airbnb: Inside Airbnb ${TL.date(S.snapshot_date || M.snapshot_date)}${LS.live_checked ? ` + ${fmt(LS.live_checked)} ${L("revisados en directo", "re-checked live")}` : ""}</span>` : "");

    const P = [];   // [id, tocLabel, html]
    const after = [];   // wiring to run once the cards are in the page
    const sub = S.subareas;
    const subName = (r) => esc(sub.kind === "locality" ? `${r.name}${r.locality ? " · " + r.locality : ""}` : r.name);
    const plain = (h) => h.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
    const point = (id, toc, figure, h2, body, viz = "", src = "") => P.push([id, toc, (`
      <section class="point" id="${id}">
        <div class="idx">${String(P.length + 1).padStart(2, "0")}</div>
        <div><div class="figure">${figure}</div><h2>${h2}</h2>${body}${viz ? `<div class="viz">${viz}</div>` : ""}${src ? `<p class="src">${src}</p>` : ""}
          <div class="point-share">${TL.shareButton({ url: `https://tienelicencia.com/${slug}#${id}`,
            text: `${plain(figure.replace(/<span class="pill[^>]*>.*?<\/span>/g, ""))} ${plain(h2)} · ${name(area.name)} · tienelicencia.com`, content: `point_${id}` })}</div></div>
      </section>`).replace(/\bde el\b/g, "del")]);   // "de el Consell" → "del Consell"
    const srcReg = L(`Fuente: ${RG.es} (${RG.src}).`, `Source: ${RG.en} (${RG.src}).`);
    const srcAirbnb = LS && !LS.live_checked   // a new city, before its first live checks
      ? L(`Fuente: lista de anuncios de Airbnb de Inside Airbnb (${TL.date(S.snapshot_date || M.snapshot_date)}). Leemos el número que muestra cada anuncio y lo comprobamos en el ${RG.es}. Las revisiones en directo de esta zona empiezan ahora; hasta entonces usamos el texto de la lista. <a href="/metodologia#comprobacion">Cómo lo hacemos</a>.`,
        `Source: Airbnb listing list from Inside Airbnb (${TL.date(S.snapshot_date || M.snapshot_date)}). We read the number each listing shows and check it against the ${RG.en}. Live re-checks for this area are just starting; until then we use the list's text. <a href="/metodologia#comprobacion">How we do it</a>.`)
      : LS ? L(`Fuente: lista de anuncios de Airbnb de Inside Airbnb (${TL.date(S.snapshot_date || M.snapshot_date)}). Nuestros servidores visitan cada anuncio, leen el número que muestra y lo comprueban en el ${RG.es}: ${fmt(LS.live_checked)} de ${fmt(LS.listings)} verificados en directo en los últimos 45 días. <a href="/metodologia#comprobacion">Cómo lo hacemos</a>.`,
      `Source: Airbnb listing list from Inside Airbnb (${TL.date(S.snapshot_date || M.snapshot_date)}). Our servers visit each listing, read the number it shows and check it against the ${RG.en}: ${fmt(LS.live_checked)} of ${fmt(LS.listings)} verified live in the last 45 days. <a href="/metodologia#comprobacion">How we do it</a>.`) : "";

    // 01 registered
    const other = Object.values(R.other || {}).reduce((a, b) => a + b, 0);
    point("registradas", L("Registradas", "Registered"), `<span class="big brand">${fmt(R.vut)}</span>`,
      L(`viviendas turísticas inscritas en ${esc(name(area.name))}`, `tourist flats registered in ${esc(name(area.name))}`),
      area.restricted ? `<p>${L(`Según el ${RG.es}. Sus condiciones de uso no permiten republicar el listado, así que aquí solo damos el total y lo usamos para comprobar los números de los anuncios.`,
        `According to the ${RG.en}. Its terms of use don't allow republishing the list, so here we only give the total and use it to check the numbers listings show.`)}</p>`
      : `<p>${L(`Suman <b>${fmt(R.vut_places)} plazas</b> en <b>${fmt(R.buildings_with_vut)} edificios</b>. ${R.vut_rooms ? `${fmt(R.vut_rooms)} se alquilan por habitaciones. ` : ""}${other ? `Además hay ${fmt(other)} hoteles, apartamentos turísticos y otros alojamientos registrados.` : ""}`,
        `They add up to <b>${fmt(R.vut_places)} guest places</b> in <b>${fmt(R.buildings_with_vut)} buildings</b>. ${R.vut_rooms ? `${fmt(R.vut_rooms)} are let by the room. ` : ""}${other ? `There are also ${fmt(other)} hotels, tourist apartments and other registered establishments.` : ""}`)}</p>`,
      "", srcReg);

    // Andalucía: one card per province (each has its own page and building-level map)
    if (area.kind === "region") {
      const provs = A.areas.filter((a) => a.kind === "province").sort((x, y) => y.vut - x.vut);
      point("provincias", L("Provincias", "Provinces"), `<span class="big brand">8</span>`,
        L("provincias, cada una con su mapa edificio a edificio", "provinces, each with its own building-by-building map"),
        `<div class="prov-grid">${provs.map((p) => `<a class="prov-link" href="${areaHref(p.slug)}"><b>${esc(name(p.name).replace(/^Provincia de /, "").replace(/ province$/, ""))}</b>
          <span>${fmt(p.vut)} ${L("viviendas turísticas", "tourist flats")}${p.vut_share != null ? ` · ${String(p.vut_share).replace(".", TL.lang() === "es" ? "," : ".")}&nbsp;% ${L("de las viviendas", "of homes")}` : ""}</span></a>`).join("")}</div>`, "", srcReg);
    }

    // 02 share of homes: registered (Junta + Catastro) vs advertised (INE, all platforms; Airbnb by barrio). Indicative.
    if (R.homes) {
      const pctS = (x) => `${Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 })}${TL.lang() === "es" ? "\u00a0%" : "%"}`;
      const period = R.ine_period ? TL.date(`${R.ine_period}-01`, { month: "long", year: "numeric" }) : "";
      const isBarrio = sub.kind === "barrio";
      const byAirbnb = (sub.rows || []).some((r) => r.airbnb_share != null);   // sub-areas with Airbnb listings (barrios; Mallorca's municipalities)
      const byFrame = !byAirbnb && (sub.rows || []).some((r) => r.listings_per_100 != null);   // towns: our list of all their listings
      const advKey = byAirbnb ? "airbnb_share" : byFrame ? "listings_per_100" : "ine_pct";
      const ranked = (sub.rows || []).filter((r) => r.vut_share != null && (sub.kind !== "municipality" || r.homes >= 2000))
        .sort((x, y) => y.vut_share - x.vut_share);
      const over8 = isBarrio && CAP ? ranked.filter((r) => r.vut_share > CAP) : [];
      const top = ranked.slice(0, 10);
      const hasAdv = top.some((r) => r[advKey] != null);
      const smax = Math.max(...top.flatMap((r) => [r.vut_share, r[advKey] || 0]), 10);
      const advLabel = byAirbnb ? L("Anunciadas en Airbnb (vivienda completa)", "Advertised on Airbnb (entire home)")
        : byFrame ? L("Anuncios de Airbnb por cada 100 viviendas", "Airbnb listings per 100 homes")
        : L("Anunciadas en plataformas (INE)", "Advertised on platforms (INE)");
      point("proporcion", L("% de viviendas", "% of homes"),
        `<span class="big brand">${pctS(R.vut_share)}</span><span class="pill warn">${L("Indicativo", "Indicative")}</span>`,
        L(`de las viviendas de ${esc(name(area.name))} están registradas como turísticas`, `of homes in ${esc(name(area.name))} are registered as tourist flats`),
        `<p>${L(`<b>${fmt(R.vut)}</b> viviendas registradas en ${RG.by_es}${R.ine_homes != null ? ` y <b>${fmt(R.ine_homes)}</b> anunciadas en las tres grandes plataformas,` : ""} sobre unas ${fmt(R.homes)} viviendas según ${area.kind === "region" || area.census ? "el censo (INE)" : "el Catastro"}.`,
          `<b>${fmt(R.vut)}</b> flats registered with ${RG.by_en}${R.ine_homes != null ? ` and <b>${fmt(R.ine_homes)}</b> advertised on the three big platforms,` : ""} out of about ${fmt(R.homes)} homes ${area.kind === "region" || area.census ? "in the census (INE)" : "in the Catastro"}.`)}
         ${R.ine_homes != null ? L(" Las dos cifras miden cosas distintas: una vivienda registrada puede no estar anunciándose (o anunciarse en otro sitio), y una anunciada puede no estar registrada.",
          " The two measure different things: a registered flat may not be advertised (or advertised elsewhere), and an advertised one may not be registered.") : ""}
         ${over8.length ? L(` <b>${fmt(over8.length)} barrios superan el ${CAP}&nbsp;%</b> de viviendas registradas, el límite que usa el Ayuntamiento${COUNCIL_OVER ? ` (con su propio recuento identifica ${COUNCIL_OVER})` : ""}.`,
          ` <b>${fmt(over8.length)} barrios are above ${CAP}%</b> registered, the limit the council uses${COUNCIL_OVER ? ` (by its own count it identifies ${COUNCIL_OVER})` : ""}.`) : ""}</p>
         ${R.ine_pct != null ? (() => {
            const mx = Math.max(R.vut_share, R.ine_pct) * 1.1;
            return `<div class="compare">
              <div class="cmp-row"><span class="cmp-lab">${L(`Registradas en ${RG.by_es}`, `Registered with ${RG.by_en}`)}</span>
                <span class="track"><span class="fill" style="width:${(100 * R.vut_share / mx).toFixed(1)}%"></span></span><b>${pctS(R.vut_share)}</b></div>
              <div class="cmp-row"><span class="cmp-lab">${L(`Anunciadas en Airbnb, Booking o Vrbo (INE, ${period})`, `Advertised on Airbnb, Booking or Vrbo (INE, ${period})`)}</span>
                <span class="track"><span class="fill adv" style="width:${(100 * R.ine_pct / mx).toFixed(1)}%"></span></span><b>${pctS(R.ine_pct)}</b></div>
              <p class="small" style="margin:10px 0 0">${R.ine_pct < R.vut_share
                ? (() => {   // "of every 100 homes, about 1 … only about 1" reads oddly: use 1,000 when both round the same
                    const per = Math.round(R.vut_share) === Math.round(R.ine_pct) ? 1000 : 100, a = Math.round(R.vut_share * per / 100), b = Math.round(R.ine_pct * per / 100);
                    if (R.ine_pct >= 0.9 * R.vut_share) return L(`Es decir, se anuncian casi tantas viviendas como hay registradas: unas ${b} de cada ${fmt(per)}. Que las cifras se parezcan no significa que sean las mismas viviendas: parte de las registradas puede no anunciarse y parte de las anunciadas puede no estar registrada.`,
                      `In other words, almost as many homes are advertised as are registered: about ${b} in every ${fmt(per)}. Similar figures don't mean they're the same homes: some registered flats may not be advertised and some advertised ones may not be registered.`);
                    return L(`Es decir, de cada ${fmt(per)} viviendas, unas ${a} tienen registro turístico pero solo unas ${b} se anuncian ahora en las grandes plataformas. El resto puede estar sin uso turístico, alquilarse de otra forma o anunciarse en otras webs, y podría empezar a anunciarse sin pedir un permiso nuevo.`,
                      `In other words, of every ${fmt(per)} homes about ${a} hold a tourist registration but only about ${b} are advertised on the big platforms right now. The rest may not be in tourist use, may be let another way or advertised elsewhere, and could start advertising without any new permission.`);
                  })()
                : L("Se anuncian más viviendas de las que están registradas: parte de los anuncios no tiene registro.", "More homes are advertised than registered: some adverts have no registration.")}</p></div>`;
          })() : ""}
         <p class="small muted">${L("Indicativo, no exhaustivo: el Catastro cuenta todas las viviendas (también vacías y segundas residencias); el INE solo cubre Airbnb, Booking y Vrbo; y por barrios solo tenemos Airbnb.",
          "Indicative, not comprehensive: the Catastro counts every home (including empty and second homes); the INE only covers Airbnb, Booking and Vrbo; and by barrio we only have Airbnb.")}</p>`,
        top.length ? `<div class="legend-title" style="margin-bottom:6px">${isBarrio ? (sub.level === "district" ? L("Distritos con mayor proporción", "Districts with the highest share") : L("Barrios con mayor proporción", "Barrios with the highest share")) : L("Municipios con mayor proporción (más de 2.000 viviendas)", "Municipalities with the highest share (over 2,000 homes)")}</div>
          <div class="legend" style="margin:0 0 12px"><span><i style="background:var(--brand-2)"></i>${L("Registradas", "Registered")}</span>${hasAdv ? `<span><i style="background:var(--other)"></i>${advLabel}</span>` : ""}</div>
          <div class="hbars">${top.map((r) => `<div class="hbar pair" tabindex="0" data-tip="${esc(`${subName(r)}: ${L("registradas", "registered")} ${pctS(r.vut_share)}${r[advKey] != null ? ` · ${L("anunciadas", "advertised")} ${pctS(r[advKey])}` : ""}`)}">
            <span class="lab">${subName(r)}</span>
            <span class="tracks"><span class="track"><span class="fill" style="width:${(100 * r.vut_share / smax).toFixed(1)}%"></span>${isBarrio && CAP ? `<span class="mark" style="left:${(100 * CAP / smax).toFixed(1)}%"></span>` : ""}</span>
              ${hasAdv ? `<span class="track thin"><span class="fill adv" style="width:${(100 * (r[advKey] || 0) / smax).toFixed(1)}%"></span>${isBarrio && CAP ? `<span class="mark" style="left:${(100 * CAP / smax).toFixed(1)}%"></span>` : ""}</span>` : ""}</span>
            <span class="val">${pctS(r.vut_share)}${hasAdv && r[advKey] != null ? `<small>${pctS(r[advKey])}</small>` : ""}</span></div>`).join("")}</div>
          ${isBarrio && CAP ? `<p class="tiny muted" style="margin-top:8px"><span class="mark-key"></span> ${L(`Límite del ${CAP}&nbsp;% del Ayuntamiento (sobre viviendas registradas)`, `Council's ${CAP}% limit (on registered flats)`)}</p>` : ""}
          <p style="margin-top:14px"><a href="${areaHref(slug, "zonas")}">${isBarrio ? L("Ver la clasificación de todos los barrios →", "See the ranking of every barrio →") : sub.kind === "municipality" ? L("Ver la clasificación de todos los municipios →", "See the ranking of every municipality →") : L("Ver todos los códigos postales →", "See every postcode →")}</a></p>` : "",
        L(`Fuentes: ${RG.es}, Catastro (viviendas por edificio), INE (viviendas turísticas, estadística experimental) e Inside Airbnb.`,
          `Sources: ${RG.en}, Catastro (homes per building), INE (tourist homes, experimental statistic) and Inside Airbnb.`));
    }

    if (LS) {
      const n = LS.listings, v = LS.verdicts, b = LS.not_valid_breakdown;
      // 02 listings
      point("anuncios", L("Anuncios", "Listings"), `<span class="big">${fmt(n)}</span>`,
        area.kind === "island" ? L("anuncios de Airbnb activos en la isla", "active Airbnb listings on the island")
          : L("anuncios de Airbnb activos en el municipio", "active Airbnb listings in the municipality"),
        `<p>${L(`Solo <b>${fmt(LS.registered_vut_seen)} de las ${fmt(LS.registered_vut)}</b> viviendas registradas aparecen en Airbnb con su número. El resto puede anunciarse en otras plataformas, alquilarse directamente o no estar en uso.`,
          `Only <b>${fmt(LS.registered_vut_seen)} of the ${fmt(LS.registered_vut)}</b> registered flats appear on Airbnb with their number. The rest may advertise elsewhere, let directly or not be in use.`)}</p>`,
        bar([[L("Muestran un número del registro", "Show a number in the register"), v.VALID + v.VALID_CODE_SHARED + v.VALID_LOCATION_MISMATCH + (v.VALID_TYPE_MISMATCH || 0), COLORS.valid],
          [L("No muestran un número válido", "Don't show a valid number"), v.NOT_VALID, COLORS.bad],
          [L("Posiblemente exentos", "Possibly exempt"), v.POSSIBLY_EXEMPT, COLORS.exempt]], n)
          + `<p class="tiny muted" style="margin-top:10px;max-width:70ch">${L(`<b>Posiblemente exentos:</b> anuncios sin número de ${RG.by_es} que parecen no necesitarlo: hoteles y aparthoteles (tienen otro tipo de registro), alojamientos rurales, estancias mínimas de ${RG.seasonal_nights} noches o más (alquiler de temporada) o anuncios que solo muestran un número nacional. No los contamos como «sin número válido».`,
            `<b>Possibly exempt:</b> listings without a number from ${RG.by_en} that look like they may not need one: hotels and aparthotels (they have a different registration), rural lets, minimum stays of ${RG.seasonal_nights} nights or more (seasonal lets) or listings showing only a national number. We don't count them as “no valid number”.`)}</p>`, srcAirbnb);

      // 03 not valid
      point("sin-numero", L("Sin número válido", "No valid number"), `<span class="big bad">${pctStr(v.NOT_VALID, n)}</span>`,
        L(`de los anuncios (${fmt(v.NOT_VALID)}) no muestran un número de registro válido de ${RG.by_es}`, `of listings (${fmt(v.NOT_VALID)}) don't display a valid registration number from ${RG.by_en}`),
        `<p>${L("La mayoría simplemente no muestra ningún número. Otros muestran uno que no está en el registro hoy (no sabemos por qué: puede haberse dado de baja o tener una errata) o que pertenece a otro municipio. Es una discrepancia con el registro, <b>no demuestra por sí sola que la vivienda no tenga permiso</b>.",
          "Most simply show no number at all. Others show one that isn't in the register today (we don't know why: it may have been closed or have a typo) or that belongs to another town. It's a mismatch with the register and <b>doesn't on its own show that a flat lacks a permit</b>.")}</p>
         ${RG.number_required === false ? `<p class="callout">${L("<b>En Madrid no es obligatorio mostrar el número en los anuncios</b>: el Tribunal Supremo anuló esa obligación en 2018, porque inscribirse en el registro es voluntario (lo obligatorio es presentar la declaración responsable). Por eso esta cifra no mide incumplimientos: mide cuántos anuncios <b>no</b> muestran un número del registro, aunque hacerlo sea buena práctica y permita comprobar que la vivienda está registrada.",
           "<b>In Madrid adverts don't have to show the number</b>: the Supreme Court annulled that duty in 2018, because joining the register is voluntary (what's compulsory is filing a declaración responsable). So this figure doesn't measure breaches: it measures how many listings <b>don't</b> show a registered number, even though doing so is good practice and lets anyone check the flat is registered.")}</p>` : ""}
         ${LS.need_number_not_valid_pct != null ? `<p>${L(`Si solo contamos los anuncios que necesitan número (sin los ${fmt(v.POSSIBLY_EXEMPT)} posiblemente exentos), <b>el ${String(LS.need_number_not_valid_pct).replace(".", ",")}&nbsp;% no muestra uno válido</b>.`,
           `Counting only listings that need a number (leaving out the ${fmt(v.POSSIBLY_EXEMPT)} possibly exempt), <b>${LS.need_number_not_valid_pct}% don't display a valid one</b>.`)}</p>` : ""}`,
        bar([[L("No muestran número", "No number shown"), b.no_number, COLORS.no_number],
          [L("Número fuera del registro", "Number not in the register"), b.not_in_register + (b.cancelled || 0), COLORS.not_in_register],
          [L("Licencia de otro municipio", "Another town's licence"), b.other_town, COLORS.other_town]], v.NOT_VALID, true), srcAirbnb);

      // 04 shared licences
      point("compartidas", L("Compartidas", "Shared"), `<span class="big" style="color:var(--shared)">${fmt(v.VALID_CODE_SHARED)}</span>`,
        L("anuncios de vivienda completa usan una licencia que también usan otros anfitriones", "entire-home listings use a licence that other hosts also use"),
        `<p>${L(`Son ${fmt(LS.shared_codes)} licencias de una sola vivienda que aparecen en anuncios de vivienda completa de dos o más anfitriones distintos. El número es real, pero no puede ser válido para todos: uno de ellos puede ser el legítimo. No contamos al mismo anfitrión anunciando dos veces la misma vivienda.${area.kind === "island" ? " En Mallorca, donde una misma casa la anuncian a menudo varias agencias, solo contamos anuncios en lugares distintos (a más de 300&nbsp;m)." : ""}`,
          `That's ${fmt(LS.shared_codes)} single-dwelling licences that appear on entire-home listings from two or more different hosts. The number is real, but it can't be valid for all of them: one may be the genuine listing. The same host listing the same flat twice isn't counted.${area.kind === "island" ? " In Mallorca, where one house is often marketed by several agencies, we only count listings in different places (more than 300 m apart)." : ""}`)}</p>`, "", srcAirbnb);

      // room listings showing a whole-dwelling licence
      if (v.VALID_TYPE_MISMATCH) point("habitaciones", L("Habitaciones", "Rooms"), `<span class="big" style="color:var(--shared)">${fmt(v.VALID_TYPE_MISMATCH)}</span>`,
        L("anuncios de habitación muestran una licencia registrada para una vivienda completa", "room listings show a licence registered for a whole home"),
        `<p>${RG.src === "Open RTA" ? L("El número existe, pero esa licencia es para alquilar la vivienda entera. Para alquilar habitaciones hace falta una inscripción «por habitaciones». No lo contamos como «sin número válido», pero el número no encaja con lo que se anuncia.",
          "The number exists, but that licence is for letting the whole home. Letting rooms needs a “by rooms” registration. We don't count these as “no valid number”, but the number doesn't fit what's advertised.")
          : L("El número existe, pero esa licencia es para alquilar la vivienda entera, y aquí la normativa no permite alquilar habitaciones con ella. No lo contamos como «sin número válido», pero el número no encaja con lo que se anuncia.",
            "The number exists, but that licence is for letting the whole home, and the rules here don't allow letting rooms under it. We don't count these as “no valid number”, but the number doesn't fit what's advertised.")}</p>`, "", srcAirbnb);

      // 05 host size
      const HS = [["1", L("1 anuncio", "1 listing")], ["2-5", L("2–5 anuncios", "2–5 listings")], ["6-20", L("6–20 anuncios", "6–20 listings")], ["21+", L("21 o más", "21 or more")]];
      const hmax = Math.max(...HS.map(([k]) => LS.by_host_size[k]?.not_valid_pct || 0));
      const pct = (k) => Math.round(LS.by_host_size[k]?.not_valid_pct || 0);
      const byPct = [...HS].sort((a, b) => pct(a[0]) - pct(b[0])), lo = byPct[0], hi = byPct[byPct.length - 1];
      point("anfitriones", L("Anfitriones", "Hosts"), `<span class="big">${pct(lo[0])}–${pct(hi[0])}%</span>`,
        L("de anuncios sin número válido, según cuántos anuncios tiene el anfitrión", "of listings without a valid number, depending on how many listings the host has"),
        `<p>${L(`El porcentaje más bajo es el de anfitriones con ${lo[1]} (${pct(lo[0])}%) y el más alto, el de anfitriones con ${hi[1]} (${pct(hi[0])}%).`,
          `The lowest share is for hosts with ${lo[1]} (${pct(lo[0])}%) and the highest for hosts with ${hi[1]} (${pct(hi[0])}%).`)}</p>`,
        `<div class="hbars">${HS.map(([k, lab]) => { const h = LS.by_host_size[k] || { n: 0, not_valid_pct: 0 }; return `
          <div class="hbar" tabindex="0" data-tip="${esc(`${lab}: ${fmt(h.n)} ${L("anuncios", "listings")}`)}"><span class="lab">${lab}</span>
            <span class="track"><span class="fill bad" style="width:${(100 * h.not_valid_pct / (hmax || 1)).toFixed(1)}%"></span></span>
            <span class="val">${Math.round(h.not_valid_pct)}%</span></div>`; }).join("")}</div>
          <p class="tiny muted" style="margin-top:10px">${L("Porcentaje de anuncios sin número válido, según cuántos anuncios tiene el anfitrión.", "Share of listings without a valid number, by how many listings the host has.")}</p>`, srcAirbnb);
    }

    // where: barrios / postcodes / municipalities
    const rows = sub.rows;
    const kindName = { barrio: sub.level === "district" ? L("distrito", "district") : L("barrio", "barrio"), locality: L("código postal", "postcode"), municipality: L("municipio", "municipality") }[sub.kind];
    // Cities without Inside Airbnb data but with official barrios: Airbnb listings per barrio from our own complete list
    // of the city's listings (locations only), and the live-checked sample's result where a barrio has enough of it
    const FR = !LS && sub.kind === "barrio" && rows.some((r) => r.listings != null);
    const located = rows.some((r) => r.vut != null);   // registered flats per barrio need the register's coordinates
    const the = sub.level === "district" ? L("el distrito ", "the district of ") : L("el barrio ", "the barrio of ");
    const sinDatos = `<span class="muted">${L("sin datos", "no data")}</span>`;
    const nf1 = (x) => Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 });
    const byListings = !located && rows.some((r) => r.listings);   // no registered flats by barrio: describe where the listings are
    const top = byListings ? [...rows].sort((a, b) => (b.listings || 0) - (a.listings || 0))[0] : rows[0];
    const frameN = FR ? (S.sample || {}).frame || rows.reduce((a, r) => a + (r.listings || 0), 0) : 0;
    const share = !top ? 0 : byListings ? Math.round(100 * top.listings / ((LS ? LS.listings : frameN) || 1)) : Math.round(100 * top.vut / R.vut);
    const maxV = Math.max(...rows.map((r) => r.vut || 0), 1);
    const withPct = rows.filter((r) => r.not_valid_pct != null);
    const hasShare = rows.some((r) => r.vut_share != null);
    const shareCell = (r) => hasShare ? `<td class="n hide-sm">${r.vut_share != null ? `${CAP && r.vut_share > CAP && sub.kind === "barrio" ? "<b>" : ""}${Number(r.vut_share).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 })}%${CAP && r.vut_share > CAP && sub.kind === "barrio" ? "</b>" : ""}` : "—"}</td>` : "";
    const tableRows = (list) => list.map((r) => `<tr><td>${subName(r)}</td><td class="n">${r.vut != null ? fmt(r.vut) : sinDatos}</td>${shareCell(r)}
        ${LS ? `<td class="n hide-sm">${fmt(r.listings)}</td><td class="n">${r.not_valid_pct != null ? Math.round(r.not_valid_pct) + "%" : "—"}</td>
          <td class="bar-cell hide-sm"><div class="mini">${r.not_valid_pct != null ? `<i style="width:${Math.min(100, r.not_valid_pct * 1.6)}%"></i>` : ""}</div></td>`
        : FR ? `<td class="n hide-sm">${fmt(r.listings || 0)}</td><td class="n hide-sm">${r.listings_per_100 != null ? nf1(r.listings_per_100) : "—"}</td>
          <td class="n">${r.not_valid_pct != null ? Math.round(r.not_valid_pct) + "%" : "—"}</td>`
        : `<td class="n hide-sm">${fmt(r.places)}</td><td class="bar-cell hide-sm"><div class="mini"><i class="brand" style="width:${(100 * r.vut / maxV).toFixed(1)}%"></i></div></td>`}</tr>`).join("");
    const head = `<tr><th>${kindName[0].toUpperCase() + kindName.slice(1)}</th><th class="n">${L("Viviendas reg.", "Registered")}</th>${hasShare ? `<th class="n hide-sm">${L("% viviendas*", "% homes*")}</th>` : ""}
      ${LS ? `<th class="n hide-sm">${L("Anuncios", "Listings")}</th><th class="n">${L("Sin nº válido", "No valid no.")}</th><th class="hide-sm"></th>`
        : FR ? `<th class="n hide-sm">${L("Anuncios", "Listings")}</th><th class="n hide-sm">${L("Por 100 viv.", "Per 100 homes")}</th><th class="n">${L("Sin nº válido†", "No valid no.†")}</th>`
        : `<th class="n hide-sm">${L("Plazas", "Places")}</th><th class="hide-sm"></th>`}</tr>`;
    const list = LS || byListings ? [...rows].filter((r) => r.listings > 0).sort((a, b) => b.listings - a.listings) : rows;
    const minS = sub.min_sample || 30;
    if (top) point("donde", L("Dónde", "Where"), `<span class="big brand">${share}%</span>`,
      byListings ? L(`de los anuncios de Airbnb están en ${the}${subName(top)}`, `of Airbnb listings are in ${the}${subName(top)}`)
        : L(`de las viviendas turísticas están en ${sub.kind === "barrio" ? the : sub.kind === "locality" ? "el código postal " : ""}${subName(top)}`,
          `of tourist flats are in ${sub.kind === "barrio" ? the : sub.kind === "locality" ? "postcode " : ""}${subName(top)}`),
      LS ? `<p>${L(`${sub.kind === "municipality" ? "Por municipios" : "Por barrios"}, el porcentaje de anuncios sin número válido va del ${Math.round(Math.min(...withPct.map((r) => r.not_valid_pct)))}% al ${Math.round(Math.max(...withPct.map((r) => r.not_valid_pct)))}%. Solo mostramos el porcentaje donde hay al menos ${M.min_listings_area} anuncios.${located ? "" : ` Al ${RG.es} le faltan las coordenadas de demasiadas viviendas para repartirlas por barrios.`}`,
        `${sub.kind === "municipality" ? "By municipality" : "By barrio"}, the share of listings without a valid number ranges from ${Math.round(Math.min(...withPct.map((r) => r.not_valid_pct)))}% to ${Math.round(Math.max(...withPct.map((r) => r.not_valid_pct)))}%. We only show a percentage where there are at least ${M.min_listings_area} listings.${located ? "" : ` Too many flats in the ${RG.en} have no coordinates to split them by barrio.`}`)}</p>`
      : FR ? `<p>${L(`Anuncios: los ${fmt(frameN)} anuncios de Airbnb que encontramos en el municipio, situados en su ${kindName}. ${located ? "" : `Al ${RG.es} le faltan las coordenadas de demasiadas viviendas para repartirlas por ${kindName}s. `}El porcentaje sin número válido sale de la muestra revisada en directo y solo lo damos donde hay al menos ${minS} anuncios revisados${withPct.length ? ` (${fmt(withPct.length)} ${withPct.length === 1 ? kindName : kindName + "s"})` : `: ningún ${kindName} llega todavía`}; la cifra de toda la ciudad, con la muestra completa, está en «Anuncios (muestra)».`,
          `Listings: the ${fmt(frameN)} Airbnb listings we found in the municipality, placed in their ${kindName}. ${located ? "" : `Too many flats in the ${RG.en} have no coordinates to split them by ${kindName}. `}The share without a valid number comes from the live-checked sample and is only given where at least ${minS} listings were checked${withPct.length ? ` (${fmt(withPct.length)} ${withPct.length === 1 ? kindName : kindName + "s"})` : `: no ${kindName} has that many yet`}; the city-wide figure, from the whole sample, is under “Listings (sample)”.`)}</p>` : "",
      `<table class="data"><thead>${head}</thead><tbody id="sub-body">${tableRows(list.slice(0, 10))}</tbody></table>
       ${list.length > 10 ? `<button class="more" type="button" id="sub-more">${L(`Ver los ${fmt(list.length)}`, `Show all ${fmt(list.length)}`)}</button>` : ""}
       ${hasShare ? `<p class="tiny muted" style="margin-top:8px">${L("* Viviendas turísticas registradas sobre el total de viviendas del Catastro. Indicativo.", "* Registered tourist flats as a share of all homes in the Catastro. Indicative.")}</p>` : ""}
       ${FR ? `<p class="tiny muted" style="margin-top:8px">${L(`† Estimación con la muestra aleatoria, solo con ${minS} o más anuncios revisados en el ${kindName}; con pocos anuncios el margen de error es amplio (ver la clasificación completa). Un anuncio no es una vivienda: una vivienda puede tener varios.`,
          `† Estimate from the random sample, only with ${minS} or more listings checked in the ${kindName}; with few listings the margin of error is wide (see the full ranking). A listing isn't a home: one home can have several.`)}</p>
          <p style="margin-top:14px"><a href="${areaHref(slug, "zonas")}">${sub.level === "district" ? L("Ver todos los distritos →", "See every district →") : L("Ver la clasificación de todos los barrios →", "See the ranking of every barrio →")}</a></p>` : ""}`,
      LS ? srcAirbnb + (sub.source ? L(` Límites: ${esc(sub.source.es)}.`, ` Boundaries: ${esc(sub.source.en)}.`) : "") : FR ? L(`Fuentes: ${RG.es}, Catastro, lista de anuncios de Airbnb de tienelicencia.com (${TL.date((S.sample || {}).frame_date)}) y ${esc(sub.source?.es || "límites oficiales de los barrios")}.`,
        `Sources: ${RG.en}, Catastro, tienelicencia.com's list of Airbnb listings (${TL.date((S.sample || {}).frame_date)}) and ${esc(sub.source?.en || "official barrio boundaries")}.`)
        : srcReg + (sub.source ? L(` Límites: ${esc(sub.source.es)}.`, ` Boundaries: ${esc(sub.source.en)}.`) : ""));

    // concentration + biggest buildings
    if (R.buildings_10plus) point("edificios", L("Edificios", "Buildings"), `<span class="big brand">${fmt(R.buildings_10plus)}</span>`,
      L(`edificios tienen 10 o más viviendas turísticas`, `buildings have 10 or more tourist flats`),
      `<p>${L(`Entre todos suman ${fmt(R.vut_in_buildings_10plus)} viviendas, el ${pctStr(R.vut_in_buildings_10plus, R.vut)} del total.`, `Together they hold ${fmt(R.vut_in_buildings_10plus)} flats, ${pctStr(R.vut_in_buildings_10plus, R.vut)} of the total.`)}</p>`,
      `<div class="bld-sort" role="group" aria-label="${L("Ordenar", "Sort")}">${L("Ordenar por", "Sort by")}
          <button type="button" data-bsort="n" aria-pressed="true">${L("nº de turísticas", "tourist flats")}</button>
          <button type="button" data-bsort="pct" aria-pressed="false">${L("% del edificio", "% of building")}</button></div>
        <table class="data bld"><thead><tr><th>${L("Edificio", "Building")}</th><th class="n">${L("Turísticas", "Tourist flats")}</th>
          <th class="n">${L("% del edificio", "% of building")}</th><th></th></tr></thead><tbody id="bld-rows"></tbody></table>
        <p class="small" style="margin-top:10px"><button type="button" class="linkish" id="bld-more"></button>
          · <a href="/data/${slug}/edificios.csv" download>${L("Descargar la lista completa (CSV)", "Download the full list (CSV)")}</a></p>
        <p class="tiny muted">${L("«% del edificio»: viviendas turísticas registradas sobre las viviendas del edificio según el Catastro. Indicativo.",
          "“% of building”: registered tourist flats over the homes in the building according to the Catastro. Indicative.")}</p>`, srcReg);
    if (R.buildings_10plus) after.push(() => {
      const all = R.top_buildings.filter((b) => b[2] >= 10);
      let sortBy = "n", open = false;
      const pct = (b) => (b[6] ? b[2] / b[6] : -1);
      const draw = () => {
        // By share, ignore tiny buildings so a 12-flat block at 100% doesn't top the list
        const rows = sortBy === "n" ? all : all.filter((b) => (b[6] || 0) >= 20).sort((x, y) => pct(y) - pct(x));
        document.getElementById("bld-rows").innerHTML = rows.slice(0, open ? 200 : 5).map(([id, lab, n, , , , hm, nm, muni, barrio]) => `<tr>
          <td><b>${esc(nm || lab)}</b>${barrio || muni ? `<br><span class="tiny muted">${esc(barrio || muni)}</span>` : ""}</td><td class="n">${fmt(n)}</td>
          <td class="n">${hm ? `<b>${Math.round(100 * n / hm)}%</b> <span class="tiny muted hide-sm">${L("de", "of")} ${fmt(hm)}</span>` : "—"}</td>
          <td class="n"><a href="${areaHref(slug, "mapa")}?b=${encodeURIComponent(id)}">${t("map")}</a></td></tr>`).join("");
        const more = document.getElementById("bld-more");
        more.textContent = open ? L("Ver menos", "Show fewer")
          : L(`Ver ${rows.length > 200 ? "los 200 primeros" : `los ${fmt(rows.length)}`} edificios`, `Show ${rows.length > 200 ? "the top 200" : `all ${fmt(rows.length)}`} buildings`);
        more.hidden = rows.length <= 5;
        document.querySelectorAll("[data-bsort]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.bsort === sortBy));
      };
      document.querySelectorAll("[data-bsort]").forEach((x) => x.addEventListener("click", () => { sortBy = x.dataset.bsort; draw(); }));
      document.getElementById("bld-more").addEventListener("click", () => { open = !open; draw(); });
      draw();
    });

    // Towns without Inside Airbnb data: an estimate from a live-checked random sample of the town's listings
    const SM = S.sample;
    if (!LS && SM && SM.checked >= 300) {
      const nf = (x) => Number(x).toLocaleString(TL.lang() === "es" ? "es-ES" : "en-GB", { maximumFractionDigits: 1 });
      const [lo, hi] = (SM.not_valid_ci || []).map(nf);
      const nv = SM.verdicts.NOT_VALID || 0, bd = SM.breakdown;
      point("anuncios", L("Anuncios (muestra)", "Listings (sample)"), `<span class="big bad">${Math.round(SM.not_valid_pct)}%</span>`,
        L(`de los anuncios de Airbnb en ${esc(name(area.name))} no muestran un número de registro válido (estimación)`,
          `of Airbnb listings in ${esc(name(area.name))} don't display a valid registration number (estimate)`),
        `<p>${L(`Hemos revisado en directo <b>${fmt(SM.checked)} anuncios elegidos al azar</b> entre los ${fmt(SM.frame)} que encontramos en Airbnb en el municipio. Con esa muestra, el porcentaje real está, con un 95&nbsp;% de confianza, <b>entre el ${lo}&nbsp;% y el ${hi}&nbsp;%</b>.`,
          `We checked <b>${fmt(SM.checked)} randomly chosen listings</b> live, out of the ${fmt(SM.frame)} we found on Airbnb in the municipality. With that sample, the true share is, with 95% confidence, <b>between ${lo}% and ${hi}%</b>.`)}</p>
         <p class="small muted">${L("Es una discrepancia con el registro, no demuestra por sí sola que la vivienda no tenga permiso. No incluye posibles exenciones por estancia mínima larga (Airbnb no la muestra en el anuncio).",
          "It's a mismatch with the register and doesn't on its own show that a flat lacks a permit. It can't account for long minimum stays, which Airbnb doesn't show on the listing.")}</p>`,
        bar([[L("No muestran número", "No number shown"), bd.no_number, COLORS.no_number],
          [L("Número fuera del registro", "Number not in the register"), bd.not_in_register, COLORS.not_in_register],
          [L("Licencia de otro municipio", "Another town's licence"), bd.other_town, COLORS.other_town]], nv, true),
        L(`Fuente: muestra aleatoria de anuncios de Airbnb revisados por tienelicencia.com (lista del ${TL.date(SM.frame_date)}), comprobados en el ${RG.es}. <a href="/metodologia#muestras">Cómo lo hacemos</a>.`,
          `Source: random sample of Airbnb listings checked by tienelicencia.com (list of ${TL.date(SM.frame_date)}), checked against the ${RG.en}. <a href="/metodologia#muestras">How we do it</a>.`));
    } else if (!LS && SM) {
      point("anuncios", L("Anuncios", "Listings"), `<span class="big" style="font-size:40px">${L("En curso", "In progress")}</span>`,
        L(`estamos revisando una muestra de anuncios de ${esc(name(area.name))}`, `we're checking a sample of listings in ${esc(name(area.name))}`),
        `<p>${L(`Hemos encontrado ${fmt(SM.frame)} anuncios de Airbnb en el municipio y estamos revisando ${fmt(SM.sample)} elegidos al azar: ${fmt(SM.checked)} hasta ahora. Publicaremos la estimación cuando haya al menos 300.`,
          `We found ${fmt(SM.frame)} Airbnb listings in the municipality and are checking ${fmt(SM.sample)} chosen at random: ${fmt(SM.checked)} so far. We'll publish the estimate once there are at least 300.`)}</p>`);
    } else if (!LS) point("anuncios", L("Anuncios", "Listings"), `<span class="big" style="font-size:40px">${L("En preparación", "In preparation")}</span>`,
      L("aún no tenemos el análisis de anuncios de esta zona", "we don't have the listing analysis for this area yet"),
      `<p>${L("En esta zona todavía no analizamos los anuncios uno a uno: lo hacemos en las ciudades, a partir de la lista de Inside Airbnb o de nuestra propia lista de anuncios. Mientras tanto, el porcentaje de viviendas anunciadas (INE) de arriba sí cubre esta zona, y puedes comprobar cualquier anuncio concreto.",
        "We don't analyse listings one by one in this area yet: we do it in the cities, from Inside Airbnb's list or our own list of listings. Meanwhile, the share of advertised homes (INE) above does cover this area, and you can check any individual advert.")}</p>
        <a class="btn btn-ghost" href="/comprobar">${t("check")} ${ICON.arrow.replace("<svg", '<svg width="18" height="18"')}</a>
        <p class="small" style="margin-top:14px"><a href="/contacto?tipo=zona">${L("¿Quieres que el análisis de anuncios llegue a tu municipio? Pídenoslo →", "Want the listing analysis for your town? Ask us →")}</a></p>`);

    point("normativa", L("Normativa", "The law"), `<span class="big" style="font-size:40px">${L("Qué dice la ley", "What the law says")}</span>`,
      L(`Normas para viviendas turísticas en ${esc(name(area.name))}`, `Rules for tourist flats in ${esc(name(area.name))}`),
      `<ul class="lede" style="font-size:16.5px;padding-left:20px">${(LAW[slug] || JUNTA_LAW)().map((x) => `<li style="margin:8px 0">${x}</li>`).join("")}</ul>
       <p><a href="/metodologia#ley">${L("Normativa completa y fuentes →", "Full rules and sources →")}</a> · <a href="/metodologia#denunciar">${L("Cómo comunicar un anuncio →", "How to report an advert →")}</a></p>`);

    $("#points").innerHTML = P.map((p) => p[2]).join("");
    after.forEach((f) => f());
    $("#toc").innerHTML = P.map(([id, label]) => `<a href="#${id}">${label}</a>`).join("");
    document.querySelectorAll("[data-tip]").forEach((el) => TL.tip(el, el.dataset.tip));
    $("#sub-more")?.addEventListener("click", (e) => {
      $("#sub-body").innerHTML = tableRows(list);
      e.target.remove();
    });
  }



  /** Stacked bar of parts of a whole (2px gaps), with a legend carrying the values. */
  function bar(parts, total, ofSub) {
    return `<div class="stack" role="img" aria-label="${esc(parts.map(([l, n]) => `${l}: ${n}`).join(", "))}">
      ${parts.map(([l, n, c]) => `<span style="flex:${n};background:${c}" data-tip="${esc(`${l}: ${fmt(n)} (${pctStr(n, total)})`)}" tabindex="0"></span>`).join("")}</div>
      <div class="legend">${parts.map(([l, n, c]) => `<span><i style="background:${c}"></i>${l} <b>${fmt(n)}</b> <span class="muted">${pctStr(n, total)}${ofSub ? "" : ""}</span></span>`).join("")}</div>`;
  }
})();
