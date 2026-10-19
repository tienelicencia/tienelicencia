"""Official barrio (or district) outlines for the cities without Inside Airbnb neighbourhoods: downloaded from each city
council's open data, normalised to one WGS84 GeoJSON per city in the Inside Airbnb neighbourhoods shape
({"neighbourhood": name, "neighbourhood_group": district}), which geo.Barrios reads.

Monthly, like the other sources: a failed download keeps the previous copy (cache/boundaries/raw/<city>.*); the normalised
file (cache/boundaries/<city>.geojson) is rewritten from whatever raw copy there is. Each source's licence is recorded in
SOURCES (and shown on the area pages / methodology). Checked 19 Oct 2026.
"""
import io
import json
import math
import os
import re
import struct
import time
import zipfile

from .buildings import street_name

MAX_AGE_DAYS = 30
THIN_M = 8   # drop outline points closer than this to the last one kept: the site's barrio file stays small

# level: "barrio" (preferred) or "district" (fallback, where the council publishes nothing finer)
SOURCES = {
    "zaragoza": {   # no barrio layer: the 15 urban juntas municipales (one per district) and the 14 rural barrios
        "url": "https://idezar-sig.zaragoza.es/servicios/geoserver/urbanismo/wfs?service=WFS&version=2.0.0&request=GetFeature"
               "&outputFormat=application%2Fjson&srsName=EPSG%3A4326&typeNames=urbanismo:Juntas_Municipales_Vecinales",
        "format": "geojson", "name": "nombre", "level": "district", "skip_prop": ("estado", "BAJA"),
        "es": "juntas municipales y vecinales del Ayuntamiento de Zaragoza (IDEZar)",
        "en": "Zaragoza city council district and rural-barrio boards (IDEZar)",
        "page": "https://zaragoza.es/web/espacio-de-datos/servicio/catalogo/3962",
        "licence": "Condiciones generales de reutilización del Ayuntamiento de Zaragoza (reuse allowed, cite "
                   "\"Origen de los datos: Ayuntamiento de Zaragoza\"): https://www.zaragoza.es/sede/portal/aviso-legal#condiciones"},
    "valladolid": {
        "url": "https://gisava.valladolid.es/server/rest/services/Barrios_y_Subzonas_de_Valladolid/FeatureServer/2/query"
               "?where=1%3D1&outFields=*&outSR=4326&f=geojson",
        "format": "geojson", "name": "NOMBRE_BAR", "level": "barrio",
        "es": "barrios del Ayuntamiento de Valladolid (Barrios y Subzonas)", "en": "Valladolid city council barrios (Barrios y Subzonas)",
        "page": "https://www10.ava.es/cartografia/ficheros_shp.html",
        "licence": "CC BY 3.0 ES (Ayuntamiento de Valladolid open-data reuse conditions): "
                   "https://www.valladolid.es/es/temas/hacemos/open-data-datos-abiertos/condiciones-reutilizacion"},
    "murcia": {   # the city's 28 barrios and the municipality's 55 pedanías
        "url": "https://geoserver.murcia.es/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature"
               "&typeNames=Murcia:pedanias_barrios&outputFormat=application%2Fjson&srsName=EPSG%3A4326",
        "format": "geojson", "name": "nombre", "level": "barrio",
        "es": "barrios y pedanías del Ayuntamiento de Murcia (Geoportal)", "en": "Murcia city council barrios and pedanías (Geoportal)",
        "page": "https://geoportal.murcia.es/centro-de-descargas",
        "licence": "No licence stated; the council's Ordenanza de Transparencia y Reutilización (BORM 248, 26 Oct 2017, art. 36) "
                   "makes reuse without conditions the default, citing the source"},
    "alicante": {
        "url": "https://guiaurbana.alicante.es/geoserver/publicowfs/wfs?service=WFS&version=2.0.0&request=GetFeature"
               "&typeNames=publicowfs:Barrio&outputFormat=application/json&srsName=EPSG:4326",
        "format": "geojson", "name": "NOMBRE", "level": "barrio",
        "es": "barrios del Ayuntamiento de Alicante (Guía Urbana, WFS)", "en": "Alicante city council barrios (Guía Urbana WFS)",
        "page": "https://guiaurbana.alicante.es/geoserver/publicowfs/wfs?service=WFS&version=2.0.0&request=GetCapabilities",
        "licence": "No licence stated (service: no fees, no access constraints); reused under Ley 37/2007 with attribution"},
    "laspalmas": {
        "url": "https://sit.laspalmasgc.es/server/rest/services/opendata/barrios/MapServer/0/query?where=1%3D1&outFields=*"
               "&f=geojson&outSR=4326",
        "format": "geojson", "name": "NUCL_DS_NOMBRE", "group": "DIST_CO_ID", "level": "barrio",
        # DIST_CO_ID by membership (the district layer's own geometry doesn't come back in WGS84)
        "groups": {"1": "Vegueta, Cono Sur y Tafira", "2": "Centro", "3": "Isleta-Puerto-Guanarteme", "4": "Ciudad Alta",
                   "5": "Tamaraceite-San Lorenzo-Tenoya"},
        "es": "barrios del Ayuntamiento de Las Palmas de Gran Canaria (datos abiertos, callejero municipal)",
        "en": "Las Palmas de Gran Canaria city council barrios (open data, municipal street map)",
        "page": "https://datos.gob.es/es/catalogo/l01350167-callejero-municipal-de-las-palmas-de-gran-canaria",
        "licence": "Condiciones de reutilización del Ayuntamiento (reuse allowed with attribution): "
                   "http://datosabiertos.laspalmasgc.es/condiciones-de-reutilizacion/"},
    "palma": {
        "url": "https://geoportal.palma.es/geoserver/space/ows?authkey=null&service=WFS&version=2.0.0&request=GetFeature"
               "&typeNames=space:ADMBARRIOS&outputFormat=application/json&srsName=EPSG:4326",
        "format": "geojson", "name": "barri", "group": "districte", "level": "barrio",
        "es": "barris de l'Ajuntament de Palma (IDE de Palma)", "en": "Ajuntament de Palma barrios (Palma SDI)",
        "page": "https://geoportal.palma.cat/geonetwork/srv/api/records/spa_ajpalma_admbarrios",
        "licence": "No licence named; metadata: no limitations on public access; reused under Ley 37/2007 with attribution"},
    "cordoba": {
        "url": "https://datosabiertos.cordoba.es/ckan/dataset/26295d6b-02a8-4a77-93a0-8e8f45bd36fb/resource/"
               "b12bf527-ea7e-4e17-bfdc-2e9e0172e834/download/distritos.geojson",
        "format": "geojson", "name": "name", "level": "district", "skip": r"^ZONA INDUSTRIAL",
        "es": "distritos del Ayuntamiento de Córdoba (datos abiertos, recursos cartográficos)",
        "en": "Córdoba city council districts (open data, map resources)",
        "page": "https://datosabiertos.cordoba.es/ckan/dataset/movilidad-cartografia",
        "licence": "Not specified on the portal (license_id notspecified); reused under Ley 37/2007 with attribution"},
    "granada": {
        "ckan": ("https://opendata.granada.org/api/3/action/package_show?id=distritos-y-territorio-granada", r"\.zip$"),
        "url": "https://opendata.granada.org/dataset/cf4dab5c-6e37-4cb2-996f-d72576e71f14/resource/"
               "e3487eb6-2543-4165-8252-3fa00597579a/download/101_distritos_municipales_20230101.zip",
        "format": "shpzip", "member": r"Asociaciones_Vecinos.*\.shp$", "crs": "ed50utm30", "encoding": "latin-1",
        "name": "AAVV", "group": "DISTRITO", "level": "barrio",
        "es": "barrios (ámbitos de las asociaciones de vecinos) del Ayuntamiento de Granada (datos abiertos)",
        "en": "Granada city council barrios (residents' association areas; open data)",
        "page": "https://opendata.granada.org/dataset/distritos-y-territorio-granada",
        "licence": "CC BY (http://www.opendefinition.org/licenses/cc-by)"},
}


