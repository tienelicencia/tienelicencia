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
import re
import sqlite3
import sys
import time
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
from rta_audit import index as pindex  # noqa: E402
PINDEX_CFG = pindex.load_config()
from rta_audit import aragon, baleares, boundaries, buildings, canarias, catastro, catalunya, classify, codes, cyl, euskadi, geo, ine, madrid, murcia, valencia, live, register, sample, serpavi, snapshot, state  # noqa: E402

PIPE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(PIPE)
CACHE = os.environ.get("RTA_CACHE", os.path.join(PIPE, "cache"))
REG_DIR = os.path.join(CACHE, "register")
STATE_DIR = os.environ.get("TL_STATE") or os.path.join(REPO, "state")   # CI checks the private state repo out here; locally TL_STATE can point at a clone
SITE_DATA = os.path.join(REPO, "site", "data")
FN_DATA = os.path.join(REPO, "netlify", "functions", "data")
MIN_LISTINGS_AREA = 15   # suppress % for barrios with fewer listings
MIN_LISTINGS_HEX = 10    # don't draw problem hexes with fewer listings (privacy + noise)
MIN_HOMES_SHARE = 30     # don't give a "% of homes" for map areas with fewer dwellings (noise)
MIN_HOMES_BARRIO = 100   # same for barrios in rankings
LIVE_MAX_AGE_DAYS = 45   # older live checks fall back to snapshot text
RECHECK_CYCLE_DAYS = 30  # "--budget auto": each city's listings re-checked about once a month
RECHECK_MAX = 1500       # …at most this many per city per run (~4 h at 9–10 s each)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_path(city):
    """Live checks per city, in separate files so each city's re-check job commits its own. An area inside another
    (Palma in Mallorca) reads its parent's: its listings are re-checked once, under the parent."""
    city = next((A["parent"] for A in AREAS if A["slug"] == city and A.get("parent")), city)
    return os.path.join(STATE_DIR, "listings_live.json" if city == "malaga" else f"listings_live_{city}.json")


# ------------------------------------------------------------------ refresh
def cmd_refresh(a):
    """Each source on its own: one being down never stops the others (the build uses the cached copies). Catastro has a
    time budget so a first full download can't run past the job's limit; it carries on where it stopped next run."""
    t0, out = time.monotonic(), {}

    def step(name, fn):
        try:
            out[name] = fn()
        except Exception as e:  # noqa: BLE001
            print(f"{name}: FAILED, using the cached copy if there is one: {e}", flush=True)
        print(f"{name}: done at {round((time.monotonic() - t0) / 60, 1)} min", flush=True)

    step("register", lambda: register.fetch(REG_DIR))
    for c in SNAPSHOT_CITIES:
        step(f"snapshot {c}", lambda c=c: snapshot.update(CACHE, c))
    step("catalunya", lambda: catalunya.fetch(CACHE))   # Barcelona: Generalitat register (province) + Ajuntament HUT file
    step("baleares", lambda: baleares.fetch(CACHE))     # Mallorca: the Consell de Mallorca's two registers
    step("madrid", lambda: madrid.fetch(CACHE))         # Madrid: the Comunidad's register and the city's address points
    step("aragon", lambda: aragon.fetch(CACHE))         # Zaragoza: the Registro de Turismo de Aragón (numbers only)
    step("murcia", lambda: murcia.fetch(CACHE))         # Murcia: the ITREM's register listings
    step("cyl", lambda: cyl.fetch(CACHE))               # Valladolid: the Registro de Turismo de Castilla y León
    step("canarias", lambda: canarias.fetch(CACHE))     # Las Palmas: the Registro General Turístico de Canarias
    step("valencia", lambda: valencia.fetch(CACHE))     # Valencia: the Generalitat's register of tourist flats
    step("euskadi", lambda: euskadi.fetch(CACHE))       # Bilbao, Donostia: the Basque register (REATE) and city address points
    step("barrios", lambda: geo.ensure_barrios(CACHE))
    step("boundaries", lambda: boundaries.fetch(CACHE))   # other cities' barrios / districts (councils' open data)
    step("ine", lambda: ine.fetch(CACHE))               # tourist homes advertised on the main platforms (about twice a year)
    step("ine rent", lambda: ine.fetch_rent(CACHE))     # rent index by district / municipality (yearly)
    step("sections", lambda: geo.ensure_sections(CACHE))
    # dwellings per building, for "tourist flats as a share of homes" (about one release a year)
    deadline = time.time() + a.catastro_minutes * 60
    step("catastro málaga", lambda: catastro.ensure(CACHE, catastro.municipalities(CATASTRO_PROVINCE), CATASTRO_PROVINCE, deadline=deadline))
    for prov_, name_ in CATASTRO_EXTRA:   # other listing cities: just the municipality
        step(f"catastro {name_}", lambda p=prov_, n=name_: catastro.ensure(
            CACHE, [m for m in catastro.municipalities(p) if m[1].strip().upper() == n], p, deadline=deadline))
    step("catastro mallorca", lambda: catastro.ensure(CACHE, [m for m in catastro.municipalities("07") if m[0] not in NOT_MALLORCA], "07",
                                                      deadline=deadline))
    m = out.get("register") or {}
    print("register", m.get("lastUpdateData"), "| snapshots", {k[9:]: v[0] for k, v in out.items() if k.startswith("snapshot") and v})


