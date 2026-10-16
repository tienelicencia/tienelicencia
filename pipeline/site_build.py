#!/usr/bin/env python3
"""Keep the public site's data current.

  python3 site_build.py refresh                 # register (if changed), newest Inside Airbnb snapshot, barrios
  python3 site_build.py recheck --budget 1500   # rolling live recheck of the oldest-checked listings
  python3 site_build.py build                   # write site/data/<area>/* and the function lookup + search index
  python3 site_build.py seed-state              # one-off: import earlier audit runs (cache/audit.sqlite)

A scheduled job runs: refresh → recheck → build, then deploys site/.
"""
import argparse
import csv
import gzip
import json
import os
import sqlite3
import sys
import time
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
from rta_audit import buildings, catastro, classify, codes, geo, ine, live, register, sample, serpavi, snapshot, state  # noqa: E402

PIPE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(PIPE)
CACHE = os.environ.get("RTA_CACHE", os.path.join(PIPE, "cache"))
REG_DIR = os.path.join(CACHE, "register")
STATE_DIR = os.path.join(REPO, "state")
SITE_DATA = os.path.join(REPO, "site", "data")
FN_DATA = os.path.join(REPO, "netlify", "functions", "data")
MIN_LISTINGS_AREA = 15   # suppress % for barrios with fewer listings
MIN_LISTINGS_HEX = 10    # don't draw problem hexes with fewer listings (privacy + noise)
MIN_HOMES_SHARE = 30     # don't give a "% of homes" for map areas with fewer dwellings (noise)
MIN_HOMES_BARRIO = 100   # same for barrios in rankings
LIVE_MAX_AGE_DAYS = 45   # older live checks fall back to snapshot text


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_path(city):
    """Live checks per city, in separate files so each city's re-check job commits its own."""
    return os.path.join(STATE_DIR, "listings_live.json" if city == "malaga" else f"listings_live_{city}.json")


# ------------------------------------------------------------------ refresh
def cmd_refresh(a):
    meta = register.fetch(REG_DIR)
    snaps = {c: snapshot.update(CACHE, c) for c in LISTING_CITIES}
    snap = snaps["malaga"]
    geo.ensure_barrios(CACHE)
    i = ine.fetch(CACHE)   # tourist homes advertised on the main platforms, per municipality (about twice a year)
    ine.fetch_rent(CACHE)  # rent index by district / municipality (yearly)
    geo.ensure_sections(CACHE)
    print("ine", i and i["period"])
    try:   # dwellings per building, for "tourist flats as a share of homes" (about one release a year)
        cat = catastro.ensure(CACHE, catastro.municipalities(CATASTRO_PROVINCE), CATASTRO_PROVINCE)
        for prov_, name_ in CATASTRO_EXTRA:   # other listing cities: just the municipality
            cat |= catastro.ensure(CACHE, [m for m in catastro.municipalities(prov_) if m[1].strip().upper() == name_], prov_)
        print("catastro", len(cat), "municipalities")
    except Exception as e:  # never block the daily refresh on Catastro
        print("catastro skipped:", e)
    print("register", meta["lastUpdateData"], "| snapshots", {c: s_[0] + (" (new)" if s_[2] else "") for c, s_ in snaps.items()})


# ------------------------------------------------------------------ recheck
def cmd_recheck(a):
    date, path = snapshot.latest_local(CACHE, a.city)
    ids = [r["id"] for r in sample.load_snapshot(path)]
    STATE = state_path(a.city)
    st = state.load(STATE)
    todo = state.due(st, ids, a.budget)
    blocked, start, tally = 0, time.monotonic(), Counter()
    for n, lid in enumerate(todo, 1):
        if a.max_minutes and time.monotonic() - start > a.max_minutes * 60:
            print(f"STOP: {a.max_minutes} min time limit after {n - 1} listings; the next run continues")
            break
        rec = live.fetch_live(lid, os.path.join(PIPE, "evidence", lid) if a.evidence else None)
        state.record(st, rec)
        if n % 25 == 0:
            state.save(STATE, st)
        tally[rec.get("live_status")] += 1
        if n % 100 == 0 or n == len(todo):
            print(f"[{n}/{len(todo)}] {dict(tally)}", flush=True)   # counts only: workflow logs may be public
        blocked = blocked + 1 if rec.get("live_status") == "blocked" else 0
        if blocked >= 3:
            print("STOP: blocked by Airbnb; will resume next run")
            break
    state.save(STATE, st)


# ------------------------------------------------------------------ town samples (no Inside Airbnb data)
SAMPLE_DIR = os.path.join(REPO, "state", "samples")
SAMPLE_TOWNS = {"marbella", "granada", "cordoba", "cadiz"}
FRAME_MAX_AGE_DAYS = 80   # rebuild the list of a town's listings about once a quarter


def muni_locator(index):
    """Nearest registered tourist accommodation → municipality, for deciding whether a listing is in a town.
    Grid of ~1 km cells over every register record with coordinates."""
    grid = defaultdict(list)
    for rs in index.values():
        for x in rs:
            if x.get("lat") is not None and x.get("municipalities"):
                grid[(round(x["lat"] * 100), round(x["lon"] * 100))].append((x["lat"], x["lon"], x["municipalities"]))

    def locate(lat, lon, max_m=1500):
        cy, cx = round(lat * 100), round(lon * 100)
        best = (max_m, None)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for la, lo, m in grid.get((cy + dy, cx + dx), ()):
                    d = register.haversine_m(lat, lon, la, lo)
                    if d < best[0]:
                        best = (d, m)
        return best[1]
    return locate


def sample_path(town):
    return os.path.join(SAMPLE_DIR, f"{town}.json")


