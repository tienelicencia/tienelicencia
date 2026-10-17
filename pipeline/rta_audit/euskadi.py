"""Bilbao and Donostia/San Sebastián (Euskadi): registration numbers, the Basque tourism register (REATE), and the same
classification as the other regions.

Numbers: a letter for the kind of accommodation, the province (BI Bizkaia, SS Gipuzkoa, VI Araba) and five digits:
EBI00123 tourist flat (vivienda de uso turístico), LSS00123 rooms in a private home (habitaciones en vivienda particular),
H… hotels, P… pensions, T… tourist apartments, B… hostels, K/X… rural houses and agrotourism, C… campsites. The national
number (ESFCTU…ESS005789) ends with the regional number followed by a check digit.
Register: the Basque Government's open data lists active flats and rooms (address, no coordinates) and the other
establishments (with coordinates). We never keep phone, email, web or trade-name columns.
"""
import json
import re

from .buildings import muni_key
from .register import haversine_m

LOCATION_THRESHOLD_M = 800      # same as everywhere else
SEASONAL_NIGHTS = 32            # tourist use is presumed for stays of 31 days or less (Decreto 101/2018, art. 2.4.b)

REGIONAL_RE = re.compile(r"(?<![A-Z0-9])([ELHPTBKXC])[\s\-_./]*(BI|SS|VI)[\s\-_./]*(\d{1,6})(?![0-9])", re.IGNORECASE)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)

# ---------------------------------------------------------------- downloads
BASE = "https://opendata.euskadi.eus/contenidos/ds_recursos_turisticos"
SOURCES = {"viviendas.json": f"{BASE}/habitaciones_viviendas_turisti/opendata/viviendas.json",
           "habitaciones.json": f"{BASE}/habitaciones_viviendas_turisti/opendata/habitaciones.json",
           "alojamientos.json": f"{BASE}/alojamiento_de_euskadi/opendata/alojamientos.json",
           "rurales.json": f"{BASE}/alojamientos_rurales_euskadi/opendata/alojamientos.json"}
# Only the columns we use: never phone, email, web or the trade name
KEEP = {"Nregistro": "code", "signatura": "code", "FechainscripcionREATE": "since", "Direccion": "address", "address": "address",
        "Codigopostal": "postcode", "postalCode": "postcode", "Localidad": "locality", "locality": "locality",
        "Municipio": "muni", "municipality": "muni", "Capacidad": "places", "capacity": "places", "latwgs84": "lat",
        "lonwgs84": "lon", "lodgingType": "kind", "Tipoalojamiento": "kind"}


def _rows(text):
    j = json.loads(text.lstrip("﻿"))
    if isinstance(j, dict):
        j = next((v for v in j.values() if isinstance(v, list)), [])
    return j


