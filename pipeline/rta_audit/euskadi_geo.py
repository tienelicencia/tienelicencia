"""Bilbao and Donostia: barrio polygons, address points, and an offline geocoder for the Basque register's addresses
(the REATE publishes addresses but no coordinates, and the Spanish Catastro doesn't cover the Basque Country).

Address points come from the two city councils (no Catastro in Euskadi):

  Bilbao   GeoBilbao entity GEOBILBAO_Portales (EPSG:25830 points)
           https://www.geobilbao.eus/geobilbao/api/entities/GEOBILBAO_Portales/geojson
           (the CC BY 3.0 ES open-data CSV of the same "Portales de Bilbao",
           https://www.bilbao.eus/callejero/jsp/od_callejero.jsp?idioma=c&formato=csv&tipo=portales,
           returned HTTP 504 on 17 Oct 2026)
  Donostia "Direcciones postales activas", CC BY-SA 3.0, WGS84 Lon/Lat columns
           https://www.donostia.eus/datosabiertos/recursos/direcciones_activas/indarrekohelbideguztiak.csv

Usage (the pipeline calls prepare(cache_dir, register_idx), which does all of this):
    from rta_audit import euskadi_geo as geocode
    geocode.load_address_points("bilbao", "raw/bilbao_geobilbao_portales.geojson")
    geocode.load_address_points("donostia", "raw/donostia_indarrekohelbideguztiak.csv")
    geocode.geocode("Bidebarrieta, 7, 1º DR (Bilbao)", "48005", "bilbao")
    -> (43.25..., -2.92..., "exact")

Methods returned: "exact" (street+number+letter), "number" (street+number, letter
dropped), "near" (same street, closest same-parity number within 4), "cartociudad"
(only when use_cartociudad=True; 1 req/s, cached). None when the street or number isn't found.
No network is used unless use_cartociudad=True; CartoCiudad answers are cached in
a JSON file (cartociudad_cache.json next to this module, or cache_path=...).
"""
import csv
import difflib
import json
import math
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- normalising

# Street-type words (Spanish, Basque, abbreviations) dropped from the name.
TYPE_WORDS = {
    "calle", "c", "cl", "kalea", "kale", "k", "plaza", "pl", "pza", "plz", "enparantza",
    "plazuela", "avenida", "avda", "av", "avd", "etorbidea", "etorb", "hiribidea", "hirib",
    "paseo", "po", "pso", "pasealekua", "pas", "alameda", "zumardia", "camino", "cm", "bidea",
    "b", "travesia", "zeharbidea", "zeharkalea", "calzada", "galtzada", "grupo", "taldea",
    "barrio", "auzoa", "auzunea", "barriada", "carretera", "ctra", "errepidea", "estrada",
    "ribera", "erribera", "muelle", "kaia", "moll", "ronda", "erronda", "costanilla",
    "aldapa", "cuesta", "subida", "igoera", "jardines", "lorategiak", "parque", "parkea",
    "callejon", "kalezuloa", "pasaje", "pasajea", "pasadizo", "glorieta", "biribilgunea",
    "urbanizacion", "urbanizazioa", "campa", "zelaia", "rampas", "arrapalak", "puente", "zubia",
    "ramal", "adarra", "viaducto", "bidezubia", "alto", "falda", "monte", "mendia",
    "poligono", "industrialdea", "escalinata", "eskailerak", "bajada", "jaitsiera", "trav",
    "gran", "via", "kalexka", "kaleartea", "pasealeku", "enparan", "jardin", "rampa", "pz",
    "pza", "nagusia", "galt", "plazoleta", "plazatxoa", "carrera", "calzadas", "gp", "ps",
}
TYPE_CLASS = {}
for _cls, _words in {
    "calle": "calle c cl kalea kale k",
    "plaza": "plaza pl pza plz pz enparantza plazuela plazoleta plazatxoa",
    "avenida": "avenida avda av avd etorbidea etorb hiribidea hirib",
    "paseo": "paseo po pso ps pasealekua pas pasealeku",
    "camino": "camino cm bidea b",
    "travesia": "travesia trav tr zeharbidea zeharkalea",
    "alameda": "alameda zumardia",
    "calzada": "calzada calzadas galtzada galtzadak",
    "grupo": "grupo gp taldea",
    "barrio": "barrio auzoa auzunea barriada",
    "carretera": "carretera ctra errepidea estrada",
    "carrera": "carrera",
    "ribera": "ribera erribera",
    "muelle": "muelle kaia",
    "jardines": "jardines jardin lorategiak",
    "rampas": "rampas rampa arrapalak",
    "cuesta": "cuesta aldapa subida igoera",
}.items():
    for _w in _words.split():
        TYPE_CLASS[_w] = _cls


