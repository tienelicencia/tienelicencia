"""Inside Airbnb snapshot discovery + download, per city. New snapshots appear roughly quarterly.
Málaga's files live in cache/insideairbnb/<date>/ (the original layout); other cities in cache/insideairbnb/<city>/<date>/."""
import os
import re

from . import http

INDEX = "https://insideairbnb.com/get-the-data/"
BASE = "https://data.insideairbnb.com/spain/{region}/{city}/{date}/{path}"
REGION = {"malaga": "andaluc%C3%ADa", "sevilla": "andaluc%C3%ADa", "barcelona": "catalonia", "mallorca": "islas-baleares", "euskadi": "pv"}   # Inside Airbnb's folders
REGION_RE = {"malaga": "andaluc[^/]*", "sevilla": "andaluc[^/]*", "barcelona": "catalonia", "mallorca": "islas-baleares", "euskadi": "pv"}


def _dir(cache_dir, city):
    return os.path.join(cache_dir, "insideairbnb") if city == "malaga" else os.path.join(cache_dir, "insideairbnb", city)


def latest_remote_date(city="malaga"):
    h = http.get(INDEX, timeout=60).text
    dates = re.findall(rf"spain/{REGION_RE[city]}/{city}/(\d{{4}}-\d{{2}}-\d{{2}})/data/listings\.csv\.gz", h)
    return max(dates) if dates else None


def local_dates(cache_dir, city="malaga"):
    d = _dir(cache_dir, city)
    if not os.path.isdir(d):
        return []
    return sorted(x for x in os.listdir(d) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", x)
                  and os.path.exists(os.path.join(d, x, "listings.csv.gz")))


def latest_local(cache_dir, city="malaga"):
    ds = local_dates(cache_dir, city)
    if not ds:
        return None, None
    return ds[-1], os.path.join(_dir(cache_dir, city), ds[-1], "listings.csv.gz")


def update(cache_dir, city="malaga"):
    """Download the newest snapshot if we don't have it. Returns (date, path, downloaded_bool)."""
    remote = latest_remote_date(city)
    have = local_dates(cache_dir, city)
    if remote and remote not in have:
        d = os.path.join(_dir(cache_dir, city), remote)
        os.makedirs(d, exist_ok=True)
        for path, name in (("data/listings.csv.gz", "listings.csv.gz"),
                           ("visualisations/neighbourhoods.geojson", "neighbourhoods.geojson")):
            r = http.get(BASE.format(region=REGION[city], city=city, date=remote, path=path), timeout=600)
            open(os.path.join(d, name), "wb").write(r.content)
        return remote, os.path.join(d, "listings.csv.gz"), True
    date, p = latest_local(cache_dir, city)
    return date, p, False
