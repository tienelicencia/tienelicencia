"""Barcelona (Catalonia): registration numbers, the tourism register, and the same classification as Andalucía.

Numbers: tourist flats are HUTB-NNNNNN (Habitatge d'Ús Turístic, Barcelona). Adverts also show hotel (HB-), tourist
apartment (ATB-) and hostel (AJ-) numbers, and the national number (ESFCTU…), which usually embeds the HUTB number.
Register: the Generalitat's Registre de Turisme de Catalunya says which numbers exist (only active entries are published);
the Ajuntament's open data adds coordinates and barri for each HUTB. We never read the holder columns (names, tax IDs).
"""
import csv
import re

from .register import haversine_m

LOCATION_THRESHOLD_M = 800      # same as Andalucía
SEASONAL_NIGHTS = 31            # Catalonia: stays of 31+ days are seasonal lets, outside tourist-flat rules (to verify)

# Regional prefixes we recognise (Barcelona province): flats, hotels, tourist apartments, hostels, guesthouses
REGIONAL_RE = re.compile(r"(?<![A-Z0-9])(HUTB|HB|ATB|AJ|HSB|PB|HUT)[\s\-_/.]*0*(\d{1,6})(?![0-9])", re.IGNORECASE)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EMBEDDED_HUTB = re.compile(r"HUTB-?(\d{6})", re.IGNORECASE)   # six digits, then usually a check digit
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)


def key(prefix, num):
    p = prefix.upper()
    return f"{'HUTB' if p == 'HUT' else p}-{int(num):06d}"


def parse(raw):
    """→ {"regional": [keys], "national": [raw], "embedded": [keys from national numbers], "exempt_text": str|None}"""
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    rest = NATIONAL_RE.sub(" ", text)
    regional = list(dict.fromkeys(key(m.group(1), m.group(2)) for m in REGIONAL_RE.finditer(rest)))
    embedded = list(dict.fromkeys(f"HUTB-{int(m.group(1)):06d}" for n in national for m in EMBEDDED_HUTB.finditer(n)))
    e = EXEMPT_RE.search(text)
    return {"regional": regional, "national": national, "embedded": embedded, "exempt_text": e.group(0).strip() if e else None}


def load_register(generalitat_csv, ajuntament_csv, municipi="Barcelona"):
    """{key: {"type", "lat", "lon", "barri", "district", "places"}} for active entries in the municipality.
    Valid numbers come from the Generalitat; coordinates and barri from the Ajuntament where it has them."""
    idx = {}
    with open(generalitat_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("municipi") != municipi or (r.get("estat") or "").lower() != "alta":
                continue
            m = re.match(r"([A-Z]+)-0*(\d+)", (r.get("n_mero_inscripci") or "").strip().upper())
            if not m:
                continue
            idx[key(m.group(1), m.group(2))] = {"type": r.get("tipus_establiment"), "lat": None, "lon": None,
                                                "barri": None, "district": None,
                                                "places": int(r["total_places"]) if (r.get("total_places") or "").isdigit() else None}
    with open(ajuntament_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = re.match(r"HUTB-?0*(\d+)", (r.get("NUMERO_REGISTRE_GENERALITAT") or "").strip().upper())
            if not m:
                continue
            k = f"HUTB-{int(m.group(1)):06d}"
            if k not in idx:      # in the city's file but no longer active with the Generalitat: not valid
                continue
            try:
                idx[k].update(lat=float(r["LATITUD_Y"]), lon=float(r["LONGITUD_X"]))
            except (TypeError, ValueError):
                pass
            idx[k].update(barri=r.get("NOM_BARRI"), district=r.get("NOM_DISTRICTE"),
                          places=idx[k]["places"] or (int(r["NUMERO_PLACES"]) if (r.get("NUMERO_PLACES") or "").isdigit() else None))
    return idx


def classify(raw, lat, lon, room_type, min_nights, idx):
    """Same categories as rta_audit.classify (so the site's cards work unchanged):
    FOUND_CONSISTENT / FOUND_INCONSISTENT (valid, location within / beyond 800 m), NOT_IN_REGISTER,
    NO_CODE_IN_SCOPE (no number), NO_CODE_POSSIBLY_EXEMPT (seasonal stay, hotel-type listing, national number only)."""
    p = parse(raw)
    codes = p["regional"] or p["embedded"]      # the regional field wins over the number inside the national one
    if codes:
        best = None
        for k in codes:
            rec = idx.get(k)
            if not rec:
                cat = "NOT_IN_REGISTER"
            elif rec["lat"] is not None and lat is not None and haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]) > LOCATION_THRESHOLD_M:
                cat = "FOUND_INCONSISTENT"
            else:
                cat = "FOUND_CONSISTENT"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "NOT_IN_REGISTER": 2}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        return {"category": best[1], "key": best[2], "embedded_only": not p["regional"]}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or (p["exempt_text"] and re.search(r"(?i)seasonal|temporada", p["exempt_text"])) \
            or p["national"]:
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}
