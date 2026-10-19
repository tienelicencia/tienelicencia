"""Barcelona (Catalonia): registration numbers, the tourism register, and the same classification as Andalucía.

Numbers: tourist flats are HUTB-NNNNNN (Habitatge d'Ús Turístic, Barcelona). Adverts also show hotel (HB-), tourist
apartment (ATB-) and hostel (AJ-) numbers, and the national number (ESFCTU…), which usually embeds the HUTB number.
Register: the Generalitat's Registre de Turisme de Catalunya says which numbers exist (only active entries are published);
the Ajuntament's open data adds coordinates and barri for each HUTB. We never read the holder columns (names, tax IDs).
"""
import csv
import re

from .classify import seasonal_claim
from .register import haversine_m

LOCATION_THRESHOLD_M = 800      # same as Andalucía
SEASONAL_NIGHTS = 32            # Catalonia: a tourist stay is 31 days or less (Decret 75/2020, art. 221-1.2); more is seasonal

# Regional prefixes we recognise (Barcelona province): flats, hotels, tourist apartments, hostels, guesthouses
REGIONAL_RE = re.compile(r"(?<![A-Z0-9])(HUTB|HB|ATB|AJ|HSB|PB|HUT)[\s\-_/.]*0*(\d{1,6})(?![0-9])", re.IGNORECASE)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EMBEDDED_HUTB = re.compile(r"HUTB-?(\d{6})", re.IGNORECASE)   # six digits, then usually a check digit
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)


# ---------------------------------------------------------------- downloads
GENCAT = "https://analisi.transparenciacatalunya.cat/resource/t2h3-cgys.csv"
# Only the columns we use: never the holder's name or tax ID
GENCAT_COLS = ["tipus_establiment", "n_mero_inscripci", "d_git_de_control", "estat", "tipus_de_via", "nom_de_la_via", "numero", "pis",
               "porta", "escala", "bloc", "codi_postal", "municipi", "prov_ncia", "referencia_cadastral", "modalitat",
               "unitat_d_allotjament", "total_places"]
AJT_PACKAGE = "https://opendata-ajuntament.barcelona.cat/data/api/3/action/package_show?id=habitatges-us-turistic"


