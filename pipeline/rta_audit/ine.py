"""INE experimental statistic "Medición del número de viviendas turísticas en España y su capacidad".

The INE scrapes the three main platforms (Airbnb, Booking.com, Vrbo), keeps listings that meet each region's definition
of a tourist dwelling, removes duplicates across platforms, and publishes counts per municipality (about twice a year).
It is the only open, multi-platform count of *advertised* tourist homes. It has no listing-level data or numbers.

  table 39363: tourist homes, places, places per home (municipalities; province totals included)
  table 39366: tourist homes as % of all census dwellings (municipalities; province totals included)

cache/ine.json = {"period": "2026-05", "province": {...}, "munis": {"29067": {"name", "homes", "places", "pct"}}}"""
import json
import os

from . import http

API = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{t}?nult=1&tip=AM"
CONCEPT = {"Viviendas turísticas": "homes", "Plazas": "places",
           "Porcentaje de viviendas turísticas sobre el total de viviendas censadas": "pct"}


def _series(table):
    return http.get(API.format(t=table), timeout=300).json()


def fetch(cache_dir, provs=("29", "41", "04", "11", "14", "18", "21", "23", "08", "07", "48", "20", "46", "28", "50", "30", "35")):
    """Download the latest period for these provinces' municipalities ("province" = the first one, Málaga; all of them under
    "provinces"). Keeps the cached copy if INE is unreachable."""
    p = os.path.join(cache_dir, "ine.json")
    try:
        out = {"source": "INE, Medición del número de viviendas turísticas (estadística experimental)", "period": None,
               "province": {}, "provinces": {}, "munis": {}}
        for table in (39363, 39366):
            for s in _series(table):
                md = {m["T3_Variable"]: m for m in s.get("MetaData", [])}
                concept = CONCEPT.get((md.get("Concepto turístico") or {}).get("Nombre"))
                if not concept or (md.get("Tipo de dato") or {}).get("Nombre") != "Dato base" or not s.get("Data"):
                    continue
                d = s["Data"][0]
                period = f"{d['Anyo']}-{d['T3_Periodo'][1:]}"
                out["period"] = max(out["period"] or period, period)
                if "Municipios" in md and md["Municipios"]["Codigo"][:2] in provs:
                    m = out["munis"].setdefault(md["Municipios"]["Codigo"], {"name": md["Municipios"]["Nombre"]})
                    m[concept] = d["Valor"]
                elif "Provincias" in md and md["Provincias"]["Codigo"] in provs:
                    pv = out["provinces"].setdefault(md["Provincias"]["Codigo"], {"name": md["Provincias"]["Nombre"]})
                    pv[concept] = d["Valor"]
        out["province"] = out["provinces"].get(provs[0], {})
        if out["munis"]:
            json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
    except Exception as e:  # never block the refresh on INE
        print("ine skipped:", e)
    return load(cache_dir)


def load(cache_dir):
    p = os.path.join(cache_dir, "ine.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


# ---------------------------------------------------------------- rent index (IPVA)
# INE "Índice de Precios de Vivienda en Alquiler" (experimental, yearly, from tax returns; 2015 = 100). It follows rents of
# homes let for at least two consecutive years, so it tracks existing tenancies rather than new asking rents.
#   table 59061: districts of provincial capitals     table 59060: municipalities over 10,000 inhabitants
RENT_TABLES = {"districts": 59061, "munis": 59060}


def fetch_rent(cache_dir, prov="29"):
    p = os.path.join(cache_dir, "ine_rent.json")
    try:
        out = {"source": "INE, Índice de Precios de Vivienda en Alquiler (IPVA), base 2015", "districts": {}, "munis": {}}
        for kind, table in RENT_TABLES.items():
            url = f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{table}?nult=30&tip=AM"
            for s in http.get(url, timeout=300).json():
                md = {m["T3_Variable"]: m for m in s.get("MetaData", [])}
                if "Índice" not in s["Nombre"] or "Total" not in s["Nombre"]:
                    continue
                geo = md.get("Distritos") or md.get("Municipios")
                if not geo or not geo["Codigo"].startswith(prov):
                    continue
                out[kind][geo["Codigo"]] = {"name": geo["Nombre"],
                                            "index": {str(d["Anyo"]): d["Valor"] for d in s["Data"] if d["Valor"] is not None}}
        if out["districts"] or out["munis"]:
            json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
    except Exception as e:
        print("ine rent skipped:", e)
    return load_rent(cache_dir)


def load_rent(cache_dir):
    p = os.path.join(cache_dir, "ine_rent.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