def cmd_sample(a):
    """Build (or reuse) the list of a town's Airbnb listings, then live-check a fixed random sample of it."""
    from rta_audit import airbnb_search
    import hashlib
    A = next(x for x in AREAS if x["slug"] == a.town)
    home = A["home"]
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    path = sample_path(a.town)
    S = json.load(open(path)) if os.path.exists(path) else {"town": a.town, "home": home, "checks": {}}
    t0 = time.monotonic()
    fresh = S.get("frame_date") and (datetime.now(timezone.utc) - datetime.fromisoformat(S["frame_date"])).days < FRAME_MAX_AGE_DAYS
    if not fresh or a.refresh_frame:
        recs = register.load_records(REG_DIR)
        index = register.build_index(recs)
        del recs
        pts = [(x["lat"], x["lon"]) for rs in index.values() for x in rs if x.get("municipalities") == home and x.get("lat") is not None]
        lats, lons = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
        q = lambda v, f: v[int(f * (len(v) - 1))]
        box = (q(lats, .002) - .004, q(lons, .002) - .004, q(lats, .998) + .004, q(lons, .998) + .004)
        print("town box", box, "from", len(pts), "register points")
        found, capped = airbnb_search.enumerate_box(box)
        locate = muni_locator(index)
        inside = {k: v for k, v in found.items() if locate(v["lat"], v["lon"]) == home}
        S.update(frame_date=now(), frame=[[k, v["lat"], v["lon"]] for k, v in sorted(inside.items())], frame_found=len(found),
                 frame_outside=len(found) - len(inside), capped_areas=len(capped))
        json.dump(S, open(path, "w"), separators=(",", ":"))
        print(f"frame: {len(inside)} listings in {home} ({len(found) - len(inside)} outside, {len(capped)} capped areas)")
    # Fixed random order (hash of the id): the first N of the list are a simple random sample.
    order = sorted((r[0] for r in S["frame"]), key=lambda i: hashlib.sha1(i.encode()).hexdigest())[:a.n]
    todo = [i for i in order if i not in S["checks"]]
    print(f"sample {len(order)} of {len(S['frame'])}: {len(order) - len(todo)} already checked, {len(todo)} to go")
    blocked, tally = 0, Counter()
    for k, lid in enumerate(todo, 1):
        if a.max_minutes and time.monotonic() - t0 > a.max_minutes * 60:
            print(f"STOP: time limit after {k - 1}; the next run continues")
            break
        rec = live.fetch_live(lid, None)
        S["checks"][lid] = {"checked_at": rec.get("live_fetched_at") or now(), **{f: rec.get(f) for f in state.KEEP}}
        tally[rec.get("live_status")] += 1
        if k % 100 == 0 or k == len(todo):
            print(f"[{k}/{len(todo)}] {dict(tally)}", flush=True)   # counts only: workflow logs may be public
        if k % 25 == 0:
            json.dump(S, open(path, "w"), separators=(",", ":"))
        blocked = blocked + 1 if rec.get("live_status") == "blocked" else 0
        if blocked >= 3:
            print("STOP: blocked by Airbnb; will resume next run")
            break
    S["sample_n"] = a.n
    json.dump(S, open(path, "w"), separators=(",", ":"))


def sample_summary(path, index, official, mx, home):
    """Town estimate from its live-checked random sample: shares with 95% intervals (Wilson)."""
    S = json.load(open(path))
    order = sorted((r[0] for r in S["frame"]), key=lambda i: __import__("hashlib").sha1(i.encode()).hexdigest())[:S.get("sample_n", 1000)]
    checked = [S["checks"][i] for i in order if i in S["checks"]]
    ok = [c for c in checked if c.get("live_status") == "ok"]
    V, C = Counter(), Counter()
    for c in ok:
        r = classify.classify({"registration_raw": c.get("registration_raw"), "lat": c.get("lat"), "lon": c.get("lon"),
                               "room_type": c.get("room_type"), "property_type": c.get("property_type"), "min_nights": None},
                              index, official, mx, home)
        V[classify.VERDICT[r["category"]]] += 1
        C[r["category"]] += 1
    n = len(ok)

    def wilson(k):
        if not n:
            return None
        z, p = 1.96, k / n
        d = 1 + z * z / n
        c = (p + z * z / (2 * n)) / d
        h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
        return [round(100 * (c - h), 1), round(100 * (c + h), 1)]
    return {"frame": len(S["frame"]), "frame_date": S["frame_date"][:10], "sample": len(order), "checked": n,
            "removed": sum(1 for c in checked if c.get("live_status") == "removed"),
            "last_checked": max((c["checked_at"] for c in checked), default=None),
            "verdicts": dict(V), "not_valid_pct": round(100 * V["NOT_VALID"] / n, 1) if n else None,
            "not_valid_ci": wilson(V["NOT_VALID"]),
            "breakdown": {"no_number": C["NO_CODE_IN_SCOPE"], "not_in_register": C["NOT_IN_REGISTER"] + C["MALFORMED"],
                          "other_town": C["FOUND_OTHER_MUNICIPALITY"]}}


def cmd_seed_state(a):
    STATE = state_path("malaga")
    st = state.load(STATE)
    c = sqlite3.connect(os.path.join(CACHE, "audit.sqlite"))
    n = 0
    for lid, js in c.execute("SELECT listing_id, json FROM live"):
        rec = json.loads(js)
        if lid.isdigit() and (lid not in st or st[lid]["checked_at"] < rec["live_fetched_at"]):
            state.record(st, rec)
            n += 1
    state.save(STATE, st)
    print("seeded", n, "listings; state has", len(st))


# ------------------------------------------------------------------ build
def load_official():
    # Hand-collected official documents live with the private state (state/inputs) in the public setup
    p = next((x for x in (os.path.join(STATE_DIR, "inputs", "official_status.csv"), os.path.join(PIPE, "inputs", "official_status.csv"))
              if os.path.exists(x)), "")
    out = {}
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            k = register.code_key(r["registration_code"])
            if k:
                out[k] = r
    return out


def fresh(st_rec, snap_date):
    if not st_rec:
        return False
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(st_rec["checked_at"].replace("Z", "+00:00"))).days
    return age <= LIVE_MAX_AGE_DAYS and st_rec["checked_at"][:10] >= snap_date


def host_bucket(n):
    n = int(n or 1)
    return "1" if n == 1 else "2-5" if n <= 5 else "6-20" if n <= 20 else "21+"


