"""Las Palmas de Gran Canaria (Canarias): registration numbers, the Registro General Turístico de Canarias, and the same
classification as the other regions.

Numbers: <type>-<province>-<island>-<7 digits>, e.g. VV-35-1-0012345 (VV vivienda vacacional; 35 Las Palmas province;
island 1 Gran Canaria). Older entries have no province or island (VV---0000621). Hosts often drop hyphens or write VT for
VV; the national number (ESFCTU…) ends with the regional digits plus a check digit.
Register: the Gobierno de Canarias open data (holiday homes, other non-hotel establishments, hotels), with coordinates for
about two thirds. We never keep the trade-name column (often a person's name).
Letting rooms isn't banned (the room ban in Decreto 113/2015 was annulled), so room listings aren't flagged.
"""
import csv
import io
import re

from .classify import seasonal_claim
from .register import haversine_m

LOCATION_THRESHOLD_M = 800
SEASONAL_NIGHTS = 32    # tourist use presumed for stays of 31 days or less (Ley 6/2025, arts. 11–12 added by Ley 7/2026)
BOX = (27.6, 28.2, -15.9, -15.3)   # Gran Canaria: register points outside are broken (e.g. lat 28138.0)

BASE = "https://datos.canarias.es/catalogos/general/dataset/"
SOURCES = {
    "vv.csv": BASE + "9f4355a2-d086-4384-ba72-d8c99aa2d544/resource/8ff8cc43-c00b-4513-8f42-a5b961c579e1/download/"
                     "establecimientos-extrahoteleros-de-tipologia-vivienda-vacacional-inscritos-en-el-registro-genera.csv",
    "extra.csv": BASE + "1364104c-b86c-4ab9-8ef5-12fdf399aa01/resource/d98c2617-db26-4d15-8ee4-3b2da1130bd0/download/"
                        "establecimientos-extrahoteleros-sin-viviendas-vacacionales-inscritos-en-el-registro-general-turi.csv",
    "hotel.csv": BASE + "429db33d-cbce-4920-b1b6-b4dde9e5f90f/resource/87741d75-2ce2-4a45-8131-ad8263257664/download/"
                        "establecimientos-hoteleros-inscritos-en-el-registro-general-turistico-de-canarias.csv"}
KEEP = ["establecimiento_id", "establecimiento_tipologia", "direccion", "direccion_isla_nombre", "direccion_municipio_nombre",
        "direccion_localidad_nombre", "direccion_codigo_postal", "plazas", "latitud", "longitud"]

TYPES = "VV|VT|EMR|CR|HR|H|A|E|AT"
CODE_RE = re.compile(rf"(?<![A-Z0-9])({TYPES})((?:[\s\-_./]*\d){{7,12}})(?![0-9])", re.IGNORECASE)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)


def fetch(cache_dir):
    """Download the three registers (selected columns only); keep previous copies if a download fails."""
    import os
    from . import http
    d = os.path.join(cache_dir, "canarias")
    os.makedirs(d, exist_ok=True)
    for name, url in SOURCES.items():
        try:
            text = http.get(url, timeout=300).content.decode("utf-8-sig", "ignore")
            rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
            if len(rows) < 500 or "establecimiento_id" not in rows[0]:
                raise ValueError(f"unexpected file ({len(rows)} rows)")
            with open(os.path.join(d, name), "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, KEEP, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
        except Exception as e:  # noqa: BLE001
            print(f"canarias: {name} download failed, keeping previous copy:", e)
    return [os.path.join(d, n) for n in SOURCES]


def key_from(typ, digits):
    """'VV', '3510012345' → 'VV-35-1-0012345'; 7 digits (old entries) → 'VV---0012345'. Extra trailing digits (a check
    digit, a stray digit) are dropped."""
    typ = typ.upper()
    if len(digits) >= 10:
        return f"{typ}-{digits[:2]}-{digits[2]}-{digits[3:10]}"
    if len(digits) >= 7:
        return f"{typ}---{digits[-7:]}"
    return None


def parse(raw):
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    rest = NATIONAL_RE.sub(" ", text)
    regional = [k for m in CODE_RE.finditer(rest) for k in [key_from(m.group(1), re.sub(r"\D", "", m.group(2)))] if k]
    embedded = []
    for n in national:
        m = re.search(rf"({TYPES})-?(\d{{2}})-?(\d)-?(\d{{7}})\d?$", n.upper())
        if m:
            embedded.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}")
    e = EXEMPT_RE.search(text)
    return {"regional": list(dict.fromkeys(regional)), "national": national, "embedded": list(dict.fromkeys(embedded)),
            "exempt_text": e.group(0).strip() if e else None}


