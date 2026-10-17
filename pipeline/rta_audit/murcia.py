"""Murcia (Región de Murcia): registration numbers, the Registro de Empresas y Actividades Turísticas (ITREM listings),
and the same classification as the other regions.

Numbers: tourist flats are VV.MU.<filing>-<dwelling> (e.g. VV.MU.6415-1); hosts write VV MU 6415-1, VV-MU-6415-1 or
VVMU6415.1. Other types: A.MU (apartments), H.MU (hotels), AR.MU (rural), CT.MU (campsites), ALB.MU (hostels). The
national number often ends with the regional number plus a check digit.
Register: the ITREM's "Listados de establecimientos" (HTML tables served as .xls, updated daily): the whole region's
tourist flats, so a number from another town is recognised, plus the other types in Murcia itself. No coordinates: each
flat is placed on its Catastro parcel from its cadastral reference. We never keep trade names, phones, webs or emails.
Letting rooms is allowed (Decreto 256/2019, art. 2.2.b), so room listings aren't flagged.
"""
import html as _html
import re

from .register import haversine_m

LOCATION_THRESHOLD_M = 800
SEASONAL_NIGHTS = 32   # no regional figure: lets under the national tenancy law are excluded (Decreto 256/2019, art. 1.2.b)

URL = "https://www.turismoregiondemurcia.es/es/etudoc.xls?vtip={t}&vmuni={m}"
FILES = {"vv_region.html": (6, ""), "vv_murcia.html": (6, "30030"), "h_murcia.html": (1, "30030"), "a_murcia.html": (2, "30030"),
         "ar_murcia.html": (3, "30030"), "ct_murcia.html": (7, "30030"), "alb_murcia.html": (14, "30030")}
KEEP = {"SIGNATURA": "code", "DIRECCIÓN": "address", "LOCALIDAD": "locality", "C.POSTAL": "postcode", "PLAZAS": "places",
        "REF. CATASTRAL": "cadastral", "FECHA DE PRESENTACIÓN DECLARACIÓN RESPONSABLE": "filed"}   # never names, phones, webs, emails

CODE_RE = re.compile(r"^(VV|A|AR|H|CT|ALB)\.MU\.0*(\d+)(?:-(\d+))?$")
AD_RE = re.compile(r"(?<![A-Z0-9])(VV|AR|ALB|CT|A|H)[\s.\-_]*MU[\s.\-_]*0*(\d{1,5})(?:[\s.\-_]+(\d{1,4}))?(?![0-9])", re.IGNORECASE)
EMB_RE = re.compile(r"(VV|AR|A)[\s.\-_]*MU[\s.\-_]*0*(\d{1,5})(?:[\s.\-_]+(\d{1,4}))?$", re.IGNORECASE)
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}[0-9A-Z]{10,}[0-9A-Z/.\-]*", re.IGNORECASE)
EXEMPT_RE = re.compile(r"\b(exempt|exento|exempt[ae])\b[^|<]*", re.IGNORECASE)


def key(prefix, n, k=None):
    return f"{prefix.upper()}.MU.{int(n)}" + (f"-{int(k)}" if k else "")


def read_table(text):
    """Rows of an ITREM listing (an HTML table), only the columns we keep."""
    rows = [[_html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)]
    hdr = next((r for r in rows if r and r[0] == "SIGNATURA"), None)
    out = []
    for r in rows if hdr else []:
        if len(r) != len(hdr) or r[0] == "SIGNATURA":
            continue
        rec = {}
        for h, v in zip(hdr, r):
            if h in KEEP and KEEP[h] not in rec:
                rec[KEEP[h]] = v
        out.append(rec)
    return out