# Areas shown on the site. `match` picks register records; only Málaga city has Airbnb listing data
# (Inside Airbnb covers the municipality only). Add a city here and in netlify.toml's redirects.
ANDALUSIA = {"ALMERÍA", "CÁDIZ", "CÓRDOBA", "GRANADA", "HUELVA", "JAÉN", "MÁLAGA", "SEVILLA"}
AREAS = [
    {"slug": "malaga", "name": {"es": "Málaga (ciudad)", "en": "Málaga (city)"}, "kind": "city", "home": "MÁLAGA",
     "match": lambda x: x.get("municipalities") == "MÁLAGA", "listings": True, "barrios": True, "ine": "29067",
     "center": [-4.425, 36.722], "zoom": 13.2, "hex_m": 90, "subareas": "barrio", "cap": 8},
    {"slug": "sevilla", "name": {"es": "Sevilla (ciudad)", "en": "Seville (city)"}, "kind": "city", "home": "SEVILLA",
     "match": lambda x: x.get("municipalities") == "SEVILLA", "listings": True, "barrios": True, "ine": "41091",
     "center": [-5.987, 37.389], "zoom": 13.2, "hex_m": 90, "subareas": "barrio", "cap": 10},
    {"slug": "marbella", "name": {"es": "Marbella", "en": "Marbella"}, "kind": "city",
     "match": lambda x: x.get("municipalities") == "MARBELLA", "listings": False, "barrios": False, "ine": "29069",
     "center": [-4.93, 36.51], "zoom": 12, "hex_m": 150, "subareas": "locality"},
    {"slug": "granada", "name": {"es": "Granada (ciudad)", "en": "Granada (city)"}, "kind": "city", "home": "GRANADA",
     "match": lambda x: x.get("municipalities") == "GRANADA", "listings": False, "barrios": False, "ine": "18087",
     "center": [-3.598, 37.177], "zoom": 13.4, "hex_m": 90, "subareas": "locality"},
    {"slug": "cordoba", "name": {"es": "Córdoba (ciudad)", "en": "Córdoba (city)"}, "kind": "city", "home": "CÓRDOBA",
     "match": lambda x: x.get("municipalities") == "CÓRDOBA", "listings": False, "barrios": False, "ine": "14021",
     "center": [-4.779, 37.884], "zoom": 13.4, "hex_m": 90, "subareas": "locality"},
    {"slug": "cadiz", "name": {"es": "Cádiz (ciudad)", "en": "Cádiz (city)"}, "kind": "city", "home": "CÁDIZ",
     "match": lambda x: x.get("municipalities") == "CÁDIZ", "listings": False, "barrios": False, "ine": "11012",
     "center": [-6.292, 36.527], "zoom": 14, "hex_m": 90, "subareas": "locality"},
    {"slug": "provincia", "name": {"es": "Provincia de Málaga", "en": "Málaga province"}, "kind": "province",
     "match": lambda x: (x.get("provinces") or "").upper() == "MÁLAGA", "listings": False, "barrios": False, "ine": "province",
     "center": [-4.65, 36.68], "zoom": 8.6, "hex_m": 450, "subareas": "municipality"},
    # The other seven provinces: register only; "% of homes" from the INE census (no Catastro for whole provinces yet).
    *[{"slug": f"provincia-{slug}", "name": {"es": f"Provincia de {es}", "en": f"{es} province"}, "kind": "province",
       "match": (lambda P: lambda x: (x.get("provinces") or "").upper() == P)(reg), "listings": False, "barrios": False,
       "ine": f"prov:{code}", "census": True, "center": c, "zoom": z, "hex_m": 450, "subareas": "municipality"}
      for slug, es, reg, code, c, z in [
          ("sevilla", "Sevilla", "SEVILLA", "41", [-5.75, 37.35], 8.4), ("cadiz", "Cádiz", "CÁDIZ", "11", [-5.75, 36.45], 8.4),
          ("granada", "Granada", "GRANADA", "18", [-3.35, 37.25], 8.2), ("almeria", "Almería", "ALMERÍA", "04", [-2.35, 37.05], 8.2),
          ("cordoba", "Córdoba", "CÓRDOBA", "14", [-4.75, 37.85], 8.2), ("huelva", "Huelva", "HUELVA", "21", [-6.85, 37.55], 8.2),
          ("jaen", "Jaén", "JAÉN", "23", [-3.6, 37.95], 8.2)]],
    # Whole region: register only. "% of homes" uses the INE census count for every municipality (one consistent source).
    {"slug": "andalucia", "name": {"es": "Andalucía", "en": "Andalucía"}, "kind": "region",
     "match": lambda x: (x.get("provinces") or "").upper() in ANDALUSIA, "listings": False, "barrios": False, "ine": "region",
     "center": [-4.55, 37.35], "zoom": 7.1, "hex_m": 2500, "subareas": "municipality"},
]
SEARCH_PROVINCES = ANDALUSIA   # the search index covers all of Andalucía
CATASTRO_PROVINCE = "29"     # Catastro: every municipality in Málaga province…
CATASTRO_EXTRA = [("41", "SEVILLA"), ("18", "GRANADA"), ("14", "CORDOBA"), ("11", "CADIZ")]   # …plus these cities
LISTING_CITIES = [A["slug"] for A in AREAS if A["listings"]]   # Inside Airbnb city slugs = our area slugs


def city_barrios(slug):
    """Barrio polygons: Málaga's from its open data, Sevilla's from the Inside Airbnb neighbourhoods file (108 barrios)."""
    if slug == "malaga":
        return geo.Barrios(geo.ensure_barrios(CACHE))
    _, p = snapshot.latest_local(CACHE, slug)
    return geo.Barrios(os.path.join(os.path.dirname(p), "neighbourhoods.geojson"))


def classify_listings(index, official, mx, snap_date, rows, st, home="MÁLAGA"):
    """Classify every listing of one city (live if fresh, else snapshot text). Returns (listings, removed, by_key)."""
    out, removed = [], 0
    for r in rows:
        s = st.get(r["id"])
        basis = "snapshot"
        if fresh(s, snap_date) and s["live_status"] == "removed":
            removed += 1
            continue
        if fresh(s, snap_date) and s["live_status"] == "ok":
            basis = "live"
            v = {"registration_raw": s["registration_raw"], "lat": s["lat"], "lon": s["lon"],
                 "room_type": s["room_type"], "property_type": s["property_type"], "min_nights": r["minimum_nights"]}
        else:
            v = {"registration_raw": r["license"], "lat": r["latitude"], "lon": r["longitude"], "room_type": r["room_type"],
                 "property_type": r["property_type"], "min_nights": r["minimum_nights"]}
        c = classify.classify(v, index, official, mx, home)
        out.append({"id": r["id"], "lat": float(v["lat"]), "lon": float(v["lon"]), "basis": basis, "cat": c["category"],
                    "verdict": classify.VERDICT[c["category"]], "key": c.get("match_key") or c.get("primary_code_norm"),
                    "keys": [k for k in (c.get("junta_codes_norm") or "").split("; ") if k],
                    "entire": (v["room_type"] == "Entire home/apt"), "host": r["host_id"],
                    "host_bucket": host_bucket(r["calculated_host_listings_count"]),
                    "reg_group": (c.get("register_record") or {}).get("group")})

    # shared whole-dwelling codes
    by_key = defaultdict(list)
    for o in out:
        for k in o["keys"]:
            by_key[k].append(o)
    # A single-dwelling licence on whole-home listings from more than one host can't be valid for all of them.
    # The same host listing the same flat twice is not flagged.
    for o in out:
        if o["verdict"] == "VALID" and o["entire"] and o["reg_group"] == "Completa":
            if shared_hosts(by_key[o["key"]]) > 1:
                o["verdict"] = "VALID_CODE_SHARED"
    return out, removed, by_key


