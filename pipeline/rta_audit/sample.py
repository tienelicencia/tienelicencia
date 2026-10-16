"""Inside Airbnb snapshot loading and stratified sampling."""
import csv
import gzip
import math
import random
from collections import defaultdict

csv.field_size_limit(10 ** 9)

SNAPSHOT_FIELDS = ["id", "listing_url", "last_scraped", "name", "host_id", "host_name",
                   "neighbourhood_cleansed", "latitude", "longitude", "property_type", "room_type",
                   "minimum_nights", "maximum_nights", "license", "calculated_host_listings_count",
                   "number_of_reviews_ltm", "availability_365", "description"]


def load_snapshot(path):
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({k: r.get(k, "") for k in SNAPSHOT_FIELDS})
    return rows


def room_group(room_type):
    return "entire" if room_type == "Entire home/apt" else "room"


def stratified_sample(rows, n, seed, min_per_stratum=2):
    """Neighbourhood x (entire|room) strata. Allocation proportional to sqrt(N_h) so the
    centre (~2/3 of listings) doesn't dominate, with a floor of min_per_stratum (capped by N_h).
    Returns list of rows with stratum, stratum_N, stratum_n and design weight N_h/n_h."""
    strata = defaultdict(list)
    for r in rows:
        strata[(r["neighbourhood_cleansed"], room_group(r["room_type"]))].append(r)
    keys = sorted(strata)
    w = {k: math.sqrt(len(strata[k])) for k in keys}
    tot = sum(w.values())
    alloc = {k: min(len(strata[k]), max(min_per_stratum, round(n * w[k] / tot))) for k in keys}
    # adjust to exactly n: add/remove from largest strata with room
    while sum(alloc.values()) != n:
        diff = n - sum(alloc.values())
        order = sorted(keys, key=lambda k: -len(strata[k]))
        for k in order:
            if diff > 0 and alloc[k] < len(strata[k]):
                alloc[k] += 1
                break
            if diff < 0 and alloc[k] > min(min_per_stratum, len(strata[k])):
                alloc[k] -= 1
                break
    rng = random.Random(seed)
    out = []
    for k in keys:
        pool = sorted(strata[k], key=lambda r: r["id"])
        for r in rng.sample(pool, alloc[k]):
            out.append({**r, "stratum": f"{k[0]} | {k[1]}", "stratum_N": len(pool), "stratum_n": alloc[k],
                        "design_weight": round(len(pool) / alloc[k], 3)})
    rng.shuffle(out)  # so a partial run (e.g. first 8) spans strata
    return out, {f"{k[0]} | {k[1]}": (len(strata[k]), alloc[k]) for k in keys}