def street_type(name, default=None):
    """Canonical street type of a name ('Pl. Santiago' -> 'plaza'), first or last word."""
    toks = re.sub(r"[^a-z ]+", " ", _strip_accents(name.lower())).split()
    for t in (toks[:1] + toks[-1:]) if toks else []:
        if t in TYPE_CLASS:
            return TYPE_CLASS[t]
    return default

# Generic "street" words that never carry meaning on their own.
GENERIC = {"calle", "c", "cl", "kalea", "kale", "k", "kalea"}
# Words kept for meaning but that vary between sources; dropped too.
STOP_WORDS = {"de", "del", "la", "el", "los", "las", "y", "e", "eta", "da", "d", "l", "s",
              "san", "santa", "sta", "sto", "santo", "don", "dona", "doctor", "dr",
              "general", "gral", "plaza", "kalea"}
# Basque genitive endings on the Basque form ("Askatasunaren hiribidea").
_EUS_SUFFIX = re.compile(r"(aren|ren|en|ko|eko|ako)$")


def _strip_accents(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _fold(word):
    """Phonetic fold so Spanish and Basque spellings meet (Recalde/Rekalde,
    Arriquibar/Arrikibar, Chávarri/Txabarri, Vizcaya/Bizkaia, Ybarra/Ibarra)."""
    w = word
    w = w.replace("ch", "tx").replace("qu", "k").replace("gu", "g")
    w = re.sub(r"c(?=[ei])", "z", w)
    w = w.replace("c", "k").replace("v", "b").replace("y", "i").replace("ll", "il")
    w = w.replace("h", "").replace("tz", "z").replace("ts", "s").replace("tx", "x")
    w = re.sub(r"(.)\1+", r"\1", w)  # rr -> r, ss -> s
    return w


def name_tokens(name, drop_types=True):
    s = _strip_accents(name.lower()).replace("ñ", "n")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [t for t in s.split() if t]
    out = []
    for t in toks:
        if drop_types and t in TYPE_WORDS:
            continue
        if t in STOP_WORDS:
            continue
        out.append(_fold(t))
    if not out:  # e.g. the street is literally called "Ronda", "Gran Vía" or "Jardines"
        out = ([_fold(t) for t in toks if t not in STOP_WORDS and t not in GENERIC]
               or [_fold(t) for t in toks])
    return out


def street_keys(name):
    """Return (ordered key, sorted-token key) for a street name."""
    toks = name_tokens(name)
    return " ".join(toks), " ".join(sorted(toks))


# ----------------------------------------------------------- coordinate maths

def utm_to_wgs84(x, y, zone=30):
    """ETRS89 / UTM (EPSG:258zz) -> lat, lon (GRS80; ETRS89 ~ WGS84 to <1 m)."""
    a, f = 6378137.0, 1 / 298.257222101
    k0, e2 = 0.9996, f * (2 - f)
    ep2 = e2 / (1 - e2)
    x -= 500000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
          + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    n1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    t1 = math.tan(p1) ** 2
    c1 = ep2 * math.cos(p1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (
        d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d ** 3 / 6
           + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(p1)
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    return math.degrees(lat), math.degrees(lon0 + lon)


# ------------------------------------------------------------- address index

class CityIndex:
    def __init__(self):
        self.points = {}      # (street_id, num, letter) -> (lat, lon)
        self.nums = {}        # street_id -> {num: (lat, lon)}  (letterless or first seen)
        self.by_key = {}      # ordered key -> set(street_id)
        self.by_sorted = {}   # sorted-token key -> set(street_id)
        self.postcodes = {}   # street_id -> set(postcode)
        self.names = {}       # street_id -> display name
        self.types = {}       # street_id -> set(type class)

    def add_name(self, sid, name):
        alts = [name] + ([a for a in re.split(r"\s*/\s*", name) if a] if "/" in name else [])
        for alt in alts:
            k, ks = street_keys(alt)
            if k:
                self.by_key.setdefault(k, set()).add(sid)
                self.by_sorted.setdefault(ks, set()).add(sid)
        self.names.setdefault(sid, name)
        t = street_type(name)
        if t:
            self.types.setdefault(sid, set()).add(t)

    def add_point(self, sid, num, letter, lat, lon, postcode=None):
        letter = (letter or "").strip().upper()
        self.points.setdefault((sid, num, letter), (lat, lon))
        nd = self.nums.setdefault(sid, {})
        if num not in nd or not letter:
            nd[num] = (lat, lon)
        if postcode:
            self.postcodes.setdefault(sid, set()).add(postcode)


_CITIES = {}

CITY_ALIASES = {"bilbao": "bilbao", "bilbo": "bilbao",
                "donostia": "donostia", "san sebastian": "donostia",
                "donostia / san sebastian": "donostia", "donostia-san sebastian": "donostia"}


def _city(city):
    c = _strip_accents(city.lower()).strip()
    return CITY_ALIASES.get(c, c)


def _int(s):
    m = re.match(r"\s*(\d+)", str(s or ""))
    return int(m.group(1)) if m else None


def load_address_points(city, path, streets_path=None):
    """Load a city's address points. Bilbao: the GeoBilbao portales GeoJSON
    (EPSG:25830). Donostia: the 'direcciones postales activas' CSV (Lon/Lat).
    streets_path (optional, recommended for Donostia): the street-name list
    indarrekokaleak.csv, adding Spanish names (the address file is mostly Basque)."""
    city = _city(city)
    idx = CityIndex()
    if city == "bilbao":
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        for f in data["features"]:
            p = f["properties"]
            x, y = f["geometry"]["coordinates"][:2]
            lat, lon = utm_to_wgs84(float(x), float(y), 30)
            sid = p.get("CodigoCalle") or p.get("Via")
            idx.add_name(sid, p.get("Via") or "")
            idx.add_name(sid, "%s %s" % (p.get("NombreTipoVia") or "", p.get("Via") or ""))
            n = _int(p.get("Portal"))
            if n is not None:
                idx.add_point(sid, n, p.get("Bis"), lat, lon)
    elif city == "donostia":
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    lat, lon = float(r["Lat"]), float(r["Lon"])
                except (KeyError, ValueError):
                    continue
                sid = r.get("Kale_Kodea") or r.get("Kale_IzenMotza")
                for col in ("Kale_IzenMotza", "Kale_IzenLuzea_es", "Kale_IzenLuzea_eu"):
                    if r.get(col):
                        idx.add_name(sid, r[col])
                n = _int(r.get("Atari_ZK"))
                if n is not None:
                    idx.add_point(sid, n, r.get("AtariBis"), lat, lon, (r.get("PostaKodea") or "").strip())
    else:
        raise ValueError("unknown city %r" % city)
    if streets_path:
        with open(streets_path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                sid = r.get("Kale_Kodea")
                if sid in idx.nums:
                    for col in ("Kale_IzenMotza", "Kale_IzenLuzea_es", "Kale_IzenLuzea_eu"):
                        if r.get(col):
                            idx.add_name(sid, r[col])
    idx._keys = list(idx.by_key)
    idx._skeys = list(idx.by_sorted)
    _CITIES[city] = idx
    return idx


# ------------------------------------------------------------- register parse

_TYPE_PREFIX = re.compile(
    r"^(?:[A-Za-zÁÉÍÓÚáéíóúñÑ\.]+/)?"  # Basque type + slash, e.g. "Pasealekua/"
    r"(?:Paseo|Avenida|Avda\.|Plaza|Pl\.|Alameda|Camino|Calzada|Grupo|Travesía|Travesia|"
    r"Barrio|Carretera|Ribera|Muelle|Ronda|Cuesta|Subida|Callejón|Pasaje|Glorieta|"
    r"Urbanización|Barriada|Plazuela|Jardines|Parque|Estrada|Campa)\s+", re.I)


def parse_register_address(text):
    """'Pasealekua/Paseo Uribitarte, 10, 4º E (Bilbao)' -> ('Paseo Uribitarte', 10, '')"""
    s = re.sub(r"\s*\([^)]*\)\s*$", "", text or "").strip()
    parts = [p.strip() for p in s.split(",")]
    street = parts[0] if parts else ""
    # "Pasealekua/Paseo X" -> "Paseo X"; "Etorb./Avda. X" -> "Avda. X"
    street = re.sub(r"^[^\s/]+/(?=\S)", "", street)
    num, letter = None, ""
    if len(parts) > 1:
        m = re.match(r"^(\d+)\s*[-‐ ]?\s*(bis|[A-Za-z])?\b", parts[1])
        if m:
            num = int(m.group(1))
            letter = (m.group(2) or "").upper()
            if letter == "BIS":
                letter = "1"   # Donostia codes "bis" as AtariBis=1
    if num is None:  # "Calle 7" without comma
        m = re.search(r"\s(\d+)\s*([A-Za-z])?$", street)
        if m:
            num, letter = int(m.group(1)), (m.group(2) or "").upper()
            street = street[:m.start()].strip()
    return street, num, letter


# ------------------------------------------------------------------ matching

def _candidate_streets(idx, street, postcode):
    if "/" in street:
        for alt in [street.replace("/", " ")] + re.split(r"\s*/\s*", street):
            c, how = _candidate_streets(idx, alt, postcode)
            if c and how == "name":
                return c, how
        street = re.split(r"\s*/\s*", street)[-1]
    k, ks = street_keys(street)
    cands = idx.by_key.get(k) or idx.by_sorted.get(ks)
    how = "name"
    if not cands:
        # fuzzy on both key forms
        best = difflib.get_close_matches(k, idx._keys, n=3, cutoff=0.86)
        cands = set().union(*(idx.by_key[b] for b in best)) if best else set()
        if not cands:
            best = difflib.get_close_matches(ks, idx._skeys, n=3, cutoff=0.86)
            cands = set().union(*(idx.by_sorted[b] for b in best)) if best else set()
        how = "fuzzy"
    if cands and postcode and len(cands) > 1:
        pc = {c for c in cands if postcode in idx.postcodes.get(c, ())}
        if pc:
            cands = pc
    if cands and len(cands) > 1:
        want = street_type(street, "calle")   # no type word in the register = Calle
        same = {c for c in cands if want in idx.types.get(c, ())}
        if same:
            cands = same
    return cands, how


def _lookup(idx, cands, num, letter):
    for sid in cands:
        if (sid, num, letter) in idx.points:
            return idx.points[(sid, num, letter)], "exact"
    for sid in cands:
        if num in idx.nums.get(sid, {}):
            return idx.nums[sid][num], ("number" if letter else "exact")
    best = None
    for sid in cands:
        for n, ll in idx.nums.get(sid, {}).items():
            d = abs(n - num)
            if d <= 4 and d % 2 == 0 and (best is None or d < best[0]):
                best = (d, ll)
    if best:
        return best[1], "near"
    return None, None


_CC_CACHE = {}
_CC_LAST = [0.0]


def _cartociudad(street, num, postcode, city_label, cache_path, muni_code=None):
    if not _CC_CACHE and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            _CC_CACHE.update(json.load(fh))
    # CartoCiudad returns nothing when a postcode is in the query: street, number, town only
    q = "%s %s, %s" % (street, num, city_label)
    if q in _CC_CACHE:
        return _CC_CACHE[q]
    wait = 1.0 - (time.time() - _CC_LAST[0])
    if wait > 0:
        time.sleep(wait)
    url = "https://www.cartociudad.es/geocoder/api/geocoder/findJsonp?" + urllib.parse.urlencode({"q": q})
    res = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "tienelicencia.com geocoder"}), timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
        _CC_LAST[0] = time.time()
        body = body[body.find("(") + 1: body.rfind(")")] if body.lstrip().startswith("callback") else body
        d = json.loads(body)
        # only accept a portal-level hit ("portal"/"Portal"), with the same number
        if d and d.get("lat") and str(d.get("type", "")).lower() == "portal" \
                and _int(d.get("portalNumber")) == num \
                and (not muni_code or d.get("muniCode") == muni_code):
            res = [float(d["lat"]), float(d["lng"])]
    except Exception:
        res = None
    _CC_CACHE[q] = res
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(_CC_CACHE, fh, ensure_ascii=False)
    return res


def geocode(address_text, postcode, city, use_cartociudad=False, cache_path=None, allow_near=True):
    """Return (lat, lon, method) or None. Call load_address_points(city, ...) first."""
    c = _city(city)
    idx = _CITIES.get(c)
    if idx is None:
        raise RuntimeError("call load_address_points(%r, path) first" % c)
    street, num, letter = parse_register_address(address_text)
    if not street or num is None:
        return None
    pc = (postcode or "").strip()
    cands, _ = _candidate_streets(idx, street, pc)
    if cands:
        ll, method = _lookup(idx, cands, num, letter)
        if ll and (allow_near or method != "near"):
            return ll[0], ll[1], method
    if use_cartociudad:
        label = {"bilbao": "Bilbao", "donostia": "Donostia"}.get(c, city)
        ine = {"bilbao": "48020", "donostia": "20069"}.get(c)
        cp = cache_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "cartociudad_cache.json")
        r = _cartociudad(street, num, pc, label, cp, ine)
        if r:
            return r[0], r[1], "cartociudad"
    return None


# ------------------------------------------------------------- barrios, download, geocoding for the pipeline
SMALL = {"de", "del", "la", "el", "y"}


def nice(name):
    words = name.strip().lower().split()
    out = []
    for i, w in enumerate(words):
        out.append(w if (i and w in SMALL) else "-".join(p[:1].upper() + p[1:] for p in w.split("-")))
    return " ".join(out).replace(" - ", "-")


THIN_M = 8   # drop outline points closer than this to the last one kept: the site's barrio file stays small


def ring(r, conv):
    out = []
    for p in r:
        q = [round(c, 6) for c in conv(p)]
        if not out or abs(q[0] - out[-1][0]) * 81000 + abs(q[1] - out[-1][1]) * 111000 >= THIN_M:
            out.append(q)
    if out[-1] != out[0]:
        out.append(out[0])
    return out if len(out) >= 4 else [[round(c, 6) for c in conv(p)] for p in r]


def as_multi(geom):
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]


