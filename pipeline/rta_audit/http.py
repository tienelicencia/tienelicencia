"""Polite HTTP: randomised delay between requests to the same host, retries with backoff."""
import random
import time
from urllib.parse import urlparse

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"})
_last = {}
DELAYS = {"www.airbnb.co.uk": (6.0, 12.0)}  # seconds, per host; others default to small


class Blocked(Exception):
    pass


def _wait(host):
    lo, hi = DELAYS.get(host, (0.5, 1.5))
    gap = random.uniform(lo, hi)
    since = time.time() - _last.get(host, 0)
    if since < gap:
        time.sleep(gap - since)
    _last[host] = time.time()


def get(url, retries=4, ok_status=(200,), final_status=(404, 410), **kw):
    """Return response. Status in final_status is returned without retrying.
    403/429 after retries raises Blocked so the caller can stop the run."""
    host = urlparse(url).netloc
    kw.setdefault("timeout", 45)
    for attempt in range(retries + 1):
        _wait(host)
        try:
            r = _session.get(url, **kw)
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(min(120, 5 * 2 ** attempt) + random.uniform(0, 3))
            continue
        if r.status_code in ok_status or r.status_code in final_status:
            return r
        if attempt == retries:
            if r.status_code in (403, 429):
                raise Blocked(f"{r.status_code} from {host}")
            r.raise_for_status()
            return r
        time.sleep(min(300, 10 * 2 ** attempt) + random.uniform(0, 5))
    return r


def head(url, **kw):
    kw.setdefault("timeout", 45)
    kw.setdefault("allow_redirects", True)
    _wait(urlparse(url).netloc)
    return _session.head(url, **kw)