def fetch(cache_dir):
    """Download the four register files (selected fields only). Keeps the previous copies if a download fails."""
    import os
    from . import http
    d = os.path.join(cache_dir, "euskadi")
    os.makedirs(d, exist_ok=True)
    for name, url in SOURCES.items():
        try:
            r = http.get(url, timeout=300)
            rows = _rows(r.content.decode("utf-8-sig", "ignore"))
            if len(rows) < 100:
                raise ValueError(f"unexpected file ({len(rows)} rows)")
            slim = [{k2: x.get(k1) for k1, k2 in KEEP.items() if x.get(k1) not in (None, "")} for x in rows]
            json.dump([x for x in slim if x.get("code")], open(os.path.join(d, name), "w", encoding="utf-8"), ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            print(f"euskadi: {name} download failed, keeping previous copy:", e)
    paths = [os.path.join(d, n) for n in SOURCES]
    from . import euskadi_geo   # barrios and address points for the two cities; places the register's flats and rooms
    euskadi_geo.prepare(cache_dir, load_register(paths))
    return paths


def key(letter, prov, num):
    """'E', 'SS', '005789' → 'ESS00578' (six digits = five plus a check digit); '578' → 'ESS00578'."""
    n = num[:5] if len(num) == 6 else num
    return f"{letter.upper()}{prov.upper()}{int(n):05d}"


def parse(raw):
    """→ {"regional": [keys], "national": [raw], "embedded": [keys from national numbers], "exempt_text": str|None}"""
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    rest = NATIONAL_RE.sub(" ", text)
    regional = list(dict.fromkeys(key(*m.groups()) for m in REGIONAL_RE.finditer(rest)))
    embedded = []
    for n in national:
        m = re.search(r"([ELHPTBKXC])(BI|SS|VI)(\d{5,6})$", n.upper())
        if m:
            embedded.append(key(*m.groups()))
    e = EXEMPT_RE.search(text)
    return {"regional": regional, "national": national, "embedded": list(dict.fromkeys(embedded)),
            "exempt_text": e.group(0).strip() if e else None}


def fix_text(s):
    """Inside Airbnb's Basque file has double-encoded accents ('SebastiÃ¡n'): undo that when it applies."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError, AttributeError):
        return s


def muni(name):
    """'Donostia / San Sebastián', 'Donostia-San SebastiÃ¡n' → 'DONOSTIASANSEBASTIAN'."""
    return muni_key(fix_text(name or ""))


def load_register(paths, geocoded=None):
    """{key: {"kind", "group", "muni", "lat", "lon", "places", "address", "postcode", "since"}} for every entry.
    geocoded: {key: [lat, lon]} for flats and rooms, whose addresses we place ourselves (rta_audit.euskadi_geo)."""
    import os
    idx = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        for r in json.load(open(p, encoding="utf-8")):
            m = re.match(r"([ELHPTBKXC])(BI|SS|VI)0*(\d+)$", (r.get("code") or "").strip().upper())
            if not m:
                continue
            k = f"{m.group(1)}{m.group(2)}{int(m.group(3)):05d}"
            try:
                la, lo = float(r["lat"]), float(r["lon"])
            except (KeyError, TypeError, ValueError):
                la, lo = (geocoded or {}).get(k, (None, None))
            idx[k] = {"letter": m.group(1), "kind": r.get("kind"), "muni": fix_text(r.get("muni") or ""),
                      "lat": la, "lon": lo, "address": " ".join((r.get("address") or "").split()),
                      "postcode": r.get("postcode"), "locality": r.get("locality"), "since": r.get("since"),
                      "places": int(r["places"]) if str(r.get("places") or "").isdigit() else None,
                      "group": "Completa" if m.group(1) == "E" else "Por habitaciones" if m.group(1) == "L" else None}
    return idx


def classify(raw, lat, lon, room_type, min_nights, idx, listing_muni):
    """Same categories and location rule as rta_audit.baleares: within 800 m of the registered point is a match; beyond
    that, or with no registered point, the municipality decides (FOUND_INCONSISTENT in the same one, else
    FOUND_OTHER_MUNICIPALITY)."""
    p = parse(raw)
    codes = p["regional"] or p["embedded"]
    here = muni(listing_muni) if listing_muni else None
    if codes:
        best = None
        for k in codes:
            rec = idx.get(k)
            if not rec:
                cat = "NOT_IN_REGISTER"
            else:
                d = haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]) \
                    if rec["lat"] is not None and lat not in (None, "") else None
                same = here is None or muni(rec["muni"]) == here
                cat = "FOUND_CONSISTENT" if (d is not None and d <= LOCATION_THRESHOLD_M) or (d is None and same) \
                    else "FOUND_INCONSISTENT" if same else "FOUND_OTHER_MUNICIPALITY"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        rec = idx.get(best[2]) or {}
        return {"category": best[1], "key": best[2], "embedded_only": not p["regional"], "group": rec.get("group")}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or (p["exempt_text"] and re.search(r"(?i)seasonal|temporada", p["exempt_text"])) \
            or p["national"]:
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


VUT_TYPE = "Vivienda de uso turístico"
TYPE_MAP = {"E": VUT_TYPE, "L": VUT_TYPE, "H": "Establecimiento Hotelero", "P": "Establecimiento Hotelero",
            "T": "Apartamento turístico", "B": "Establecimiento Hotelero", "K": "Casa rural", "X": "Casa rural", "C": "Camping"}
_ADDR = re.compile(r"^(.*?),\s*(\d+\s*[A-Z]?)\b(.*)$", re.IGNORECASE)   # "Bidebarrieta, 7, 1º DR (Bilbao)"
PROVINCE = {"BI": "BIZKAIA", "SS": "GIPUZKOA", "VI": "ARABA"}


def as_register_records(idx, munis):
    """Entries in `munis` (register spelling, e.g. {"Bilbao", "Donostia / San Sebastián"}) in the same shape as Junta
    register records, so maps, buildings, barrios and search work unchanged."""
    want = {muni(m) for m in munis}
    out = []
    for k, v in idx.items():
        if muni(v["muni"]) not in want:
            continue
        addr = re.sub(r"\s*\([^)]*\)\s*$", "", v.get("address") or "")
        m = _ADDR.match(addr)
        rest = (m.group(3) if m else "").strip(" ,")
        out.append({"registration_code": k, "objects_type_id": TYPE_MAP.get(v["letter"], "Otros"), "group": v["group"],
                    "municipalities": v["muni"], "provinces": PROVINCE[k[1:3]], "lat": v["lat"], "lon": v["lon"],
                    "road_name": m.group(1) if m else addr, "km_num": m.group(2).replace(" ", "") if m else None,
                    "floor": rest or None, "door": None, "staircase": None, "block": None, "portal": None,
                    "postal_code": v.get("postcode"), "locality": v.get("locality"), "tot_gen_places": v.get("places"),
                    "registration_date": _ymd(v.get("since")), "domicile_complement": None, "catastral_ref": None})
    return out


def _ymd(d):
    s = str(d or "")
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", s) or None
    if m:
        return "".join(m.groups())
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    return f"{m.group(3)}{m.group(2)}{m.group(1)}" if m else ""
