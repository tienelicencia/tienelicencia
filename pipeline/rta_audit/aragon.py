"""Zaragoza (Aragón): registration numbers, the Registro de Turismo de Aragón (viviendas de uso turístico), and the same
classification as the other regions.

Numbers: VU-ZA-18-101 (2015–2024: province, year of registration, serial) and VUT-ZA-25-0015 (from late 2024). Province +
year + serial is unique, so the VU/VUT prefix and leading zeros are ignored. Hosts write VU-ZA18101, VUZA-18-101…; the
national number (ESFCTU…) ends with the regional number plus one digit.
Register: the Gobierno de Aragón's register app exports every active tourist flat in Aragón as one xlsx (no coordinates,
and most addresses lack a street number). Aragón Open Data lists its tourism registers under CC BY 4.0; the app's own
legal notice mentions personal use. This is a free, non-commercial public-interest tool, so we republish number and
address as for every other region (see the note on the methodology page) and will remove it if Aragón asks. We never read
the name, phone, email or web columns.
Letting by rooms isn't allowed (Decreto 1/2023, art. 3), so a room listing showing a flat's number is flagged.
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

SEASONAL_NIGHTS = 32   # tourist use presumed for stays of a month or less (Decreto 1/2023, art. 4.3); see docs/law-sources.md
URL = "https://aplicaciones.aragon.es/wturpub/informes/exportarActividadesTuristicasExcel?tipoExportacion=exportarVUT"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
# Localities inside the municipality of Zaragoza (its barrios rurales), as the register writes them
ZARAGOZA = {"ZARAGOZA", "ALFOCEA", "CASETAS", "GARRAPINILLOS", "JUSLIBOL", "MONTAÑANA", "MONZALBARBA", "MOVERA", "PEÑAFLOR",
            "PEÑAFLOR DE GALLEGO", "SAN JUAN DE MOZARRIFAR", "TORRECILLA DE VALMADRID", "VILLARRAPA", "LA CARTUJA BAJA",
            "CARTUJA BAJA", "SAN GREGORIO", "VENTA DEL OLIVAR", "EL BURGO DE EBRO"} - {"EL BURGO DE EBRO"}

REGIONAL_RE = re.compile(r"(?<![A-Z0-9])(VUT?)[\s\-_./]*(HU|TE|ZA|Z)[\s\-_./]*(\d{2})[\s\-_./]*(\d{1,5})(?![0-9])", re.IGNORECASE)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)


def key(prov, yy, num):
    return f"{'ZA' if prov.upper() == 'Z' else prov.upper()}-{yy}-{int(num)}"


def _read_xlsx(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    ss = [("".join(t.text or "" for t in si.iter(NS + "t"))) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si")] \
        if "xl/sharedStrings.xml" in z.namelist() else []
    rows = []
    for r in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(NS + "row"):
        vals = {}
        for c in r.iter(NS + "c"):
            col = 0
            for ch in re.match(r"[A-Z]+", c.get("r")).group(0):
                col = col * 26 + ord(ch) - 64
            v = c.find(NS + "v")
            vals[col - 1] = "".join(x.text or "" for x in c.iter(NS + "t")) if c.get("t") == "inlineStr" \
                else "" if v is None else ss[int(v.text)] if c.get("t") == "s" else v.text
        if vals:
            rows.append([vals.get(i, "") for i in range(max(vals) + 1)])
    return rows


def fetch(cache_dir):
    """Download the register; keep only number, province, locality, address and postcode (never names or contacts)."""
    import csv
    import os
    from . import http
    d = os.path.join(cache_dir, "aragon")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "vut.csv")
    try:
        rows = _read_xlsx(http.get(URL, timeout=300).content)
        head = [h.strip().lower() for h in rows[0]]
        i_sig, i_prov, i_loc = head.index("signatura"), head.index("provincia"), head.index("localidad")
        i_dir, i_cp = head.index("dirección"), head.index("c.p.")
        body = [[r[i_sig], r[i_prov], r[i_loc], r[i_dir] if len(r) > i_dir else "", r[i_cp] if len(r) > i_cp else ""]
                for r in rows[1:] if len(r) > i_sig]
        if len(body) < 1000:
            raise ValueError(f"unexpected file ({len(body)} rows)")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["signatura", "provincia", "localidad", "direccion", "cp"])
            w.writerows(body)
    except Exception as e:  # noqa: BLE001
        print("aragon: register download failed, keeping previous copy:", e)
    return p


def load_register(path):
    import csv
    import os
    idx = {}
    if not os.path.exists(path):
        return idx
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = re.match(r"VUT?-(HU|TE|ZA)-(\d{2})-0*(\d+)$", (r.get("signatura") or "").strip().upper())
            if m:
                loc = (r.get("localidad") or "").strip().upper()
                idx[key(*m.groups())] = {"zaragoza": loc in ZARAGOZA and (r.get("provincia") or "").strip().upper() == "ZARAGOZA", "locality": loc, "code": r["signatura"].strip().upper(),
                                         "address": " ".join((r.get("direccion") or "").split()), "postcode": r.get("cp")}
    return idx


def parse(raw, idx=None):
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    embedded = []
    for n in national:
        m = re.search(r"(VUT?)[\-_./]?(HU|TE|ZA)[\-_./]?(\d{2})[\-_./]?(\d{2,6})$", n.upper())
        if m:
            embedded.append(key(m.group(2), m.group(3), m.group(4)[:-1]))
    regional = []
    for m in REGIONAL_RE.finditer(NATIONAL_RE.sub(" ", text)):
        pre, prov, yy, num = m.groups()
        cands = [key(prov, yy, num)]
        if (pre.upper() == "VU" and len(num) >= 4) or len(num) >= 5:   # one digit too many: try without it
            cands.append(key(prov, yy, num[:-1]))
        regional.append(next((c for c in cands if idx is None or c in idx), cands[0]))
    e = EXEMPT_RE.search(text)
    return {"regional": list(dict.fromkeys(regional)), "national": national, "embedded": list(dict.fromkeys(embedded)),
            "exempt_text": e.group(0).strip() if e else None}


def classify(raw, lat, lon, room_type, min_nights, idx):
    """No coordinates in the register: the municipality decides (FOUND_CONSISTENT in Zaragoza, else
    FOUND_OTHER_MUNICIPALITY)."""
    p = parse(raw, idx)
    codes = p["regional"] or p["embedded"]
    if codes:
        best = None
        for k in codes:
            rec = idx.get(k)
            cat = "NOT_IN_REGISTER" if not rec else "FOUND_CONSISTENT" if rec["zaragoza"] else "FOUND_OTHER_MUNICIPALITY"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        return {"category": best[1], "key": best[2], "embedded_only": not p["regional"],
                "group": "Completa" if best[2] in idx else None}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or p["national"] \
            or (p["exempt_text"] and re.search(r"(?i)seasonal|temporada|apartamento|apartment|hotel", p["exempt_text"])):
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


def as_register_records(idx, name="ZARAGOZA"):
    """Zaragoza's flats in the same shape as Junta register records (search only: the register has no coordinates)."""
    out = []
    for k, v in idx.items():
        if not v["zaragoza"]:
            continue
        addr = re.sub(r"\s+(ZARAGOZA|%s)$" % "|".join(map(re.escape, ZARAGOZA)), "", v.get("address") or "")
        m = re.match(r"^(.*?),\s*(\d+\s*[A-Z]?)\b(.*)$", addr)
        out.append({"registration_code": v["code"], "objects_type_id": "Vivienda de uso turístico", "group": "Completa",
                    "municipalities": name, "provinces": "ZARAGOZA", "lat": None, "lon": None,
                    "road_name": m.group(1) if m else addr, "km_num": m.group(2).replace(" ", "") if m else None,
                    "floor": (m.group(3).strip(" ,") or None) if m else None, "door": None, "staircase": None, "block": None,
                    "portal": None, "postal_code": v.get("postcode") or None, "locality": v["locality"].title(), "tot_gen_places": None,
                    "registration_date": "", "domicile_complement": None, "catastral_ref": None})
    return out
