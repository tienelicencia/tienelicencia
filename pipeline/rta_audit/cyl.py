"""Valladolid (Castilla y León): registration numbers, the Registro de Turismo de Castilla y León, and the same
classification as the other regions.

Numbers: <province>/<serial>, e.g. 47/000547 (47 = Valladolid). Each class of establishment has its own serial, so the same
number exists as a tourist flat, a tourist apartment, a rural house and a hostel. Hosts write VUT-47/547, VUT 47/000547,
47/547… We therefore accept a shown number if any tourist-accommodation entry with it is in the municipality, and call it
another municipality's only when every entry with that number is elsewhere.
Advertising must show the number (Decreto 3/2017, art. 35.1). Letting by rooms isn't banned: the room ban (art. 3.2) was
annulled by the TSJ de Castilla y León (Orden CYT/1318/2019), so room listings aren't flagged. See docs/law-sources.md.
Register: the Junta's open data (CC BY 4.0), updated daily, about a third with coordinates. We never keep the name, phone,
email or web columns.
"""
import csv
import io
import os
import re

from .classify import seasonal_claim
from .register import haversine_m

LOCATION_THRESHOLD_M = 800
SEASONAL_NIGHTS = 32    # no regional figure: national RDL 29/2026 caps tourist lets at 31 days (as for Madrid)
URL = ("https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/catalog/datasets/registro-de-turismo-de-castilla-y-leon/exports/csv"
       "?delimiter=%3B&select=n_registro,establecimiento,tipo,categoria,direccion,c_postal,provincia,municipio,localidad,plazas,"
       "gps_latitud,gps_longitud")
ACCOMMODATION = {"Vivienda turística": "Vivienda de uso turístico", "Apartamentos Turísticos": "Apartamento turístico",
                 "Alojamientos Hoteleros": "Establecimiento Hotelero", "Alojam. Turismo Rural": "Casa rural",
                 "Albergues": "Otros", "Campings": "Campamento de turismo"}
KEEP = ["n_registro", "establecimiento", "tipo", "categoria", "direccion", "c_postal", "provincia", "municipio", "localidad", "plazas",
        "gps_latitud", "gps_longitud"]
PROVINCES = "05|09|24|34|37|40|42|47|49"   # Ávila, Burgos, León, Palencia, Salamanca, Segovia, Soria, Valladolid, Zamora
PREFIX = r"(?:VUT|VT|VUT?\s*N[ºo°.]*|AT|APT?|CR|TR|HS?|HT|AL)"
# a prefix, or the canonical slash, is required: a bare "47 547" is too easily something else
CODE_RE = re.compile(rf"(?<![A-Z0-9/])(?:{PREFIX}[\s\-_./:]*({PROVINCES})[\s\-_./]*0*(\d{{1,6}})|({PROVINCES})\s*/\s*0*(\d{{1,6}}))(?![0-9/])",
                     re.IGNORECASE)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)


def fetch(cache_dir):
    """Download the tourist-accommodation entries (selected columns only); keep the previous copy if it fails."""
    from . import http
    d = os.path.join(cache_dir, "cyl")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "registro.csv")
    try:
        text = http.get(URL, timeout=600).content.decode("utf-8-sig", "ignore")
        rows = [r for r in csv.DictReader(io.StringIO(text), delimiter=";") if r.get("establecimiento") in ACCOMMODATION]
        if len(rows) < 3000 or "n_registro" not in rows[0]:
            raise ValueError(f"unexpected file ({len(rows)} accommodation rows)")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, KEEP, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    except Exception as e:  # noqa: BLE001
        print("cyl: register download failed, keeping previous copy:", e)
    return p


def key(prov, serial):
    return f"{prov}/{int(serial)}"


def _muni(s):
    return re.sub(r"[^A-Z]", "", (s or "").upper().replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U"))


def load_register(path):
    """{"47/547": [entry, …]} (one number can belong to several classes); entry = class, type, municipality, lat, lon…"""
    idx = {}
    if not os.path.exists(path):
        return idx
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = re.match(rf"^({PROVINCES})/0*(\d+)$", (r.get("n_registro") or "").strip())
            if not m:
                continue
            try:
                la, lo = float(r.get("gps_latitud") or "x"), float(r.get("gps_longitud") or "x")
                ok = 40 < la < 43.3 and -7.2 < lo < -1.7
            except ValueError:
                ok = False
            idx.setdefault(key(*m.groups()), []).append({
                "code": r["n_registro"].strip(), "cls": r.get("establecimiento"), "type": ACCOMMODATION.get(r.get("establecimiento"), "Otros"),
                "flat": r.get("establecimiento") == "Vivienda turística", "muni": (r.get("municipio") or "").strip(),
                "lat": la if ok else None, "lon": lo if ok else None, "address": " ".join((r.get("direccion") or "").split()),
                "postcode": r.get("c_postal"), "locality": (r.get("localidad") or "").strip().title(),
                "places": int(r["plazas"]) if (r.get("plazas") or "").isdigit() else None})
    return idx


def parse(raw):
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    rest = NATIONAL_RE.sub(" ", text)
    regional = [key(m.group(1) or m.group(3), m.group(2) or m.group(4)) for m in CODE_RE.finditer(rest)]
    e = EXEMPT_RE.search(text)
    return {"regional": list(dict.fromkeys(regional)), "national": national, "exempt_text": e.group(0).strip() if e else None}


def classify(raw, lat, lon, room_type, min_nights, idx, home="Valladolid"):
    p = parse(raw)
    if p["regional"]:
        best = None
        for k in p["regional"]:
            recs = idx.get(k) or []
            here = [r for r in recs if _muni(r["muni"]) == _muni(home)]
            if not recs:
                cat = "NOT_IN_REGISTER"
            elif not here:
                cat = "FOUND_OTHER_MUNICIPALITY"
            elif lat not in (None, "") and all(r["lat"] is not None for r in here) and \
                    min(haversine_m(float(lat), float(lon), r["lat"], r["lon"]) for r in here) > LOCATION_THRESHOLD_M:
                cat = "FOUND_INCONSISTENT"
            else:
                cat = "FOUND_CONSISTENT"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        return {"category": best[1], "key": best[2], "embedded_only": False, "group": None}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or p["national"] or seasonal_claim(p["exempt_text"], min_nights, SEASONAL_NIGHTS):
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


def as_register_records(idx, home="Valladolid", name="VALLADOLID"):
    """The municipality's entries in the same shape as Junta de Andalucía register records."""
    out = []
    for k, recs in idx.items():
        for v in recs:
            if _muni(v["muni"]) != _muni(home):
                continue
            m = re.match(r"^(.*?)\s+(\d+\s*[A-Z]?)\b\s*(.*)$", v.get("address") or "")
            out.append({"registration_code": v["code"], "objects_type_id": v["type"], "group": "Completa" if v["flat"] else None,
                        "municipalities": name, "provinces": "VALLADOLID", "lat": v["lat"], "lon": v["lon"],
                        "road_name": m.group(1) if m else v.get("address"), "km_num": m.group(2).replace(" ", "") if m else None,
                        "floor": (m.group(3).strip() or None) if m else None, "door": None, "staircase": None, "block": None,
                        "portal": None, "postal_code": v.get("postcode") or None, "locality": v.get("locality") or None,
                        "tot_gen_places": v.get("places"), "registration_date": "", "domicile_complement": None, "catastral_ref": None})
    return out
