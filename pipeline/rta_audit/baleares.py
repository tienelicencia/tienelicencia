"""Mallorca (Illes Balears): registration numbers, the Consell de Mallorca's tourism registers, and the same
classification as Andalucía and Barcelona.

Numbers: holiday lets are ETV/1234 (estancia turística en vivienda), ETVPL/1234 (in an apartment block), ETV60/1234 (main
home, up to 60 days a year) and VT/123 (older "vivienda turística de vacaciones"). Adverts also show hotel (H/, HA/, HR/),
tourist apartment (AT/), agrotourism (AG/), interior tourism (TI/) and hostel (ABT/) numbers, and the national number
(ESFCTU…ETV/12345X), which embeds the regional number followed by a check digit.
Registers: the Consell de Mallorca's open data lists every active holiday let and every other tourist accommodation, about
half of them with coordinates. We never keep the holder ("Explotador/s") or trade-name columns.
"""
import csv
import re

from .buildings import muni_key
from .register import haversine_m

LOCATION_THRESHOLD_M = 800      # same as Andalucía and Barcelona
SEASONAL_NIGHTS = 31            # a tourist stay is at most 30 nights (Ley 8/2012, art. 50.13); see docs/law-sources.md
ISLAND_BOX = (39.1, 40.1, 2.2, 3.6)   # lat/lon sanity box: a few register points are misplaced

FLATS = ("ETV60", "ETVPL", "ETV", "VT")
PREFIXES = "ETV60|ETVPL|ETV|ET|VT|ABT|AG|AT|TI|HA|HR|HO|HS|H|CA|CE|EH"
REGIONAL_RE = re.compile(rf"(?<![A-Z0-9])({PREFIXES})[\s\-_.]*/[\s]*0*(\d{{1,6}})(?![0-9])|"
                         rf"(?<![A-Z0-9])(ETV60|ETVPL|ETV)[\s\-_.]*0*(\d{{1,6}})(?![0-9])", re.IGNORECASE)   # no bare VT-12345 (Valencia)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EMBEDDED = re.compile(r"(ETV60|ETVPL|ETV|ET|VT)/?(\d{2,7})$", re.IGNORECASE)   # national tail: number + one check digit
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)
AGENCY = ("CE", "EH")           # marketing companies, not a dwelling: no location check

# ---------------------------------------------------------------- downloads
CKAN = "https://intranet.caib.es/opendatacataleg/files/dataset"
SOURCES = {"habitatges.csv": f"{CKAN}/habitatges_turistics_mallorca/habitatges_turistics_mallorca.csv",
           "allotjaments.csv": f"{CKAN}/allotjaments_turistics_mallorca/allotjaments_turistics_mallorca.csv"}
# Only the columns we use: never the holder ("Explotador/s") or the trade name, which is often a person's name
KEEP = ["Signatura", "Estat", "Grup", "Municipi", "Localitat", "Direcció", "Places", "Unitats", "Inici d'activitat",
        "latitude", "longitude"]


