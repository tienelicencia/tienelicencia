"""Address clues in listing text + proximity to registered tourist dwellings.

Airbnb never shows the exact address and fuzzes the map pin (~up to 500 m), but hosts sometimes
write the street (and even number/floor) into the title or description. Where they do, we check
which registered dwellings exist at that street/number."""
import math
import re
import unicodedata
from collections import defaultdict

from .register import haversine_m

STREET_TYPES = (r"CALLE|C/|CL\.?|AVENIDA|AVDA\.?|AV\.?|PLAZA|PZA\.?|PL\.?|PASEO|PSO\.?|ALAMEDA|PASAJE|PSJE\.?|"
                r"CAMINO|CMNO\.?|CARRERA|CALLEJA|CALLEJON|PLAZUELA|GLORIETA|URBANIZACION|URB\.?|STREET")
STOP = {"DE", "DEL", "LA", "LAS", "EL", "LOS"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9/ ]+", " ", s)


def road_key(name):
    words = [w for w in norm(name).split() if w not in STOP]
    return " ".join(words)


class StreetIndex:
    def __init__(self, records):
        """records: Málaga register records (slim dicts incl. road_name, km_num, floor, door)."""
        self.by_road = defaultdict(list)
        for r in records:
            k = road_key(r.get("road_name"))
            if len(k) >= 4:
                self.by_road[k].append(r)
        self.max_words = max((len(k.split()) for k in self.by_road), default=1)

    def find(self, text):
        """Return list of clues: {street, number, records_on_street, records_at_number}."""
        t = norm(text)
        clues, seen = [], set()
        for m in re.finditer(rf"(?<![A-Z])(?:{STREET_TYPES})\s+((?:[A-Z0-9]+\s+){{0,8}}[A-Z0-9]+)", t):
            words = [w for w in m.group(1).split() if w not in STOP]
            # longest prefix of following words that is a known road
            for n in range(min(len(words), self.max_words), 0, -1):
                k = " ".join(words[:n])
                if k in self.by_road and not k.isdigit():
                    rest = words[n:n + 2]
                    num = None
                    for w in rest:
                        if w in ("N", "NO", "NUM", "NUMERO"):
                            continue
                        if re.fullmatch(r"\d{1,3}", w):
                            num = w
                        break
                    if (k, num) in seen:
                        break
                    seen.add((k, num))
                    on = self.by_road[k]
                    at = [r for r in on if num and str(r.get("km_num") or "").lstrip("0") == num.lstrip("0")]
                    clues.append({"street": k, "number": num, "records_on_street": on, "records_at_number": at,
                                  "context": t[max(0, m.start() - 30): m.end() + 30].strip()})
                    break
        return clues


class Grid:
    """Cheap radius search over register points (degrees grid, ~550 m cells)."""
    CELL = 0.005

    def __init__(self, records):
        self.cells = defaultdict(list)
        for r in records:
            if r.get("lat") is not None:
                self.cells[(int(r["lat"] / self.CELL), int(r["lon"] / self.CELL))].append(r)

    def within(self, lat, lon, radius_m):
        out = []
        ci, cj = int(lat / self.CELL), int(lon / self.CELL)
        span = int(math.ceil(radius_m / 450.0))
        for i in range(ci - span, ci + span + 1):
            for j in range(cj - span, cj + span + 1):
                for r in self.cells.get((i, j), ()):
                    if haversine_m(lat, lon, r["lat"], r["lon"]) <= radius_m:
                        out.append(r)
        return out
