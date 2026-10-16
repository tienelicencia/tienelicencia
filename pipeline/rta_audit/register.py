"""OpenRTA (Junta de Andalucía tourism register) download, cache, profile and index.

Verified behaviour (2026-10-10):
  GET /api/v0/openrta/search/lastUpdateData -> {"date": "..."}
  GET /api/v0/openrta/all?format=json        -> 302 to a static file (~330 MB JSON array)
Only records with ind_pub_open_rta == 'S' are present; there is no cancellation/status field,
so cancelled registrations are absent rather than marked.
"""
import json
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone

from . import http
from .codes import normalise_key

API = "https://datos.juntadeandalucia.es/api/v0/openrta"
TOURIST_ACCOMMODATION_TYPES = [
    "Vivienda de uso turístico",
    "Apartamento turístico",
    "Establecimiento Hotelero",
    "Vivienda turística de alojamiento rural",
    "Casa rural",
    "Complejo turístico rural",
    "Campamento de turismo",
]
# Fields kept in the local index. Deliberately excludes holder, identification_doc_num,
# email, phone, mobile, fax, name (name is often the holder or a street-address label).
KEEP_FIELDS = [
    "id", "registration_code", "objects_type_id", "group", "categories", "municipalities", "provinces",
    "registration_date", "activity_start_date", "catastral_ref", "road_name", "portal", "block", "staircase",
    "floor", "door", "domicile_complement", "postal_code", "locality", "establishment_address", "road_code", "km_num", "numbering_type", "coord_x", "coord_y", "srid", "ind_pub_open_rta",
    "state_present_rtadseg", "state_verif_rtadseg", "rtadseg_verif_result",
    "rtadseg_presentation_date", "rtadseg_verification_date", "tot_gen_places",
]
STATUS_FIELDS = ["ind_pub_open_rta", "state_present_rtadseg", "state_verif_rtadseg",
                 "rtadseg_verif_result", "private_use_ind", "rental_type_ind", "shared_ind"]


def _num(s):
    if s in (None, "", "-"):
        return None
    try:
        return float(str(s).replace(",", "."))
    except ValueError:
        return None