def _bilbao_barrios(raw):
    src = json.load(open(os.path.join(raw, "bilbao_barrios.geojson"), encoding="utf-8"))
    districts = {"1": "Deusto", "2": "Uribarri", "3": "Otxarkoaga-Txurdinaga", "4": "Begoña",
                 "5": "Ibaiondo", "6": "Abando", "7": "Errekalde", "8": "Basurto-Zorrotza"}
    conv = lambda p, _u=utm_to_wgs84: (lambda la_lo: (la_lo[1], la_lo[0]))(_u(p[0], p[1], 30))
    feats = {}
    for f in src["features"]:
        p = f["properties"]
        name = nice(p["Nombre"])
        dist = districts.get(str(p["CodigoDistrito"]), str(p["CodigoDistrito"]))
        if name == "Diseminado":
            name = "Diseminado (%s)" % dist
        polys = [[ring(r, conv) for r in poly] for poly in as_multi(f["geometry"])]
        feats.setdefault(name, {"polys": [], "group": dist})["polys"].extend(polys)
    return feats


def _donostia_barrios(raw):
    src = json.load(open(os.path.join(raw, "donostia_auzoak.json"), encoding="utf-8-sig"))
    conv = lambda p: (p[0], p[1])
    feats = {}
    for f in src["features"]:
        name = nice(f["properties"]["IzenAuzo"])
        polys = [[ring(r, conv) for r in poly] for poly in as_multi(f["geometry"])]
        feats.setdefault(name, {"polys": [], "group": None})["polys"].extend(polys)
    return feats