def label(slug):
    """What the page says about a city's outlines: {"es", "en", "level", "page", "licence"}."""
    s = SOURCES[slug]
    return {k: s[k] for k in ("es", "en", "level", "page", "licence")}


# ---------------------------------------------------------------- coordinates
def _utm_inverse(x, y, zone, a, f):
    """UTM → geographic (lat, lon in degrees) on the given ellipsoid."""
    k0, lon0, e2 = 0.9996, math.radians(zone * 6 - 183), f * (2 - f)
    ep2 = e2 / (1 - e2)
    x -= 500000.0
    mu = y / k0 / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    n1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    t1, c1 = math.tan(p1) ** 2, ep2 * math.cos(p1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                          + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(p1)
    return math.degrees(lat), math.degrees(lon)


def ed50_utm30_to_wgs84(x, y):
    """ED50 / UTM 30N (EPSG:23030) → WGS84 (lat, lon): International 1924 ellipsoid, then the three-parameter shift
    ED50 → WGS84 (EPSG:1133, dx −87, dy −98, dz −121 m; a few metres, plenty for barrio outlines)."""
    a, f = 6378388.0, 1 / 297.0
    la, lo = map(math.radians, _utm_inverse(x, y, 30, a, f))
    e2 = f * (2 - f)
    n = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    X, Y, Z = n * math.cos(la) * math.cos(lo) - 87, n * math.cos(la) * math.sin(lo) - 98, n * (1 - e2) * math.sin(la) - 121
    a2, f2 = 6378137.0, 1 / 298.257223563
    e22, p = f2 * (2 - f2), math.hypot(X, Y)
    lat = math.atan2(Z, p * (1 - e22))
    for _ in range(5):
        n2 = a2 / math.sqrt(1 - e22 * math.sin(lat) ** 2)
        lat = math.atan2(Z + e22 * n2 * math.sin(lat), p)
    return math.degrees(lat), math.degrees(math.atan2(Y, X))


# ---------------------------------------------------------------- shapefiles (no GDAL on the runners)
def read_shp(shp, dbf, encoding="latin-1"):
    """Polygons from a Shapefile: [(properties, [ring, …])], rings as [(x, y), …] in the file's own coordinates."""
    out = []
    # .dbf: header, field descriptors, fixed-width records
    n, hlen, rlen = struct.unpack("<IHH", dbf[4:12])
    fields, pos = [], 32
    while dbf[pos] != 0x0D:
        name = dbf[pos:pos + 11].split(b"\0")[0].decode("ascii")
        fields.append((name, dbf[pos + 11:pos + 12].decode("ascii"), dbf[pos + 16]))
        pos += 32
    props = []
    for i in range(n):
        r, o, p = dbf[hlen + i * rlen: hlen + (i + 1) * rlen], 1, {}
        for name, typ, ln in fields:
            v = r[o:o + ln].decode(encoding, "replace").strip()
            if typ in "NF" and v:
                try:
                    v = float(v) if "." in v else int(v)
                except ValueError:
                    pass
            p[name], o = v, o + ln
        props.append(p)
    # .shp: 100-byte header, then records (big-endian header, little-endian content)
    pos, k = 100, 0
    while pos + 8 <= len(shp):
        _num, clen = struct.unpack(">ii", shp[pos:pos + 8])
        body = shp[pos + 8: pos + 8 + clen * 2]
        pos += 8 + clen * 2
        typ = struct.unpack("<i", body[:4])[0]
        rings = []
        if typ in (5, 15, 25):   # polygon (Z, M variants share the same leading layout)
            nparts, npts = struct.unpack("<ii", body[36:44])
            parts = list(struct.unpack(f"<{nparts}i", body[44:44 + 4 * nparts])) + [npts]
            base = 44 + 4 * nparts
            pts = [struct.unpack("<dd", body[base + 16 * j: base + 16 * j + 16]) for j in range(npts)]
            rings = [pts[parts[j]:parts[j + 1]] for j in range(nparts)]
        if k < len(props) and rings:
            out.append((props[k], rings))
        k += 1
    return out


def _ring_area(r):
    return sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1)) / 2