# ------------------------------------------------------------------ recheck
def cmd_recheck(a):
    date, rows = area_snapshot(next(A for A in AREAS if A["slug"] == a.city))
    ids = [r["id"] for r in rows]
    STATE = state_path(a.city)
    st = state.load(STATE)
    # "auto": enough to re-check every listing about once a month (RECHECK_CYCLE_DAYS), capped so a job stays well inside
    # the runner's time limit at ~9 s per listing
    budget = min(RECHECK_MAX, -(-len(ids) // RECHECK_CYCLE_DAYS)) if a.budget == "auto" else int(a.budget)
    print(f"{a.city}: {len(ids)} listings, checking {budget} this run")
    todo = state.due(st, ids, budget)
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
SAMPLE_DIR = os.path.join(STATE_DIR, "samples")
SAMPLE_TOWNS = {"marbella", "granada", "cordoba", "cadiz", "zaragoza", "murcia", "laspalmas", "alicante", "valladolid"}
FRAME_MAX_AGE_DAYS = 25   # rebuild the list of a town's listings each monthly run
SAMPLE_MAX_AGE_DAYS = 25  # …and re-check sampled listings whose last check is older than this


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


def parcel_locator(pts, home, max_m=250):
    """For towns outside Andalucía: a listing is in the town if it lies within max_m of one of its residential
    buildings (Catastro). Airbnb's map positions are shifted by up to ~150 m, so this keeps listings at the town's edge."""
    grid = defaultdict(list)
    for la, lo in pts:
        grid[(round(la * 200), round(lo * 200))].append((la, lo))   # ~500 m cells

    def locate(lat, lon):
        cy, cx = round(lat * 200), round(lon * 200)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if any(register.haversine_m(lat, lon, la, lo) <= max_m for la, lo in grid.get((cy + dy, cx + dx), ())):
                    return home
        return None
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
        if A.get("catastro"):   # outside Andalucía: the town's outline from its Catastro buildings
            prov_, code_, name_ = A["catastro"]
            parcels = catastro.ensure(CACHE, [(code_, name_)], prov_)[code_]
            pts = [(v[1], v[2]) for v in parcels.values() if v[3]]   # residential buildings
            locate = parcel_locator(pts, home)
        else:
            recs = register.load_records(REG_DIR)
            index = register.build_index(recs)
            del recs
            pts = [(x["lat"], x["lon"]) for rs in index.values() for x in rs if x.get("municipalities") == home and x.get("lat") is not None]
            locate = muni_locator(index)
        lats, lons = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
        q = lambda v, f: v[int(f * (len(v) - 1))]
        box = (q(lats, .002) - .004, q(lons, .002) - .004, q(lats, .998) + .004, q(lons, .998) + .004)
        print("town box", box, "from", len(pts), "register points")
        found, capped = airbnb_search.enumerate_box(box)
        inside = {k: v for k, v in found.items() if locate(v["lat"], v["lon"]) == home}
        S.update(frame_date=now(), frame=[[k, v["lat"], v["lon"]] for k, v in sorted(inside.items())], frame_found=len(found),
                 frame_outside=len(found) - len(inside), capped_areas=len(capped))
        json.dump(S, open(path, "w"), separators=(",", ":"))
        print(f"frame: {len(inside)} listings in {home} ({len(found) - len(inside)} outside, {len(capped)} capped areas)")
    # Fixed random order (hash of the id): the first N of the list are a simple random sample.
    order = sorted((r[0] for r in S["frame"]), key=lambda i: hashlib.sha1(i.encode()).hexdigest())[:a.n]
    def stale(c):
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(c["checked_at"].replace("Z", "+00:00"))).days >= SAMPLE_MAX_AGE_DAYS
        except (KeyError, ValueError, TypeError):
            return True
    todo = [i for i in order if i not in S["checks"] or stale(S["checks"][i])]
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


def wilson(k, n):
    """95% interval (Wilson) for k of n, in % to one decimal; None without data."""
    if not n:
        return None
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


MIN_SAMPLE_BARRIO = 30   # a barrio's share without a valid number from the random sample: only with this many checked in it


def sample_by_barrio(path, sm, barrios):
    """The live-checked sample split by barrio (each listing placed at its position in our list of the city's listings):
    {barrio id: Counter(n, NOT_VALID, …)}. A simple random sample of the city is also one of each barrio's listings."""
    loc = {r[0]: (r[1], r[2]) for r in json.load(open(path))["frame"]}
    out = defaultdict(Counter)
    for lid, (_cat, verdict) in zip(sm["_ids"], sm["_items"]):
        if lid in loc:
            bid, _ = barrios.lookup(*loc[lid])
            out[bid]["n"] += 1
            out[bid][verdict] += 1
    return out


def sample_summary(path, judge):
    """Town estimate from its live-checked random sample: shares with 95% intervals (Wilson)."""
    S = json.load(open(path))
    order = sorted((r[0] for r in S["frame"]), key=lambda i: __import__("hashlib").sha1(i.encode()).hexdigest())[:S.get("sample_n", 1000)]
    checked = [S["checks"][i] for i in order if i in S["checks"]]
    ok = [c for c in checked if c.get("live_status") == "ok"]
    ids = [i for i in order if i in S["checks"] and S["checks"][i].get("live_status") == "ok"]   # aligned with ok / items
    V, C, items = Counter(), Counter(), []
    for c in ok:
        cat = judge({"registration_raw": c.get("registration_raw"), "lat": c.get("lat"), "lon": c.get("lon"),
                     "room_type": c.get("room_type"), "property_type": c.get("property_type"), "min_nights": None})
        V[classify.VERDICT[cat]] += 1
        C[cat] += 1
        items.append((cat, classify.VERDICT[cat]))
    n = len(ok)
    return {"_items": items, "_ids": ids, "frame": len(S["frame"]), "frame_date": S["frame_date"][:10], "sample": len(order), "checked": n,
            "removed": sum(1 for c in checked if c.get("live_status") == "removed"),
            "last_checked": max((c["checked_at"] for c in checked), default=None),
            "verdicts": dict(V), "not_valid_pct": round(100 * V["NOT_VALID"] / n, 1) if n else None,
            "need_number_not_valid_pct": round(100 * V["NOT_VALID"] / (n - V["POSSIBLY_EXEMPT"]), 1) if n > V["POSSIBLY_EXEMPT"] else None,
            "not_valid_ci": wilson(V["NOT_VALID"], n),
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
# (Inside Airbnb covers the municipality only). Add a city here and in site/_redirects.
ANDALUSIA = {"ALMERÍA", "CÁDIZ", "CÓRDOBA", "GRANADA", "HUELVA", "JAÉN", "MÁLAGA", "SEVILLA"}
AREAS = [
    {"slug": "malaga", "name": {"es": "Málaga", "en": "Málaga"}, "kind": "city", "home": "MÁLAGA",
     "match": lambda x: x.get("municipalities") == "MÁLAGA", "listings": True, "barrios": True, "ine": "29067",
     "center": [-4.425, 36.722], "zoom": 13.2, "hex_m": 90, "subareas": "barrio", "cap": 8},
    {"slug": "sevilla", "name": {"es": "Sevilla", "en": "Seville"}, "kind": "city", "home": "SEVILLA",
     "match": lambda x: x.get("municipalities") == "SEVILLA", "listings": True, "barrios": True, "ine": "41091",
     "center": [-5.987, 37.389], "zoom": 13.2, "hex_m": 90, "subareas": "barrio", "cap": 10},
    # Catalonia: register from the Generalitat (numbers) + Ajuntament (coordinates); see rta_audit/catalunya.py
    {"slug": "barcelona", "name": {"es": "Barcelona", "en": "Barcelona"}, "kind": "city", "home": "BARCELONA", "region": "catalunya",
     "match": lambda x: x.get("municipalities") == "BARCELONA", "listings": True, "barrios": True, "ine": "08019",
     "center": [2.165, 41.392], "zoom": 13, "hex_m": 90, "subareas": "barrio"},
    # Mallorca: the whole island as one area (municipalities as its sub-areas); see rta_audit/baleares.py
    {"slug": "mallorca", "name": {"es": "Mallorca", "en": "Mallorca"}, "kind": "island", "region": "baleares",
     "match": lambda x: (x.get("provinces") or "") == "ILLES BALEARS", "listings": True, "barrios": True, "ine": "mallorca",
     "center": [2.99, 39.61], "zoom": 9.3, "hex_m": 200, "subareas": "municipality"},
    # Palma: the municipality on its own, with its barrios. Its listings and live checks are Mallorca's, filtered to Palma
    # ("parent"): classified once with the whole island (shared licences across the island count) and re-checked under mallorca
    {"slug": "palma", "name": {"es": "Palma", "en": "Palma"}, "kind": "city", "region": "baleares", "parent": "mallorca", "ia": "mallorca",
     "ia_muni": "Palma de Mallorca", "home": "PALMA", "match": lambda x: (x.get("provinces") or "") == "ILLES BALEARS" and x.get("municipalities") == "PALMA",
     "listings": True, "barrios": True, "barrios_file": "boundaries/palma.geojson", "ine": "07040",
     "center": [2.65, 39.575], "zoom": 12.8, "hex_m": 90, "subareas": "barrio"},
    # Comunidad de Madrid: showing the number isn't required there (see rta_audit/madrid.py): same figures, different wording
    {"slug": "madrid", "name": {"es": "Madrid", "en": "Madrid"}, "kind": "city", "region": "madrid", "home": "MADRID",
     "match": lambda x: x.get("municipalities") == "MADRID" and x.get("provinces") == "MADRID", "listings": True, "barrios": True,
     "ine": "28079", "center": [-3.7035, 40.4169], "zoom": 12.6, "hex_m": 90, "subareas": "barrio"},
    # Comunitat Valenciana: the Generalitat's register; see rta_audit/valencia.py
    {"slug": "valencia", "name": {"es": "Valencia", "en": "Valencia"}, "kind": "city", "region": "valencia", "home": "VALENCIA",
     "match": lambda x: x.get("municipalities") == "VALENCIA" and x.get("provinces") == "VALENCIA", "listings": True, "barrios": True,
     "ine": "46250", "center": [-0.376, 39.47], "zoom": 13, "hex_m": 90, "subareas": "barrio"},
    # Basque Country: one Inside Airbnb file (Euskadi) for both cities; see rta_audit/euskadi.py
    {"slug": "bilbao", "name": {"es": "Bilbao", "en": "Bilbao"}, "kind": "city", "region": "euskadi", "ia": "euskadi", "ia_muni": "Bilbao", "home": "Bilbao",
     "match": lambda x: euskadi.muni(x.get("municipalities")) == "BILBAO", "listings": True, "barrios": True,
     "barrios_file": "euskadi/bilbao_barrios.geojson", "ine": "48020", "census": True,
     "center": [-2.935, 43.262], "zoom": 13.2, "hex_m": 90, "subareas": "barrio"},
    {"slug": "donostia", "name": {"es": "San Sebastián", "en": "San Sebastián"}, "kind": "city", "region": "euskadi", "ia": "euskadi",
     "ia_muni": "Donostia / San Sebastián", "home": "Donostia / San Sebastián", "match": lambda x: euskadi.muni(x.get("municipalities")) == "DONOSTIASANSEBASTIAN",
     "listings": True, "barrios": True, "barrios_file": "euskadi/donostia_barrios.geojson", "ine": "20069", "census": True,
     "center": [-1.98, 43.313], "zoom": 13.4, "hex_m": 90, "subareas": "barrio"},
    # No Inside Airbnb data: our own random sample of each city's listings, live-checked (cmd_sample); outline from the Catastro.
    # Barrios (or districts) from each council's open data (rta_audit/boundaries.py); without the file: postcodes
    {"slug": "zaragoza", "name": {"es": "Zaragoza", "en": "Zaragoza"}, "kind": "city", "region": "aragon", "home": "ZARAGOZA",
     "match": lambda x: x.get("municipalities") == "ZARAGOZA" and x.get("provinces") == "ZARAGOZA", "listings": False, "barrios": True, "barrios_file": "boundaries/zaragoza.geojson",
     "catastro": ("50", "50900", "ZARAGOZA"), "ine": "50297", "center": [-0.889, 41.65], "zoom": 12.6, "hex_m": 90, "subareas": "barrio"},
    {"slug": "murcia", "name": {"es": "Murcia", "en": "Murcia"}, "kind": "city", "region": "murcia", "home": "MURCIA",
     "match": lambda x: x.get("municipalities") == "MURCIA" and x.get("provinces") == "MURCIA", "listings": False, "barrios": True, "barrios_file": "boundaries/murcia.geojson",
     "catastro": ("30", "30030", "MURCIA"), "ine": "30030", "center": [-1.13, 37.985], "zoom": 12.6, "hex_m": 90, "subareas": "barrio"},
    {"slug": "alicante", "name": {"es": "Alicante", "en": "Alicante"}, "kind": "city", "region": "valencia", "home": "ALICANTE",
     "match": lambda x: x.get("municipalities") == "ALICANTE" and x.get("provinces") == "ALICANTE", "listings": False, "barrios": True, "barrios_file": "boundaries/alicante.geojson",
     "catastro": ("03", "03900", "ALICANTE ALACANT"), "ine": "03014", "center": [-0.481, 38.345], "zoom": 12.8, "hex_m": 90, "subareas": "barrio"},
    {"slug": "valladolid", "name": {"es": "Valladolid", "en": "Valladolid"}, "kind": "city", "region": "cyl", "home": "Valladolid",
     "match": lambda x: x.get("municipalities") == "VALLADOLID" and x.get("provinces") == "VALLADOLID", "listings": False, "barrios": True, "barrios_file": "boundaries/valladolid.geojson",
     "catastro": ("47", "47900", "VALLADOLID"), "ine": "47186", "map": False, "center": [-4.728, 41.652], "zoom": 12.8, "hex_m": 90, "subareas": "barrio"},
    {"slug": "laspalmas", "name": {"es": "Las Palmas de Gran Canaria", "en": "Las Palmas de Gran Canaria"}, "kind": "city", "region": "canarias",
     "home": "LAS PALMAS DE GRAN CANARIA", "match": lambda x: x.get("municipalities") == "LAS PALMAS DE GRAN CANARIA", "listings": False,
     "barrios": True, "barrios_file": "boundaries/laspalmas.geojson", "catastro": ("35", "35017", "LAS PALMAS DE GRAN CANARIA"), "ine": "35016", "center": [-15.43, 28.12], "zoom": 12.6,
     "hex_m": 90, "subareas": "barrio"},
    {"slug": "marbella", "name": {"es": "Marbella", "en": "Marbella"}, "kind": "city",
     "match": lambda x: x.get("municipalities") == "MARBELLA", "listings": False, "barrios": False, "ine": "29069",
     "center": [-4.93, 36.51], "zoom": 12, "hex_m": 150, "subareas": "locality"},
    {"slug": "granada", "name": {"es": "Granada", "en": "Granada"}, "kind": "city", "home": "GRANADA",
     "match": lambda x: x.get("municipalities") == "GRANADA", "listings": False, "barrios": True, "barrios_file": "boundaries/granada.geojson", "ine": "18087",
     "center": [-3.598, 37.177], "zoom": 13.4, "hex_m": 90, "subareas": "barrio"},
    {"slug": "cordoba", "name": {"es": "Córdoba", "en": "Córdoba"}, "kind": "city", "home": "CÓRDOBA",
     "match": lambda x: x.get("municipalities") == "CÓRDOBA", "listings": False, "barrios": True, "barrios_file": "boundaries/cordoba.geojson", "ine": "14021",
     "center": [-4.779, 37.884], "zoom": 13.4, "hex_m": 90, "subareas": "barrio"},
    {"slug": "cadiz", "name": {"es": "Cádiz", "en": "Cádiz"}, "kind": "city", "home": "CÁDIZ",
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
ANDALUSIA_INE = {"04", "11", "14", "18", "21", "23", "29", "41"}   # INE province codes
SEARCH_PROVINCES = ANDALUSIA   # the search index covers all of Andalucía
CATASTRO_PROVINCE = "29"     # Catastro: every municipality in Málaga province…
# Balearic municipalities on Menorca, Ibiza and Formentera (INE / Catastro codes): not part of the Mallorca area
NOT_MALLORCA = {"07002", "07015", "07064", "07037", "07067", "07023", "07032", "07052", "07026", "07024", "07046", "07050",
                "07048", "07054"}
CATASTRO_EXTRA = [("41", "SEVILLA"), ("18", "GRANADA"), ("14", "CORDOBA"), ("11", "CADIZ"), ("08", "BARCELONA"), ("46", "VALENCIA"), ("30", "MURCIA"), ("50", "ZARAGOZA"),
                  ("35", "LAS PALMAS DE GRAN CANARIA"), ("28", "MADRID"),
                  ("03", "ALICANTE ALACANT"), ("47", "VALLADOLID")]   # …plus these cities
LISTING_CITIES = [A["slug"] for A in AREAS if A["listings"] and not A.get("parent")]   # re-checked (Palma: under mallorca)
SNAPSHOT_CITIES = list(dict.fromkeys(A.get("ia", A["slug"]) for A in AREAS if A["listings"]))   # Inside Airbnb's own city names


def area_snapshot(A):
    """(date, rows) of an area's Inside Airbnb listings. Bilbao and Donostia share Inside Airbnb's Euskadi file, so their
    rows are those in their municipality."""
    d_, p_ = snapshot.latest_local(CACHE, A.get("ia", A["slug"]))
    if not p_:
        return None, []
    rows = sample.load_snapshot(p_)
    if A.get("ia_muni"):
        rows = [r for r in rows if euskadi.muni(r["neighbourhood_cleansed"]) == euskadi.muni(A["ia_muni"])]
    return d_, rows


def sub_listings(parent, parent_subareas, muni_name):
    """A municipality's share of its parent area's classified listings (Palma in Mallorca): the listings inside its
    outline (the parent's municipality polygons, as the index always did), so every verdict, including licences shared
    across the island, is the same as on the parent's page. Returns the same tuple as LIST entries."""
    rows, d_, out, _removed, by_key = parent
    if parent_subareas is not None:
        out_ = [o for o in out if parent_subareas.lookup(o["lat"], o["lon"])[1] == muni_name]
    else:
        ids_ = {r["id"] for r in rows if euskadi.muni(r["neighbourhood_cleansed"]) == euskadi.muni(muni_name)}
        out_ = [o for o in out if o["id"] in ids_]
    ids, kept = {o["id"] for o in out_}, {o["id"] for o in out}
    removed = sum(1 for r in rows if r["id"] not in kept and euskadi.muni(r["neighbourhood_cleansed"]) == euskadi.muni(muni_name))
    keys = {k for o in out_ for k in o["keys"]}
    return [r for r in rows if r["id"] in ids], d_, out_, removed, {k: [o for o in v if o["id"] in ids] for k, v in by_key.items() if k in keys}


AREA_REGION = {A["slug"]: A.get("region", "andalucia") for A in AREAS}
AREA_BY_SLUG = {A["slug"]: A for A in AREAS}
# Residents (INE, official figures at 1 Jan 2025, table 29005), to order areas by size on the site. Index cities from the cohort.
AREA_POPULATION = {**{c["area"]: c["population"] for c in PINDEX_CFG["cohort"]["cities"] if not c["row"]},
                   "marbella": 159786, "granada": 233975, "cadiz": 109950, "donostia": 189866, "mallorca": 962035, "andalucia": 8666412}
# The official register behind each region's areas (names for the page) and its seasonal-let threshold
REGISTERS = {
    "andalucia": {"es": "Registro de Turismo de Andalucía", "en": "Andalusian Tourism Register", "by_es": "la Junta", "by_en": "the Junta",
                  "src": "Open RTA", "seasonal_nights": 60},
    "catalunya": {"es": "Registre de Turisme de Catalunya", "en": "Catalan Tourism Register", "by_es": "la Generalitat", "by_en": "the Generalitat",
                  "src": "Generalitat de Catalunya y Ajuntament de Barcelona", "seasonal_nights": 32},
    "valencia": {"es": "Registro de Turismo de la Comunitat Valenciana", "en": "Valencian Tourism Register", "by_es": "la Generalitat Valenciana",
                 "by_en": "the Generalitat Valenciana", "src": "Generalitat Valenciana, dades obertes", "seasonal_nights": valencia.SEASONAL_NIGHTS},
    "madrid": {"es": "Registro de Empresas Turísticas de la Comunidad de Madrid", "en": "Comunidad de Madrid tourism register",
               "by_es": "la Comunidad de Madrid", "by_en": "the Comunidad de Madrid", "src": "Comunidad de Madrid, datos abiertos",
               "seasonal_nights": madrid.SEASONAL_NIGHTS, "number_required": False},
    # (names and thresholds checked against docs/law-sources.md when each region's register is wired in)
    "aragon": {"es": "Registro de Turismo de Aragón", "en": "Aragón Tourism Register", "by_es": "el Gobierno de Aragón",
               "by_en": "the Government of Aragón", "src": "Gobierno de Aragón, Aragón Open Data", "seasonal_nights": 32},
    "cyl": {"es": "Registro de Turismo de Castilla y León", "en": "Castilla y León Tourism Register", "by_es": "la Junta de Castilla y León",
            "by_en": "the Junta de Castilla y León", "src": "Junta de Castilla y León, datos abiertos", "seasonal_nights": cyl.SEASONAL_NIGHTS},
    "murcia": {"es": "Registro de Empresas y Actividades Turísticas de la Región de Murcia", "en": "Region of Murcia tourism register",
               "by_es": "la Región de Murcia", "by_en": "the Region of Murcia", "src": "Región de Murcia, datos abiertos", "seasonal_nights": 32},
    "canarias": {"es": "Registro General Turístico de Canarias", "en": "Canary Islands tourism register", "by_es": "el Gobierno de Canarias",
                 "by_en": "the Government of the Canary Islands", "src": "Gobierno de Canarias, datos abiertos", "seasonal_nights": 32},
    "euskadi": {"es": "Registro de Empresas y Actividades Turísticas de Euskadi", "en": "Basque tourism register (REATE)",
                "by_es": "el Gobierno Vasco", "by_en": "the Basque Government", "src": "Gobierno Vasco, Open Data Euskadi",
                "seasonal_nights": euskadi.SEASONAL_NIGHTS},
    "baleares": {"es": "registro turístico del Consell de Mallorca", "en": "Consell de Mallorca tourism register",
                 "by_es": "el Consell de Mallorca", "by_en": "the Consell de Mallorca", "src": "Consell de Mallorca",
                 "seasonal_nights": baleares.SEASONAL_NIGHTS},
}   # Inside Airbnb city slugs = our area slugs


def city_barrios(slug):
    """Barrio polygons: Málaga's from its open data, Sevilla's from the Inside Airbnb neighbourhoods file (108 barrios)."""
    if slug == "malaga":
        return geo.Barrios(geo.ensure_barrios(CACHE))
    A = next(x for x in AREAS if x["slug"] == slug)
    if A.get("barrios_file"):
        p_ = os.path.join(CACHE, A["barrios_file"])
        if not os.path.exists(p_):   # a council's server down (or blocking the runner): the copy kept in the repo
            p_ = os.path.join(REPO, "pipeline", "inputs", A["barrios_file"])
        return geo.Barrios(p_)
    _, p = snapshot.latest_local(CACHE, A.get("ia", slug))
    return geo.Barrios(os.path.join(os.path.dirname(p), "neighbourhoods.geojson"))


def classify_listings(index, official, mx, snap_date, rows, st, home="MÁLAGA", cat_idx=None, bal=None, eus=None, fn=None):
    """Classify every listing of one city (live if fresh, else snapshot text). Returns (listings, removed, by_key)."""
    out, removed, no_position = [], 0, 0
    for r in rows:
        s = st.get(r["id"])
        basis = "snapshot"
        if fresh(s, snap_date) and s["live_status"] == "removed":
            removed += 1
            continue
        if fresh(s, snap_date) and s["live_status"] == "ok":
            basis = "live"
            # a live read can lack a field (e.g. no map position): fall back to the snapshot's
            v = {"registration_raw": s["registration_raw"],
                 "lat": s.get("lat") if s.get("lat") not in (None, "") else r["latitude"],
                 "lon": s.get("lon") if s.get("lon") not in (None, "") else r["longitude"],
                 "room_type": s.get("room_type") or r["room_type"], "property_type": s.get("property_type") or r["property_type"],
                 "min_nights": r["minimum_nights"]}
        else:
            v = {"registration_raw": r["license"], "lat": r["latitude"], "lon": r["longitude"], "room_type": r["room_type"],
                 "property_type": r["property_type"], "min_nights": r["minimum_nights"]}
        if v["lat"] in (None, "") or v["lon"] in (None, ""):   # no position anywhere: can't place it, so leave it out
            no_position += 1
            continue
        if fn is not None:    # a region's own classifier: fn(view, snapshot row) → {"category", "key", "group"}
            cc = fn(v, r)
            c = {"category": cc["category"], "match_key": cc["key"] if cc["category"].startswith("FOUND") else None,
                 "primary_code_norm": cc["key"], "junta_codes_norm": cc["key"] or "", "register_record": {"group": cc.get("group")}}
        elif eus is not None:   # Bilbao, Donostia: EBI/ESS… numbers against the Basque register (rta_audit.euskadi)
            cc = euskadi.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], eus, r["neighbourhood_cleansed"])
            c = {"category": cc["category"], "match_key": cc["key"] if cc["category"].startswith("FOUND") else None,
                 "primary_code_norm": cc["key"], "junta_codes_norm": cc["key"] or "", "register_record": {"group": cc.get("group")}}
        elif bal is not None:   # Mallorca: ETV/VT… numbers against the Consell de Mallorca registers (rta_audit.baleares)
            bidx, edges = bal
            cc = baleares.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], bidx,
                                   r["neighbourhood_cleansed"], edges)
            c = {"category": cc["category"], "match_key": cc["key"] if cc["category"].startswith("FOUND") else None,
                 "primary_code_norm": cc["key"], "junta_codes_norm": cc["key"] or "", "register_record": {"group": cc.get("group")}}
        elif cat_idx is not None:   # Catalonia: HUTB numbers against the Generalitat register (rta_audit.catalunya)
            cc = catalunya.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], cat_idx, home.title())
            c = {"category": cc["category"], "match_key": cc["key"] if cc["category"].startswith("FOUND") else None,
                 "primary_code_norm": cc["key"], "junta_codes_norm": cc["key"] or "", "register_record": {"group": cc.get("group")}}
        else:
            c = classify.classify(v, index, official, mx, home)
        out.append({"id": r["id"], "lat": float(v["lat"]), "lon": float(v["lon"]), "basis": basis, "cat": c["category"],
                    "verdict": classify.VERDICT[c["category"]], "key": c.get("match_key") or c.get("primary_code_norm"),
                    "keys": [k for k in (c.get("junta_codes_norm") or "").split("; ") if k],
                    "entire": (v["room_type"] == "Entire home/apt"), "host": r["host_id"],
                    "host_bucket": host_bucket(r["calculated_host_listings_count"]),
                    "reg_group": (c.get("register_record") or {}).get("group")})

    if no_position:
        print(f"{home}: {no_position} listings without a map position left out")
    # shared whole-dwelling codes
    by_key = defaultdict(list)
    for o in out:
        for k in o["keys"]:
            by_key[k].append(o)
    # A single-dwelling licence on whole-home listings from more than one host can't be valid for all of them.
    # The same host listing the same flat twice is not flagged. In Mallorca (mostly houses, often marketed by several
    # agencies at once) only listings in clearly different places count: see shared_count.
    for o in out:
        if o["verdict"] == "VALID" and o["entire"] and o["reg_group"] == "Completa":
            if shared_count(by_key[o["key"]], places=bal is not None) > 1:
                o["verdict"] = "VALID_CODE_SHARED"
    # A room listing showing a licence registered for a whole dwelling ("Completa"): the number is real, but rooms need a
    # "por habitaciones" registration. Like shared licences: valid number, flagged, not in the headline.
    for o in out:
        if o["verdict"] == "VALID" and not o["entire"] and o["reg_group"] == "Completa":
            o["verdict"] = "VALID_TYPE_MISMATCH"
    return out, removed, by_key


