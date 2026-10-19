"""Barrio lookup (Ayuntamiento de Málaga open data, EPSG:25830), hexagon binning, building grouping."""
import json
import math
import os

from .buildings import street_name
from .register import utm30_to_wgs84

BARRIOS_URL = ("https://datosabiertos.malaga.eu/recursos/urbanismoEInfraestructura/planimetria/callejero/"
               "da_cartografiaBarrio-25830.geojson")

# Local equirectangular projection around Málaga: metres, accurate to <0.1% over the municipality.
LAT0 = 36.72
MX = 111320.0 * math.cos(math.radians(LAT0))
MY = 110574.0


def to_xy(lat, lon):
    return lon * MX, lat * MY


def to_ll(x, y):
    return y / MY, x / MX


def _rings(c):
    if isinstance(c[0][0], (int, float)):
        yield c
    else:
        for x in c:
            yield from _rings(x)


def _pip(lat, lon, ring):
    ins, j = False, len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


class Barrios:
    """Barrio polygons from Málaga's open data (EPSG:25830, NOMBARRIO/NUMBARRIO) or an Inside Airbnb
    neighbourhoods.geojson (WGS84, 'neighbourhood'; used for Sevilla, whose 108 neighbourhoods are the city's barrios)."""

    def __init__(self, path):
        g = json.load(open(path, encoding="utf-8"))
        self.polys, self.features = [], []
        for i, f in enumerate(sorted(g["features"], key=lambda f: f["properties"].get("neighbourhood") or ""), 1):
            pr = f["properties"]
            wgs84 = "neighbourhood" in pr
            name = pr["neighbourhood"] if wgs84 else street_name(pr.get("NOMBARRIO") or "")   # 'Pinares de San Antón', not '… De …'
            bid = i if wgs84 else pr.get("NUMBARRIO")
            rings_ll = []
            for rg in _rings(f["geometry"]["coordinates"]):
                ring = [(p[1], p[0]) for p in rg] if wgs84 else [utm30_to_wgs84(p[0], p[1]) for p in rg]
                rings_ll.append(ring)
                lats, lons = [p[0] for p in ring], [p[1] for p in ring]
                self.polys.append((bid, name, ring, (min(lats), max(lats), min(lons), max(lons))))
            # GeoJSON for the site, rounded to ~1 m, [lon, lat] order
            self.features.append({"type": "Feature", "properties": {"id": bid, "name": name,
                                                                    **({"group": pr["neighbourhood_group"]} if wgs84 and pr.get("neighbourhood_group") else {})},
                                  "geometry": {"type": "MultiPolygon", "coordinates": [
                                      [[[round(lo, 5), round(la, 5)] for la, lo in ring]] for ring in rings_ll]}})

    def lookup(self, lat, lon):
        for bid, name, ring, (a, b, c, d) in self.polys:
            if a <= lat <= b and c <= lon <= d and _pip(lat, lon, ring):
                return bid, name
        return None, None


def ensure_barrios(cache_dir):
    from . import http
    p = os.path.join(cache_dir, "barrios", "barrios.geojson")
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(http.get(BARRIOS_URL, timeout=120).content)
    return p


SECTIONS_URL = ("https://datosabiertos.malaga.eu/recursos/urbanismoEInfraestructura/planimetria/callejero/"
                "da_cartografiaSeccionCensal-25830.geojson")


class Sections:
    """Málaga census sections (Ayuntamiento open data, EPSG:25830). NUMSECCENSAL 8047 = district 08, section 047;
    the INE uses the same districts (code 29067 + DD), e.g. for its rent index."""

    def __init__(self, path):
        g = json.load(open(path, encoding="utf-8"))
        self.polys = []
        for f in g["features"]:
            pr = f["properties"]
            if pr.get("FECBAJA"):            # historic sections
                continue
            num = int(pr["NUMSECCENSAL"])
            for rg in _rings(f["geometry"]["coordinates"]):
                ring = [utm30_to_wgs84(p[0], p[1]) for p in rg]
                lats, lons = [p[0] for p in ring], [p[1] for p in ring]
                self.polys.append((num, ring, (min(lats), max(lats), min(lons), max(lons))))

    def lookup(self, lat, lon):
        """(district 1–11, section number) or (None, None)."""
        for num, ring, (a, b, c, d) in self.polys:
            if a <= lat <= b and c <= lon <= d and _pip(lat, lon, ring):
                return num // 1000, num
        return None, None


def ensure_sections(cache_dir):
    from . import http
    p = os.path.join(cache_dir, "barrios", "da_cartografiaSeccionCensal-25830.geojson")
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(http.get(SECTIONS_URL, timeout=120).content)
    return p


class Hex:
    """Pointy-top hexagons of a given circumradius (m) in the local projection."""

    def __init__(self, size_m=90):
        self.s = size_m

    def cell(self, lat, lon):
        x, y = to_xy(lat, lon)
        q = (math.sqrt(3) / 3 * x - y / 3) / self.s
        r = (2 / 3 * y) / self.s
        # cube rounding
        cx, cz = q, r
        cy = -cx - cz
        rx, ry, rz = round(cx), round(cy), round(cz)
        dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy > dz:
            ry = -rx - rz
        else:
            rz = -rx - ry
        return rx, rz

    def polygon(self, q, r):
        cx = self.s * math.sqrt(3) * (q + r / 2)
        cy = self.s * 1.5 * r
        pts = []
        for i in range(7):
            a = math.radians(60 * (i % 6) - 30)
            la, lo = to_ll(cx + self.s * math.cos(a), cy + self.s * math.sin(a))
            pts.append([round(lo, 5), round(la, 5)])
        return pts


def building_key(rec):
    """Group register entries into buildings: cadastral parcel (first 14 chars) when present,
    else normalised street + number."""
    c = (rec.get("catastral_ref") or "").strip().upper()
    if len(c) >= 14:
        return "P:" + c[:14]
    return "A:" + " ".join((rec.get("road_name") or "").upper().split()) + "|" + str(rec.get("km_num") or "")