def _thin(ring):
    """[(lon, lat)] rounded to ~10 cm, dropping points closer than THIN_M to the last one kept; closed."""
    out = []
    for lo, la in ring:
        q = [round(lo, 6), round(la, 6)]
        if not out or abs(q[0] - out[-1][0]) * 85000 + abs(q[1] - out[-1][1]) * 111000 >= THIN_M:
            out.append(q)
    if out[-1] != out[0]:
        out.append(out[0])
    return out if len(out) >= 4 else [[round(lo, 6), round(la, 6)] for lo, la in ring]


# ---------------------------------------------------------------- normalising
def nice(name):
    """'SANTA CATALINA - CANTERAS' → 'Santa Catalina - Canteras'; '00 Distrito CENTRO ' → 'Centro'; mixed case kept."""
    s = " ".join(str(name or "").split())
    s = re.sub(r"^\d+\s+(Distrito\s+)?", "", s, flags=re.I)              # Córdoba: "00 Distrito CENTRO"
    s = re.sub(r"^(Periurbano [^:]+):\s*", "", s)                         # Córdoba: "08 Periurbano Oeste-Sierra: VILLARRUBIA"
    if s.upper() == s:
        s = re.sub(r"\s*-\s*", " - ", street_name(s))
        s = re.sub(r"\bSta\.\s*", "Santa ", s)                                                    # Murcia: STA. EULALIA
        s = re.sub(r"\b(?:X{0,3}(?:IX|IV|V?I{1,3})|X{1,3}V?)\b", lambda m: m.group(0).upper(), s, flags=re.I)   # Juan XXIII
        s = re.sub(r"(?<=\s)(D|L|S)'(En |Es |Na )?", lambda m: m.group(0).lower(), s)           # Camp d'en Serralta
        s = re.sub(r"·(\w)", lambda m: "·" + m.group(1).lower(), s)                             # Son Rul·lan
        s = re.sub(r"(?<=\s)(Dels|Des|Del|Els|Les|Sa|Ses)(?=\s)", lambda m: m.group(1).lower(), s)   # Plaça dels Patins
    return s