def shared_hosts(rows):
    """Distinct hosts showing a code on whole-home listings."""
    return len({x["host"] for x in rows if x["entire"]})


SHARED_PLACE_M = 300   # Inside Airbnb locations are shifted up to ~150 m: closer listings may be the same home


def shared_places(rows):
    """Distinct places (listings more than SHARED_PLACE_M apart) among whole-home listings showing a code."""
    centres = []
    for x in rows:
        if x["entire"] and not any(register.haversine_m(x["lat"], x["lon"], la, lo) <= SHARED_PLACE_M for la, lo in centres):
            centres.append((x["lat"], x["lon"]))
    return len(centres)


def shared_count(rows, places=False):
    """How many homes a single-dwelling code seems to be used for: distinct hosts, or (places=True) distinct hosts that
    are also in different places, so one villa marketed by several agencies isn't counted as several homes."""
    hosts = shared_hosts(rows)
    return min(hosts, shared_places(rows)) if places and hosts > 1 else hosts


def listing_summary(out, removed, by_key, area_vut):
    V = ["VALID", "VALID_CODE_SHARED", "VALID_LOCATION_MISMATCH", "VALID_TYPE_MISMATCH", "NOT_VALID", "POSSIBLY_EXEMPT", "INCONCLUSIVE"]
    vc = Counter(o["verdict"] for o in out)
    cc = Counter(o["cat"] for o in out)
    hb = defaultdict(Counter)
    for o in out:
        hb[o["host_bucket"]]["n"] += 1
        hb[o["host_bucket"]][o["verdict"]] += 1
    shown = {o["key"] for o in out if o["verdict"] in ("VALID", "VALID_CODE_SHARED", "VALID_LOCATION_MISMATCH", "VALID_TYPE_MISMATCH")}
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
        # among listings that need a number (all but the possibly exempt): the share that don't display a valid one
        "need_number": len(out) - vc.get("POSSIBLY_EXEMPT", 0),
        "need_number_not_valid_pct": round(100 * vc.get("NOT_VALID", 0) / (len(out) - vc.get("POSSIBLY_EXEMPT", 0)), 1)
        if len(out) > vc.get("POSSIBLY_EXEMPT", 0) else None,
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


