"""Madrid city (Comunidad de Madrid): registration numbers, the Comunidad's register of tourist accommodation, and the same
classification as the other regions, with one difference: in Madrid no rule requires adverts to show the number.

The duty to show it (Decreto 79/2014, art. 17.5) was annulled by the Supreme Court in 2018, because joining the register is
voluntary (Ley 1/1999, art. 23.2); what is compulsory is the declaración responsable. So for Madrid "doesn't display a
registered number" measures transparency, not a breach. See docs/law-sources.md, "Madrid".
Numbers: tourist flats VT-12345; hotels HM-, tourist apartments AM-, rural TR-, guesthouses HH-… The register has
addresses but no coordinates; we place Madrid city's flats from the city council's address points.
"""
import csv
import io
import json
import os
import re

from .classify import seasonal_claim
from .register import haversine_m, utm_to_wgs84

LOCATION_THRESHOLD_M = 800
SEASONAL_NIGHTS = 32          # no regional figure: national RDL 29/2026 caps tourist lets at 31 days
NUMBER_REQUIRED = False       # see the module docstring

REGISTER = ("https://datos.comunidad.madrid/dataset/ef437c50-5b26-4843-92c3-d8eef5507fac/resource/"
            "260e80ac-2062-41f6-9f96-4902675b1078/download/alojamientos_turisticos.csv")
ADDRESSES_PKG = "https://datos.madrid.es/api/3/action/package_show?id=213605-0-callejero-oficial-madrid"
KEEP = ["alojamiento_tipo", "via_tipo", "via_nombre", "numero", "bloque", "portal", "escalera", "planta", "puerta", "cdpostal",
        "localidad", "signatura"]   # never the trade name (denominacion)
PREFIXES = "VT|HM|AM|TR|HH|HR|AR|CM|CH|HS"
CODE_RE = re.compile(rf"(?<![A-Z0-9])({PREFIXES})[\s\-_/.]*0*(\d{{1,6}})(?![0-9])(?![\s\-]*(?:CS|V|A)\b)", re.IGNORECASE)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)
STOP = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y"}


def norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(w for w in re.sub(r"[^A-Z0-9 ]", " ", s).split() if w not in STOP)