def normalise(slug, raw):
    """Raw bytes of a city's download → {name: {"polys": [[ring, …], …], "group": district}} in WGS84 [lon, lat]."""
    src = SOURCES[slug]
    feats = []
    if src["format"] == "geojson":
        g = json.loads(raw.decode("utf-8-sig"))
        for f in g["features"]:
            geom = f.get("geometry") or {}
            if geom.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            feats.append((f["properties"], [[[(p[0], p[1]) for p in r] for r in poly] for poly in polys]))
    else:   # zipped Shapefile
        z = zipfile.ZipFile(io.BytesIO(raw))
        shp = next(n for n in z.namelist() if re.search(src["member"], n, re.I))
        rows = read_shp(z.read(shp), z.read(shp[:-4] + ".dbf"), src.get("encoding", "latin-1"))
        conv = ed50_utm30_to_wgs84 if src.get("crs") == "ed50utm30" else None
        for props, rings in rows:
            ll = [[(lambda la_lo: (la_lo[1], la_lo[0]))(conv(x, y)) for x, y in r] for r in rings]
            # Shapefile rings: outer rings clockwise, holes anticlockwise; each outer ring starts a polygon
            polys = []
            for r_xy, r in zip(rings, ll):
                if _ring_area(r_xy) <= 0 or not polys:
                    polys.append([r])
                else:
                    polys[-1].append(r)
            feats.append((props, polys))
    out = {}
    groups = src.get("groups") or {}
    for props, polys in feats:
        raw_name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", str(props.get(src["name"]) or "")).strip()   # Zaragoza: stray U+0093
        if not raw_name or raw_name == "-" or (src.get("skip") and re.search(src["skip"], raw_name, re.I)):
            continue
        if src.get("skip_prop") and str(props.get(src["skip_prop"][0]) or "").upper() == src["skip_prop"][1]:
            continue
        g_ = props.get(src["group"]) if src.get("group") else None
        group = groups.get(str(g_), nice(g_) if g_ not in (None, "") else None)
        name = nice(raw_name)
        if name.lower() in ("diseminado", "disperso") and group:
            name = f"{name} ({group})"
        e = out.setdefault(name, {"polys": [], "group": group})
        e["polys"].extend([[_thin(r) for r in poly] for poly in polys])
    return out


def write(feats, path):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"neighbourhood": n, "neighbourhood_group": v["group"]},
         "geometry": {"type": "MultiPolygon", "coordinates": v["polys"]}} for n, v in sorted(feats.items())]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(",", ":"))


def _url(src):
    """A CKAN dataset's current file (its name carries the edition date), else the fixed URL."""
    from . import http
    if src.get("ckan"):
        try:
            api, pat = src["ckan"]
            res = http.get(api, timeout=60).json()["result"]["resources"]
            return next(r["url"] for r in res if re.search(pat, r.get("url") or "", re.I))
        except Exception as e:  # noqa: BLE001
            print("boundaries: CKAN lookup failed, using the known file:", e)
    return src["url"]


def fetch(cache_dir, slugs=None):
    """Download each city's outlines (monthly; keep the previous copy on failure) and write boundaries/<city>.geojson.
    Returns {city: number of barrios}."""
    from . import http
    d = os.path.join(cache_dir, "boundaries")
    raw_d = os.path.join(d, "raw")
    os.makedirs(raw_d, exist_ok=True)
    done = {}
    for slug, src in SOURCES.items():
        if slugs and slug not in slugs:
            continue
        rp = os.path.join(raw_d, f"{slug}.{'zip' if src['format'] == 'shpzip' else 'geojson'}")
        if not (os.path.exists(rp) and time.time() - os.path.getmtime(rp) < MAX_AGE_DAYS * 86400):
            try:
                body = http.get(_url(src), timeout=300).content
                if len(body) < 5000:
                    raise ValueError(f"unexpectedly small ({len(body)} bytes)")
                feats = normalise(slug, body)   # only replace the cached copy with one that parses
                if len(feats) < 5:
                    raise ValueError(f"only {len(feats)} areas")
                open(rp, "wb").write(body)
            except Exception as e:  # noqa: BLE001
                print(f"boundaries {slug}: download failed, keeping previous copy:", e)
        if os.path.exists(rp):
            feats = normalise(slug, open(rp, "rb").read())
            write(feats, os.path.join(d, f"{slug}.geojson"))
            done[slug] = len(feats)
    print("boundaries:", done)
    return done
