"""Rolling live-recheck state: one small record per listing (no page HTML), safe to commit.

state/listings_live.json = {listing_id: {checked_at, status, http, registration_raw, lat, lon,
                                         room_type, property_type, host_id}}
"""
import hashlib
import json
import os
from datetime import datetime, timezone

KEEP = ["live_status", "live_http_status", "registration_raw", "lat", "lon", "room_type", "property_type", "host_id"]


def load(path):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return {}


def save(path, st):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)


def record(st, rec):
    st[rec["listing_id"]] = {"checked_at": rec.get("live_fetched_at") or datetime.now(timezone.utc).isoformat(),
                             **{k: rec.get(k) for k in KEEP}}


def due(st, ids, budget):
    """Never-checked first, in a fixed random order (so the first N checked are a random sample of the city),
    then oldest-checked."""
    never = sorted((i for i in ids if i not in st), key=lambda i: hashlib.sha1(i.encode()).hexdigest())
    seen = sorted((i for i in ids if i in st), key=lambda i: st[i]["checked_at"])
    return (never + seen)[:budget]
