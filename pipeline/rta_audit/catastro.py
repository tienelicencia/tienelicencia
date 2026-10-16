"""Dwellings per building from the Catastro INSPIRE Buildings dataset (open data, updated about once a year).

Each municipality is one zip (Málaga 34 MB, Marbella 23 MB) holding a large GML file. Every bu-ext2d:Building is
one cadastral parcel (gml localId = the 14-character parcel reference, the same key we group register entries by)
with numberOfDwellings. We stream that file once per new release and keep a compact per-parcel summary:

  cache/catastro/<code>.json = {"last_modified": ..., "parcels": {ref14: [dwellings, lat, lon, residential]}}

Note: the Catastro counts every dwelling unit (including empty and second homes), so shares computed against it are
indicative and won't exactly match a council's own count of "viviendas familiares"."""
import json
import os
import re
import zipfile
from datetime import datetime, timezone

from . import http
from .register import utm_to_wgs84

FEED = "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/{prov}/ES.SDGC.bu.atom_{prov}.xml"
ZIP = "https://www.catastro.hacienda.gob.es/INSPIRE/Buildings/{prov}/{code}-{name}/A.ES.SDGC.BU.{code}.zip"

_FEATURE = re.compile(r"<bu-ext2d:Building gml:id=\"ES\.SDGC\.BU\.([0-9A-Z]+)\">(.*?)</bu-ext2d:Building>", re.S)
_ENV = re.compile(r"<gml:lowerCorner>([\d.]+) ([\d.]+)</gml:lowerCorner>\s*<gml:upperCorner>([\d.]+) ([\d.]+)</gml:upperCorner>")
_DW = re.compile(r"<bu-ext2d:numberOfDwellings>(\d+)</bu-ext2d:numberOfDwellings>")
_USE = re.compile(r"<bu-ext2d:currentUse>([^<]+)</bu-ext2d:currentUse>")


def municipalities(prov="29"):
    """[(code, name)] from the province ATOM feed, e.g. ('29900', 'MALAGA')."""
    xml = http.get(FEED.format(prov=prov), timeout=120).text
    return re.findall(r"<title>\s*(\d{5})-([^<]+?) buildings\s*</title>", xml)


def parse_zip(path):
    """Stream the building GML inside a municipality zip → {ref14: [dwellings, lat, lon, residential]}."""
    out = {}
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(".building.gml"))
        buf, zone = "", None
        with z.open(name) as fh:
            while True:
                chunk = fh.read(1 << 22)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", "ignore")
                if zone is None:   # the file's grid: EPSG 25830 (Andalucía) or 25831 (Catalonia)
                    zm = re.search(r"EPSG:+258(\d\d)", buf)
                    zone = int(zm.group(1)) if zm else None
                last = 0
                for m in _FEATURE.finditer(buf):
                    ref, body = m.group(1)[:14], m.group(2)
                    e, d, u = _ENV.search(body), _DW.search(body), _USE.search(body)
                    if not e:
                        continue
                    x, y = (float(e.group(1)) + float(e.group(3))) / 2, (float(e.group(2)) + float(e.group(4))) / 2
                    lat, lon = utm_to_wgs84(x, y, zone or 30)
                    p = out.get(ref)
                    dw = int(d.group(1)) if d else 0
                    res = 1 if (u and u.group(1).startswith("1_residential")) else 0
                    if p:
                        p[0] += dw
                        p[3] = max(p[3], res)
                    else:
                        out[ref] = [dw, round(lat, 5), round(lon, 5), res]
                    last = m.end()
                buf = buf[last:] if last else buf[-(1 << 20):] if len(buf) > (8 << 20) else buf
    return out


def ensure(cache_dir, munis, prov="29", recheck_days=7):
    """Download/refresh the given municipalities [(code, name)] when Catastro publishes a new file (checked at most
    every `recheck_days`). The zip is deleted after parsing; only the compact JSON is kept. Returns {code: parcels}."""
    d = os.path.join(cache_dir, "catastro")
    os.makedirs(d, exist_ok=True)
    out, now = {}, datetime.now(timezone.utc)
    for code, name in munis:
        jp = os.path.join(d, f"{code}.json")
        url = ZIP.format(prov=prov, code=code, name=name)
        cached = json.load(open(jp)) if os.path.exists(jp) else None
        if cached and cached.get("checked_at") and (now - datetime.fromisoformat(cached["checked_at"])).days < recheck_days:
            out[code] = cached["parcels"]
            continue
        try:
            lm = http.head(url, timeout=60).headers.get("last-modified")
        except Exception:  # offline or Catastro down: keep what we have
            lm = cached and cached["last_modified"]
        if not cached or cached["last_modified"] != lm:
            zp = os.path.join(d, f"{code}.zip")
            if not os.path.exists(zp) or cached:   # reuse a zip downloaded by hand, else fetch
                r = http.get(url, timeout=1800, stream=True)
                with open(zp + ".part", "wb") as fh:
                    for c in r.iter_content(1 << 20):
                        fh.write(c)
                os.replace(zp + ".part", zp)
            cached = {"code": code, "name": name, "last_modified": lm, "parcels": parse_zip(zp)}
            os.remove(zp)
        cached["checked_at"] = now.isoformat(timespec="seconds")
        json.dump(cached, open(jp, "w"), separators=(",", ":"))
        out[code] = cached["parcels"]
    return out


def load_cached(cache_dir):
    """{code: parcels} for whatever has been fetched, without touching the network."""
    d = os.path.join(cache_dir, "catastro")
    out = {}
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                j = json.load(open(os.path.join(d, f)))
                out[j["code"]] = {"name": j["name"], "parcels": j["parcels"]}
    return out