def _write_barrios(feats, path):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"neighbourhood": n, "neighbourhood_group": v["group"]},
         "geometry": {"type": "MultiPolygon", "coordinates": v["polys"]}}
        for n, v in sorted(feats.items())]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(",", ":"))



GEOBILBAO = "https://www.geobilbao.eus/geobilbao/api/entities/{}/geojson"   # Ayuntamiento de Bilbao, CC BY 3.0 ES
DSS = "https://www.donostia.eus/datosabiertos/recursos/"                    # Ayuntamiento de Donostia, CC BY-SA 3.0
GEO_SOURCES = {"bilbao_portales.geojson": GEOBILBAO.format("GEOBILBAO_Portales"),
               "bilbao_barrios.geojson": GEOBILBAO.format("GEOBILBAO_Barrios"),
               "donostia_direcciones.csv": DSS + "direcciones_activas/indarrekohelbideguztiak.csv",
               "donostia_calles.csv": DSS + "callejero/indarrekokaleak.csv",
               "donostia_auzoak.json": DSS + "mapa_auzoak/auzoak.json"}
GEO_MAX_AGE_DAYS = 30


def prepare(cache_dir, idx):
    """Download the cities' address points and barrios (monthly; keep old copies on failure), write
    euskadi/<city>_barrios.geojson and euskadi/geocoded.json ({register key: [lat, lon]} for flats and rooms)."""
    from . import http
    d = os.path.join(cache_dir, "euskadi")
    raw = os.path.join(d, "raw")
    os.makedirs(raw, exist_ok=True)
    for name, url in GEO_SOURCES.items():
        p = os.path.join(raw, name)
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < GEO_MAX_AGE_DAYS * 86400:
            continue
        try:
            r = http.get(url, timeout=300)
            if len(r.content) < 10000:
                raise ValueError(f"unexpectedly small ({len(r.content)} bytes)")
            open(p, "wb").write(r.content)
        except Exception as e:  # noqa: BLE001
            print(f"euskadi geo: {name} download failed, keeping previous copy:", e)
    if os.path.exists(os.path.join(raw, "bilbao_barrios.geojson")):
        _write_barrios(_bilbao_barrios(raw), os.path.join(d, "bilbao_barrios.geojson"))
    if os.path.exists(os.path.join(raw, "donostia_auzoak.json")):
        _write_barrios(_donostia_barrios(raw), os.path.join(d, "donostia_barrios.geojson"))
    loaded = set()
    if os.path.exists(os.path.join(raw, "bilbao_portales.geojson")):
        load_address_points("bilbao", os.path.join(raw, "bilbao_portales.geojson"))
        loaded.add("bilbao")
    if os.path.exists(os.path.join(raw, "donostia_direcciones.csv")):
        load_address_points("donostia", os.path.join(raw, "donostia_direcciones.csv"),
                            os.path.join(raw, "donostia_calles.csv") if os.path.exists(os.path.join(raw, "donostia_calles.csv")) else None)
        loaded.add("donostia")
    out, tried = {}, 0
    for k, v in idx.items():
        c = _city(v.get("muni") or "")
        if c not in loaded or v.get("lat") is not None or k[0] not in "EL":
            continue
        tried += 1
        g = geocode(v.get("address") or "", v.get("postcode"), c)
        if g:
            out[k] = [round(g[0], 6), round(g[1], 6)]
    json.dump(out, open(os.path.join(d, "geocoded.json"), "w"))
    print(f"euskadi geo: {len(out)} of {tried} flats and rooms placed from their address")
    return out