def fetch(cache_dir):
    """Download the listings (kept as slim JSON); keep the previous copies if a download fails."""
    import json
    import os
    from . import http
    d = os.path.join(cache_dir, "murcia")
    os.makedirs(d, exist_ok=True)
    for name, (t, m) in FILES.items():
        p = os.path.join(d, name.replace(".html", ".json"))
        try:
            rows = read_table(http.get(URL.format(t=t, m=m), timeout=300).content.decode("latin-1"))
            if not rows and t == 6:
                raise ValueError("empty listing")
            json.dump(rows, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            print(f"murcia: {name} download failed, keeping previous copy:", e)
    return d


def load_register(d, parcels=None):
    """{key: {"in_murcia", "lat", "lon", "places", "address", "postcode", "locality", "cadastral"}}."""
    import json
    import os
    idx = {}
    for name in FILES:
        p = os.path.join(d, name.replace(".html", ".json"))
        if not os.path.exists(p):
            continue
        here = name.endswith("_murcia.html")
        for r in json.load(open(p, encoding="utf-8")):
            m = CODE_RE.match((r.get("code") or "").strip().upper())
            if not m:
                continue
            k = key(*m.groups())
            ref = (r.get("cadastral") or "").strip().upper()[:14]
            pt = (parcels or {}).get(ref) if here else None
            rec = idx.get(k) or {}
            idx[k] = {"in_murcia": here or rec.get("in_murcia", False), "lat": pt[1] if pt else rec.get("lat"),
                      "lon": pt[2] if pt else rec.get("lon"), "address": " ".join((r.get("address") or "").split()),
                      "postcode": r.get("postcode"), "locality": r.get("locality"), "cadastral": ref or None,
                      "places": int(r["places"]) if (r.get("places") or "").isdigit() else None, "since": r.get("filed")}
    filings = {}
    for k in idx:   # VV.MU.2867-1 → filing VV.MU.2867 (one holder's declaration, which can cover several flats)
        filings.setdefault(k.split("-")[0], k)
    idx["_filing"] = filings
    return idx


def find(idx, k):
    """The register entry for a shown number, allowing for how hosts write it: the filing alone (VV.MU.2867 for
    VV.MU.2867-1), filing and flat run together (VV.MU.50722 for 5072-2), or a check digit added to the flat (2935-19)."""
    if k in idx and k != "_filing":
        return k
    F = idx.get("_filing", {})
    base, _, flat = k.partition("-")
    if flat and len(flat) > 1 and f"{base}-{flat[:-1]}" in idx:
        return f"{base}-{flat[:-1]}"
    if not flat:
        pre, num = base.rsplit(".", 1)
        for cut in (1, 2):   # run together: the last one or two digits are the flat
            if len(num) > cut and f"{pre}.{int(num[:-cut])}-{int(num[-cut:])}" in idx:
                return f"{pre}.{int(num[:-cut])}-{int(num[-cut:])}"
    return F.get(base)


def parse(raw):
    text = re.sub(r"<br\s*/?>", " | ", raw or "")
    national = [m.group(0) for m in NATIONAL_RE.finditer(text)]
    rest = NATIONAL_RE.sub(" ", text)
    regional = list(dict.fromkeys(key(*m.groups()) for m in AD_RE.finditer(rest)))
    embedded = []
    for n in national:
        m = EMB_RE.search(n.upper())
        if m:   # the national number adds a check digit to the end of the regional one
            n_, k_ = m.group(2), m.group(3)
            if k_ and len(k_) > 1:
                k_ = k_[:-1]
            elif not k_ and len(n_) > 1:
                n_ = n_[:-1]
            embedded.append(key(m.group(1), n_, k_))
    e = EXEMPT_RE.search(text)
    return {"regional": regional, "national": national, "embedded": list(dict.fromkeys(embedded)),
            "exempt_text": e.group(0).strip() if e else None}


def classify(raw, lat, lon, room_type, min_nights, idx):
    p = parse(raw)
    codes = p["regional"] or p["embedded"]
    if codes:
        best = None
        for k0 in codes:
            k = find(idx, k0) or k0
            rec = idx.get(k) if k != "_filing" else None
            if not rec:
                cat = "NOT_IN_REGISTER"
            elif not rec["in_murcia"]:
                cat = "FOUND_OTHER_MUNICIPALITY"
            elif rec["lat"] is not None and lat not in (None, "") and \
                    haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]) > LOCATION_THRESHOLD_M:
                cat = "FOUND_INCONSISTENT"
            else:
                cat = "FOUND_CONSISTENT"
            rank = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "NOT_IN_REGISTER": 3}[cat]
            if best is None or rank < best[0]:
                best = (rank, cat, k)
        return {"category": best[1], "key": best[2], "embedded_only": not p["regional"], "group": None}
    try:
        long_stay = int(min_nights or 0) >= SEASONAL_NIGHTS
    except ValueError:
        long_stay = False
    if long_stay or room_type == "Hotel room" or p["national"] \
            or (p["exempt_text"] and re.search(r"(?i)seasonal|temporada|apartamento|apartment|hotel", p["exempt_text"])):
        return {"category": "NO_CODE_POSSIBLY_EXEMPT", "key": None}
    return {"category": "NO_CODE_IN_SCOPE", "key": None}


TYPE_MAP = {"VV": "Vivienda de uso turístico", "A": "Apartamento turístico", "H": "Establecimiento Hotelero", "AR": "Casa rural",
            "CT": "Camping", "ALB": "Establecimiento Hotelero"}


def as_register_records(idx, name="MURCIA"):
    out = []
    for k, v in idx.items():
        if k == "_filing" or not v["in_murcia"]:
            continue
        m = re.match(r"^(.*?)[,\s]+(\d+\s*[A-Z]?)\b(.*)$", v.get("address") or "")
        out.append({"registration_code": k, "objects_type_id": TYPE_MAP.get(k.split(".")[0], "Otros"), "group": None,
                    "municipalities": name, "provinces": "MURCIA", "lat": v["lat"], "lon": v["lon"],
                    "road_name": m.group(1) if m else v.get("address"), "km_num": m.group(2).replace(" ", "") if m else None,
                    "floor": (m.group(3).strip(" ,") or None) if m else None, "door": None, "staircase": None, "block": None,
                    "portal": None, "postal_code": v.get("postcode"), "locality": v.get("locality"), "tot_gen_places": v.get("places"),
                    "registration_date": _ymd(v.get("since")), "domicile_complement": None, "catastral_ref": v.get("cadastral")})
    return out


def _ymd(d):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", d or "")
    return f"{m.group(3)}{m.group(2)}{m.group(1)}" if m else ""