def load_register(paths):
    """{key: {"type", "muni", "lat", "lon", "places", "address", "postcode", "locality"}}; plus "_short": {type-number: key}
    for old entries and numbers written without province/island (only where the number is unambiguous)."""
    import os
    idx, short = {}, {}
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                m = re.match(rf"^({TYPES})-(\d{{2}})?-(\d)?-?(\d{{7}})$", (r.get("establecimiento_id") or "").strip().upper())
                if not m:
                    continue
                k = f"{m.group(1)}-{m.group(2) or ''}-{m.group(3) or ''}-{m.group(4)}"
                try:
                    la, lo = float(r.get("latitud") or 0), float(r.get("longitud") or 0)
                    ok = BOX[0] <= la <= BOX[1] and BOX[2] <= lo <= BOX[3]
                except ValueError:
                    ok = False
                idx[k] = {"type": r.get("establecimiento_tipologia"), "muni": (r.get("direccion_municipio_nombre") or "").strip(),
                          "lat": la if ok else None, "lon": lo if ok else None, "address": " ".join((r.get("direccion") or "").split()),
                          "postcode": r.get("direccion_codigo_postal"), "locality": r.get("direccion_localidad_nombre"),
                          "places": int(r["plazas"]) if (r.get("plazas") or "").isdigit() else None, "vv": m.group(1) in ("VV", "A")}
                s = f"{m.group(1)}-{m.group(4)}"
                short[s] = None if s in short and short[s] != k else k
    idx["_short"] = {s: k for s, k in short.items() if k}
    return idx


def find(idx, k):
    """The register key for a shown number, allowing the usual host slips: no province/island, or VT written for VV."""
    if k in idx:
        return k
    typ, num = k.split("-")[0], k[-7:]
    for t in ([typ, "VV"] if typ == "VT" else [typ]):
        kk = idx["_short"].get(f"{t}-{num}")
        if kk:
            return kk
    return None


def _same_muni(a, b):
    n = lambda s: re.sub(r"[^A-Z]", "", (s or "").upper().replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U"))
    return n(a) == n(b)


def classify(raw, lat, lon, room_type, min_nights, idx, home="Las Palmas De Gran Canaria"):
    p = parse(raw)
    codes = p["regional"] or p["embedded"]
    if codes:
        best = None
        for k in codes:
            rk = find(idx, k)
            rec = idx.get(rk) if rk else None
            if not rec:
                cat, rk = "NOT_IN_REGISTER", k
            else:
                d = haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]) if rec["lat"] is not None and lat not in (None, "") else None
                same = _same_muni(rec["muni"], home)
                cat = "FOUND_CONSISTENT" if (d is not None and d <= LOCATION_THRESHOLD_M) or (d is None and same) \
                    else "FOUND_INCONSISTENT" if same else "FOUND_OTHER_MUNICIPALITY"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, rk)
        return {"category": best[1], "key": best[2], "embedded_only": not p["regional"], "group": None}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or p["national"] \
            or seasonal_claim(p["exempt_text"], min_nights, SEASONAL_NIGHTS):
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


TYPE_MAP = {"VV": "Vivienda de uso turístico", "A": "Vivienda de uso turístico", "VT": "Vivienda de uso turístico",
            "H": "Establecimiento Hotelero", "HR": "Establecimiento Hotelero", "E": "Apartamento turístico", "AT": "Apartamento turístico",
            "CR": "Casa rural", "EMR": "Casa rural"}


def as_register_records(idx, home="Las Palmas De Gran Canaria", name="LAS PALMAS DE GRAN CANARIA"):
    out = []
    for k, v in idx.items():
        if k == "_short" or not _same_muni(v["muni"], home):
            continue
        m = re.match(r"^(.*?)[,\s]+(\d+\s*[A-Z]?)\b", v.get("address") or "")
        out.append({"registration_code": k, "objects_type_id": TYPE_MAP.get(k.split("-")[0], "Otros"), "group": None,
                    "municipalities": name, "provinces": "LAS PALMAS", "lat": v["lat"], "lon": v["lon"],
                    "road_name": m.group(1) if m else v.get("address"), "km_num": m.group(2).replace(" ", "") if m else None,
                    "floor": None, "door": None, "staircase": None, "block": None, "portal": None,
                    "postal_code": v.get("postcode") if v.get("postcode") != "_U" else None,
                    "locality": v.get("locality") if v.get("locality") != "_U" else None, "tot_gen_places": v.get("places"),
                    "registration_date": "", "domicile_complement": None, "catastral_ref": None})
    return out