def utm30_to_wgs84(x, y):
    """ETRS89 / UTM zone 30N (EPSG:25830) -> (lat, lon). GRS80 ellipsoid, ~cm accuracy."""
    a, f = 6378137.0, 1 / 298.257222101
    k0, lon0, e2 = 0.9996, math.radians(-3.0), f * (2 - f)
    ep2 = e2 / (1 - e2)
    x -= 500000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
          + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    n1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    t1, c1 = math.tan(p1) ** 2, ep2 * math.cos(p1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                          + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(p1)
    return math.degrees(lat), math.degrees(lon)


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def fetch(cache_dir, force=False):
    """Download the full dataset only when lastUpdateData changed. Returns metadata dict."""
    os.makedirs(cache_dir, exist_ok=True)
    meta_path = os.path.join(cache_dir, "register_meta.json")
    data_path = os.path.join(cache_dir, "openrta_all.json")
    last = http.get(f"{API}/search/lastUpdateData", timeout=60).json()["date"]
    old = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    if not force and old.get("lastUpdateData") == last and os.path.exists(data_path):
        old["checked_at"] = datetime.now(timezone.utc).isoformat()
        json.dump(old, open(meta_path, "w"), indent=2, ensure_ascii=False)
        return old
    count = http.get(f"{API}/count", timeout=60).json()
    t0 = time.time()
    tmp = data_path + ".part"
    # The Junta's server sometimes drops this ~330 MB download part-way: retry, and if it keeps failing
    # keep yesterday's copy (lastUpdateData isn't advanced, so the next run tries again).
    tries = 4 if os.path.exists(data_path) else 8   # no previous copy to fall back on: try harder
    for attempt in range(tries):
        try:
            r = http.get(f"{API}/all", params={"format": "json"}, timeout=1800, stream=True)
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
            json.load(open(tmp, encoding="utf-8"))   # must be complete, valid JSON
            break
        except Exception as e:  # noqa: BLE001 — network drop, truncated or invalid file
            print(f"register download attempt {attempt + 1} failed: {e}")
            if attempt < tries - 1:
                time.sleep(min(300, 30 * 2 ** attempt))
    else:
        if os.path.exists(data_path):
            print("register download failed; keeping the previous copy")
            old["checked_at"] = datetime.now(timezone.utc).isoformat()
            return old
        raise RuntimeError("register download failed and there is no previous copy")
    os.replace(tmp, data_path)
    meta = {
        "lastUpdateData": last,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "download_seconds": round(time.time() - t0, 1),
        "final_url": r.url,
        "etag": r.headers.get("etag"),
        "last_modified": r.headers.get("last-modified"),
        "bytes": os.path.getsize(data_path),
        "api_count": count,
    }
    json.dump(meta, open(meta_path, "w"), indent=2, ensure_ascii=False)
    return meta


def adopt_existing(cache_dir, path, last_update, downloaded_at, headers=None):
    """Register an already-downloaded file (used for the first manual download)."""
    data_path = os.path.join(cache_dir, "openrta_all.json")
    if os.path.abspath(path) != os.path.abspath(data_path):
        os.replace(path, data_path)
    meta = {"lastUpdateData": last_update, "downloaded_at": downloaded_at,
            "bytes": os.path.getsize(data_path), **(headers or {})}
    json.dump(meta, open(os.path.join(cache_dir, "register_meta.json"), "w"), indent=2)
    return meta


def load_records(cache_dir):
    return json.load(open(os.path.join(cache_dir, "openrta_all.json"), encoding="utf-8"))


def is_malaga_city(r):
    return (r.get("municipalities") or "").strip().upper() == "MÁLAGA"


def code_key(code):
    m = re.match(r"^([A-Z]+)/([A-Z]{2})/(\d+)$", (code or "").strip().upper())
    return normalise_key(m.group(1), m.group(2), m.group(3)) if m else None


def build_index(records):
    """Index ALL Andalusian records by normalised key (a Málaga listing may show a code
    registered in another municipality — that is itself a location inconsistency)."""
    idx = {}
    for r in records:
        k = code_key(r.get("registration_code"))
        if not k:
            continue
        slim = {f: r.get(f) for f in KEEP_FIELDS}
        x, y = _num(r.get("coord_x")), _num(r.get("coord_y"))
        if x and y and str(r.get("srid") or "25830") == "25830" and 100000 < x < 900000:
            slim["lat"], slim["lon"] = utm30_to_wgs84(x, y)
        idx.setdefault(k, []).append(slim)
    return idx


def max_issued(records):
    out = {}
    for r in records:
        m = re.match(r"^([A-Z]+)/([A-Z]{2})/(\d+)$", (r.get("registration_code") or ""))
        if m:
            k = (m.group(1), m.group(2))
            out[k] = max(out.get(k, 0), int(m.group(3)))
    return out


def profile(records):
    mal = [r for r in records if is_malaga_city(r)]
    acc = [r for r in mal if r.get("objects_type_id") in TOURIST_ACCOMMODATION_TYPES]
    vut = [r for r in mal if r.get("objects_type_id") == "Vivienda de uso turístico"]
    fields = Counter(k for r in records for k in r)
    p = {
        "total_records": len(records),
        "fields": sorted(fields),
        "malaga_city_records": len(mal),
        "malaga_by_type": Counter(r.get("objects_type_id") for r in mal).most_common(),
        "malaga_accommodation_records": len(acc),
        "malaga_accommodation_by_group": Counter(f"{r.get('objects_type_id')} / {r.get('group')}" for r in acc).most_common(),
        "status_fields_malaga": {f: Counter(str(r.get(f)) for r in mal).most_common() for f in STATUS_FIELDS},
        "code_shapes_malaga": Counter(re.sub(r"\d", "9", r.get("registration_code") or "None") for r in acc).most_common(),
        "vft_codes_anywhere": sum("VFT" in (r.get("registration_code") or "") for r in records),
        "vut_completeness": {f: sum(1 for r in vut if r.get(f) not in (None, "", "-")) for f in
                             ["catastral_ref", "coord_x", "postal_code", "road_name", "portal", "floor", "door",
                              "registration_date", "activity_start_date"]},
        "vut_count": len(vut),
        "vut_registered_after_2025_08_23": sum(1 for r in vut if (r.get("registration_date") or "") > "20250823"),
        "vut_max_registration_date": max((r.get("registration_date") or "" for r in vut), default=None),
        "vut_registration_year": sorted(Counter((r.get("registration_date") or "")[:4] for r in vut).items()),
        "duplicate_registration_codes": sum(1 for v in Counter(r.get("registration_code") for r in records).values() if v > 1),
        "malaga_vut_cadastral_refs_with_multiple_codes": sum(
            1 for v in Counter(r.get("catastral_ref") for r in vut if r.get("catastral_ref")).values() if v > 1),
    }
    return p
