"""Fetch a live Airbnb listing page (plain HTTP, no login, no CAPTCHA handling) or read a saved
HTML file, and extract the fields we need. Airbnb embeds the page data as JSON in
<script id="data-deferred-state-0">; the 'Registration details' section lives there."""
import gzip
import json
import os
import re
from datetime import datetime, timezone

from . import http

URL = "https://www.airbnb.co.uk/rooms/{}"


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _first(pattern, h, group=1):
    m = re.search(pattern, h)
    return m.group(group) if m else None


def extract(h, listing_id):
    out = {"listing_id": str(listing_id)}
    blobs = []
    for m in re.finditer(r'<script[^>]*id="data-(?:deferred-state|injector-instances)[^"]*"[^>]*>(.*?)</script>', h, re.S):
        try:
            blobs.append(json.loads(m.group(1)))
        except ValueError:
            pass
    reg_texts, desc = [], None
    for b in blobs:
        for d in _walk(b):
            t = d.get("title")
            if isinstance(t, str) and re.match(r"(?i)registration details|detalles del registro|licen[cs]e", t):
                html = (d.get("html") or {}).get("htmlText")
                if html:
                    reg_texts.append(html)
            if d.get("__typename") == "PdpSharingConfig" and d.get("propertyType"):
                out["property_type"] = d.get("propertyType")
                out["title_summary"] = d.get("title")
            if d.get("__typename") == "DemandStayListingLocation":
                c = d.get("coordinate") or {}
                out["lat"], out["lon"] = c.get("latitude"), c.get("longitude")
            if d.get("__typename") == "StaysPdpLocation" and d.get("subtitle"):
                out["advertised_location"] = d.get("subtitle")
            if d.get("__typename") == "DemandStayListingDescription" and not desc:
                name = (d.get("name") or {}).get("localizedStringWithTranslationPreference")
                if name:
                    out["title"] = name
    # Fallbacks from flat HTML
    out.setdefault("lat", _num(_first(r'"listingLat":(-?[\d.]+)', h)))
    out.setdefault("lon", _num(_first(r'"listingLng":(-?[\d.]+)', h)))
    out["room_type"] = _first(r'"listingLat":[^}]*?"roomType":"([^"]+)"', h)
    out["host_id"] = _first(r'"hostId":"(\d+)"', h)
    out["host_name"] = _first(r'Hosted by ([^"\\<]{1,60})', h)
    out.setdefault("title", _first(r'<meta property="og:description" content="([^"]{0,200})', h))
    if not reg_texts:
        # older layout: bold "Registration details" inside the description html
        m = re.search(r'Registration details\\u003c/b>(.*?)(?:\\u003cb>|"[,}])', h)
        if m:
            reg_texts.append(m.group(1).encode().decode("unicode_escape", errors="ignore"))
    out["registration_raw"] = "\n".join(dict.fromkeys(reg_texts)) or None
    out["page_ok"] = bool(out.get("host_id") or out.get("lat"))
    return out


def _num(s):
    try:
        return float(s) if s is not None else None
    except ValueError:
        return None


def fetch_live(listing_id, evidence_dir):
    """Return dict with status in {ok, removed, blocked, error, no_data}."""
    now = datetime.now(timezone.utc).isoformat()
    url = URL.format(listing_id)
    rec = {"listing_id": str(listing_id), "live_url": url, "live_fetched_at": now}
    try:
        r = http.get(url)
    except http.Blocked as e:
        rec.update(live_status="blocked", live_error=str(e))
        return rec
    except Exception as e:  # network etc.
        rec.update(live_status="error", live_error=repr(e)[:300])
        return rec
    rec["live_http_status"] = r.status_code
    if r.status_code in (404, 410):
        rec["live_status"] = "removed"
        return rec
    if "captcha" in r.text[:20000].lower() or "/login" in r.url:
        rec["live_status"] = "blocked"
        return rec
    return _finish(rec, r.text, listing_id, evidence_dir)


def from_saved_html(listing_id, path, evidence_dir, captured_at=None):
    h = open(path, encoding="utf-8", errors="replace").read()
    rec = {"listing_id": str(listing_id), "live_url": URL.format(listing_id),
           "live_fetched_at": captured_at or datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat(),
           "live_source": f"saved_html:{path}"}
    return _finish(rec, h, listing_id, evidence_dir)


def _finish(rec, h, listing_id, evidence_dir):
    d = extract(h, listing_id)
    rec.update(d)
    rec.setdefault("live_source", "http")
    rec["live_status"] = "ok" if d["page_ok"] else "no_data"
    if not evidence_dir:  # scheduled runs: keep only the extracted fields
        return rec
    os.makedirs(evidence_dir, exist_ok=True)
    stamp = rec["live_fetched_at"][:19].replace(":", "")
    hp = os.path.join(evidence_dir, f"live_{stamp}.html.gz")
    with gzip.open(hp, "wt", encoding="utf-8") as fh:
        fh.write(h)
    tp = os.path.join(evidence_dir, f"registration_{stamp}.txt")
    with open(tp, "w", encoding="utf-8") as fh:
        fh.write(f"listing_id: {listing_id}\nurl: {rec['live_url']}\ncaptured_at: {rec['live_fetched_at']}\n"
                 f"source: {rec['live_source']}\n\n--- raw registration section ---\n{d['registration_raw'] or '(none found)'}\n")
    rec["evidence_html"], rec["evidence_registration_txt"] = hp, tp
    return rec