def shared_hosts(rows):
    """Distinct hosts showing a code on whole-home listings."""
    return len({x["host"] for x in rows if x["entire"]})


def listing_summary(out, removed, by_key, area_vut):
    V = ["VALID", "VALID_CODE_SHARED", "VALID_LOCATION_MISMATCH", "NOT_VALID", "POSSIBLY_EXEMPT", "INCONCLUSIVE"]
    vc = Counter(o["verdict"] for o in out)
    cc = Counter(o["cat"] for o in out)
    hb = defaultdict(Counter)
    for o in out:
        hb[o["host_bucket"]]["n"] += 1
        hb[o["host_bucket"]][o["verdict"]] += 1
    shown = {o["key"] for o in out if o["verdict"] in ("VALID", "VALID_CODE_SHARED", "VALID_LOCATION_MISMATCH")}
    return {
        "listings": len(out), "removed_since_snapshot": removed, "live_checked": sum(1 for o in out if o["basis"] == "live"),
        "verdicts": {v: vc.get(v, 0) for v in V},
        "categories": dict(cc),
        "not_valid_breakdown": {
            "no_number": cc.get("NO_CODE_IN_SCOPE", 0),
            "not_in_register": cc.get("NOT_IN_REGISTER", 0) + cc.get("MALFORMED", 0),
            "other_town": cc.get("FOUND_OTHER_MUNICIPALITY", 0),
            "cancelled": cc.get("CANCELLED_OFFICIAL", 0)},
        "by_host_size": {k: {"n": v["n"], "not_valid_pct": round(100 * v["NOT_VALID"] / v["n"], 1)} for k, v in hb.items()},
        "registered_vut": len(area_vut),
        "registered_vut_seen": len({register.code_key(x["registration_code"]) for x in area_vut} & shown),
        "shared_codes": len({o["key"] for o in out if o["verdict"] == "VALID_CODE_SHARED"}),
    }


def listing_dots(out, hexg):
    """Dot-density layer: one dot per Airbnb listing, coloured by result, placed at a RANDOM spot inside its ~150 m
    hexagon (never at the listing's own, already approximate, location). Only hexagons with MIN_LISTINGS_HEX+ listings,
    like the hexagon layer. The randomness is seeded per hexagon so the picture is stable between builds.
    Returns [[lon, lat, v]] with v = 0 no valid number, 1 valid number, 2 possibly exempt."""
    import random
    by_hex = defaultdict(list)
    for o in out:
        by_hex[hexg.cell(o["lat"], o["lon"])].append(
            0 if o["verdict"] == "NOT_VALID" else 2 if o["verdict"] == "POSSIBLY_EXEMPT" else 1)
    dots = []
    for (q, r_), vs in by_hex.items():
        if len(vs) < MIN_LISTINGS_HEX:
            continue
        ring = hexg.polygon(q, r_)[:6]
        lons, lats = [p[0] for p in ring], [p[1] for p in ring]
        rnd = random.Random(f"{q},{r_}")
        rnd.shuffle(vs)   # order carries no information either
        for v in vs:
            while True:   # uniform inside the hexagon (rejection sampling in its bounding box)
                lo, la = rnd.uniform(min(lons), max(lons)), rnd.uniform(min(lats), max(lats))
                if geo._pip(la, lo, [(p[1], p[0]) for p in ring]):
                    break
            dots.append([round(lo, 5), round(la, 5), v])
    return dots


def registered_summary(recs, agg_ids, agg):
    """Register-only facts for an area: counts, places, years, biggest buildings."""
    vut = [x for x in recs if x.get("objects_type_id") == buildings.VUT]
    years = Counter((x.get("registration_date") or "")[:4] for x in vut)
    bids = Counter(agg_ids[id(x)] for x in vut if id(x) in agg_ids)
    by_id = {b["id"]: b for b in agg.b.values()}
    # Every building with 10+ tourist flats (the card shows the top few and expands to the first 200; the CSV has all):
    # [id, full label, flats, places, lat, lon, homes, short name, municipality, barrio]
    top = []
    for bid, n in bids.most_common():
        if n < 10 and len(top) >= 12:
            break
        b = by_id[bid]
        if b["lat"]:
            top.append([bid, buildings.label(b["addr"]), n, b["places"], round(sum(b["lat"]) / len(b["lat"]), 5),
                        round(sum(b["lon"]) / len(b["lon"]), 5), None, buildings.short_label(b["addr"]),
                        buildings.street_name(b["muni"].most_common(1)[0][0]), None])
    return {
        "vut": len(vut),
        "vut_places": sum(x.get("tot_gen_places") or 0 for x in vut),
        "vut_rooms": sum(1 for x in vut if x.get("group") == "Por habitaciones"),
        "other": dict(Counter(buildings.KIND.get(x.get("objects_type_id"), "?") for x in recs
                              if x.get("objects_type_id") != buildings.VUT)),
        "buildings_with_vut": len(bids),
        "vut_in_buildings_10plus": sum(n for n in bids.values() if n >= 10),
        "buildings_10plus": sum(1 for n in bids.values() if n >= 10),
        "by_year": {y: years[y] for y in sorted(years) if y},
        "top_buildings": top,
    }


def ine_region(I):
    """Andalucía totals from the INE's eight provinces."""
    P = I.get("provinces") or {}
    homes = sum(p.get("homes") or 0 for p in P.values())
    census = sum(100 * p["homes"] / p["pct"] for p in P.values() if p.get("homes") and p.get("pct"))
    return {"homes": homes, "pct": round(100 * homes / census, 2)} if census else None


def ine_census_homes(im):
    """All census homes in a municipality, from the INE's tourist-home count and its % of all homes."""
    return round(100 * im["homes"] / im["pct"]) if im and im.get("homes") and im.get("pct") else None


def subarea_rows(kind, recs, muni_homes=None, ine_by_key=None, census=False):
    """Where the licences are: by municipality (province) or by locality / postcode (city)."""
    vut = [x for x in recs if x.get("objects_type_id") == buildings.VUT]
    if kind == "municipality":
        keyf = lambda x: buildings.street_name(x.get("municipalities"))
    else:  # by postcode, named after the most common locality recorded in it
        keyf = lambda x: (x.get("postal_code") or "").strip() or "—"
    c, pl, loc = Counter(), Counter(), defaultdict(Counter)
    for x in vut:
        k = keyf(x)
        c[k] += 1
        pl[k] += x.get("tot_gen_places") or 0
        if x.get("locality"):
            loc[k][buildings.street_name(x["locality"])] += 1
    rows = [{"name": k, "vut": n, "places": pl[k], **({"locality": loc[k].most_common(1)[0][0]} if loc[k] else {})}
            for k, n in c.most_common()]
    if kind == "municipality" and (muni_homes or census):
        for r in rows:
            h = ine_census_homes((ine_by_key or {}).get(buildings.muni_key(r["name"]))) if census \
                else muni_homes.get(buildings.muni_key(r["name"]))
            if h:
                r.update(homes=h, vut_share=round(100 * r["vut"] / h, 1))
            im = (ine_by_key or {}).get(buildings.muni_key(r["name"]))
            if im and im.get("homes") is not None:
                r.update(ine_homes=int(im["homes"]), ine_pct=im.get("pct"))
    return rows


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx, syy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else 0.0


