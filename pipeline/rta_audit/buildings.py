"""Group register entries into buildings and describe them for the site.

A building is one cadastral parcel (first 14 characters of the catastral reference). A parcel can
span several street numbers (e.g. Calle Principal del Candado 5 and 9 in Málaga) on one parcel with
one register coordinate, so the label lists every number rather than the most common one."""
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict

VUT = "Vivienda de uso turístico"
KIND = {  # short codes used in the site data
    VUT: "VUT", "Apartamento turístico": "AT", "Establecimiento Hotelero": "H",
    "Vivienda turística de alojamiento rural": "VTAR", "Casa rural": "CR",
    "Complejo turístico rural": "CTR", "Campamento de turismo": "CAMP",
}
LOWER = {"De", "Del", "La", "Las", "Los", "El", "Y", "E"}
STOP = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "CALLE", "AVENIDA", "AVDA", "PLAZA", "PASEO", "URBANIZACION", "URB"}


def building_key(rec):
    """Cadastral parcel when present, else municipality + normalised street + number."""
    c = (rec.get("catastral_ref") or "").strip().upper()
    if len(c) >= 14:
        return "P:" + c[:14]
    return ("A:" + (rec.get("municipalities") or "") + "|" + " ".join((rec.get("road_name") or "").upper().split())
            + "|" + str(rec.get("km_num") or ""))


def building_id(key):
    """Short stable id for URLs: the parcel itself, or a hash of the address key."""
    return key[2:] if key.startswith("P:") else "a" + hashlib.sha1(key.encode()).hexdigest()[:10]


def muni_key(name):
    """'VÉLEZ-MÁLAGA' / 'VELEZ MALAGA' → 'VELEZMALAGA' (register and Catastro spell municipalities differently).
    Ç is dropped, not made C: Catastro writes POLLENÇA as 'POLLEN A'."""
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", (name or "").replace("Ç", "").replace("ç", "")).encode("ascii", "ignore").decode().upper())


def street_name(road):
    words = " ".join((road or "").split()).title().split()
    return " ".join(w.lower() if i and w in LOWER else w for i, w in enumerate(words))


def _numkey(n):
    m = re.match(r"\d+", n)
    return (int(m.group()) if m else 10 ** 6, n)


def _street_key(street):
    """'De Martiricos' / 'Martiricos', 'Pacífico' / 'Pacifico' → one key."""
    s = unicodedata.normalize("NFKD", street).encode("ascii", "ignore").decode().upper()
    words = [w for w in re.sub(r"[^A-Z0-9 ]+", " ", s).split()]
    while words and words[0] in STOP:
        words = words[1:]
    return " ".join(words)


def _clean_num(n):
    n = (n or "").strip().upper().rstrip(".")
    if not n or re.fullmatch(r"S\s*/?\s*N|0+|-", n):
        return None
    return n.lstrip("0") or None


def label(addrs, max_streets=2, max_nums=4):
    """addrs: Counter of (street, number) → 'Principal del Candado 5, 9' or 'Larios 5 · Strachan 2 +1'."""
    forms, nums, weight = defaultdict(Counter), defaultdict(set), Counter()
    for (street, num), n in addrs.items():
        if not street:
            continue
        k = _street_key(street)
        forms[k][street] += n
        weight[k] += n
        c = _clean_num(num)
        if c:
            nums[k].add(c)
    if not weight:
        return ""
    parts = []
    for k, _ in weight.most_common(max_streets):
        ns = sorted(nums[k], key=_numkey)
        shown = ", ".join(ns[:max_nums]) + (" …" if len(ns) > max_nums else "")
        parts.append(f"{forms[k].most_common(1)[0][0]} {shown}".strip())
    extra = len(weight) - max_streets
    return " · ".join(parts) + (f" +{extra}" if extra > 0 else "")


def short_label(addrs):
    """One readable address for a building: the street with most flats, at its most-used number → 'Martiricos 40'."""
    forms, weight, by_num = defaultdict(Counter), Counter(), defaultdict(Counter)
    for (street, num), n in addrs.items():
        if not street:
            continue
        k = _street_key(street)
        forms[k][street] += n
        weight[k] += n
        c = _clean_num(num)
        if c:
            by_num[k][c] += n
    if not weight:
        return ""
    k = weight.most_common(1)[0][0]
    num = by_num[k].most_common(1)[0][0] if by_num[k] else ""
    return f"{forms[k].most_common(1)[0][0]} {num}".strip()


class Aggregator:
    """Accumulates register records (tourist accommodation, with coordinates) into buildings."""

    def __init__(self):
        self.b = {}

    def add(self, x):
        key = building_key(x)
        b = self.b.get(key)
        if b is None:
            b = self.b[key] = {"id": building_id(key), "lat": [], "lon": [], "vut": 0, "places": 0, "other": 0,
                               "years": [], "addr": Counter(), "types": Counter(), "muni": Counter()}
        if x.get("lat") is not None:
            b["lat"].append(x["lat"])
            b["lon"].append(x["lon"])
        if x.get("objects_type_id") == VUT:
            b["vut"] += 1
            b["places"] += x.get("tot_gen_places") or 0
        else:
            b["other"] += 1
            b["types"][x.get("objects_type_id")] += 1
        b["years"].append((x.get("registration_date") or "")[:4])
        b["addr"][(street_name(x.get("road_name")), str(x.get("km_num") or "").strip())] += 1
        b["muni"][x.get("municipalities")] += 1
        return b["id"]

    def rows(self, keep=lambda b: True, homes=None):
        """[lat, lon, label, vut, places, other, since, other_types, id, homes] for buildings with coordinates.
        homes: {parcel ref: dwellings} from the Catastro (None where unknown)."""
        out = []
        for b in self.b.values():
            if not b["lat"] or not keep(b):
                continue
            yrs = [y for y in b["years"] if y]
            out.append([round(sum(b["lat"]) / len(b["lat"]), 5), round(sum(b["lon"]) / len(b["lon"]), 5),
                        label(b["addr"]), b["vut"], b["places"], b["other"], min(yrs) if yrs else "",
                        ", ".join(KIND.get(t, t) for t, _ in b["types"].most_common(2)), b["id"],
                        (homes or {}).get(b["id"])])
        return out
