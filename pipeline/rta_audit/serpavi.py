"""Housing Ministry rent database (SERPAVI: Sistema Estatal de Referencia del Precio del Alquiler de Vivienda).

Built from income-tax returns (rents declared by private landlords) joined to the Catastro, yearly, published with a
~2-year lag, down to census section. We use, per section and year:
  ALQM2_LV_M_VC_YY      median rent, €/m² per month, flats in blocks ("vivienda colectiva")
  BI_ALVHEPCO_TVC_YY    number of rented flats behind that figure (sections with <10 are suppressed by the Ministry)
Section-level figures are noisy; we only use them aggregated (e.g. by barrio) and label the result indicative.

The download page blocks scripts, so the file URL is set here and updated by hand when a new edition appears
(https://www.mivau.gob.es/vivienda/alquila-bien-es-tu-derecho/serpavi → "BD Sistema Estatal Índices Alquiler de Vivienda")."""
import json
import os

from . import http

URL = ("https://cdn.mivau.gob.es/portal-web-mivau/vivienda/serpavi/"
       "2026-03_09_bd_SERPAVI_2011-2024%20-%20DEFINITIVO%20WEB_v2.xlsx")
EDITION = "2011-2024"


def ensure(cache_dir, municipality="29067"):
    """Per-section rents for one municipality: {cusec: {"YYYY": [median €/m², rented flats]}}. Cached as JSON."""
    # The extracted sections are small and committed (pipeline/inputs), so the scheduled build needs neither the
    # 70 MB workbook nor openpyxl. Re-extract by hand when a new edition comes out (delete the file and run a build).
    committed = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inputs",
                             f"serpavi_sections_{municipality}_{EDITION}.json")
    if os.path.exists(committed):
        return json.load(open(committed))
    d = os.path.join(cache_dir, "serpavi")
    jp = os.path.join(d, f"sections_{municipality}_{EDITION}.json")
    if os.path.exists(jp):
        return json.load(open(jp))
    xp = os.path.join(d, f"serpavi_{EDITION}.xlsx")
    if not os.path.exists(xp):
        os.makedirs(d, exist_ok=True)
        r = http.get(URL, timeout=1800, stream=True)
        with open(xp + ".part", "wb") as fh:
            for c in r.iter_content(1 << 20):
                fh.write(c)
        os.replace(xp + ".part", xp)
    import openpyxl
    ws = openpyxl.load_workbook(xp, read_only=True)["Secciones censales"]
    rows = ws.iter_rows(values_only=True)
    head = list(next(rows))
    col = {h: i for i, h in enumerate(head) if h}
    years = sorted({h[-2:] for h in head if h and h.startswith("ALQM2_LV_M_VC_")})
    out = {}
    for r in rows:
        if r[col["CUMUN"]] != municipality:
            continue
        rec = {}
        for y in years:
            m, n = r[col[f"ALQM2_LV_M_VC_{y}"]], r[col.get(f"BI_ALVHEPCO_TVC_{y}")]
            if isinstance(m, (int, float)) and isinstance(n, (int, float)):
                rec[f"20{y}"] = [round(float(m), 3), int(n)]
        if rec:
            out[r[col["CUSEC"]]] = rec
    json.dump(out, open(jp, "w"), separators=(",", ":"))
    return out