_SECTIONS = None   # INE census districts are NOT the council's 11 districts: we name them by their main barrios


MIN_RENTED_BARRIO = 40   # rented flats behind a barrio's rent figure (both years), below this we don't show it
RENT_BANDS = [(0, 2), (2, 5), (5, 8), (8, 20), (20, 100)]   # % of homes registered as tourist flats; 8 = council's limit


def serpavi_barrios(barrios, parcel_pts):
    """Median rent €/m² (flats) per barrio for 2015 and the latest year, from census sections (Housing Ministry, SERPAVI).
    Each section goes to the barrio holding most of its homes; barrio rent = mean of its sections weighted by rented flats,
    using only sections with data in both years. Returns ({barrio_id: {...}}, {year: city €/m²}, (first, last))."""
    global _SECTIONS
    try:
        rent = serpavi.ensure(CACHE)
    except Exception as e:
        print("serpavi skipped:", e)
        return {}, {}, None
    _SECTIONS = _SECTIONS or geo.Sections(geo.ensure_sections(CACHE))
    sec_bar = defaultdict(Counter)
    for la, lo, dw in parcel_pts.get("MALAGA", ()):
        _, sec = _SECTIONS.lookup(la, lo)
        if sec:
            sec_bar[sec][barrios.lookup(la, lo)[0]] += dw
    years = sorted({y for v in rent.values() for y in v})
    y0, y1 = ("2015" if "2015" in years else years[0]), years[-1]
    agg = defaultdict(lambda: [0.0, 0, 0.0, 0])
    for cusec, v in rent.items():
        n = int(cusec[5:7]) * 1000 + int(cusec[7:10])
        if n not in sec_bar or y0 not in v or y1 not in v:
            continue
        a = agg[sec_bar[n].most_common(1)[0][0]]
        a[0] += v[y0][0] * v[y0][1]; a[1] += v[y0][1]; a[2] += v[y1][0] * v[y1][1]; a[3] += v[y1][1]
    out = {}
    for bid, (s0, w0, s1, w1) in agg.items():
        if bid is None or min(w0, w1) < MIN_RENTED_BARRIO:
            continue
        r0, r1 = s0 / w0, s1 / w1
        out[bid] = {"rent0": round(r0, 2), "rent1": round(r1, 2), "rent_growth": round(100 * (r1 / r0 - 1), 1), "rented": w1}
    city = {}
    for y in years:
        w = sum(v[y][1] for v in rent.values() if y in v)
        city[y] = round(sum(v[y][0] * v[y][1] for v in rent.values() if y in v) / w, 2) if w else None
    return out, city, (y0, y1)


def rent_comparison(A, recs_a, out, parcel_pts, I, ine_by_key, muni_homes, barrios=None, brows=None, city_rent=None, ryears=None):
    """Tourist-flat share vs rent growth since 2015 (INE IPVA). Málaga: by district; province: by municipality;
    Marbella: its own figure against the province's municipalities."""
    global _SECTIONS
    R = ine.load_rent(CACHE)
    if not R:
        return None
    growth = lambda idx: (lambda y: {"from": "2015", "to": y, "growth": round(idx[y] / idx["2015"] * 100 - 100, 1)})(
        max(idx)) if idx.get("2015") else None
    if A["slug"] == "malaga" and brows is not None and city_rent:
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
        rows = [r for r in brows if r.get("rent_growth") is not None and r.get("vut_share") is not None]
        bands = []
        for lo, hi in RENT_BANDS:
            g = [r for r in rows if lo <= r["vut_share"] < hi]
            if g:
                bands.append({"lo": lo, "hi": hi, "n": len(g), "growth": med([r["rent_growth"] for r in g]),
                              "rent0": med([r["rent0"] for r in g]), "rent1": med([r["rent1"] for r in g])})
        reg_year = Counter((x.get("registration_date") or "")[:4] for x in recs_a if x.get("objects_type_id") == buildings.VUT)
        timeline, cum = [], 0
        for y in sorted(city_rent):
            cum = sum(n for yy, n in reg_year.items() if yy and yy <= y)
            timeline.append({"year": y, "vut": cum, "rent": city_rent[y]})
        y0, y1 = ryears
        ipva = R["munis"].get("29067")
        return {"level": "barrio_bands", "years": [y0, y1], "bands": bands, "n_barrios": len(rows), "timeline": timeline,
                "city_growth": round(100 * (city_rent[y1] / city_rent[y0] - 1), 1),
                **({"ipva_growth": growth(ipva["index"])["growth"]} if ipva and growth(ipva["index"]) else {}),
                "corr": round(_pearson([r["vut_share"] for r in rows], [r["rent_growth"] for r in rows]), 2)}
    rows = []
    for code, d in R["munis"].items():
        g = growth(d["index"])
        k = buildings.muni_key(d["name"])
        if not g or not muni_homes.get(k):
            continue
        vut = sum(1 for x in recs_a if x.get("objects_type_id") == buildings.VUT and buildings.muni_key(x.get("municipalities")) == k) \
            if A["kind"] == "province" else None
        im = ine_by_key.get(k) or {}
        rows.append({"id": code, "name": d["name"], "homes": muni_homes[k], "ine_pct": im.get("pct"), "rent_growth": g["growth"],
                     "years": [g["from"], g["to"]], **({"vut": vut, "vut_share": round(100 * vut / muni_homes[k], 1)} if vut is not None else {})})
    if A["kind"] == "province":
        return {"level": "municipality", "rows": rows}
    own = next((r for r in rows if buildings.muni_key(r["name"]) == buildings.muni_key(A["name"]["es"])), None)
    return {"level": "own", "own": own, "rows": rows} if own else None


