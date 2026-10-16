"""List every Airbnb listing in a town from Airbnb's public search pages, to sample from.

Inside Airbnb only covers Málaga and Sevilla in Andalucía. For other towns we build the list ourselves, the way Inside Airbnb
does: Airbnb's map search returns at most 15 pages of 18 results (270) per area, so we split the town's bounding box into
quarters until every square has fewer, then read all its pages. A search without dates covers every bookable listing (each
result carries its own next-available dates, from days to months ahead), not just those free on particular dates.

Polite: one request at a time with the same per-host delay as the listing checks (http.DELAYS), no login, stops if blocked.
"""
import base64
import json
import re
from urllib.parse import urlencode

from . import http

SEARCH = "https://www.airbnb.co.uk/s/homes"
MAX_PAGES = 15        # Airbnb's cap: 15 pages x 18 results
MIN_SPAN = 0.0015     # ~150 m: don't split smaller than this (a very dense block); keep what we get and say so


def _stays_search(html):
    blobs = re.findall(r'<script[^>]*id="data-deferred-state[^"]*"[^>]*>(.*?)</script>', html, re.S)
    for b in blobs:
        stack = [json.loads(b)]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if "staysSearch" in o:
                    return o["staysSearch"]
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return None


def _listing_id(enc):
    try:
        s = base64.b64decode(enc).decode()
        return s.split(":", 1)[1] if s.startswith("DemandStayListing:") else None
    except Exception:  # noqa: BLE001
        return None


def page(box, cursor=None):
    """One search page for box = (south, west, north, east). Returns (listings, cursors) where listings are
    [{id, lat, lon, title}] and cursors the list of page cursors (len == MAX_PAGES means the area is capped)."""
    s, w, n, e = box
    q = {"ne_lat": f"{n:.5f}", "ne_lng": f"{e:.5f}", "sw_lat": f"{s:.5f}", "sw_lng": f"{w:.5f}", "search_by_map": "true",
         "search_type": "user_map_move", "refinement_paths[]": "/homes"}
    if cursor:
        q["cursor"] = cursor
    r = http.get(f"{SEARCH}?{urlencode(q)}", timeout=60, headers={"accept-language": "es-ES,es;q=0.9"})
    ss = _stays_search(r.text)
    if ss is None:
        raise http.Blocked("search page without results data")
    out = []
    for res in (ss.get("results") or {}).get("searchResults") or []:
        d = res.get("demandStayListing") or {}
        lid = _listing_id(d.get("id") or "")
        c = ((d.get("location") or {}).get("coordinate") or {})
        if lid and c.get("latitude") is not None:
            out.append({"id": lid, "lat": c["latitude"], "lon": c["longitude"], "title": res.get("title")})
    cursors = (((ss.get("results") or {}).get("paginationInfo") or {}).get("pageCursors")) or []
    return out, cursors


def enumerate_box(box, log=print):
    """All listings in box (dict id -> listing), splitting capped areas into quarters. Also returns the boxes that were
    still capped at the minimum size (their count is a floor)."""
    found, capped, todo = {}, [], [box]
    while todo:
        b = todo.pop()
        first, cursors = page(b)
        s, w, n, e = b
        if len(cursors) >= MAX_PAGES and (n - s) > MIN_SPAN and (e - w) > MIN_SPAN:
            ms, mw = (s + n) / 2, (w + e) / 2
            todo += [(s, w, ms, mw), (s, mw, ms, e), (ms, w, n, mw), (ms, mw, n, e)]
            log(f"split {b} ({len(todo)} areas queued)")
            continue
        for x in first:
            found[x["id"]] = x
        for c in cursors[1:]:
            more, _ = page(b, c)
            if not more:
                break
            for x in more:
                found[x["id"]] = x
        if len(cursors) >= MAX_PAGES:
            capped.append(b)
        log(f"area {tuple(round(v, 4) for v in b)}: {len(found)} listings so far")
    return found, capped