def fetch(cache_dir):
    """The register (selected columns) and Madrid city's address points; keep previous copies on failure. Then place
    Madrid city's flats (madrid/geocoded.json)."""
    from . import http
    d = os.path.join(cache_dir, "madrid")
    os.makedirs(d, exist_ok=True)
    try:
        rows = list(csv.DictReader(io.StringIO(http.get(REGISTER, timeout=300).content.decode("utf-8-sig", "ignore")), delimiter=";"))
        if len(rows) < 1000 or "signatura" not in rows[0]:
            raise ValueError(f"unexpected file ({len(rows)} rows)")
        with open(os.path.join(d, "alojamientos.csv"), "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, KEEP, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    except Exception as e:  # noqa: BLE001
        print("madrid: register download failed, keeping previous copy:", e)
    ap = os.path.join(d, "direcciones.csv")
    try:
        import time
        if not os.path.exists(ap) or time.time() - os.path.getmtime(ap) > 30 * 86400:
            res = http.get(ADDRESSES_PKG, timeout=60).json()["result"]["resources"]
            url = next(r["url"] for r in res if "direccionesvigentes" in r["url"] and r["url"].endswith(".csv"))
            raw = http.get(url, timeout=600).content
            if len(raw) < 1_000_000:
                raise ValueError("address file unexpectedly small")
            open(ap, "wb").write(raw)
    except Exception as e:  # noqa: BLE001
        print("madrid: address points download failed, keeping previous copy:", e)
    geocode(d)
    return d


def _address_points(path):
    pts = {}
    with open(path, encoding="latin-1") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            try:
                x, y = float(r["UTMX_ETRS"].replace(",", ".")), float(r["UTMY_ETRS"].replace(",", "."))
            except (KeyError, ValueError):
                continue
            num = re.match(r"\d+", (r.get("NUMERO") or "").strip())
            if not num:
                continue
            k = (norm(r.get("VIA_NOMBRE_ACENTOS") or r.get("VIA_NOMBRE")), int(num.group(0)))
            if k not in pts or r.get("TIPO_NDP") == "PORTAL":
                pts[k] = utm_to_wgs84(x, y, 30)
    return pts


def geocode(d):
    """{register key: [lat, lon]} for Madrid city's entries, from the council's address points (street + number)."""
    ap, rp = os.path.join(d, "direcciones.csv"), os.path.join(d, "alojamientos.csv")
    if not (os.path.exists(ap) and os.path.exists(rp)):
        return {}
    pts, out, tried = _address_points(ap), {}, 0
    with open(rp, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            k = key_from(r.get("signatura"))
            if not k or (r.get("localidad") or "").strip() != "Madrid":
                continue
            tried += 1
            num = re.match(r"\d+", (r.get("numero") or "").strip())
            g = pts.get((norm(r.get("via_nombre")), int(num.group(0)))) if num else None
            if g:
                out[k] = [round(g[0], 6), round(g[1], 6)]
    json.dump(out, open(os.path.join(d, "geocoded.json"), "w"))
    print(f"madrid: {len(out)} of {tried} Madrid city entries placed from their address")
    return out


def key_from(sig):
    m = re.match(rf"^({PREFIXES})-0*(\d+)$", (sig or "").strip().upper())
    return f"{m.group(1)}-{int(m.group(2))}" if m else None


def load_register(d):
    idx = {}
    rp = os.path.join(d, "alojamientos.csv")
    if not os.path.exists(rp):
        return idx
    gp = os.path.join(d, "geocoded.json")
    geo = json.load(open(gp)) if os.path.exists(gp) else {}
    with open(rp, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            k = key_from(r.get("signatura"))
            if not k:
                continue
            la, lo = geo.get(k, (None, None))
            idx[k] = {"type": (r.get("alojamiento_tipo") or "").strip(), "muni": (r.get("localidad") or "").strip(), "lat": la, "lon": lo,
                      "street": " ".join(filter(None, [(r.get("via_tipo") or "").title(), r.get("via_nombre")])), "num": r.get("numero"),
                      "floor": r.get("planta"), "door": r.get("puerta"), "stair": r.get("escalera"), "block": r.get("bloque"),
                      "portal": r.get("portal"), "postcode": r.get("cdpostal")}
    return idx


def parse(raw):
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    rest = NATIONAL_RE.sub(" ", text)
    regional = list(dict.fromkeys(f"{m.group(1).upper()}-{int(m.group(2))}" for m in CODE_RE.finditer(rest)))
    e = EXEMPT_RE.search(text)
    return {"regional": regional, "national": national, "exempt_text": e.group(0).strip() if e else None}


def classify(raw, lat, lon, room_type, min_nights, idx, home="Madrid"):
    p = parse(raw)
    if p["regional"]:
        best = None
        for k in p["regional"]:
            rec = idx.get(k)
            if not rec:
                cat = "NOT_IN_REGISTER"
            elif rec["muni"] != home:
                cat = "FOUND_OTHER_MUNICIPALITY"
            elif rec["lat"] is not None and lat not in (None, "") and \
                    haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]) > LOCATION_THRESHOLD_M:
                cat = "FOUND_INCONSISTENT"
            else:
                cat = "FOUND_CONSISTENT"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        return {"category": best[1], "key": best[2], "embedded_only": False,
                "group": "Completa" if best[2].startswith("VT") and best[2] in idx else None}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or p["national"] or seasonal_claim(p["exempt_text"], min_nights, SEASONAL_NIGHTS):
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


TYPE_MAP = {"VT": "Vivienda de uso turístico", "HM": "Establecimiento Hotelero", "HH": "Establecimiento Hotelero",
            "HS": "Establecimiento Hotelero", "HR": "Establecimiento Hotelero", "AM": "Apartamento turístico", "TR": "Casa rural",
            "AR": "Casa rural", "CM": "Camping", "CH": "Establecimiento Hotelero"}


def as_register_records(idx, home="Madrid"):
    out = []
    for k, v in idx.items():
        if v["muni"] != home:
            continue
        out.append({"registration_code": k, "objects_type_id": TYPE_MAP.get(k.split("-")[0], "Otros"),
                    "group": "Completa" if k.startswith("VT") else None, "municipalities": "MADRID", "provinces": "MADRID",
                    "lat": v["lat"], "lon": v["lon"], "road_name": v["street"], "km_num": v["num"], "floor": v["floor"], "door": v["door"],
                    "staircase": v["stair"], "block": v["block"], "portal": v["portal"], "postal_code": v["postcode"], "locality": None,
                    "tot_gen_places": None, "registration_date": "", "domicile_complement": None, "catastral_ref": None})
    return out