def frame_hexes(frame, hexg, hx):
    """Listing-density layer for towns without Inside Airbnb data, from our own list of the town's listings ([id, lat, lon]):
    one hexagon per cell with MIN_LISTINGS_HEX+ listings (as for every listing layer), with its count and, where the
    Catastro has enough homes there, listings per 100 homes. Counts only: no verdicts (only the sample has those)."""
    n = Counter(hexg.cell(la, lo) for _id, la, lo in frame)
    feats = []
    for (q, r_), k in sorted(n.items()):
        if k < MIN_LISTINGS_HEX:
            continue
        p, h = {"n": k}, hx.get((q, r_), {}).get("homes") or 0
        if h >= MIN_HOMES_SHARE:
            p.update(homes=h, per100=round(100 * k / h, 1))
        feats.append({"type": "Feature", "properties": p, "geometry": {"type": "Polygon", "coordinates": [hexg.polygon(q, r_)]}})
    return {"type": "FeatureCollection", "features": feats}


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
    P = {k: v for k, v in (I.get("provinces") or {}).items() if k in ANDALUSIA_INE}
    homes = sum(p.get("homes") or 0 for p in P.values())
    census = sum(100 * p["homes"] / p["pct"] for p in P.values() if p.get("homes") and p.get("pct"))
    return {"homes": homes, "pct": round(100 * homes / census, 2)} if census else None


# The index's cities: every municipality over 300,000 inhabitants, from the versioned cohort in index_config.json (INE official
# figures; reviewed once a year). (name, INE code, our area slug, the municipality's row inside a wider area, e.g. Palma)
RANKING = [(c["name"], c["ine"], c["area"], c["row"]) for c in PINDEX_CFG["cohort"]["cities"]
           if c["population"] > PINDEX_CFG["cohort"]["min_population"]]
POPULATION = {c["ine"]: c["population"] for c in PINDEX_CFG["cohort"]["cities"]}
MIN_SAMPLE_PUBLISH = 300
# The index's "most affected area": the circle (radius PEAK_M, i.e. 1 km across) with the most Airbnb listings per home,
# among circles with at least PEAK_MIN_HOMES homes (so a beach or a park with a few homes doesn't win). From index_config.json.
PEAK_M = int(os.environ.get("PEAK_M") or PINDEX_CFG["concentration"]["radius_m"])
PEAK_MIN_HOMES = PINDEX_CFG["concentration"]["min_homes"]
BUILDING_MIN_HOMES, BUILDING_SHARE = 4, 25   # apartment buildings (4+ homes) where registered tourist flats are 25%+ of homes
MIN_LINKED = 0.8        # a measure that needs register coordinates or Catastro links is shown only above this coverage


SNAP_M = 25   # a registered flat with coordinates but no cadastral reference belongs to the Catastro building within this


def building_shares(homes, ref_muni, ref_pts, mks, vut_recs, agg_ids):
    """Apartment buildings (BUILDING_MIN_HOMES+ homes in the Catastro) in these municipalities, and how many have registered
    tourist flats making up BUILDING_SHARE% or more of their homes. Each flat is linked to its Catastro building by
    cadastral reference (or address), else by snapping its coordinates to the nearest building within SNAP_M. Shown only
    where most flats link; otherwise we'd undercount."""
    grid = defaultdict(list)
    for ref, (la, lo) in ref_pts.items():
        if ref_muni.get(ref) in mks and homes.get(ref):
            grid[(round(la * 2000), round(lo * 2000))].append((la, lo, ref))   # ~50 m cells
    per, linked = Counter(), 0
    for x in vut_recs:
        ref = agg_ids.get(id(x))
        if not (ref and homes.get(ref)) and x.get("lat") is not None:
            cy, cx, best = round(x["lat"] * 2000), round(x["lon"] * 2000), (SNAP_M, None)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for la, lo, rf in grid.get((cy + dy, cx + dx), ()):
                        d = register.haversine_m(x["lat"], x["lon"], la, lo)
                        if d < best[0]:
                            best = (d, rf)
            ref = best[1]
        if ref and homes.get(ref):
            per[ref] += 1
            linked += 1
    if not vut_recs or linked / len(vut_recs) < MIN_LINKED:
        return {"buildings_linked_pct": round(100 * linked / len(vut_recs)) if vut_recs else None}
    total = sum(1 for ref, dw in homes.items() if dw >= BUILDING_MIN_HOMES and ref_muni.get(ref) in mks)
    hit = sum(1 for ref, n in per.items() if homes[ref] >= BUILDING_MIN_HOMES and 100 * n / homes[ref] >= BUILDING_SHARE)
    return {"buildings_linked_pct": round(100 * linked / len(vut_recs)), "apartment_buildings": total, "buildings_over_share": hit,
            "buildings_over_share_pct": round(100 * hit / total, 2) if total else None, "building_share_threshold": BUILDING_SHARE}


def _cells(pts, size, kx):
    """{(i, j): total} on a size-metre grid; pts [(lat, lon, weight)]; kx = cos(latitude), so cells are square everywhere."""
    g = defaultdict(float)
    for la, lo, w in pts:
        g[(round(la * 111320 / size), round(lo * 111320 * kx / size))] += w
    return g


def peak_metrics(home_pts, listing_pts, reg_pts, reg_total, place_of=None, near_place=None):
    """The circle of radius PEAK_M with the most Airbnb listings per 100 homes, among circles with PEAK_MIN_HOMES+ homes:
    its listings per 100 homes, its share of homes registered as tourist flats (if most of the register has coordinates)
    and where it is. Grid of 100 m cells; candidate centres every 200 m wherever there are listings.
    Where: place_of(lat, lon) → barrio, named after the barrio holding most of the circle's listings (the centre can fall
    in a park or the port); else near_place(lat, lon) → the neighbourhood around the centre (OpenStreetMap)."""
    if not home_pts or not listing_pts:
        return {}
    import math
    size, r = 100, PEAK_M // 100
    kx = math.cos(math.radians(sum(p[0] for p in home_pts[:5000]) / min(len(home_pts), 5000)))
    H = _cells(home_pts, size, kx)
    Lc = _cells([(la, lo, 1) for la, lo in listing_pts], size, kx)
    R = _cells([(la, lo, 1) for la, lo in reg_pts], size, kx)
    offs = [(di, dj) for di in range(-r, r + 1) for dj in range(-r, r + 1) if di * di + dj * dj <= r * r]
    best = None
    for (i, j) in {(i - i % 2, j - j % 2) for (i, j) in Lc}:
        h = sum(H.get((i + di, j + dj), 0) for di, dj in offs)
        if h < PEAK_MIN_HOMES:
            continue
        n = sum(Lc.get((i + di, j + dj), 0) for di, dj in offs)
        if best is None or n / h > best[0]:
            best = (n / h, i, j, h, n)
    if not best:
        return {}
    _, i, j, h, n = best
    la, lo = i * size / 111320, j * size / (111320 * kx)
    out = {"peak_listings_per_100_homes": round(100 * n / h, 1), "peak_homes": round(h), "peak_listings": int(n), "peak_lat": round(la, 4), "peak_lon": round(lo, 4),
           "peak_radius_m": PEAK_M}
    if reg_total and len(reg_pts) / reg_total >= MIN_LINKED:
        out["peak_registered_pct"] = round(100 * sum(R.get((i + di, j + dj), 0) for di, dj in offs) / h, 1)
    if place_of:
        inside = Counter(place_of(a, b) for a, b in listing_pts if register.haversine_m(la, lo, a, b) <= PEAK_M)
        inside.pop(None, None)
        if inside:
            out["peak_place"] = inside.most_common(1)[0][0]
    if "peak_place" not in out and near_place:
        out["peak_place"] = near_place(la, lo)
    return out


def postcode_place(recs, lat, lon):
    """Where a hotspot is, for cities without barrio maps: the postcode holding most registered flats within PEAK_M,
    e.g. "CP 03002" (the area pages describe zones by postcode too). None if the register has no coordinates there."""
    pcs = Counter(str(x.get("postal_code") or "").strip()[:5] for x in recs
                  if x.get("lat") is not None and register.haversine_m(lat, lon, x["lat"], x["lon"]) <= PEAK_M)
    pcs.pop("", None)
    return f"CP {pcs.most_common(1)[0][0]}" if pcs else None


PLACES = os.path.join(CACHE, "places.json")


def near_place(lat, lon):
    """The neighbourhood around a point, from OpenStreetMap (Nominatim reverse geocoding, one request per new point, cached;
    © OpenStreetMap contributors, ODbL). None if unavailable: the page then says "1 km circle"."""
    places = json.load(open(PLACES)) if os.path.exists(PLACES) else {}
    k = f"{lat:.3f},{lon:.3f}"
    if k not in places:
        try:
            from rta_audit import http
            a = http.get("https://nominatim.openstreetmap.org/reverse", params={"lat": lat, "lon": lon, "zoom": 15, "format": "jsonv2",
                         "accept-language": "es"}, headers={"User-Agent": "tienelicencia.com (civic research; hola@shiftedlabs.ai)"},
                         timeout=30).json().get("address") or {}
            places[k] = next((a[f] for f in ("neighbourhood", "quarter", "suburb", "city_district") if a.get(f)), None)
            json.dump(places, open(PLACES, "w"), ensure_ascii=False)
            time.sleep(1.1)   # Nominatim usage policy: at most one request a second
        except Exception as e:  # noqa: BLE001
            print("near_place: lookup failed:", e)
            return None
    return places[k]


def census_home_points(barrios, barrio_homes, around, span=0.08):
    """For census cities (no Catastro): each barrio's homes spread evenly over its area, as weighted points on a ~60 m grid."""
    step, cells, grid = 0.0006, defaultdict(int), []
    la0, lo0 = around
    y = la0 - span
    while y <= la0 + span:
        x = lo0 - span * 1.3
        while x <= lo0 + span * 1.3:
            bid = barrios.lookup(y, x)[0]
            if bid is not None:
                cells[bid] += 1
                grid.append((y, x, bid))
            x += step
        y += step
    return [(y, x, barrio_homes.get(bid, 0) / cells[bid]) for y, x, bid in grid if cells[bid]]



def ranking(I, summaries, conc, built, extra=None, kept=(), prev_rank=None):
    """Índice de presión de la vivienda turística for the principal cities (rta_audit/index.py, index_config.json):
    housing (INE share of homes advertised), concentration (most affected circle 1 km across) and registration (severity-weighted
    discrepancies), normalised against the fixed baseline. Also every figure behind it, for the page's detail view."""
    cfg = PINDEX_CFG
    out = []
    for name_, code, slug, row_name in RANKING:
        m = (I.get("munis") or {}).get(code) or {}
        if slug in kept and name_ in (prev_rank or {}):   # that city's register didn't load: last published entry
            out.append({k: v for k, v in prev_rank[name_].items() if k not in ("index", "rank", "status", "normalised", "contributions")})
            continue
        S = summaries.get(slug) or {}
        ex = dict((extra or {}).get(slug) or {})
        vitems, vmeta = ex.pop("_verif", (None, None))
        r = {**ex, "name": name_, "ine": code, "population": POPULATION.get(code), "slug": slug if slug and not row_name else None, "area": slug,
             "advertised_pct": m.get("pct"), "advertised_homes": int(m["homes"]) if m.get("homes") else None,
             "census_homes": ine_census_homes(m) if m else None, "ine_period": I.get("period")}
        if row_name:   # Palma inside the Mallorca area
            sub = next((x for x in (S.get("subareas") or {}).get("rows", []) if x.get("name") == row_name), {})
            r["registered_pct"], r["registered"] = sub.get("vut_share"), sub.get("vut")
        else:
            reg = S.get("registered") or {}
            r["registered_pct"], r["registered"] = reg.get("vut_share"), reg.get("vut")
        number_required = (REGISTERS.get(AREA_REGION.get(slug) or "") or {}).get("number_required") is not False
        if not number_required:
            r["number_required"] = False   # Madrid: showing the number isn't required (rta_audit/madrid.py)
        r["verification"] = pindex.verification(vitems, cfg, number_required=number_required, **vmeta) if vitems else None
        r["housing"] = r["advertised_pct"]
        r["concentration"] = r.get("peak_listings_per_100_homes")
        out.append(r)
    baseline = pindex.compute(out, cfg)
    out.sort(key=lambda r: (r["index"] is None, -(r["index"] or 0), r["name"]))
    return {"built_at": built, "name": cfg["name"], "version": cfg["version"], "weights": cfg["weights"], "severity": cfg["severity"],
            "min_assessed": cfg["min_assessed"], "sample_target": cfg["sample_target"], "baseline": baseline,
            "cohort": {k: cfg["cohort"][k] for k in ("rule", "min_population", "source", "population_date", "reviewed")}
            | {"eligible": len(out), "with_index": sum(1 for r in out if r["index"] is not None)},
            "ine_period": I.get("period"), "peak_radius_m": PEAK_M, "peak_min_homes": PEAK_MIN_HOMES,
            "building_min_homes": BUILDING_MIN_HOMES, "building_share": BUILDING_SHARE, "cities": out}


