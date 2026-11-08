"""Static HTML for every area page, written from the data the build has just published (site/data/*.json).

The area, zone and map pages used to be one template each (area.html, zonas.html, mapa.html) served under every area's
address and filled in by JavaScript, so a crawler got the same empty "Resumen" page for Málaga, Sevilla and Marbella.
Here each address gets its own copy of its template with the facts already in it: title, description, canonical, H1,
a short summary, the headline figures, source and date, the zones and neighbouring areas as plain links, and JSON-LD.
The page scripts still run and redraw what they always drew; what is added here stays (it is the same data).

Pages go to site/data/pages/ (the daily build commits site/data only) and site/_redirects serves them at the clean
addresses. Also written: sitemap.xml and llms.txt (served at /sitemap.xml and /llms.txt), and an embeddable ranking chart.
Reads only published files, so `site_build.py pages` can run on its own, without the data cache.
"""
import html
import json
import math
import os
import re
from datetime import datetime, timezone

ORIGIN = "https://tienelicencia.com"
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
          "diciembre"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
             "December"]
# The province page of each Andalusian city, and the island of Palma (for the "nearby" links)
PARENT = {"malaga": "provincia", "marbella": "provincia", "sevilla": "provincia-sevilla", "granada": "provincia-granada",
          "cordoba": "provincia-cordoba", "cadiz": "provincia-cadiz", "palma": "mallorca"}
NEARBY = 5            # neighbouring areas linked from each page
ZONE_LINKS = 30       # zones linked from an area page (all of them are on its /zonas page)
TOP_BUILDINGS = 10    # buildings listed on a map page
STATIC = ["comprobar", "ranking", "mapa", "metodologia", "preguntas", "contacto", "privacidad", "aviso-legal"]

esc = lambda s: html.escape(str(s if s is not None else ""), quote=True)


# ---------------------------------------------------------------- formatting (as the site's own TL.fmt / TL.date)
def num(x, d=0, lang="es"):
    if x is None:
        return "—"
    s = f"{x:,.{d}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".") if lang == "es" else s


def pct(x, d=0, lang="es"):
    if x is None:
        return "—"
    s = num(round(x, d) if d else round(x), d, lang)
    if d and s.endswith("," + "0" * d if lang == "es" else "." + "0" * d):
        s = s[:-(d + 1)]
    return f"{s} %" if lang == "es" else f"{s}%"


def day(iso, lang="es"):
    if not iso:
        return ""
    d = datetime.fromisoformat(iso[:10])
    return f"{d.day} de {MONTHS[d.month - 1]} de {d.year}" if lang == "es" else f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}"


def month(iso, lang="es"):
    d = datetime.fromisoformat(iso[:10])
    return f"{MONTHS[d.month - 1]} de {d.year}" if lang == "es" else f"{MONTHS_EN[d.month - 1]} {d.year}"


