"""Valencia city (Comunitat Valenciana): registration numbers, the Generalitat's register of tourist flats, and the same
classification as the other regions.

Numbers: tourist flats are CV-VUT0012345-V (V Valencia, A Alicante, CS Castellón); hosts also write the older VT-12345-V,
VT12345V or VUT-12345-V, and the national number (ESFCTU…VT-12345-V…) usually ends with it. Hotels (HV-), tourist
apartments (AT-) and other establishments are in other registers that aren't open data, so we can't check them.
Register: the Generalitat's open data lists every active tourist flat in the region with its address and cadastral
reference (no coordinates); we place each flat on its Catastro parcel. We don't keep the trade-name or website columns.
"""
import csv
import io
import re

from .classify import seasonal_claim
from .register import haversine_m

LOCATION_THRESHOLD_M = 800
SEASONAL_NIGHTS = 11    # a tourist flat is let for 10 days or less; 11+ is not one (Ley 15/2018, art. 65.1 and 65.3.a)

URL = ("https://dadesobertes.gva.es/dataset/758f8f8e-c5af-4622-b268-a6c591710a51/resource/"
       "b1bdc28e-9813-422a-ab7a-63c21290493d/download/lista-de-viviendas-turisticas.csv")
KEEP = ["signatura", "cod_provincia", "cod_municipio", "municipio", "provincia", "cp", "direccion", "plazas_totales",
        "fecha_alta", "ref_catastral", "rural"]

VT_RE = re.compile(r"(?<![A-Z0-9])(?:CV[\s\-_]*)?(VUT|VT)[\s\-_/.]*0*(\d{1,7})(?:[\s\-_/.]*(CS|V|A)(?![A-Z]))?", re.IGNORECASE)
OTHER_RE = re.compile(r"(?<![A-Z0-9])(?:CV[\s\-_]*)?(AT|HV|HA|HCS|APT|CV-H)[\s\-_/.]*0*\d{1,7}", re.IGNORECASE)
EMBEDDED = re.compile(r"(?:CV-?)?VU?T-?0*(\d{1,7})-?(CS|V|A)?")   # inside a national number, straight after its digits
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)
PROV = {"03": "A", "12": "CS", "46": "V"}


def fetch(cache_dir):
    """Download the register (selected columns only); keep the previous copy if the download fails."""
    import os
    from . import http
    d = os.path.join(cache_dir, "valencia")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "viviendas.csv")
    try:
        text = http.get(URL, timeout=300).content.decode("utf-8-sig", "ignore")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        if len(rows) < 10000 or "signatura" not in rows[0]:
            raise ValueError(f"unexpected file ({len(rows)} rows)")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, KEEP, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    except Exception as e:  # noqa: BLE001
        print("valencia: register download failed, keeping previous copy:", e)
    return p


def key(num, prov):
    return f"CV-VUT{int(num):07d}-{prov.upper()}"


def parse(raw):
    """→ {"vt": [(num, prov or None)], "other": bool, "national": [raw], "embedded": [(num, prov)], "exempt_text"}"""
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    rest = NATIONAL_RE.sub(" ", text)
    vt = list(dict.fromkeys((int(m.group(2)), (m.group(3) or "").upper() or None) for m in VT_RE.finditer(rest)))
    embedded = list(dict.fromkeys((int(m.group(1)), (m.group(2) or "").upper() or None)
                                  for n in national for m in EMBEDDED.finditer(n.upper())))
    e = EXEMPT_RE.search(text)
    return {"vt": vt, "other": bool(OTHER_RE.search(rest)), "national": national, "embedded": embedded,
            "exempt_text": e.group(0).strip() if e else None}