# Plain-spreadsheet copy of each area's sub-area table, for journalists (linked from /metodologia#prensa).
CSV_COLS = [("name", "zona"), ("vut", "viviendas_turisticas_registradas"), ("places", "plazas"), ("homes", "viviendas_catastro"),
            ("vut_share", "pct_viviendas_turisticas"), ("listings", "anuncios_airbnb"), ("valid", "anuncios_numero_valido"),
            ("no_number", "anuncios_sin_numero"), ("bad_number", "anuncios_numero_fuera_registro"), ("shared", "anuncios_licencia_compartida"),
            ("exempt", "anuncios_posiblemente_exentos"), ("not_valid_pct", "pct_anuncios_sin_numero_valido"),
            ("ine_pct", "pct_viviendas_anunciadas_ine"), ("rent1", "alquiler_eur_m2"), ("rent_growth", "subida_alquiler_desde_2015_pct")]


BUILDING_CSV_COLS = [("name", "edificio"), ("place", "barrio_o_municipio"), ("vut", "viviendas_turisticas"),
                     ("places", "plazas"), ("homes", "viviendas_catastro"), ("vut_share", "pct_viviendas_turisticas")]


def write_csv(path, rows, columns=CSV_COLS):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = [(k, h) for k, h in columns if any(r.get(k) is not None for r in rows)]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:   # BOM so Excel reads the accents
        cw = csv.writer(fh)
        cw.writerow([h for _, h in cols])
        for r in sorted(rows, key=lambda r: -(r.get("vut") or 0)):
            cw.writerow(["" if r.get(k) is None else r[k] for k, _ in cols])