def fetch(cache_dir):
    """Download both registers (selected columns only). Keeps the previous copies if a download fails."""
    import io
    import os
    from . import http
    d = os.path.join(cache_dir, "baleares")
    os.makedirs(d, exist_ok=True)
    for name, url in SOURCES.items():
        try:
            text = http.get(url, timeout=300).content.decode("utf-8-sig", "ignore")
            rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
            if len(rows) < 500 or "Signatura" not in rows[0]:
                raise ValueError(f"unexpected file ({len(rows)} rows)")
            with open(os.path.join(d, name), "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, KEEP, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
        except Exception as e:  # noqa: BLE001
            print(f"baleares: {name} download failed, keeping previous copy:", e)
    return [os.path.join(d, n) for n in SOURCES]


def key(prefix, num):
    p = prefix.upper()
    return f"{'ETV' if p == 'ET' else p}/{int(num)}"


def parse(raw):
    """→ {"regional": [keys], "national": [raw], "embedded": [keys from national numbers], "exempt_text": str|None}"""
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    rest = NATIONAL_RE.sub(" ", text)
    regional = list(dict.fromkeys(key(m.group(1) or m.group(3), m.group(2) or m.group(4)) for m in REGIONAL_RE.finditer(rest)))
    embedded = []
    for n in national:
        m = EMBEDDED.search(n.upper())
        if m and len(m.group(2)) > 1:
            embedded.append(key(m.group(1), m.group(2)[:-1]))
    e = EXEMPT_RE.search(text)
    return {"regional": regional, "national": national, "embedded": list(dict.fromkeys(embedded)),
            "exempt_text": e.group(0).strip() if e else None}


# Inside Airbnb's municipality names → the register's (most match once accents and spaces are dropped)
MUNI_ALIASES = {"PALMADEMALLORCA": "PALMA", "DEYA": "DEIA", "VILAFRANCDEBONANY": "VILAFRANCADEBONANY"}


def muni(name):
    k = muni_key(name)
    return MUNI_ALIASES.get(k, k)


def _coord(r):
    try:
        la, lo = float(r["latitude"]), float(r["longitude"])
    except (TypeError, ValueError, KeyError):
        return None, None
    a, b, c, d = ISLAND_BOX
    return (la, lo) if a < la < b and c < lo < d else (None, None)


def load_register(paths):
    """{key: {"type", "group", "municipi", "lat", "lon", "places", "address", ...}} for every entry in both registers."""
    idx = {}
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                m = re.match(r"([A-Z]+(?:60)?)/0*(\d+)$", (r.get("Signatura") or "").strip().upper())
                if not m:
                    continue
                la, lo = _coord(r)
                idx[key(m.group(1), m.group(2))] = {
                    "type": r.get("Grup"), "status": r.get("Estat"), "municipi": (r.get("Municipi") or "").strip(),
                    "locality": r.get("Localitat"), "address": " ".join((r.get("Direcció") or "").split()),
                    "lat": la, "lon": lo, "since": r.get("Inici d'activitat"),
                    "places": int(r["Places"]) if (r.get("Places") or "").isdigit() else None}
    return idx


class MuniEdges:
    """Municipality outlines (Inside Airbnb's neighbourhoods.geojson for Mallorca: one polygon per municipality), to tell
    whether a listing lies near the border of the municipality its number is registered in."""

    def __init__(self, path):
        import json
        import math
        self.k = math.cos(math.radians(39.6))
        self.segs = {}
        for f in json.load(open(path, encoding="utf-8"))["features"]:
            s = self.segs.setdefault(muni(f["properties"]["neighbourhood"]), [])
            stack = [f["geometry"]["coordinates"]]
            while stack:
                c = stack.pop()
                if c and isinstance(c[0][0], (int, float)):
                    s += [(c[i], c[i + 1]) for i in range(len(c) - 1)]
                else:
                    stack.extend(c)

    def near(self, lat, lon, name, m=1500):
        """Is (lat, lon) within m metres of the municipality's outline (or inside it)? Planar, fine at this scale."""
        k, M = self.k, 111320.0
        px, py = lon * k * M, lat * M
        for (x1, y1), (x2, y2) in self.segs.get(muni(name), ()):
            ax, ay, bx, by = x1 * k * M, y1 * M, x2 * k * M, y2 * M
            if min(ax, bx) - m > px or max(ax, bx) + m < px or min(ay, by) - m > py or max(ay, by) + m < py:
                continue
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ((dx * dx + dy * dy) or 1)))
            if (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2 <= m * m:
                return True
        return False


BORDER_M = 1500   # no registered point: a listing this close to the number's municipality isn't called "another place"


def classify(raw, lat, lon, room_type, min_nights, idx, listing_muni, edges=None):
    """Same categories as rta_audit.classify (so the site's cards work unchanged). The whole island is one area, so the
    location test is: within 800 m of the registered point is a match; beyond that, a number registered in another
    municipality is FOUND_OTHER_MUNICIPALITY, one in the same municipality FOUND_INCONSISTENT. With no registered point
    (about half the register), the municipality decides, allowing for listings near its border (Inside Airbnb's locations
    are approximate, and its municipality is read from them)."""
    p = parse(raw)
    codes = p["regional"] or p["embedded"]      # the regional field wins over the number inside the national one
    here = muni(listing_muni) if listing_muni else None
    if codes:
        best = None
        for k in codes:
            rec = idx.get(k)
            if not rec:
                cat = "NOT_IN_REGISTER"
            elif k.split("/")[0] in AGENCY:
                cat = "FOUND_CONSISTENT"
            else:
                d = haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]) \
                    if rec["lat"] is not None and lat not in (None, "") else None
                same = here is None or muni(rec["municipi"]) == here
                if d is None and not same and edges is not None and lat not in (None, ""):
                    same = edges.near(float(lat), float(lon), rec["municipi"], BORDER_M)
                cat = "FOUND_CONSISTENT" if (d is not None and d <= LOCATION_THRESHOLD_M) or (d is None and same) \
                    else "FOUND_INCONSISTENT" if same else "FOUND_OTHER_MUNICIPALITY"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        return {"category": best[1], "key": best[2], "embedded_only": not p["regional"],
                "group": "Completa" if best[2].split("/")[0] in ("ETV", "ETVPL", "VT") and best[2] in idx else None}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or (p["exempt_text"] and re.search(r"(?i)seasonal|temporada", p["exempt_text"])) \
            or p["national"]:
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


VUT_TYPE = "Vivienda de uso turístico"
TYPE_MAP = {"ETV": VUT_TYPE, "ETVPL": VUT_TYPE, "ETV60": VUT_TYPE, "VT": VUT_TYPE, "H": "Establecimiento Hotelero",
            "HA": "Establecimiento Hotelero", "HR": "Establecimiento Hotelero", "HO": "Establecimiento Hotelero",
            "HS": "Establecimiento Hotelero", "AT": "Apartamento turístico", "AG": "Casa rural", "TI": "Casa rural"}
_ADDR = re.compile(r"^(.*?),\s*([^.,]*?)\.\s*(\d{5})\s")   # "Carrer DE SANTA TERESA, 27. 07100 SÓLLER, Mallorca"


def as_register_records(idx):
    """The island's entries in the same shape as Junta register records, so the maps, buildings, municipalities and search
    work unchanged. Floor and door aren't published separately."""
    out = []
    for k, v in idx.items():
        pre = k.split("/")[0]
        if pre in AGENCY:
            continue
        m = _ADDR.match(v.get("address") or "")
        out.append({"registration_code": k, "objects_type_id": TYPE_MAP.get(pre, "Otros"),
                    "group": "Completa" if pre in ("ETV", "ETVPL", "VT") else None,
                    "municipalities": v.get("municipi"), "provinces": "ILLES BALEARS", "lat": v.get("lat"), "lon": v.get("lon"),
                    "road_name": m.group(1) if m else v.get("address"), "km_num": m.group(2) if m else None,
                    "floor": None, "door": None, "staircase": None, "block": None, "portal": None,
                    "postal_code": m.group(3) if m else None, "locality": v.get("locality"),
                    "tot_gen_places": v.get("places"), "registration_date": _ymd(v.get("since")),
                    "domicile_complement": None, "catastral_ref": None})
    return out


def _ymd(d):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", d or "")
    return f"{m.group(3)}{m.group(2)}{m.group(1)}" if m else ""