def load_register(path, parcels=None):
    """{key: {"muni", "muni_code", "lat", "lon", "places", "address", "postcode", "since", "cadastral"}}.
    parcels: {ref14: [dwellings, lat, lon, residential]} from the Catastro, to place each flat."""
    idx = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = re.match(r"CV-VUT0*(\d+)-(A|V|CS)$", (r.get("signatura") or "").strip().upper())
            if not m:
                continue
            ref = (r.get("ref_catastral") or "").strip().upper()[:14]
            pt = (parcels or {}).get(ref)
            idx[key(m.group(1), m.group(2))] = {
                "muni": (r.get("municipio") or "").strip(), "muni_code": f"{r.get('cod_provincia')}{r.get('cod_municipio')}",
                "lat": pt[1] if pt else None, "lon": pt[2] if pt else None, "cadastral": ref or None,
                "places": int(r["plazas_totales"]) if (r.get("plazas_totales") or "").isdigit() else None,
                "address": " ".join((r.get("direccion") or "").split()), "postcode": r.get("cp"), "since": r.get("fecha_alta")}
    return idx


def lookup(idx, num, prov, home_prov="V"):
    """The register entry for a number; a number written without its province letter is read as this province's."""
    for p in ([prov] if prov else [home_prov, "A", "CS"]):
        k = key(num, p)
        if k in idx:
            return k, idx[k]
    return key(num, prov or home_prov), None


def classify(raw, lat, lon, room_type, min_nights, idx, home_code="46250", home_prov="V"):
    """Same categories as the other regions. A number registered in another municipality is FOUND_OTHER_MUNICIPALITY;
    in Valencia but more than 800 m from its parcel, FOUND_INCONSISTENT. Hotel and tourist-apartment numbers (other
    registers, not open) and seasonal claims count as possibly exempt."""
    p = parse(raw)
    nums = p["vt"] or p["embedded"]
    if nums:
        best = None
        for num, prov in nums:
            k, rec = lookup(idx, num, prov, home_prov)
            if not rec:
                cat = "NOT_IN_REGISTER"
            elif rec["muni_code"] != home_code:
                cat = "FOUND_OTHER_MUNICIPALITY"
            elif rec["lat"] is not None and lat not in (None, "") and \
                    haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]) > LOCATION_THRESHOLD_M:
                cat = "FOUND_INCONSISTENT"
            else:
                cat = "FOUND_CONSISTENT"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        return {"category": best[1], "key": best[2], "embedded_only": not p["vt"],
                "group": "Completa" if best[2] in idx else None}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or p["other"] or p["national"] \
            or seasonal_claim(p["exempt_text"], min_nights, SEASONAL_NIGHTS):
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


_ADDR = re.compile(r"^(?:[A-Z]{2}\s+)?(.*?),\s*(\d+\s*[A-Z]?)\b(.*)$", re.IGNORECASE)   # "CL ARRABAL, 11, Es:T Pl:OD Pt:OS"


def as_register_records(idx, home_code="46250", name="VALENCIA", province="VALENCIA"):
    """The city's flats in the same shape as Junta register records (maps, buildings, barrios and search)."""
    out = []
    for k, v in idx.items():
        if v["muni_code"] != home_code:
            continue
        m = _ADDR.match(v.get("address") or "")
        rest = m.group(3) if m else ""
        fl = re.search(r"Pl:(\S+)", rest)
        dr = re.search(r"Pt:(\S+)", rest)
        es = re.search(r"Es:(\S+)", rest)
        clean = lambda x: None if not x or x.group(1) in ("OD", "OS", "T") else x.group(1)
        out.append({"registration_code": k, "objects_type_id": "Vivienda de uso turístico", "group": "Completa",
                    "municipalities": name, "provinces": province, "lat": v["lat"], "lon": v["lon"],
                    "road_name": m.group(1) if m else v.get("address"), "km_num": m.group(2).replace(" ", "") if m else None,
                    "floor": clean(fl), "door": clean(dr), "staircase": clean(es), "block": None, "portal": None,
                    "postal_code": v.get("postcode"), "locality": None, "tot_gen_places": v.get("places"),
                    "registration_date": _ymd(v.get("since")), "domicile_complement": None, "catastral_ref": v.get("cadastral")})
    return out


def _ymd(d):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", d or "")
    return f"{m.group(3)}{m.group(2)}{m.group(1)}" if m else ""