HOME_BARRIO_SHARE = 5   # homepage: barrios where registered tourist flats are more than this % of homes


def home_stats(rk, summaries):
    """The homepage's headline figures, across the index cities (and, for barrios, every area with barrio maps). Only what
    we measure: each figure says where it comes from."""
    C = [c for c in rk["cities"]]
    ranked = [c for c in C if c["index"] is not None]
    reg = [c for c in C if c.get("registered") is not None and c.get("census_homes")]
    shares = sorted((c["registered_pct"], c["name"]) for c in reg if c.get("registered_pct") is not None)
    tot = bad = wrong = shown = 0
    for c in C:
        v = c.get("verification")
        if not v:
            continue
        k = v["counts"]
        miss = k["missing"] if c.get("number_required", True) else 0   # Madrid: showing it isn't required
        tot += v["assessed"] - (0 if c.get("number_required", True) else k["missing"])
        w_ = k["unmatched"] + k["invalid_other_town"] + k["invalid_cancelled"]
        wrong += w_
        bad += w_ + miss
        shown += k["valid"] + w_   # listings that show a number of their region's register format
    barrios = []
    for slug, S in summaries.items():
        sa = S.get("subareas") or {}
        if sa.get("kind") != "barrio":
            continue
        for r in sa.get("rows", []):
            if (r.get("vut_share") or 0) > HOME_BARRIO_SHARE:
                barrios.append({"area": slug, "id": r.get("id"), "name": r.get("name"), "share": r["vut_share"]})
    by_area = Counter(b["area"] for b in barrios)
    top_b = max(barrios, key=lambda b: b["share"]) if barrios else None
    hot = max((c for c in C if c.get("concentration") is not None), key=lambda c: c["concentration"], default=None)
    return {"built_at": rk["built_at"], "cities": len(C), "min_population": rk["cohort"]["min_population"],
            "top": [{"name": c["name"], "slug": c.get("slug") or c.get("area"), "index": c["index"]} for c in ranked[:3]],
            "registered": sum(c["registered"] for c in reg), "homes": sum(c["census_homes"] for c in reg),
            "registered_pct": round(100 * sum(c["registered"] for c in reg) / sum(c["census_homes"] for c in reg), 2) if reg else None,
            "registered_min": shares[0] if shares else None, "registered_max": shares[-1] if shares else None,
            "assessed": tot, "not_valid": bad, "wrong_number": wrong, "with_number": shown,
            "barrio_share": HOME_BARRIO_SHARE, "barrios_over": len(barrios), "barrio_areas": len(by_area),
            "barrios_over_by_area": dict(by_area.most_common()), "top_barrio": top_b,
            "buildings_over": sum(c.get("buildings_over_share") or 0 for c in C), "building_share": BUILDING_SHARE,
            "building_cities": [c["name"] for c in C if c.get("buildings_over_share")],
            "hotspot": {k: hot.get(k) for k in ("name", "area", "concentration", "peak_place", "peak_listings", "peak_homes", "peak_lat",
                                                "peak_lon", "peak_radius_m")} if hot else None}


def index_history(rk, path):
    """One snapshot per month (the latest build of the month), so the page can show how each city's index moves.
    Each component keeps its own source date: not every source is refreshed monthly."""
    hist = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"version": rk["version"], "months": {}}
    month = rk["built_at"][:7]
    hist["months"][month] = {"built_at": rk["built_at"], "version": rk["version"], "baseline_frozen": rk["baseline"].get("frozen"),
                             "cities": {c["name"]: {"index": c["index"], "status": c["status"], "housing": c["housing"],
                                                    "concentration": c["concentration"],
                                                    "registration": (c.get("verification") or {}).get("R"),
                                                    "assessed": (c.get("verification") or {}).get("assessed"),
                                                    "target": (c.get("verification") or {}).get("target"),
                                                    "source": (c.get("verification") or {}).get("source")} for c in rk["cities"]}}
    return hist


LOOKUP_KEYS = {"catalunya": ["cat"], "baleares": ["bal"], "euskadi": ["eus"], "valencia": ["vlc"], "madrid": ["mad"], "aragon": ["ara"], "cyl": ["cyl"],
               "murcia": ["mur", "mur_filing"], "canarias": ["can", "can_short"]}
SEARCH_PROV = {"catalunya": ["B"], "baleares": ["IB"], "euskadi": ["BI", "SS"], "valencia": ["V"], "madrid": ["M"], "aragon": ["Z"], "cyl": ["VA"],
               "murcia": ["MU"], "canarias": ["GC"]}


def previous_published():
    """What the last build published (areas, ranking, function data), to fall back on for a region missing this run."""
    out = {}
    try:
        out["areas"] = {a["slug"]: a for a in json.load(open(os.path.join(SITE_DATA, "areas.json"), encoding="utf-8"))["areas"]}
        out["ranking"] = {c["name"]: c for c in json.load(open(os.path.join(SITE_DATA, "ranking.json"), encoding="utf-8"))["cities"]}
    except (OSError, ValueError, KeyError):
        pass
    for k, f in (("lookup", "lookup.json.gz"), ("search", "search.json.gz")):
        try:
            d = json.load(gzip.open(os.path.join(FN_DATA, f), "rt", encoding="utf-8"))
            out[k] = d if k == "lookup" else d["rows"]
        except (OSError, ValueError, KeyError):
            pass
    return out


def ine_mallorca(I):
    """Mallorca totals from the INE's municipalities on the island."""
    ms = [m for c, m in (I.get("munis") or {}).items() if c[:2] == "07" and c not in NOT_MALLORCA and m.get("homes")]
    homes, census = sum(m["homes"] for m in ms), sum(ine_census_homes(m) or 0 for m in ms)
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
            ("exempt", "anuncios_posiblemente_exentos"), ("listings_per_100", "anuncios_por_100_viviendas"),
            ("sample_checked", "anuncios_revisados_muestra"), ("not_valid_pct", "pct_anuncios_sin_numero_valido"),
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


# ---- one map of Spain (site/data/spain/, read by site/assets/js/map.js). Registered flats as hexagons at four sizes, one
# per zoom band, so the first paint needs one small file; buildings and the finest hexagons in web-map tiles, fetched for
# the part of Spain on screen; each area's own layers ("% of homes", adverts without a valid number) in a compact form.
# Built from the per-area files written just before, so a building listed by both a city and its province appears once.
SPAIN_HEX = [6000, 2000, 400, 90]   # hexagon circumradius (m) per zoom band, Spain → street
SPAIN_HEX_TZ = 9                    # 90 m hexagons: one file per web-map tile at this zoom (~80 km)
SPAIN_BLD_TZ = 11                   # buildings: one file per tile at this zoom (~20 km)
SPAIN_BLD_FIELDS = ["lat", "lon", "label", "vut", "places", "other", "id", "homes"]


def _tile(lat, lon, z):
    import math
    n = 2 ** z
    return f"{int((lon + 180) / 360 * n)}-{int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)}"


def _stops(vals):
    """Four colour breaks at the 50/75/90/97th percentiles (as the map used per area), at least 2 and increasing."""
    v = sorted(x for x in vals if x)
    if not v:
        return [2, 3, 4, 5]
    s = sorted({max(2, v[min(len(v) - 1, int(f * len(v)))]) for f in (.5, .75, .9, .97)})
    while len(s) < 4:
        s.append(s[-1] + 1)
    return s


def write_spain_map(w, areas_out):
    import shutil
    shutil.rmtree(os.path.join(SITE_DATA, "spain"), ignore_errors=True)   # ours alone: tiles that no longer exist go
    rows, ids = {}, {}
    for a in areas_out:
        p = os.path.join(SITE_DATA, a["slug"], "buildings.json")
        rs = json.load(open(p, encoding="utf-8"))["rows"] if a.get("has_map") and os.path.exists(p) else []
        ids[a["slug"]] = {r[8] for r in rs}
        for r in rs:
            rows[r[8]] = r
    # each building's finest area (the smallest that lists it); an area's parent: the smallest area holding 90% of it
    finest = {}
    for s in sorted((s for s in ids if ids[s]), key=lambda s: -len(ids[s])):
        for i in ids[s]:
            finest[i] = s
    region = next((a["slug"] for a in areas_out if a["kind"] == "region"), None)
    parent = {}
    for a in areas_out:
        s, mine = a["slug"], ids[a["slug"]]
        up = [t for t in ids if t != s and len(ids[t]) > len(mine) and mine and len(mine & ids[t]) >= .9 * len(mine)]
        parent[s] = min(up, key=lambda t: len(ids[t])) if up else region if a["kind"] == "province" else None
    bbox = {}
    for a in areas_out:   # the 2nd–98th percentiles: a few register entries are placed far from their town
        if ids[a["slug"]]:
            la, lo = sorted(rows[i][0] for i in ids[a["slug"]]), sorted(rows[i][1] for i in ids[a["slug"]])
            e = len(la) // 50
            bbox[a["slug"]] = [lo[e], la[e], lo[-1 - e], la[-1 - e]]
    for a in areas_out:   # the region: its provinces together; an area without coordinates: around its centre
        kids = [bbox[s] for s, p in parent.items() if p == a["slug"] and s in bbox]
        if a["slug"] not in bbox:
            c = a["center"]
            bbox[a["slug"]] = [min(b[0] for b in kids), min(b[1] for b in kids), max(b[2] for b in kids), max(b[3] for b in kids)] \
                if kids else [c[0] - .15, c[1] - .1, c[0] + .15, c[1] + .1]
    order = [a["slug"] for a in areas_out]

    levels = []
    for k, s in enumerate(SPAIN_HEX):
        h, n, own = geo.Hex(s), Counter(), defaultdict(Counter)
        for r in rows.values():
            c = h.cell(r[0], r[1])
            n[c] += r[3]
            own[c][finest[r[8]]] += r[3] + r[5]
        lv = {"s": s, "stops": _stops(n.values())}
        if k == 1:   # 2 km cells also name the finest area that owns most of each: how the map knows where it is
            lv["c"] = [[q, r_, n[(q, r_)], order.index(own[(q, r_)].most_common(1)[0][0])] for q, r_ in own]
        elif k == 0:
            lv["c"] = [[q, r_, v] for (q, r_), v in n.items() if v]
        elif k == 2:
            lv["file"] = "h2.json"
            w("spain/h2.json", [[q, r_, v] for (q, r_), v in n.items() if v])
        else:
            tiles = defaultdict(list)
            for (q, r_), v in n.items():
                if v:
                    ring = h.polygon(q, r_)[:6]
                    tiles[_tile(sum(p[1] for p in ring) / 6, sum(p[0] for p in ring) / 6, SPAIN_HEX_TZ)].append([q, r_, v])
            for t, cs in tiles.items():
                w(f"spain/h3/{t}.json", cs)
            lv.update(tz=SPAIN_HEX_TZ, tiles=sorted(tiles))
        levels.append(lv)

    btiles = defaultdict(list)
    for r in rows.values():   # the map uses neither "since" nor "other_types"
        btiles[_tile(r[0], r[1], SPAIN_BLD_TZ)].append([r[0], r[1], r[2], r[3], r[4], r[5], r[8], r[9]])
    for t, rs in btiles.items():
        w(f"spain/b/{t}.json", rs)

    # each area's own hexagons with "% of homes" or adverts without a valid number. A province's hexagons inside a
    # city that has its own carry that city ("o"), so the map can hide them where the city's finer ones are drawn.
    theme = {}
    for a in areas_out:
        p = os.path.join(SITE_DATA, a["slug"], "hex.geojson")
        if not a.get("has_map") or not os.path.exists(p):
            continue
        fs = [f for f in json.load(open(p, encoding="utf-8"))["features"] if "share" in f["properties"] or "pct" in f["properties"]]
        if fs:
            theme[a["slug"]] = (a, fs)
    for s, (a, fs) in theme.items():
        h = geo.Hex(a["hex_m"])
        kids = {k for k, p in parent.items() if p == s and k in theme}
        own = defaultdict(Counter)
        if kids:
            for i in ids[s]:
                if finest[i] in kids:
                    own[h.cell(rows[i][0], rows[i][1])][finest[i]] += 1
        cells = []
        for f in fs:
            ring, pr = f["geometry"]["coordinates"][0][:6], f["properties"]
            c = h.cell(sum(p[1] for p in ring) / 6, sum(p[0] for p in ring) / 6)
            cells.append([*c, *(pr.get(k) for k in ("reg", "homes", "share", "ashare", "n", "nv", "pct")),
                          own[c].most_common(1)[0][0] if own.get(c) else None])
        w(f"spain/a/{s}.json", {"s": a["hex_m"], "fields": ["q", "r", "reg", "homes", "share", "ashare", "n", "nv", "pct", "o"], "c": cells})

    w("spain/map.json", {
        "built_at": now(), "levels": levels, "owners": order,
        "bld": {"tz": SPAIN_BLD_TZ, "fields": SPAIN_BLD_FIELDS, "tiles": sorted(btiles)},
        "areas": {a["slug"]: {"bbox": [round(x, 4) for x in bbox[a["slug"]]], "parent": parent[a["slug"]], "theme": a["slug"] in theme,
                              "register": {k: REGISTERS[AREA_REGION.get(a["slug"], "andalucia")][k] for k in ("es", "en")}}
                  for a in areas_out}})