def cmd_build(a):
    meta = json.load(open(os.path.join(REG_DIR, "register_meta.json")))
    recs = register.load_records(REG_DIR)
    index, mx = register.build_index(recs), register.max_issued(recs)
    del recs
    official = load_official()
    snaps = {c: snapshot.latest_local(CACHE, c) for c in LISTING_CITIES}
    snap_date = snaps["malaga"][0]
    BAR = {A["slug"]: city_barrios(A["slug"]) for A in AREAS if A["barrios"]}

    # ---- dwellings per building (Catastro): indicative "share of homes"
    homes, muni_homes, parcel_pts, muni_prov = {}, Counter(), defaultdict(list), {}
    for code, c in catastro.load_cached(CACHE).items():
        mk = buildings.muni_key(c["name"])
        muni_prov[mk] = code[:2]
        for ref, (dw, la, lo, _res) in c["parcels"].items():
            if dw:
                homes[ref] = dw
                muni_homes[mk] += dw
                parcel_pts[mk].append((la, lo, dw))

    # ---- INE: advertised tourist homes per municipality (all platforms, de-duplicated)
    I = ine.load(CACHE) or {"munis": {}, "province": {}, "period": None}
    ine_by_key = {buildings.muni_key(m["name"]): m for m in I["munis"].values()}

    # ---- tourist accommodation in the search province, grouped into buildings
    prov = [x for rs in index.values() for x in rs if (x.get("provinces") or "").upper() in SEARCH_PROVINCES
            and x.get("objects_type_id") in register.TOURIST_ACCOMMODATION_TYPES]
    agg = buildings.Aggregator()
    agg_ids = {id(x): agg.add(x) for x in prov}

    # ---- Airbnb listings, per city (Inside Airbnb snapshot + our live checks)
    LIST = {}
    for A in AREAS:
        if A["listings"]:
            d_, p_ = snaps[A["slug"]]
            rows_ = sample.load_snapshot(p_)
            LIST[A["slug"]] = (rows_, d_, *classify_listings(index, official, mx, d_, rows_, state.load(state_path(A["slug"])), A["home"]))

    os.makedirs(SITE_DATA, exist_ok=True)

    def w(name, obj):
        p = os.path.join(SITE_DATA, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    barrio_rent, city_rent, ryears = serpavi_barrios(BAR["malaga"], parcel_pts)   # SERPAVI sections: Málaga only for now
    areas_out, hist_areas, hist_listings, listing_stats = [], {}, {}, None
    for A in AREAS:
        barrios = BAR.get(A["slug"])
        _rows, a_snap, out, removed, by_key = LIST.get(A["slug"], (None, None, [], 0, {}))
        recs_a = [x for x in prov if A["match"](x)]
        vut_a = [x for x in recs_a if x.get("objects_type_id") == buildings.VUT]
        ids_a = {agg_ids[id(x)] for x in recs_a}
        reg = registered_summary(recs_a, agg_ids, agg)
        census = A["kind"] == "region" or A.get("census")   # "% of homes" from the INE census, not the Catastro
        mks = set() if census else {m for m in muni_homes if muni_prov.get(m) == CATASTRO_PROVINCE} if A["kind"] == "province" \
            else {buildings.muni_key(x.get("municipalities")) for x in recs_a}
        pcode = A["ine"][5:] if A["ine"].startswith("prov:") else None
        area_homes = sum(ine_census_homes(m) or 0 for c_, m in I["munis"].items() if pcode is None or c_[:2] == pcode) if census \
            else sum(muni_homes[m] for m in mks)
        if area_homes:
            reg.update(homes=area_homes, vut_share=round(100 * reg["vut"] / area_homes, 2))
        im = I["province"] if A["ine"] == "province" else ine_region(I) if A["ine"] == "region" \
            else (I.get("provinces") or {}).get(pcode) if pcode else I["munis"].get(A["ine"])
        if im and im.get("homes") is not None:
            reg.update(ine_homes=int(im["homes"]), ine_pct=im.get("pct"), ine_period=I["period"])
        for t in reg["top_buildings"]:
            t[6] = homes.get(t[0])
            if A["barrios"]:
                t[9] = barrios.lookup(t[4], t[5])[1]
        write_csv(os.path.join(SITE_DATA, A["slug"], "edificios.csv"), [
            {"name": t[7], "place": t[9] or t[8], "vut": t[2], "places": t[3], "homes": t[6],
             "vut_share": round(100 * t[2] / t[6], 1) if t[6] else None} for t in reg["top_buildings"] if t[2] >= 10],
            BUILDING_CSV_COLS)
        reg["top_buildings"] = reg["top_buildings"][:200]
        summary = {"slug": A["slug"], "registered": reg, "has_listings": A["listings"], "cap": A.get("cap"),
                   **({"snapshot_date": a_snap} if a_snap else {})}
        hexg = geo.Hex(A["hex_m"])

        # buildings layer
        w(f"{A['slug']}/buildings.json", {
            "fields": ["lat", "lon", "label", "vut", "places", "other", "since", "other_types", "id", "homes"],
            "rows": [] if A["kind"] == "region" else agg.rows(lambda b: b["id"] in ids_a, homes)})   # region: hexes only (size)

        # hexes: licence density, plus the problem share where we have listings
        hx = defaultdict(Counter)
        for x in vut_a:
            if x.get("lat") is not None:
                hx[hexg.cell(x["lat"], x["lon"])]["reg"] += 1
        for m in mks:
            for la, lo, dw in parcel_pts.get(m, ()):
                hx[hexg.cell(la, lo)]["homes"] += dw
        if A["listings"]:
            for o in out:
                c = hexg.cell(o["lat"], o["lon"])
                hx[c]["n"] += 1
                hx[c]["nv"] += o["verdict"] == "NOT_VALID"
                hx[c]["ent"] += o["entire"]
        hfeats = []
        for (q, r_), c in hx.items():
            p = {"reg": c["reg"]}
            if c["homes"]:
                p["homes"] = c["homes"]
                if c["homes"] >= MIN_HOMES_SHARE:
                    p["share"] = round(100 * c["reg"] / c["homes"], 1)
                    if A["listings"]:
                        p["ashare"] = round(100 * c["ent"] / c["homes"], 1)
            if c["n"] >= MIN_LISTINGS_HEX:
                p.update(n=c["n"], nv=c["nv"], pct=round(100 * c["nv"] / c["n"]))
            if c["reg"] or "n" in p:
                hfeats.append({"type": "Feature", "properties": p,
                               "geometry": {"type": "Polygon", "coordinates": [hexg.polygon(q, r_)]}})
        w(f"{A['slug']}/hex.geojson", {"type": "FeatureCollection", "features": hfeats})
        if A["listings"]:
            w(f"{A['slug']}/dots.json", listing_dots(out, hexg))
        # small dot-density preview for cards and teasers: hex centres [lon, lat, flats, % not valid or -1]
        pv = []
        for f in hfeats:
            ring = f["geometry"]["coordinates"][0][:6]
            p = f["properties"]
            if p["reg"] or "pct" in p:
                pv.append([round(sum(c[0] for c in ring) / 6, 4), round(sum(c[1] for c in ring) / 6, 4), p["reg"], p.get("pct", -1)])
        w(f"{A['slug']}/preview.json", pv)

        if A["listings"]:
            summary["listings"] = listing_summary(out, removed, by_key, vut_a)
            if A["slug"] == "malaga":
                listing_stats = summary["listings"]
            hist_listings[A["slug"]] = {k: summary["listings"][k] for k in ("listings", "live_checked")} | {
                "not_valid": summary["listings"]["verdicts"]["NOT_VALID"], "snapshot": a_snap}
            ent = sum(1 for o in out if o["entire"])
            summary["listings"].update(entire=ent, **({"entire_share": round(100 * ent / area_homes, 2)} if area_homes else {}))

        if A["barrios"]:
            bstats = defaultdict(Counter)
            for o in out:
                bid, _ = barrios.lookup(o["lat"], o["lon"])
                bstats[bid]["n"] += 1
                bstats[bid]["entire"] += o["entire"]
                bstats[bid][o["verdict"]] += 1
                bstats[bid][o["cat"]] += 1
            breg = defaultdict(Counter)
            for x in vut_a:
                if x.get("lat") is not None:
                    bid, _ = barrios.lookup(x["lat"], x["lon"])
                    breg[bid]["vut"] += 1
                    breg[bid]["places"] += x.get("tot_gen_places") or 0
            for m in mks:
                for la, lo, dw in parcel_pts.get(m, ()):
                    bid, _ = barrios.lookup(la, lo)
                    breg[bid]["homes"] += dw
            feats, rows_ = [], []
            for f in barrios.features:
                bid = f["properties"]["id"]
                s, rg = bstats.get(bid, Counter()), breg.get(bid, Counter())
                p = {"id": bid, "name": f["properties"]["name"], "listings": s["n"], "vut": rg["vut"], "places": rg["places"]}
                if rg["homes"]:
                    p["homes"] = rg["homes"]
                    if rg["homes"] >= MIN_HOMES_BARRIO:
                        p["vut_share"] = round(100 * rg["vut"] / rg["homes"], 1)
                        p["airbnb_share"] = round(100 * s["entire"] / rg["homes"], 1)
                p["airbnb_entire"] = s["entire"]
                if A["slug"] == "malaga" and bid in barrio_rent:
                    p.update(barrio_rent[bid])
                if s["n"] >= MIN_LISTINGS_AREA:
                    p.update(not_valid_pct=round(100 * s["NOT_VALID"] / s["n"], 1),
                             no_number=s["NO_CODE_IN_SCOPE"],
                             bad_number=s["NOT_IN_REGISTER"] + s["MALFORMED"] + s["FOUND_OTHER_MUNICIPALITY"] + s["CANCELLED_OFFICIAL"],
                             shared=s["VALID_CODE_SHARED"], valid=s["VALID"], exempt=s["POSSIBLY_EXEMPT"])
                feats.append({**f, "properties": p})
                if p["vut"] or p["listings"]:
                    rows_.append(p)
            w(f"{A['slug']}/barrios.geojson", {"type": "FeatureCollection", "features": feats})
            summary["subareas"] = {"kind": "barrio", "rows": sorted(rows_, key=lambda p: -p["vut"])}
        else:
            summary["subareas"] = {"kind": A["subareas"], "rows": subarea_rows(A["subareas"], recs_a, muni_homes, ine_by_key,
                                                                              census=census)}

        if A["slug"] in SAMPLE_TOWNS and os.path.exists(sample_path(A["slug"])):
            summary["sample"] = sample_summary(sample_path(A["slug"]), index, official, mx, A["home"])
            areas_extra = {"sample_pct": summary["sample"]["not_valid_pct"], "sample_checked": summary["sample"]["checked"]}
        else:
            areas_extra = {}
        rent = rent_comparison(A, recs_a, out, parcel_pts, I, ine_by_key, muni_homes, barrios,
                               summary["subareas"]["rows"] if A["barrios"] else None, city_rent, ryears)
        if rent:
            summary["rent"] = rent
        w(f"{A['slug']}/summary.json", summary)
        write_csv(os.path.join(SITE_DATA, A["slug"], "zonas.csv"), summary["subareas"]["rows"])
        hist_areas[A["slug"]] = reg["vut"]
        areas_out.append({k: A[k] for k in ("slug", "name", "kind", "center", "zoom", "hex_m")} | {
            "has_listings": A["listings"], "has_barrios": A["barrios"], "cap": A.get("cap"), "census": bool(census), "vut": reg["vut"], "vut_places": reg["vut_places"],
            "homes": reg.get("homes"), "vut_share": reg.get("vut_share"), "ine_homes": reg.get("ine_homes"),
            "ine_pct": reg.get("ine_pct"), "ine_period": reg.get("ine_period"), **areas_extra,
            **({"listings": summary["listings"]["listings"], "not_valid": summary["listings"]["verdicts"]["NOT_VALID"]}
               if A["listings"] else {})})

    built = now()
    w("areas.json", {"built_at": built, "areas": areas_out})

    # ---- history (one point per build day)
    hp = os.path.join(SITE_DATA, "history.json")
    hist = json.load(open(hp)) if os.path.exists(hp) else []
    day = built[:10]
    L = listing_stats
    hist = [h for h in hist if h["date"] != day] + [{
        "date": day, "listings": L["listings"], "not_valid": L["verdicts"]["NOT_VALID"], "valid": L["verdicts"]["VALID"],
        "shared": L["verdicts"]["VALID_CODE_SHARED"], "registered_vut": L["registered_vut"], "snapshot": snap_date,
        "live_checked": L["live_checked"], "areas_vut": hist_areas, "areas_listings": hist_listings}]
    w("history.json", hist)
    w("meta.json", {"built_at": built, "register_lastUpdateData": meta["lastUpdateData"],
                    "register_downloaded_at": meta["downloaded_at"], "snapshot_date": snap_date,
                    "live_max_age_days": LIVE_MAX_AGE_DAYS, "min_listings_area": MIN_LISTINGS_AREA,
                    "min_listings_hex": MIN_LISTINGS_HEX, "location_threshold_m": classify.LOCATION_THRESHOLD_M})

    # ---- function data: register lookup (all Andalucía) + search index (the province)
    os.makedirs(FN_DATA, exist_ok=True)
    idx = {}
    for k, rs in index.items():
        x = rs[0]
        if x.get("objects_type_id") not in register.TOURIST_ACCOMMODATION_TYPES:
            continue
        idx[k] = [x.get("municipalities"), round(x["lat"], 5) if x.get("lat") else None,
                  round(x["lon"], 5) if x.get("lon") else None, (x.get("group") or "")[:1],
                  (x.get("registration_date") or "")]
    usage = {k: shared_hosts(v) for _r, _d, _o, _rm, bk in LIST.values() for k, v in bk.items() if shared_hosts(v) > 1}   # hosts per shared code
    with gzip.open(os.path.join(FN_DATA, "lookup.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump({"built_at": built, "register_lastUpdateData": meta["lastUpdateData"], "max_issued":
                   {f"{p}/{v}": n_ for (p, v), n_ in mx.items()}, "codes": idx, "shared": usage,
                   # listings with a minimum stay of 60+ nights (seasonal lets): the advert page doesn't show it
                   "long_stay": sorted(r["id"] for rs, *_ in LIST.values() for r in rs if int(r["minimum_nights"] or 0) >= 60),
                   # date only: the source note describes a private document and stays in the private state
                   "cancelled": {k: {"date": v.get("cancel_date")} for k, v in official.items()
                                 if v.get("status") == "cancelled"}},
                  fh, ensure_ascii=False, separators=(",", ":"))

    clean = lambda v: " ".join(str(v).split()) if v not in (None, "", "-") else ""
    srows = []
    MUNI_AREA = {A["home"]: A["slug"] for A in AREAS if A.get("home") and A["barrios"]}   # barrio names in search results
    PROV_CODE = {"ALMERÍA": "AL", "CÁDIZ": "CA", "CÓRDOBA": "CO", "GRANADA": "GR", "HUELVA": "HU", "JAÉN": "JA",
                 "MÁLAGA": "MA", "SEVILLA": "SE"}   # the register's own province codes (VUT/MA/…, VUT/HU/…)
    for x in prov:
        srows.append([x["registration_code"], buildings.KIND.get(x.get("objects_type_id"), "?"), (x.get("group") or "")[:1],
                      buildings.street_name(x.get("municipalities")), buildings.street_name(x.get("road_name")),
                      clean(x.get("km_num")), clean(x.get("block")), clean(x.get("portal")), clean(x.get("staircase")),
                      clean(x.get("floor")), clean(x.get("door")), clean(x.get("domicile_complement"))[:90],
                      clean(x.get("postal_code")), buildings.street_name(x.get("locality")), x.get("tot_gen_places") or 0,
                      (x.get("registration_date") or "")[:8],
                      round(x["lat"], 5) if x.get("lat") is not None else None,
                      round(x["lon"], 5) if x.get("lon") is not None else None, agg_ids[id(x)],
                      *((lambda b: [b[1], b[0]])(BAR[MUNI_AREA[x["municipalities"]]].lookup(x["lat"], x["lon"]))
                        if x.get("municipalities") in MUNI_AREA and x.get("lat") is not None else [None, None]),
                      PROV_CODE.get((x.get("provinces") or "").upper())])
    srows.sort(key=lambda r: (r[3], r[4], r[5]))
    with gzip.open(os.path.join(FN_DATA, "search.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump({"built_at": built, "register_lastUpdateData": meta["lastUpdateData"],
                   "fields": ["code", "kind", "group", "muni", "street", "num", "block", "portal", "stair", "floor", "door",
                              "complement", "postcode", "locality", "places", "registered", "lat", "lon", "building",
                              "barrio", "barrio_id", "prov"],
                   "rows": srows}, fh, ensure_ascii=False, separators=(",", ":"))

    print({k: v["not_valid"] for k, v in hist_listings.items()}, json.dumps(L["verdicts"]), "| areas", {a["slug"]: a["vut"] for a in areas_out},
          "| buildings", len(agg.b), "| search rows", len(srows), "| live-based", L["live_checked"])


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("refresh").set_defaults(f=cmd_refresh)
    p = sp.add_parser("recheck")
    p.add_argument("--budget", type=int, default=1500)
    p.add_argument("--city", default="malaga", help="which city's listings to re-check (malaga, sevilla)")
    p.add_argument("--evidence", action="store_true")
    p.add_argument("--max-minutes", type=float, default=0, help="stop re-checking after this long (0 = no limit)")
    p.set_defaults(f=cmd_recheck)
    p = sp.add_parser("sample")
    p.add_argument("--town", required=True, choices=sorted(SAMPLE_TOWNS))
    p.add_argument("--n", type=int, default=1000, help="sample size")
    p.add_argument("--max-minutes", type=float, default=0)
    p.add_argument("--refresh-frame", action="store_true", help="rebuild the list of listings even if recent")
    p.set_defaults(f=cmd_sample)
    sp.add_parser("build").set_defaults(f=cmd_build)
    sp.add_parser("seed-state").set_defaults(f=cmd_seed_state)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    sys.exit(main())