def bi(es, en, tag="span", cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<{tag} lang="es"{c}>{es}</{tag}><{tag} lang="en"{c}>{en}</{tag}>'


def plain(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


# ---------------------------------------------------------------- template surgery
def set_head(page, title_es, title_en, desc_es, desc_en, path, ld=None):
    """Title, descriptions (both languages: core.js swaps them on the language toggle), canonical and JSON-LD."""
    page = re.sub(r"<title>.*?</title>", f"<title>{esc(title_es)}</title>", page, count=1, flags=re.S)
    page = re.sub(r'<meta name="(title|description)-(es|en)"[^>]*>\n?', "", page)
    page = re.sub(r'<meta name="description" content="[^"]*">',
                  f'<meta name="description" content="{esc(desc_es)}">\n'
                  f'<meta name="title-es" content="{esc(title_es)}">\n<meta name="title-en" content="{esc(title_en)}">\n'
                  f'<meta name="description-es" content="{esc(desc_es)}">\n<meta name="description-en" content="{esc(desc_en)}">',
                  page, count=1)
    page = re.sub(r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="{esc(title_es)}">', page)
    page = re.sub(r'<meta property="og:description" content="[^"]*">',
                  f'<meta property="og:description" content="{esc(desc_es)}">', page)
    head = (f'<link rel="canonical" href="{ORIGIN}{path}">\n<meta property="og:url" content="{ORIGIN}{path}">\n'
            '<meta property="og:locale" content="es_ES">\n')
    if ld:
        head += f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False, separators=(",", ":"))}</script>\n'
    return page.replace("</head>", head + "</head>", 1)


def set_inner(page, el_id, inner):
    """Replace the content of the element with this id (not nested in another element of the same tag)."""
    rx = re.compile(r'(<(\w+)\b[^>]*\bid="' + re.escape(el_id) + r'"[^>]*>)(.*?)(</\2>)', re.S)
    out, n = rx.subn(lambda m: m.group(1) + inner + m.group(4), page, count=1)
    if not n:
        raise ValueError(f"#{el_id} not in template")
    return out


def set_attr(page, el_id, attr, value):
    rx = re.compile(r'(<\w+\b[^>]*\bid="' + re.escape(el_id) + r'"[^>]*?\b' + attr + r'=")[^"]*(")')
    out, n = rx.subn(lambda m: m.group(1) + esc(value) + m.group(2), page, count=1)
    if not n:
        raise ValueError(f"#{el_id}[{attr}] not in template")
    return out


def insert(page, marker, block, after=True):
    if marker not in page:
        raise ValueError(f"{marker!r} not in template")
    return page.replace(marker, marker + block if after else block + marker, 1)


# ---------------------------------------------------------------- the data
def load(site):
    D = os.path.join(site, "data")
    j = lambda *p: json.load(open(os.path.join(D, *p), encoding="utf-8"))
    A = j("areas.json")
    S = {}
    for a in A["areas"]:
        try:
            S[a["slug"]] = j(a["slug"], "summary.json")
        except (OSError, ValueError):
            S[a["slug"]] = None
    rk = None
    try:
        rk = j("ranking.json")
    except (OSError, ValueError):
        pass
    return A, S, j("meta.json"), rk


def km(a, b):
    (x1, y1), (x2, y2) = a["center"], b["center"]
    kx = math.cos(math.radians((y1 + y2) / 2))
    return 111.2 * math.hypot((x2 - x1) * kx, y2 - y1)


def nearby(area, areas):
    """Areas to link from this one: its province / island and region first, then the nearest of the same kind."""
    by = {a["slug"]: a for a in areas}
    out = []
    if area["slug"] in PARENT and PARENT[area["slug"]] in by:
        out.append(by[PARENT[area["slug"]]])
    kids = [s for s, p in PARENT.items() if p == area["slug"] and s in by]
    out += [by[s] for s in kids]
    andalusian = area["slug"] in PARENT and PARENT[area["slug"]].startswith("provincia") or area["kind"] == "province"
    if andalusian and area["slug"] != "andalucia" and "andalucia" in by:
        out.append(by["andalucia"])
    same = "province" if area["kind"] in ("province", "region") else "city"
    pool = sorted((a for a in areas if a["slug"] != area["slug"] and a not in out
                   and (a["kind"] == same or (same == "city" and a["kind"] == "island"))), key=lambda a: km(area, a))
    return out + pool[:max(NEARBY - len(out), 3)]


def register_of(S):
    return (S or {}).get("register") or {"es": "Registro de Turismo de Andalucía", "en": "Andalusian Tourism Register",
                                         "src": "Open RTA"}


def facts(area, S, meta):
    """The figures every page about the area repeats, in both languages: [(es, en)], plus the summary sentences."""
    nm_es, nm_en = area["name"]["es"], area["name"]["en"]
    R = (S or {}).get("registered") or {}
    LS = (S or {}).get("listings")
    SM = (S or {}).get("sample")
    RG = register_of(S)
    req = RG.get("number_required", True)
    vut = R.get("vut", area.get("vut"))
    city = area["kind"] == "city"
    where_es = (f"en {nm_es}" if city or area["kind"] in ("island", "region") else f"en la {nm_es[0].lower()}{nm_es[1:]}")
    where_en = f"in {nm_en}"
    s1_es = f"{where_es[0].upper()}{where_es[1:]} hay <b>{num(vut)}</b> viviendas turísticas inscritas en el {esc(RG['es'])}"
    s1_en = f"{where_en[0].upper()}{where_en[1:]} there are <b>{num(vut, lang='en')}</b> tourist flats in the {esc(RG['en'])}"
    if area.get("vut_share") is not None and area.get("homes"):
        s1_es += f", el {pct(area['vut_share'], 1)} de sus {num(area['homes'])} viviendas"
        s1_en += f", {pct(area['vut_share'], 1, 'en')} of its {num(area['homes'], lang='en')} homes"
    s1_es += "."
    s1_en += "."
    title_es = f"Viviendas turísticas {where_es}: {num(vut)} registradas"
    title_en = f"Tourist flats {where_en}: {num(vut, lang='en')} registered"
    F = [(f"<b>{num(vut)}</b> viviendas turísticas registradas", f"<b>{num(vut, lang='en')}</b> registered tourist flats")]
    if R.get("vut_places"):
        F.append((f"<b>{num(R['vut_places'])}</b> plazas", f"<b>{num(R['vut_places'], lang='en')}</b> guest places"))
    if area.get("vut_share") is not None:
        F.append((f"<b>{pct(area['vut_share'], 1)}</b> de las viviendas son turísticas registradas",
                  f"<b>{pct(area['vut_share'], 1, 'en')}</b> of homes are registered tourist flats"))
    if area.get("ine_homes"):
        per = area.get("ine_period") or ""
        pes, pen = (month(per + "-01"), month(per + "-01", "en")) if re.fullmatch(r"\d{4}-\d{2}", per) else (esc(per), esc(per))
        F.append((f"<b>{num(area['ine_homes'])}</b> viviendas anunciadas en plataformas (INE, {pes})",
                  f"<b>{num(area['ine_homes'], lang='en')}</b> homes advertised on platforms (INE, {pen})"))
    s2_es = s2_en = ""
    if LS and LS.get("listings"):
        n, bad = LS["listings"], (LS.get("verdicts") or {}).get("NOT_VALID", 0)
        share = 100 * bad / n
        if req:
            s2_es = (f"De los {num(n)} anuncios de Airbnb revisados, <b>{num(bad)} ({pct(share)})</b> no muestran un número "
                     "de registro válido.")
            s2_en = (f"Of the {num(n, lang='en')} Airbnb listings checked, <b>{num(bad, lang='en')} ({pct(share, 0, 'en')})</b> "
                     "don't display a valid registration number.")
            title_es += f" y {num(bad)} anuncios sin número válido"
            title_en += f", {num(bad, lang='en')} listings without a valid number"
            F.append((f"<b>{pct(share)}</b> de {num(n)} anuncios de Airbnb no muestran un número válido",
                      f"<b>{pct(share, 0, 'en')}</b> of {num(n, lang='en')} Airbnb listings don't display a valid number"))
        else:
            s2_es = (f"Hay {num(n)} anuncios de Airbnb; aquí mostrar el número de registro en el anuncio no es obligatorio, así que "
                     "su ausencia no indica un problema.")
            s2_en = (f"There are {num(n, lang='en')} Airbnb listings; here adverts don't have to show the registration number, "
                     "so its absence doesn't indicate a problem.")
            F.append((f"<b>{num(n)}</b> anuncios de Airbnb", f"<b>{num(n, lang='en')}</b> Airbnb listings"))
    elif SM and SM.get("checked") and SM.get("not_valid_pct") is not None:
        ci = SM.get("not_valid_ci") or [None, None]
        s2_es = (f"En una muestra aleatoria de {num(SM['checked'])} anuncios de Airbnb revisados uno a uno, <b>el {pct(SM['not_valid_pct'])}</b> "
                 f"no muestra un número de registro válido (entre el {pct(ci[0])} y el {pct(ci[1])}, con un 95&nbsp;% de confianza).")
        s2_en = (f"In a random sample of {num(SM['checked'], lang='en')} Airbnb listings checked one by one, <b>{pct(SM['not_valid_pct'], 0, 'en')}</b> "
                 f"don't display a valid registration number ({pct(ci[0], 0, 'en')}–{pct(ci[1], 0, 'en')}, 95% confidence).")
        title_es += f"; el {pct(SM['not_valid_pct'])} de los anuncios, sin número válido"
        title_en += f"; {pct(SM['not_valid_pct'], 0, 'en')} of listings without a valid number"
        F.append((f"<b>{pct(SM['not_valid_pct'])}</b> de los anuncios de Airbnb no muestran un número válido (muestra de {num(SM['checked'])})",
                  f"<b>{pct(SM['not_valid_pct'], 0, 'en')}</b> of Airbnb listings don't display a valid number (sample of {num(SM['checked'], lang='en')})"))
    else:
        rows = [r for r in ((S or {}).get("subareas") or {}).get("rows", []) if r.get("vut")]
        top = max(rows, key=lambda r: r["vut"], default=None)
        kind = ((S or {}).get("subareas") or {}).get("kind")
        if top and kind == "municipality":
            s2_es = f"El municipio con más es {esc(top['name'])}, con {num(top['vut'])}."
            s2_en = f"The municipality with most is {esc(top['name'])}, with {num(top['vut'], lang='en')}."
        elif R.get("buildings_with_vut"):
            s2_es = f"Están repartidas en {num(R['buildings_with_vut'])} edificios."
            s2_en = f"They are spread over {num(R['buildings_with_vut'], lang='en')} buildings."
    return {"title_es": title_es, "title_en": title_en, "s_es": f"{s1_es} {s2_es}".strip(), "s_en": f"{s1_en} {s2_en}".strip(),
            "facts": F, "register": RG, "updated": updated(S, meta)}


def updated(S, meta):
    """(es, en) 'Fuente: … · datos del …' line."""
    RG = register_of(S)
    d = meta.get("register_lastUpdateData") if RG.get("src") == "Open RTA" else None
    d = d or meta.get("built_at")
    es = f"Fuente: {esc(RG['es'])}. Datos actualizados el {day(d)}"
    en = f"Source: {esc(RG['en'])}. Data updated {day(d, 'en')}"
    if (S or {}).get("listings"):
        sd = (S or {}).get("snapshot_date") or meta.get("snapshot_date")
        es += f"; anuncios: Inside Airbnb ({day(sd)}) y revisiones en directo"
        en += f"; listings: Inside Airbnb ({day(sd, 'en')}) and live re-checks"
    elif (S or {}).get("sample"):
        es += f"; anuncios: muestra aleatoria revisada en directo ({day((S['sample'].get('last_checked') or '')[:10])})"
        en += f"; listings: random sample checked live ({day((S['sample'].get('last_checked') or '')[:10], 'en')})"
    return es + ".", en + "."


def zone_href(slug, area, S, r, by):
    sub = ((S or {}).get("subareas") or {})
    if sub.get("kind") == "barrio" and area.get("has_listings") and area.get("has_barrios") and r.get("id") is not None:
        return f"/{slug}/mapa?barrio={r['id']}"
    if sub.get("kind") == "municipality":
        for a in by.values():
            if a["kind"] == "city" and a["name"]["es"].lower() == str(r.get("name", "")).lower():
                return f"/{a['slug']}"
    return None


def zone_name(sub, r):
    return f"{r['name']}{' · ' + r['locality'] if sub.get('kind') == 'locality' and r.get('locality') else ''}"


def zone_word(sub, many=True):
    k, lvl = sub.get("kind"), sub.get("level")
    if k == "barrio":
        return (("distritos", "districts") if lvl == "district" else ("barrios", "barrios")) if many else \
               (("distrito", "district") if lvl == "district" else ("barrio", "barrio"))
    if k == "municipality":
        return ("municipios", "municipalities") if many else ("municipio", "municipality")
    return ("códigos postales", "postcodes") if many else ("código postal", "postcode")


def links_list(items, cls="link-grid"):
    return f'<ul class="{cls}">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"


def area_link(a, sub=""):
    nm = a["name"]
    return f'<a href="/{a["slug"]}{"/" + sub if sub else ""}">{bi(esc(nm["es"]), esc(nm["en"]))}</a>'


def crumbs_ld(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": ORIGIN + p} for i, (n, p) in enumerate(items)]}


def dataset_ld(area, S, meta, path, name_, desc):
    RG = register_of(S)
    return {"@type": "Dataset", "name": name_, "description": desc, "url": ORIGIN + path, "inLanguage": ["es", "en"],
            "isAccessibleForFree": True, "dateModified": meta.get("built_at"),
            "spatialCoverage": {"@type": "Place", "name": area["name"]["es"],
                                "geo": {"@type": "GeoCoordinates", "latitude": area["center"][1], "longitude": area["center"][0]}},
            "isBasedOn": RG["es"], "creator": {"@type": "Organization", "name": "tienelicencia.com", "url": ORIGIN},
            "license": f"{ORIGIN}/metodologia#fuentes",
            "distribution": {"@type": "DataDownload", "encodingFormat": "application/json",
                             "contentUrl": f"{ORIGIN}/data/{area['slug']}/summary.json"}}


# ---------------------------------------------------------------- pages
def area_page(tpl, area, S, meta, areas):
    slug, path = area["slug"], f"/{area['slug']}"
    by = {a["slug"]: a for a in areas}
    f = facts(area, S, meta)
    desc_es, desc_en = plain(f["s_es"]), plain(f["s_en"])
    ld = {"@context": "https://schema.org", "@graph": [
        dataset_ld(area, S, meta, path, f["title_es"], desc_es),
        crumbs_ld([("Inicio", "/"), (area["name"]["es"], path)])]}
    p = set_head(tpl, f"{f['title_es']} | tienelicencia.com", f"{f['title_en']} | tienelicencia.com", desc_es, desc_en, path, ld)
    nm = bi(esc(area["name"]["es"]), esc(area["name"]["en"]))
    p = set_inner(p, "crumb-area", nm)
    p = set_inner(p, "area-name", f'<span class="h1-pre">{bi("Viviendas turísticas en", "Tourist flats in")}</span> {nm}')
    p = p.replace('id="area-name"', 'id="area-name" data-static', 1)
    p = set_inner(p, "area-updated", f'<span class="live"></span><span>{bi(*f["updated"])}</span>')
    has_map = area.get("has_map") is not False
    for el in ("map-teaser", "cta-map"):
        p = set_attr(p, el, "href", f"{path}/mapa")
    sub = (S or {}).get("subareas") or {}
    zw = zone_word(sub)
    rows = sorted((r for r in sub.get("rows", []) if r.get("vut") or r.get("listings")),
                  key=lambda r: -(r.get("vut") or r.get("listings") or 0))
    zl = []
    for r in rows[:ZONE_LINKS]:
        h = zone_href(slug, area, S, r, by)
        n = r.get("vut") if r.get("vut") is not None else r.get("listings")
        lab = f"{esc(zone_name(sub, r))} <span class=\"muted\">{num(n)}</span>"
        zl.append(f'<a href="{h}">{lab}</a>' if h else lab)
    block = f"""
    <section class="area-facts" id="area-facts" aria-label="Resumen">
      <p class="lede" lang="es">{f["s_es"]}</p><p class="lede" lang="en">{f["s_en"]}</p>
      <ul class="fact-list">{"".join(f"<li>{bi(es, en)}</li>" for es, en in f["facts"])}</ul>
      <p class="small muted">{bi(*f["updated"])} <a href="/metodologia">{bi("Metodología", "Methodology")}</a></p>
    </section>
"""
    p = insert(p, '<nav class="toc" id="toc"', block, after=False)
    more = ""
    if zl:
        more += f"""
    <section class="area-links" id="zonas-lista">
      <h2 class="h3">{bi(f"{zw[0].capitalize()} con más viviendas turísticas", f"{zw[1].capitalize()} with most tourist flats")}</h2>
      {links_list(zl)}
      <p class="small"><a href="{path}/zonas">{bi(f"Ver los {num(len(rows))} {zw[0]} →", f"See all {num(len(rows), lang='en')} {zw[1]} →")}</a>
        {f' · <a href="{path}/mapa">{bi("Abrir el mapa", "Open the map")}</a>' if has_map else ""}</p>
    </section>"""
    near = nearby(area, areas)
    more += f"""
    <section class="area-links" id="cerca">
      <h2 class="h3">{bi("Otras zonas cercanas", "Other areas nearby")}</h2>
      {links_list([area_link(a) for a in near])}
      <p class="small"><a href="/#todas">{bi("Todas las zonas →", "All areas →")}</a> · <a href="/ranking">{bi("Ranking de ciudades", "City ranking")}</a> ·
        <a href="/guias">{bi("Guías", "Guides")}</a></p>
    </section>
"""
    return insert(p, "</main>", f'  <div class="wrap">{more}  </div>\n', after=False)


def zones_page(tpl, area, S, meta, areas):
    slug, path = area["slug"], f"/{area['slug']}/zonas"
    by = {a["slug"]: a for a in areas}
    sub = (S or {}).get("subareas") or {}
    zw = zone_word(sub)
    nm_es, nm_en = area["name"]["es"], area["name"]["en"]
    rows = sorted((r for r in sub.get("rows", []) if r.get("vut") or r.get("listings")),
                  key=lambda r: (-(r.get("vut_share") or -1), -(r.get("vut") or r.get("listings") or 0)))
    listings = area.get("has_listings") and any(r.get("not_valid_pct") is not None for r in rows)
    sample = not area.get("has_listings") and any(r.get("not_valid_pct") is not None for r in rows)
    shares = any(r.get("vut_share") is not None for r in rows)
    top = rows[0] if rows else None
    t_es = f"{zw[0].capitalize()} de {nm_es} por viviendas turísticas"
    t_en = f"{zw[1].capitalize()} of {nm_en} by tourist flats"
    d_es = f"Todos los {zw[0]} de {nm_es} ordenados por viviendas turísticas registradas"
    d_en = f"Every {zw[1][:-1] if zw[1].endswith('s') else zw[1]} in {nm_en} ranked by registered tourist flats"
    if shares and top and top.get("vut_share") is not None:
        d_es += f": {top['name']} encabeza la lista con el {pct(top['vut_share'], 1)} de sus viviendas"
        d_en += f": {top['name']} leads with {pct(top['vut_share'], 1, 'en')} of its homes"
    d_es += f". {num(len(rows))} {zw[0]}, con datos oficiales."
    d_en += f". {num(len(rows), lang='en')} {zw[1]}, from official data."
    ld = {"@context": "https://schema.org", "@graph": [
        dataset_ld(area, S, meta, path, t_es, d_es),
        crumbs_ld([("Inicio", "/"), (nm_es, f"/{slug}"), (zw[0].capitalize(), path)])]}
    p = set_head(tpl, f"{t_es} | tienelicencia.com", f"{t_en} | tienelicencia.com", d_es, d_en, path, ld)
    p = set_inner(p, "crumb-area", bi(esc(nm_es), esc(nm_en)))
    p = set_attr(p, "crumb-area", "href", f"/{slug}")
    p = set_inner(p, "rank-title", bi(esc(t_es), esc(t_en)))
    p = p.replace('id="rank-title"', 'id="rank-title" data-static', 1)
    p = set_inner(p, "rank-lede", bi(esc(d_es), esc(d_en)))
    one = zone_word(sub, many=False)
    head = [bi(one[0].capitalize(), one[1].capitalize()), bi("Viviendas turísticas registradas", "Registered tourist flats")]
    if shares:
        head += [bi("Viviendas", "Homes"), bi("% registradas", "% registered")]
    if listings or sample:
        head += [bi("Anuncios de Airbnb", "Airbnb listings"), bi("Sin nº válido" + (" (muestra)" if sample else ""),
                                                                  "No valid no." + (" (sample)" if sample else ""))]
    body = []
    for i, r in enumerate(rows):
        h = zone_href(slug, area, S, r, by)
        nm = esc(zone_name(sub, r))
        c = [f'<a href="{h}">{nm}</a>' if h else nm, num(r.get("vut"))]
        if shares:
            c += [num(r.get("homes")) if r.get("homes") else "—", pct(r.get("vut_share"), 1)]
        if listings or sample:
            c += [num(r.get("listings")), pct(r.get("not_valid_pct"))]
        body.append(f'<tr><td class="n rank-i">{i + 1}</td>' + "".join(
            f'<td{"" if j == 0 else " class=n"}>{x}</td>' for j, x in enumerate(c)) + "</tr>")
    table = (f'<thead><tr><th class="n rank-i">#</th>{"".join(f"<th>{h}</th>" for h in head)}</tr></thead>'
             f'<tbody>{"".join(body)}</tbody>')
    p = set_inner(p, "rank", table)
    upd = updated(S, meta)
    p = set_inner(p, "rank-notes", bi(upd[0] + ' <a href="/metodologia#proporcion">Metodología</a>.',
                                      upd[1] + ' <a href="/metodologia#proporcion">Methodology</a>.'))
    more = f"""
  <div class="wrap">
    <section class="area-links">
      <p class="small"><a href="/{slug}">{bi(f"Resumen de {esc(nm_es)} →", f"{esc(nm_en)} summary →")}</a>
        {f' · <a href="/{slug}/mapa">{bi("Mapa", "Map")}</a>' if area.get("has_map") is not False else ""} ·
        {bi("Otras zonas:", "Other areas:")} {" · ".join(area_link(a, "zonas") for a in nearby(area, areas))}</p>
    </section>
  </div>
"""
    return insert(p, "</main>", more, after=False)


def map_page(tpl, area, S, meta, areas, top_override=None):
    """One area's map (area given) or Spain's (area None)."""
    slug = area["slug"] if area else None
    path = f"/{slug}/mapa" if slug else "/mapa"
    nm_es, nm_en = (area["name"]["es"], area["name"]["en"]) if area else ("España", "Spain")
    R = (S or {}).get("registered") or {}
    top = top_override if top_override is not None else R.get("top_buildings") or []
    top = top[:TOP_BUILDINGS]
    t_es = f"Mapa de viviendas turísticas en {nm_es}, edificio por edificio"
    t_en = f"Map of tourist flats in {nm_en}, building by building"
    if area:
        vut = R.get("vut", area.get("vut"))
        nb = R.get("buildings_with_vut")
        d_es = (f"Mapa de las {num(vut)} viviendas turísticas registradas en {nm_es}"
                + (f", en {num(nb)} edificios" if nb else "") + ". Pulsa un edificio para ver cada vivienda, con su licencia, planta y puerta.")
        d_en = (f"Map of the {num(vut, lang='en')} registered tourist flats in {nm_en}"
                + (f", in {num(nb, lang='en')} buildings" if nb else "") + ". Tap a building to see each flat, with its licence, floor and door.")
    else:
        vut = sum(a.get("vut") or 0 for a in areas if a["kind"] in ("city", "island") and a["slug"] != "palma")
        d_es = ("Mapa de España de las viviendas turísticas registradas, de todo el país a cada edificio: Andalucía, Mallorca y "
                "las grandes ciudades. Pulsa un edificio para ver cada vivienda, con su licencia, planta y puerta.")
        d_en = ("Map of Spain's registered tourist flats, from the whole country down to each building: Andalucía, Mallorca and "
                "the big cities. Tap a building to see each flat, with its licence, floor and door.")
    graph = [crumbs_ld([("Inicio", "/")] + ([(nm_es, f"/{slug}")] if slug else []) + [("Mapa", path)])]
    if area:
        graph.insert(0, dataset_ld(area, S, meta, path, t_es, d_es))
    p = set_head(tpl, f"{t_es} | tienelicencia.com", f"{t_en} | tienelicencia.com", d_es, d_en, path,
                 {"@context": "https://schema.org", "@graph": graph})
    p = set_inner(p, "map-title", f"{bi(esc(nm_es), esc(nm_en))}<small>{bi('Viviendas turísticas registradas', 'Registered tourist flats')}</small>")
    p = set_attr(p, "back", "href", f"/{slug}" if slug else "/")
    items = []
    for b in top:
        bid, label, n, places, lat, lon = b[0], b[1], b[2], b[3], b[4], b[5]
        short, muni = (b[7] if len(b) > 7 else None) or label, b[8] if len(b) > 8 else ""
        target = b[10] if len(b) > 10 else slug
        where = f" · {esc(muni)}" if muni and (not area or area["kind"] != "city") else ""
        flats = bi(f"{num(n)} viviendas", f"{num(n, lang='en')} flats")
        items.append(f'<a href="/{target}/mapa?b={esc(bid)}&amp;lat={lat}&amp;lon={lon}">{esc(short)}</a>{where} '
                     f'<span class="muted">{flats}</span>')
    upd = updated(S, meta) if area else (f"Fuente: registros oficiales de turismo de cada comunidad. Datos actualizados el {day(meta.get('built_at'))}.",
                                         f"Source: each region's official tourism register. Data updated {day(meta.get('built_at'), 'en')}.")
    links = ""
    if area:
        sub = (S or {}).get("subareas") or {}
        links = (f'<p class="small"><a href="/{slug}">{bi(f"Resumen de {esc(nm_es)}", f"{esc(nm_en)} summary")}</a> · '
                 f'<a href="/{slug}/zonas">{bi(zone_word(sub)[0].capitalize(), zone_word(sub)[1].capitalize())}</a> · '
                 + " · ".join(area_link(a, "mapa") for a in nearby(area, areas)[:4]) + "</p>")
    else:
        links = '<p class="small">' + " · ".join(area_link(a, "mapa") for a in areas if a["kind"] in ("city", "island", "region")) + "</p>"
    block = f"""
      <section id="map-about">
        <h1>{bi(esc(t_es), esc(t_en))}</h1>
        <p lang="es">{esc(d_es)}</p><p lang="en">{esc(d_en)}</p>
        {f'<h2>{bi("Edificios con más viviendas turísticas", "Buildings with most tourist flats")}</h2><ol>' + "".join(f"<li>{x}</li>" for x in items) + "</ol>" if items else ""}
        <p class="tiny muted">{bi(*upd)}</p>
        {links}
      </section>"""
    return insert(p, '<section id="p-detail"></section>', block)


def ranking_page(tpl, rk, meta):
    """/ranking: the index stays as ranking.js (and the edge function) draw it; added here: a dated title and a press
    table of listings without a publicly verifiable number, with how to cite and embed it."""
    built = rk["built_at"]
    m_es, m_en = month(built), month(built, "en")
    t_es = f"Índice de presión de la vivienda turística · {m_es}"
    t_en = f"Tourist-housing pressure index · {m_en}"
    cities = rk["cities"]
    req = [c for c in cities if (c.get("verification") or {}).get("number_required", True)
           and (c.get("verification") or {}).get("no_verifiable_pct") is not None and (c.get("verification") or {}).get("sufficient", True)]
    req.sort(key=lambda c: -c["verification"]["no_verifiable_pct"])
    other = [c for c in cities if c not in req]
    lead = req[:3]
    if lead:
        q_es = (f"En {m_es}, {esc(lead[0]['name'])} es la gran ciudad española con más anuncios de Airbnb sin un número de registro "
                f"verificable públicamente: el {pct(lead[0]['verification']['no_verifiable_pct'])}" +
                (", seguida de " + " y ".join(f"{esc(c['name'])} ({pct(c['verification']['no_verifiable_pct'])})" for c in lead[1:]) if len(lead) > 1 else "") + ".")
        q_en = (f"In {m_en}, {esc(lead[0]['name'])} is the large Spanish city with the most Airbnb listings without a publicly "
                f"verifiable registration number: {pct(lead[0]['verification']['no_verifiable_pct'], 0, 'en')}" +
                (", followed by " + " and ".join(f"{esc(c['name'])} ({pct(c['verification']['no_verifiable_pct'], 0, 'en')})" for c in lead[1:]) if len(lead) > 1 else "") + ".")
    else:
        q_es = q_en = ""
    d_es = (f"Ranking de las {len(cities)} ciudades españolas de más de {num(rk['cohort']['min_population'])} habitantes por presión "
            f"de la vivienda turística, {m_es}. " + plain(q_es))
    d_en = (f"Ranking of the {len(cities)} Spanish cities over {num(rk['cohort']['min_population'], lang='en')} inhabitants by "
            f"tourist-housing pressure, {m_en}. " + plain(q_en))
    p = set_head(tpl, f"{t_es} | tienelicencia.com", f"{t_en} | tienelicencia.com", d_es[:300], d_en[:300], "/ranking")
    rows = []
    for i, c in enumerate(req):
        v = c["verification"]
        rows.append(f'<tr><td class="n">{i + 1}</td><td><a href="/{esc(c.get("slug") or c["area"])}">{esc(c["name"])}</a></td>'
                    f'<td class="n"><b>{pct(v["no_verifiable_pct"], 1)}</b>{ci_note(v)}</td><td class="n">{num(v.get("assessed"))}</td>'
                    f'<td class="n">{num(c.get("registered"))}</td><td class="n">{num(c.get("index"), 1) if c.get("index") is not None else "—"}</td></tr>')
    for c in other:
        v = c.get("verification") or {}
        why = (bi("no obligatorio", "not required") if v.get("number_required") is False else bi("muestra insuficiente", "sample too small"))
        rows.append(f'<tr><td class="n">–</td><td><a href="/{esc(c.get("slug") or c["area"])}">{esc(c["name"])}</a></td>'
                    f'<td class="n muted">{why}</td><td class="n">{num(v.get("assessed")) if v.get("assessed") else "—"}</td>'
                    f'<td class="n">{num(c.get("registered"))}</td><td class="n">{num(c.get("index"), 1) if c.get("index") is not None else "—"}</td></tr>')
    th = "".join(f"<th>{h}</th>" for h in ["#", bi("Ciudad", "City"), bi("Anuncios sin número verificable", "Listings without a verifiable number"),
                                            bi("Anuncios analizados", "Listings assessed"), bi("Viviendas turísticas registradas", "Registered tourist flats"),
                                            bi("Índice (de 100)", "Index (out of 100)")])
    cite_es = f"Fuente: tienelicencia.com, Índice de presión de la vivienda turística, {m_es} (https://tienelicencia.com/ranking)."
    cite_en = f"Source: tienelicencia.com, Tourist-housing pressure index, {m_en} (https://tienelicencia.com/ranking)."
    embed = (f'<a href="{ORIGIN}/ranking"><img src="{ORIGIN}/data/ranking-anuncios.svg" width="1200" height="{svg_height(len(req))}" '
             f'alt="{esc(plain(q_es))}" style="max-width:100%;height:auto"></a>')
    block = f"""
    <section class="press-table" id="tabla">
      <span class="eyebrow">{bi("Para prensa · " + esc(m_es), "For the press · " + esc(m_en))}</span>
      <h2 class="h2">{bi(f"Ciudades con más anuncios sin número de registro verificable, {esc(m_es)}", f"Cities with most listings without a verifiable registration number, {esc(m_en)}")}</h2>
      <p class="lede" lang="es">{q_es}</p><p class="lede" lang="en">{q_en}</p>
      <div class="table-scroll"><table class="data"><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
      <p class="small muted" lang="es">«Sin número verificable»: el anuncio no muestra número, el número no está en el registro oficial de su comunidad o es de otro municipio. No demuestra que la vivienda no tenga licencia. En la Comunidad de Madrid mostrar el número no es obligatorio. Anuncios: Airbnb (Inside Airbnb y nuestras muestras aleatorias), comprobados uno a uno con los registros oficiales. Datos al {day(built)}. <a href="/metodologia#indice">Cómo se calcula</a>.</p>
      <p class="small muted" lang="en">"Without a verifiable number": the listing shows no number, or the number isn't in its region's official register or belongs to another town. It doesn't prove the home is unlicensed. In the Comunidad de Madrid showing the number isn't required. Listings: Airbnb (Inside Airbnb and our random samples), checked one by one against the official registers. Data as of {day(built, 'en')}. <a href="/metodologia#indice">How it's calculated</a>.</p>
      <h3 class="h3" style="margin-top:28px">{bi("Citar y reutilizar", "Cite and reuse")}</h3>
      <p class="small" lang="es">Puedes citar estas cifras y reproducir el gráfico con el enlace a la fuente: <q>{esc(cite_es)}</q> Datos completos en <a href="/data/ranking.json">JSON</a>; prensa: <a href="/metodologia#prensa">contacto y notas</a>.</p>
      <p class="small" lang="en">You may quote these figures and reproduce the chart with a link to the source: <q>{esc(cite_en)}</q> Full data as <a href="/data/ranking.json">JSON</a>; press: <a href="/metodologia#prensa">contact and notes</a>.</p>
      <figure style="margin:16px 0"><a href="/data/ranking-anuncios.svg"><img src="/data/ranking-anuncios.svg" alt="{esc(plain(q_es))}" loading="lazy" style="width:100%;height:auto;border:1px solid var(--line);border-radius:8px"></a></figure>
      <label class="small" for="embed-code">{bi("Código para insertar el gráfico", "Code to embed the chart")}</label>
      <textarea id="embed-code" readonly rows="3" style="width:100%;font:13px/1.4 ui-monospace,monospace;margin-top:6px" onclick="this.select()">{esc(embed)}</textarea>
    </section>
"""
    return insert(p, '<div class="ix-notes small muted" id="ix-notes"></div>', block, after=False)


def ci_note(v):
    """Sample-based figures carry their 95% interval, so the number isn't quoted without its margin."""
    ci = v.get("no_verifiable_ci")
    if v.get("source") != "sample" or not ci:
        return ""
    lo, hi = num(ci[0]), num(ci[1])
    lo_en, hi_en = num(ci[0], lang="en"), num(ci[1], lang="en")
    return f'<br><span class="tiny muted">{bi(f"muestra; {lo}–{hi}&nbsp;%", f"sample; {lo_en}–{hi_en}%")}</span>'


def svg_height(n):
    return 194 + 46 * n


def ranking_svg(rk):
    """Embeddable bar chart of the press table (plain SVG, no external fonts or scripts)."""
    built = rk["built_at"]
    req = [c for c in rk["cities"] if (c.get("verification") or {}).get("number_required", True)
           and (c.get("verification") or {}).get("no_verifiable_pct") is not None and (c.get("verification") or {}).get("sufficient", True)]
    req.sort(key=lambda c: -c["verification"]["no_verifiable_pct"])
    W, H = 1200, svg_height(len(req))
    mx = max([c["verification"]["no_verifiable_pct"] for c in req] + [1])
    x0, x1 = 300, 1080
    f = 'font-family="Public Sans,Helvetica,Arial,sans-serif"'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">',
           f'<title>{esc(f"Anuncios de Airbnb sin número de registro verificable, {month(built)}")}</title>',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           f'<text x="40" y="58" {f} font-size="30" font-weight="700" fill="#142036">Anuncios de Airbnb sin número de registro verificable</text>',
           f'<text x="40" y="94" {f} font-size="20" fill="#5d6779">Grandes ciudades españolas, {esc(month(built))}. % de los anuncios analizados.</text>']
    for i, c in enumerate(req):
        y = 130 + 46 * i
        v = c["verification"]["no_verifiable_pct"]
        w = (x1 - x0) * v / mx
        out += [f'<text x="{x0 - 16}" y="{y + 22}" {f} font-size="20" text-anchor="end" fill="#142036">{esc(c["name"])}</text>',
                f'<rect x="{x0}" y="{y}" width="{w:.1f}" height="30" rx="3" fill="{"#b3261e" if i < 3 else "#d77a6f"}"/>',
                f'<text x="{x0 + w + 10:.1f}" y="{y + 22}" {f} font-size="20" font-weight="700" fill="#142036">{pct(v, 1).replace(chr(160), " ")}</text>']
    out += [f'<text x="40" y="{H - 52}" {f} font-size="16" fill="#5d6779">Fuente: tienelicencia.com/ranking, a partir de los registros oficiales de turismo e Inside Airbnb. Datos al {esc(day(built))}.</text>',
            f'<text x="40" y="{H - 28}" {f} font-size="16" fill="#5d6779">No mostrar un número válido no demuestra que la vivienda no tenga licencia. Sin Madrid: allí mostrarlo no es obligatorio.</text>',
            "</svg>"]
    return "\n".join(out)


def spain_top(S, areas):
    """The biggest buildings across all areas (cities first, no building twice: Palma is also in Mallorca)."""
    seen, out = set(), []
    for a in areas:
        if a["kind"] not in ("city", "island"):
            continue
        for b in ((S.get(a["slug"]) or {}).get("registered") or {}).get("top_buildings") or []:
            if b[0] in seen:
                continue
            seen.add(b[0])
            out.append(list(b) + [None] * (10 - len(b)) + [a["slug"]])
    return sorted(out, key=lambda b: -b[2])[:TOP_BUILDINGS]


# ---------------------------------------------------------------- sitemap, llms.txt
def sitemap(areas, meta, site):
    lm = (meta.get("built_at") or "")[:10]
    urls = [("/", lm)]
    for a in areas:
        urls.append((f"/{a['slug']}", lm))
        urls.append((f"/{a['slug']}/zonas", lm))
        if a.get("has_map") is not False:
            urls.append((f"/{a['slug']}/mapa", lm))
    urls += [("/ranking", lm), ("/mapa", lm)]
    gd = os.path.join(site, "guias")
    if os.path.isdir(gd):
        urls.append(("/guias", None))
        urls += [(f"/guias/{n[:-5]}", None) for n in sorted(os.listdir(gd)) if n.endswith(".html") and n != "index.html"]
    urls += [(f"/{s}", None) for s in STATIC if s not in ("ranking", "mapa")]
    seen, body = set(), []
    for u, d in urls:
        if u in seen:
            continue
        seen.add(u)
        body.append(f"  <url><loc>{ORIGIN}{u}</loc>{f'<lastmod>{d}</lastmod>' if d else ''}</url>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + \
           "\n".join(body) + "\n</urlset>\n"


def llms(intro, areas, S, meta, rk, site):
    """The hand-written site/llms.txt, followed by current, dated, sourced figures for every area and the guides."""
    lines = [intro.rstrip(), "", f"## Cifras actuales / Current figures ({day(meta.get('built_at'))})",
             "Cada línea: zona, viviendas turísticas registradas y anuncios sin número de registro válido, con su fuente. "
             "Cite la página de la zona y su fecha. / Each line: area, registered tourist flats and listings without a valid "
             "registration number, with its source. Please cite the area's page and its date."]
    for a in areas:
        try:
            f = facts(a, S.get(a["slug"]), meta)
        except Exception:  # noqa: BLE001  (that area's page reports it)
            lines.append(f"- [{a['name']['es']}]({ORIGIN}/{a['slug']})")
            continue
        lines.append(f"- [{a['name']['es']}]({ORIGIN}/{a['slug']}): {plain(f['s_es'])} {plain(f['updated'][0])}")
    if rk:
        lines += ["", f"## Ranking ({month(rk['built_at'])})", f"- [Índice de presión de la vivienda turística]({ORIGIN}/ranking): " +
                  "; ".join(f"{c['rank']}. {c['name']} ({num(c['index'], 1)})" for c in rk["cities"] if c.get("index") is not None) + "."]
    gd = os.path.join(site, "guias")
    if os.path.isdir(gd):
        lines += ["", "## Guías / Guides"]
        for n in sorted(os.listdir(gd)):
            if not n.endswith(".html") or n == "index.html":
                continue
            t = re.search(r"<title>(.*?)</title>", open(os.path.join(gd, n), encoding="utf-8").read(), re.S)
            title = html.unescape(t.group(1)).split(" | ")[0].strip() if t else n[:-5]
            lines.append(f"- [{title}]({ORIGIN}/guias/{n[:-5]})")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- all of it
def write_all(site):
    """Write every page. One page failing writes its bare template instead (the address still works) and is reported."""
    A, S, meta, rk = load(site)
    areas = A["areas"]
    meta = {**meta, "built_at": A.get("built_at") or meta.get("built_at")}
    out = os.path.join(site, "data", "pages")
    tpl = {n: open(os.path.join(site, f"{n}.html"), encoding="utf-8").read() for n in ("area", "zonas", "mapa", "ranking")}
    problems, written = [], 0

    def put(rel, fn, fallback):
        nonlocal written
        try:
            text = fn()
        except Exception as e:  # noqa: BLE001
            problems.append((rel, f"{type(e).__name__}: {e}"))
            text = fallback
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, dst)
        written += 1

    for a in areas:
        s = S.get(a["slug"])
        put(f"{a['slug']}/index.html", lambda: area_page(tpl["area"], a, s, meta, areas), tpl["area"])
        put(f"{a['slug']}/zonas.html", lambda: zones_page(tpl["zonas"], a, s, meta, areas), tpl["zonas"])
        put(f"{a['slug']}/mapa.html", lambda: map_page(tpl["mapa"], a, s, meta, areas), tpl["mapa"])
    put("mapa.html", lambda: map_page(tpl["mapa"], None, None, meta, areas, spain_top(S, areas)), tpl["mapa"])
    put("ranking.html", (lambda: ranking_page(tpl["ranking"], rk, meta)) if rk else (lambda: tpl["ranking"]), tpl["ranking"])

    def side(name, fn):   # a file beside the pages: on failure the previous one stays
        try:
            text = fn()
        except Exception as e:  # noqa: BLE001
            problems.append((name, f"{type(e).__name__}: {e}"))
            return
        with open(os.path.join(site, "data", name), "w", encoding="utf-8") as fh:
            fh.write(text)
    if rk:
        side("ranking-anuncios.svg", lambda: ranking_svg(rk))
    side("sitemap.xml", lambda: sitemap(areas, meta, site))
    intro_p = os.path.join(site, "llms.txt")
    intro = open(intro_p, encoding="utf-8").read() if os.path.exists(intro_p) else "# tienelicencia.com\n"
    side("llms.txt", lambda: llms(intro, areas, S, meta, rk, site))
    return written, problems