def cmd_build(a):
    meta = json.load(open(os.path.join(REG_DIR, "register_meta.json")))
    recs = register.load_records(REG_DIR)
    index, mx = register.build_index(recs), register.max_issued(recs)
    del recs
    official = load_official()
    snap_date = snapshot.latest_local(CACHE, "malaga")[0]
    BAR = {}
    for A in AREAS:   # barrio outlines; a city whose file is missing (a source down on a first run) is built without barrios
        if A["barrios"]:
            try:
                BAR[A["slug"]] = city_barrios(A["slug"])
            except (OSError, ValueError, KeyError) as e:
                print(f"{A['slug']}: no barrio outlines ({e}); built without barrios this time")

    # ---- dwellings per building (Catastro): indicative "share of homes"
    homes, muni_homes, parcel_pts, muni_prov, ref_muni, ref_pts = {}, Counter(), defaultdict(list), {}, {}, {}
    for code, c in catastro.load_cached(CACHE).items():
        mk = buildings.muni_key(c["name"])
        muni_prov[mk] = code[:2]
        for ref, (dw, la, lo, _res) in c["parcels"].items():
            if dw:
                homes[ref] = dw
                ref_muni[ref] = mk
                ref_pts[ref] = (la, lo)
                muni_homes[mk] += dw
                parcel_pts[mk].append((la, lo, dw))

    # ---- INE: advertised tourist homes per municipality (all platforms, de-duplicated)
    I = ine.load(CACHE) or {"munis": {}, "province": {}, "period": None}
    ine_by_key = {buildings.muni_key(m["name"]): m for m in I["munis"].values()}

    # ---- tourist accommodation in the search province, grouped into buildings
    prov = [x for rs in index.values() for x in rs if (x.get("provinces") or "").upper() in SEARCH_PROVINCES
            and x.get("objects_type_id") in register.TOURIST_ACCOMMODATION_TYPES]
    # Catalonia (Barcelona city): converted to the same record shape, so buildings, barrios and search work unchanged
    cg, ca = os.path.join(CACHE, "catalunya", "generalitat.csv"), os.path.join(CACHE, "catalunya", "ajuntament_hut.csv")
    CAT = catalunya.load_register(cg, ca) if os.path.exists(cg) and os.path.exists(ca) else {}
    prov += [x for x in catalunya.as_register_records(CAT) if x["objects_type_id"] in register.TOURIST_ACCOMMODATION_TYPES]
    # Mallorca: the Consell de Mallorca's registers, same shape
    bp = [os.path.join(CACHE, "baleares", n) for n in baleares.SOURCES]
    BAL = baleares.load_register(bp) if all(os.path.exists(p_) for p_ in bp) else {}
    prov += [x for x in baleares.as_register_records(BAL) if x["objects_type_id"] in register.TOURIST_ACCOMMODATION_TYPES]
    # Valencia: the Generalitat's register, each flat placed on its Catastro parcel
    vp = os.path.join(CACHE, "valencia", "viviendas.csv")
    cat_ = catastro.load_cached(CACHE)
    vparcels = {**((cat_.get("46900") or {}).get("parcels") or {}), **((cat_.get("03900") or {}).get("parcels") or {})}   # Valencia, Alicante
    VLC = valencia.load_register(vp, vparcels) if os.path.exists(vp) else {}
    prov += valencia.as_register_records(VLC)
    prov += valencia.as_register_records(VLC, "03014", "ALICANTE", "ALICANTE")
    # Las Palmas de Gran Canaria: the Registro General Turístico de Canarias
    CAN = canarias.load_register([os.path.join(CACHE, "canarias", n) for n in canarias.SOURCES])
    prov += [x for x in canarias.as_register_records(CAN) if x["objects_type_id"] in register.TOURIST_ACCOMMODATION_TYPES]
    # Murcia: the ITREM listings, flats placed on their Catastro parcel
    MUR = murcia.load_register(os.path.join(CACHE, "murcia"), (catastro.load_cached(CACHE).get("30030") or {}).get("parcels") or {})
    prov += [x for x in murcia.as_register_records(MUR) if x["objects_type_id"] in register.TOURIST_ACCOMMODATION_TYPES]
    # Madrid: the Comunidad's register; city flats placed from the council's address points
    MAD = madrid.load_register(os.path.join(CACHE, "madrid"))
    prov += [x for x in madrid.as_register_records(MAD) if x["objects_type_id"] in register.TOURIST_ACCOMMODATION_TYPES]
    # Zaragoza: the Aragón register (no coordinates: in search, not on the map)
    ARA = aragon.load_register(os.path.join(CACHE, "aragon", "vut.csv"))
    prov += aragon.as_register_records(ARA)
    # Valladolid: the Castilla y León register (a third with coordinates)
    CYL = cyl.load_register(os.path.join(CACHE, "cyl", "registro.csv"))
    prov += [x for x in cyl.as_register_records(CYL) if x["objects_type_id"] in register.TOURIST_ACCOMMODATION_TYPES]
    FN = {"madrid": lambda v, r: madrid.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], MAD),
          "aragon": lambda v, r: aragon.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], ARA),
          "cyl": lambda v, r: cyl.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], CYL),
          "murcia": lambda v, r: murcia.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], MUR),
          "alicante": lambda v, r: valencia.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], VLC,
                                                     "03014", "A"),
          "valencia": lambda v, r: valencia.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], VLC),
          "canarias": lambda v, r: canarias.classify(v["registration_raw"], v["lat"], v["lon"], v["room_type"], v["min_nights"], CAN)}
    # Basque Country (Bilbao, Donostia): the REATE; flats and rooms placed from their addresses where we can
    ep = [os.path.join(CACHE, "euskadi", n) for n in euskadi.SOURCES]
    gp = os.path.join(CACHE, "euskadi", "geocoded.json")
    EUS = euskadi.load_register(ep, json.load(open(gp)) if os.path.exists(gp) else None) if os.path.exists(ep[0]) else {}
    prov += [x for x in euskadi.as_register_records(EUS, [A["ia_muni"] for A in AREAS if A.get("region") == "euskadi"])
             if x["objects_type_id"] in register.TOURIST_ACCOMMODATION_TYPES]
    # A region whose register couldn't be loaded (no fresh download and no cached copy) keeps what was published last time
    MISSING = {r for r, d in {"catalunya": CAT, "baleares": BAL, "euskadi": EUS, "valencia": VLC, "madrid": MAD, "aragon": ARA,
                               "cyl": CYL, "murcia": MUR, "canarias": CAN}.items() if not d}
    prev = previous_published() if MISSING else {}
    if MISSING:
        print("registers missing this run (previous figures kept):", ", ".join(sorted(MISSING)))
    agg = buildings.Aggregator()
    agg_ids = {id(x): agg.add(x) for x in prov}

    # ---- Airbnb listings, per city (Inside Airbnb snapshot + our live checks)
    LIST = {}
    for A in AREAS:
        if A["listings"] and A.get("parent"):   # Palma: its parent's classified listings inside the municipality
            if A["parent"] in LIST:
                LIST[A["slug"]] = sub_listings(LIST[A["parent"]], BAR.get(A["parent"]), A["ia_muni"])
            continue
        if A["listings"]:
            d_, rows_ = area_snapshot(A)
            p_ = snapshot.latest_local(CACHE, A.get("ia", A["slug"]))[1]
            rg_ = A.get("region")
            if not rows_ or (rg_ == "catalunya" and not CAT) or (rg_ == "baleares" and not BAL) or (rg_ == "euskadi" and not EUS) \
                    or (rg_ == "valencia" and not VLC):
                print(f"{A['slug']}: no register or listings in the cache; skipped")
                continue
            bal = (BAL, baleares.MuniEdges(os.path.join(os.path.dirname(p_), "neighbourhoods.geojson"))) if rg_ == "baleares" else None
            LIST[A["slug"]] = (rows_, d_, *classify_listings(index, official, mx, d_, rows_, state.load(state_path(A["slug"])), A.get("home"),
                                                             CAT if rg_ == "catalunya" else None, bal, EUS if rg_ == "euskadi" else None,
                                                             FN.get(rg_)))

    os.makedirs(SITE_DATA, exist_ok=True)

    def w(name, obj):
        p = os.path.join(SITE_DATA, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    barrio_rent, city_rent, ryears = serpavi_barrios(BAR["malaga"], parcel_pts) if "malaga" in BAR else ({}, None, None)   # SERPAVI sections: Málaga only for now
    areas_out, hist_areas, hist_listings, listing_stats, conc, summaries, rk_extra, kept, sample_items = [], {}, {}, None, {}, {}, {}, set(), {}
    for A in AREAS:
        if A.get("region") in MISSING and A["slug"] in prev.get("areas", {}) and os.path.exists(os.path.join(SITE_DATA, A["slug"], "summary.json")):
            summaries[A["slug"]] = json.load(open(os.path.join(SITE_DATA, A["slug"], "summary.json"), encoding="utf-8"))
            areas_out.append(prev["areas"][A["slug"]])
            hist_areas[A["slug"]] = prev["areas"][A["slug"]].get("vut")
            kept.add(A["slug"])
            print(f"{A['slug']}: register missing this run; keeping the previously published figures")
            continue
        barrios = BAR.get(A["slug"])
        _rows, a_snap, out, removed, by_key = LIST.get(A["slug"], (None, None, [], 0, {}))
        has_l = A["listings"] and A["slug"] in LIST   # a listing city whose data didn't load this time is built without listings
        recs_a = [x for x in prov if A["match"](x)]
        vut_a = [x for x in recs_a if x.get("objects_type_id") == buildings.VUT]
        ids_a = {agg_ids[id(x)] for x in recs_a}
        reg = registered_summary(recs_a, agg_ids, agg)
        census = A["kind"] == "region" or A.get("census")   # "% of homes" from the INE census, not the Catastro
        mks = set() if census else {m for m in muni_homes if muni_prov.get(m) == CATASTRO_PROVINCE} if A["kind"] == "province" \
            else {buildings.muni_key(A["catastro"][2])} if A.get("catastro") else {buildings.muni_key(x.get("municipalities")) for x in recs_a}
        pcode = A["ine"][5:] if A["ine"].startswith("prov:") else None
        in_area = (lambda c_: c_ == A["ine"]) if A["kind"] == "city" else (lambda c_: c_[:2] == pcode) if pcode \
            else (lambda c_: c_[:2] in ANDALUSIA_INE)   # a census city: just it; a province; the region: Andalucía only
        area_homes = sum(ine_census_homes(m) or 0 for c_, m in I["munis"].items() if in_area(c_)) if census \
            else sum(muni_homes[m] for m in mks)
        if area_homes:
            reg.update(homes=area_homes, vut_share=round(100 * reg["vut"] / area_homes, 2))
        im = I["province"] if A["ine"] == "province" else ine_region(I) if A["ine"] == "region" else ine_mallorca(I) if A["ine"] == "mallorca" \
            else (I.get("provinces") or {}).get(pcode) if pcode else I["munis"].get(A["ine"])
        if im and im.get("homes") is not None:
            reg.update(ine_homes=int(im["homes"]), ine_pct=im.get("pct"), ine_period=I["period"])
        for t in reg["top_buildings"]:
            t[6] = homes.get(t[0])
            if barrios is not None:
                t[9] = barrios.lookup(t[4], t[5])[1]
        write_csv(os.path.join(SITE_DATA, A["slug"], "edificios.csv"), [
            {"name": t[7], "place": t[9] or t[8], "vut": t[2], "places": t[3], "homes": t[6],
             "vut_share": round(100 * t[2] / t[6], 1) if t[6] else None} for t in reg["top_buildings"] if t[2] >= 10],
            BUILDING_CSV_COLS)
        reg["top_buildings"] = reg["top_buildings"][:200]
        summary = {"slug": A["slug"], "registered": reg, "has_listings": has_l, "cap": A.get("cap"),
                   "register": REGISTERS[A.get("region", "andalucia")],
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
        if has_l:
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
                    if has_l:
                        p["ashare"] = round(100 * c["ent"] / c["homes"], 1)
            if c["n"] >= MIN_LISTINGS_HEX:
                p.update(n=c["n"], nv=c["nv"], pct=round(100 * c["nv"] / c["n"]))
            if c["reg"] or "n" in p:
                hfeats.append({"type": "Feature", "properties": p,
                               "geometry": {"type": "Polygon", "coordinates": [hexg.polygon(q, r_)]}})
        w(f"{A['slug']}/hex.geojson", {"type": "FeatureCollection", "features": hfeats})
        if not has_l and A["slug"] in SAMPLE_TOWNS and os.path.exists(sample_path(A["slug"])):
            w(f"{A['slug']}/listings_hex.geojson", frame_hexes(json.load(open(sample_path(A["slug"])))["frame"], hexg, hx))
        # concentration (for the ranking): share of homes in ~150 m areas where registered flats exceed 10% of homes
        tot_ = sum(f["properties"].get("homes") or 0 for f in hfeats)
        if tot_ and A["kind"] == "city":
            conc[A["slug"]] = (round(100 * sum(f["properties"]["homes"] for f in hfeats if (f["properties"].get("share") or 0) > 10) / tot_, 1), "area")
        if has_l:
            w(f"{A['slug']}/dots.json", listing_dots(out, hexg))
        # small dot-density preview for cards and teasers: hex centres [lon, lat, flats, % not valid or -1]
        pv = []
        for f in hfeats:
            ring = f["geometry"]["coordinates"][0][:6]
            p = f["properties"]
            if p["reg"] or "pct" in p:
                pv.append([round(sum(c[0] for c in ring) / 6, 4), round(sum(c[1] for c in ring) / 6, 4), p["reg"], p.get("pct", -1)])
        w(f"{A['slug']}/preview.json", pv)

        if has_l:
            summary["listings"] = listing_summary(out, removed, by_key, vut_a)
            if A["slug"] == "malaga":
                listing_stats = summary["listings"]
            hist_listings[A["slug"]] = {k: summary["listings"][k] for k in ("listings", "live_checked")} | {
                "not_valid": summary["listings"]["verdicts"]["NOT_VALID"], "snapshot": a_snap}
            ent = sum(1 for o in out if o["entire"])
            summary["listings"].update(entire=ent, **({"entire_share": round(100 * ent / area_homes, 2)} if area_homes else {}))

        # towns without Inside Airbnb data: our own list of the town's listings (locations) and its live-checked random sample
        frame, smp_bar = None, {}
        if A["slug"] in SAMPLE_TOWNS and os.path.exists(sample_path(A["slug"])):
            fn_ = FN.get(A["slug"]) or FN.get(A.get("region"))
            judge = (lambda v, f_=fn_: f_(v, None)["category"]) if fn_ \
                else (lambda v, h=A["home"]: classify.classify(v, index, official, mx, h)["category"])
            summary["sample"] = sample_summary(sample_path(A["slug"]), judge)
            if barrios is not None:
                smp_bar = sample_by_barrio(sample_path(A["slug"]), summary["sample"], barrios)
            summary["sample"].pop("_ids")
            sample_items[A["slug"]] = summary["sample"].pop("_items")
            areas_extra = {"sample_pct": summary["sample"]["not_valid_pct"], "sample_checked": summary["sample"]["checked"]}
            if not has_l:
                frame = [(r_[1], r_[2]) for r_ in json.load(open(sample_path(A["slug"])))["frame"]]
        else:
            areas_extra = {}

        if barrios is not None:
            bstats = defaultdict(Counter)
            for la, lo in frame or ():   # listings per barrio from our list (no verdicts: only the sample has those)
                bstats[barrios.lookup(la, lo)[0]]["frame"] += 1
            for o in out:
                bid, _ = barrios.lookup(o["lat"], o["lon"])
                bstats[bid]["n"] += 1
                bstats[bid]["entire"] += o["entire"]
                bstats[bid][o["verdict"]] += 1
                bstats[bid][o["cat"]] += 1
            breg = defaultdict(Counter)
            # Mallorca's sub-areas are its municipalities: count each entry in its registered one (half have no point)
            by_muni = {baleares.muni(f["properties"]["name"]): f["properties"]["id"] for f in barrios.features} \
                if A.get("region") == "baleares" and A["subareas"] == "municipality" else {}
            # Registered flats by barrio need the register's coordinates: where most have none (Zaragoza, Palma…), counting
            # only the located ones would undercount, so those barrios get no registered figures ("sin datos")
            located = by_muni or not vut_a or sum(1 for x in vut_a if x.get("lat") is not None) / len(vut_a) >= MIN_LINKED
            if not located:
                print(f"{A['slug']}: {sum(1 for x in vut_a if x.get('lat') is not None)} of {len(vut_a)} registered flats located:"
                      " no registered figures by barrio")
            for x in vut_a:
                if by_muni.get(baleares.muni(x.get("municipalities"))) is not None:   # Mallorca: by its registered municipality
                    bid = by_muni[baleares.muni(x["municipalities"])]
                    breg[bid]["vut"] += 1
                    breg[bid]["places"] += x.get("tot_gen_places") or 0
                elif x.get("lat") is not None:
                    bid, _ = barrios.lookup(x["lat"], x["lon"])
                    breg[bid]["vut"] += 1
                    breg[bid]["places"] += x.get("tot_gen_places") or 0
            for m in mks:
                for la, lo, dw in parcel_pts.get(m, ()):
                    bid, _ = barrios.lookup(la, lo)
                    breg[bid]["homes"] += dw
            if A.get("region") == "euskadi":   # no Catastro in Euskadi: census 2021 homes per barrio (pipeline/inputs)
                hb = json.load(open(os.path.join(PIPE, "inputs", "euskadi_homes_per_barrio_2021.json")))[A["slug"]]["homes"]
                for f in barrios.features:
                    breg[f["properties"]["id"]]["homes"] = hb.get(f["properties"]["name"], 0)
            feats, rows_ = [], []
            for f in barrios.features:
                bid = f["properties"]["id"]
                s, rg = bstats.get(bid, Counter()), breg.get(bid, Counter())
                p = {"id": bid, "name": f["properties"]["name"], "listings": s["n"] if has_l else s["frame"] if frame is not None else None,
                     "vut": rg["vut"] if located else None, "places": rg["places"] if located else None}
                if f["properties"].get("group") and A["slug"] in boundaries.SOURCES:   # the council's district, for the table
                    p["district"] = f["properties"]["group"]
                if rg["homes"]:
                    p["homes"] = rg["homes"]
                    if rg["homes"] >= MIN_HOMES_BARRIO:
                        if located:
                            p["vut_share"] = round(100 * rg["vut"] / rg["homes"], 1)
                        if has_l:
                            p["airbnb_share"] = round(100 * s["entire"] / rg["homes"], 1)
                        elif frame is not None:   # all listings (our list has no room type), not entire homes only
                            p["listings_per_100"] = round(100 * s["frame"] / rg["homes"], 1)
                if has_l:
                    p["airbnb_entire"] = s["entire"]
                sb = smp_bar.get(bid)
                if sb:
                    p["sample_checked"] = sb["n"]
                    if sb["n"] >= MIN_SAMPLE_BARRIO:
                        p.update(not_valid_pct=round(100 * sb["NOT_VALID"] / sb["n"], 1), not_valid_ci=wilson(sb["NOT_VALID"], sb["n"]))
                if A["slug"] == "malaga" and bid in barrio_rent:
                    p.update(barrio_rent[bid])
                if has_l and s["n"] >= MIN_LISTINGS_AREA:
                    p.update(not_valid_pct=round(100 * s["NOT_VALID"] / s["n"], 1),
                             no_number=s["NO_CODE_IN_SCOPE"],
                             bad_number=s["NOT_IN_REGISTER"] + s["MALFORMED"] + s["FOUND_OTHER_MUNICIPALITY"] + s["CANCELLED_OFFICIAL"],
                             shared=s["VALID_CODE_SHARED"], valid=s["VALID"], exempt=s["POSSIBLY_EXEMPT"])
                feats.append({**f, "properties": p})
                if p["vut"] or p["listings"] or (not located and p.get("homes")):
                    rows_.append(p)
            w(f"{A['slug']}/barrios.geojson", {"type": "FeatureCollection", "features": feats})
            summary["subareas"] = {"kind": "barrio" if A["subareas"] == "barrio" else A["subareas"],
                                   "rows": sorted(rows_, key=lambda p: -p["vut"] if located else -(p["listings"] or 0))}
            if A["slug"] in boundaries.SOURCES:   # official outlines we fetch (rta_audit/boundaries.py): which, and whose
                summary["subareas"].update(level=boundaries.SOURCES[A["slug"]]["level"], source=boundaries.label(A["slug"]))
            if not located:
                summary["subareas"]["vut_located"] = False
            if frame is not None:
                summary["subareas"].update(listings_from="frame", min_sample=MIN_SAMPLE_BARRIO)
            if A.get("census") and A["kind"] == "city":   # no Catastro grid: concentration by barrio instead (census homes)
                th = sum(p.get("homes") or 0 for p in rows_)
                if th:
                    conc[A["slug"]] = (round(100 * sum(p.get("homes") or 0 for p in rows_ if (p.get("vut_share") or 0) > 10) / th, 1), "barrio")
        else:
            sk = "locality" if A["subareas"] == "barrio" else A["subareas"]   # barrios missing this time: postcodes instead
            summary["subareas"] = {"kind": sk, "rows": subarea_rows(sk, recs_a, muni_homes, ine_by_key,
                                                                              census=census)}
        rent = rent_comparison(A, recs_a, out, parcel_pts, I, ine_by_key, muni_homes, barrios,
                               summary["subareas"]["rows"] if barrios is not None else None, city_rent, ryears)
        if rent:
            summary["rent"] = rent
        w(f"{A['slug']}/summary.json", summary)
        summaries[A["slug"]] = summary
        # ---- ranking extras (Spain's ten largest cities): the most affected circle 1 km across, and buildings
        if any(x[2] == A["slug"] for x in RANKING):   # (Palma has had its own area since Oct 2026: no special case)
            vut_m, mk_, out_m = vut_a, mks, out
            hp = [p_ for m_ in mk_ for p_ in parcel_pts.get(m_, ())]
            if not hp and A.get("census") and barrios is not None:
                cen = A["center"][::-1]
                hp = census_home_points(barrios, {p_["id"]: p_.get("homes") or 0 for p_ in summary["subareas"]["rows"]}, cen)
            if has_l:
                lp = [(o["lat"], o["lon"]) for o in out_m]
            elif A["slug"] in SAMPLE_TOWNS and os.path.exists(sample_path(A["slug"])):
                lp = [(r_[1], r_[2]) for r_ in json.load(open(sample_path(A["slug"])))["frame"]]
            else:
                lp = []
            place_of = (lambda la, lo, b=barrios: b.lookup(la, lo)[1]) if barrios is not None else None
            rk = peak_metrics(hp, lp, [(x["lat"], x["lon"]) for x in vut_m if x.get("lat") is not None], len(vut_m), place_of,
                              lambda la, lo, v=vut_m: postcode_place(v, la, lo) or near_place(la, lo))
            rk.update(building_shares(homes, ref_muni, ref_pts, mk_, vut_m, agg_ids))
            # registration verification: every listing (Inside Airbnb cities) or the live-checked random sample (towns)
            if has_l:
                rk["_verif"] = ([(o["cat"], o["verdict"]) for o in out_m],
                                {"source": "full", "date": a_snap, "live_checked": sum(1 for o in out_m if o["basis"] == "live")})
            elif A["slug"] in sample_items:
                sm_ = summary["sample"]
                rk["_verif"] = (sample_items[A["slug"]], {"source": "sample", "checked": sm_["checked"],
                                                          "target": min(PINDEX_CFG["sample_target"], sm_["frame"]),
                                                          "date": (sm_.get("last_checked") or "")[:10], "frame": sm_["frame"]})
            rk_extra[A["slug"]] = rk
        write_csv(os.path.join(SITE_DATA, A["slug"], "zonas.csv"), summary["subareas"]["rows"])
        hist_areas[A["slug"]] = reg["vut"]
        areas_out.append({k: A[k] for k in ("slug", "name", "kind", "center", "zoom", "hex_m", "subareas")} | {
            "has_listings": has_l, "has_barrios": barrios is not None, "population": AREA_POPULATION.get(A["slug"]), "has_map": A.get("map", True) and (any(x.get("lat") is not None for x in recs_a) or bool(has_l)), "cap": A.get("cap"), "census": bool(census), "vut": reg["vut"], "vut_places": reg["vut_places"],
            "homes": reg.get("homes"), "vut_share": reg.get("vut_share"), "ine_homes": reg.get("ine_homes"),
            "ine_pct": reg.get("ine_pct"), "ine_period": reg.get("ine_period"), **areas_extra,
            **({"listings": summary["listings"]["listings"], "not_valid": summary["listings"]["verdicts"]["NOT_VALID"],
                "live_checked": summary["listings"]["live_checked"]}
               if has_l else {})})

    built = now()
    w("areas.json", {"built_at": built, "areas": areas_out})
    write_spain_map(w, areas_out)
    rk_ = ranking(I, summaries, conc, built, rk_extra, kept, prev.get("ranking", {}))
    w("ranking.json", rk_)
    w("index_history.json", index_history(rk_, os.path.join(SITE_DATA, "index_history.json")))
    w("home.json", home_stats(rk_, summaries))

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
    OWN = {k: v for k, v in LIST.items() if not AREA_BY_SLUG[k].get("parent")}   # (Palma's listings are Mallorca's)
    usage = {k: n_ for slug_, (_r, _d, _o, _rm, bk) in OWN.items() for k, v in bk.items()   # hosts (Mallorca: places) per shared code
             for n_ in [shared_count(v, places=AREA_REGION[slug_] == "baleares")] if n_ > 1}
    with gzip.open(os.path.join(FN_DATA, "lookup.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump({"built_at": built, "register_lastUpdateData": meta["lastUpdateData"], "max_issued":
                   {f"{p}/{v}": n_ for (p, v), n_ in mx.items()}, "codes": idx, "shared": usage,
                   # listings with a minimum stay of 60+ nights (seasonal lets): the advert page doesn't show it
                   # (Andalucía: 60+ nights; Catalonia: more than 31 days is seasonal)
                   "long_stay": sorted(r["id"] for slug_, (rs, *_) in OWN.items() for r in rs
                                       if int(r["minimum_nights"] or 0) >= REGISTERS[AREA_REGION[slug_]]["seasonal_nights"]),
                   # listings that say "seasonal" but whose recorded minimum stay is shorter: the claim doesn't count
                   "seasonal_short": sorted(r["id"] for slug_, (rs, *_) in OWN.items() for r in rs
                                            if r["minimum_nights"] and re.search(r"(?i)(exempt|exento)[^<|]*(seasonal|temporada)", r["license"] or "")
                                            and int(r["minimum_nights"]) < REGISTERS[AREA_REGION[slug_]]["seasonal_nights"]),
                   # Catalonia (province of Barcelona): HUTB/HB/ATB numbers → [municipality, lat, lon, group]
                   "cat": {k: [v.get("municipi"), round(v["lat"], 5) if v.get("lat") else None, round(v["lon"], 5) if v.get("lon") else None,
                               "C" if k.startswith("HUTB") else ""] for k, v in CAT.items()},
                   # Basque Country: EBI/LSS/HBI… numbers → [municipality, lat, lon, group (C whole flat, H rooms)]
                   "eus": {k: [v.get("muni"), round(v["lat"], 5) if v.get("lat") else None, round(v["lon"], 5) if v.get("lon") else None,
                               (v.get("group") or "")[:1]] for k, v in EUS.items()},
                   # Canarias: VV-35-1-0012345 → [municipality, lat, lon, group]; "can_short": old / short forms → key
                   "can": {k: [v.get("muni"), round(v["lat"], 5) if v.get("lat") else None, round(v["lon"], 5) if v.get("lon") else None, ""]
                           for k, v in CAN.items() if k != "_short" and v.get("muni") and canarias._same_muni(v["muni"], "Las Palmas De Gran Canaria")
                           or (k != "_short" and k.split("-")[1:3] == ["35", "1"])},
                   "can_short": {s: k for s, k in (CAN.get("_short") or {}).items() if k.split("-")[1:3] in (["35", "1"], ["", ""])},
                   # Comunidad de Madrid: VT-12345 → [municipality, lat, lon, group]
                   "mad": {k: [v.get("muni"), round(v["lat"], 5) if v.get("lat") else None, round(v["lon"], 5) if v.get("lon") else None,
                               "C" if k.startswith("VT") else ""] for k, v in MAD.items()},
                   # Aragón: VU-ZA-18-101 → key ZA-18-101 → [municipality (Zaragoza or other), lat, lon, group]
                   "ara": {k: ["Zaragoza" if v["zaragoza"] else v["locality"].title(), None, None, "C"] for k, v in ARA.items()},
                   # Castilla y León: 47/547 → [municipality (one in the town if any entry with the number is), lat, lon, group]
                   "cyl": {k: (lambda h: [h["muni"], round(h["lat"], 5) if h.get("lat") else None, round(h["lon"], 5) if h.get("lon") else None,
                                          "C" if h["flat"] else ""])(next((r for r in rs if cyl._muni(r["muni"]) == "VALLADOLID"), rs[0]))
                           for k, rs in CYL.items()},
                   # Región de Murcia: VV.MU.6415-1 → [municipality (Murcia or other), lat, lon, group]
                   "mur": {k: ["Murcia" if v["in_murcia"] else "", round(v["lat"], 5) if v.get("lat") else None,
                               round(v["lon"], 5) if v.get("lon") else None, ""] for k, v in MUR.items() if k != "_filing"},
                   "mur_filing": MUR.get("_filing", {}),
                   # Comunitat Valenciana: CV-VUT0012345-V → [municipality, lat, lon, group]
                   "vlc": {k: [v.get("muni"), round(v["lat"], 5) if v.get("lat") else None, round(v["lon"], 5) if v.get("lon") else None,
                               "C"] for k, v in VLC.items()},
                   # Mallorca: ETV/ETVPL/VT/H… numbers → [municipality, lat, lon, group]
                   "bal": {k: [v.get("municipi"), round(v["lat"], 5) if v.get("lat") else None, round(v["lon"], 5) if v.get("lon") else None,
                               "C" if k.split("/")[0] in ("ETV", "ETVPL", "VT") else ""] for k, v in BAL.items()},
                   # date only: the source note describes a private document and stays in the private state
                   "cancelled": {k: {"date": v.get("cancel_date")} for k, v in official.items()
                                 if v.get("status") == "cancelled"}},
                  fh, ensure_ascii=False, separators=(",", ":"))
    if MISSING and prev.get("lookup"):   # keep the missing regions' number lists from the last build
        L2 = json.load(gzip.open(os.path.join(FN_DATA, "lookup.json.gz"), "rt", encoding="utf-8"))
        for r_ in MISSING:
            for k_ in LOOKUP_KEYS[r_]:
                if not L2.get(k_) and prev["lookup"].get(k_):
                    L2[k_] = prev["lookup"][k_]
        for k_ in ("long_stay", "seasonal_short"):
            L2[k_] = sorted(set(L2.get(k_) or []) | set(prev["lookup"].get(k_) or []))
        with gzip.open(os.path.join(FN_DATA, "lookup.json.gz"), "wt", encoding="utf-8") as fh:
            json.dump(L2, fh, ensure_ascii=False, separators=(",", ":"))

    clean = lambda v: " ".join(str(v).split()) if v not in (None, "", "-") else ""
    srows = []
    MUNI_AREA = {A["home"]: A["slug"] for A in AREAS if A.get("home") and A["slug"] in BAR}   # barrio names in search results
    PROV_CODE = {"BARCELONA": "B", "ILLES BALEARS": "IB", "BIZKAIA": "BI", "GIPUZKOA": "SS", "VALENCIA": "V", "LAS PALMAS": "GC", "MURCIA": "MU", "ZARAGOZA": "Z", "MADRID": "M", "ALICANTE": "A", "VALLADOLID": "VA", "ALMERÍA": "AL", "CÁDIZ": "CA", "CÓRDOBA": "CO", "GRANADA": "GR", "HUELVA": "HU", "JAÉN": "JA",
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
    if MISSING and prev.get("search"):   # keep the missing regions' register rows from the last build
        codes_ = {c for r_ in MISSING for c in SEARCH_PROV[r_]}
        srows += [r_ for r_ in prev["search"] if r_ and r_[-1] in codes_]
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
    p = sp.add_parser("refresh")
    p.add_argument("--catastro-minutes", type=float, default=120, help="stop Catastro downloads after this long (next run continues)")
    p.set_defaults(f=cmd_refresh)
    p = sp.add_parser("recheck")
    p.add_argument("--budget", default="auto", help='listings to re-check, or "auto" (all of the city about once a month)')
    p.add_argument("--city", default="malaga", choices=LISTING_CITIES, help="which city's listings to re-check")
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