def fetch(cache_dir, provincia="Barcelona"):
    """Download the Generalitat register (the whole province, so a neighbouring town's HUTB number is recognised; selected
    columns only) and the Ajuntament's latest quarterly HUT file (coordinates and barri for the city).
    Keeps the previous copies if a download fails. Returns (generalitat_csv, ajuntament_csv)."""
    import io
    import os
    import time
    import zipfile
    from urllib.parse import urlencode
    from . import http
    d = os.path.join(cache_dir, "catalunya")
    os.makedirs(d, exist_ok=True)
    gen, ajt = os.path.join(d, "generalitat.csv"), os.path.join(d, "ajuntament_hut.csv")
    q = {"$select": ",".join(GENCAT_COLS), "$where": f"prov_ncia='{provincia}'", "$limit": "300000"}
    for attempt in range(3):
        try:
            r = http.get(f"{GENCAT}?{urlencode(q)}", timeout=300)
            if r.text.count("\n") > 1000:
                open(gen, "w", encoding="utf-8").write(r.text)
                print(f"catalunya: generalitat register, {r.text.count(chr(10))} rows")
                break
            print(f"catalunya: generalitat answered HTTP {r.status_code} with {len(r.text)} bytes: {r.text[:200]!r}")
        except Exception as e:  # noqa: BLE001
            print(f"catalunya: generalitat download attempt {attempt + 1} failed:", e)
        time.sleep(20 * (attempt + 1))
    else:
        print("catalunya: generalitat register not refreshed; keeping the previous copy" if os.path.exists(gen) else
              "catalunya: generalitat register not available (no previous copy): Barcelona is skipped this run")
    try:
        res = http.get(AJT_PACKAGE, timeout=60).json()["result"]["resources"]
        dated = [(m.group(1), m.group(2), x) for x in res for m in [re.search(r"(\d{4})_(\d)T", x.get("name") or "")] if m]
        _, _, latest = max(dated, key=lambda t: (t[0], t[1]))
        raw = http.get(latest["url"], timeout=300).content
        if raw[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                raw = z.read(next(n for n in z.namelist() if n.lower().endswith(".csv")))
        text = raw.decode("utf-8-sig", "ignore")
        if "NUMERO_REGISTRE_GENERALITAT" in text:
            open(ajt, "w", encoding="utf-8").write(text)
            print("catalunya: ajuntament file", latest.get("name"))
        else:
            print(f"catalunya: ajuntament file {latest.get('name')} has no register column ({len(raw)} bytes): {text[:200]!r}")
    except Exception as e:  # noqa: BLE001
        print("catalunya: ajuntament download failed, keeping previous copy:", e)
    return gen, ajt


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


def load_register(generalitat_csv, ajuntament_csv):
    """{key: {"type", "municipi", "lat", "lon", "barri", "district", "places", "address"...}} for active entries in the
    province. Valid numbers come from the Generalitat; coordinates and barri (Barcelona city) from the Ajuntament."""
    idx = {}
    with open(generalitat_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("estat") or "").lower() != "alta":
                continue
            m = re.match(r"([A-Z]+)-0*(\d+)", (r.get("n_mero_inscripci") or "").strip().upper())
            if not m:
                continue
            idx[key(m.group(1), m.group(2))] = {"type": r.get("tipus_establiment"), "municipi": r.get("municipi"),
                                                "lat": None, "lon": None, "barri": None, "district": None,
                                                "street": " ".join(filter(None, [r.get("tipus_de_via"), r.get("nom_de_la_via")])),
                                                "num": r.get("numero"), "floor": r.get("pis"), "door": r.get("porta"),
                                                "stair": r.get("escala"), "block": r.get("bloc"), "postcode": r.get("codi_postal"),
                                                "cadastral": r.get("referencia_cadastral"),
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


def classify(raw, lat, lon, room_type, min_nights, idx, home="Barcelona"):
    """Same categories as rta_audit.classify (so the site's cards work unchanged):
    FOUND_CONSISTENT / FOUND_INCONSISTENT (valid, location within / beyond 800 m), FOUND_OTHER_MUNICIPALITY, NOT_IN_REGISTER,
    NO_CODE_IN_SCOPE (no number), NO_CODE_POSSIBLY_EXEMPT (seasonal stay, hotel-type listing, national number only)."""
    p = parse(raw)
    codes = p["regional"] or p["embedded"]      # the regional field wins over the number inside the national one
    if codes:
        best = None
        for k in codes:
            rec = idx.get(k)
            if not rec:
                cat = "NOT_IN_REGISTER"
            elif rec.get("municipi") and rec["municipi"] != home:
                cat = "FOUND_OTHER_MUNICIPALITY"
            elif rec["lat"] is not None and lat is not None and haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]) > LOCATION_THRESHOLD_M:
                cat = "FOUND_INCONSISTENT"
            else:
                cat = "FOUND_CONSISTENT"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        rec = idx.get(best[2]) or {}
        return {"category": best[1], "key": best[2], "embedded_only": not p["regional"],
                "group": "Completa" if best[2].startswith("HUTB") and rec else None}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or seasonal_claim(p["exempt_text"], min_nights, SEASONAL_NIGHTS) \
            or p["national"]:
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


VUT_TYPE = "Vivienda de uso turístico"
TYPE_MAP = {"HUTB": VUT_TYPE, "HB": "Establecimiento Hotelero", "ATB": "Apartamento turístico"}


def as_register_records(idx, municipi="Barcelona"):
    """The city's entries in the same shape as Junta register records, so the maps, buildings, barrios and search work
    unchanged. Registration dates aren't published, so they're left empty."""
    out = []
    for k, v in idx.items():
        if v.get("municipi") != municipi:
            continue
        pre = k.split("-")[0]
        out.append({"registration_code": k, "objects_type_id": TYPE_MAP.get(pre, "Otros"), "group": "Completa" if pre == "HUTB" else None,
                    "municipalities": municipi.upper(), "provinces": "BARCELONA", "lat": v.get("lat"), "lon": v.get("lon"),
                    "road_name": v.get("street"), "km_num": v.get("num"), "floor": v.get("floor"), "door": v.get("door"),
                    "staircase": v.get("stair"), "block": v.get("block"), "portal": None, "postal_code": v.get("postcode"),
                    "locality": v.get("barri"), "tot_gen_places": v.get("places"), "registration_date": "",
                    "domicile_complement": None, "catastral_ref": v.get("cadastral")})
    return out
