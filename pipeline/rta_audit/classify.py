"""Match parsed codes against the register index and assign one primary category + flags."""
import re

from . import codes
from .register import haversine_m

LOCATION_THRESHOLD_M = 800  # Airbnb map fuzz (~500 m) + register geocode error margin
SUSPENSION_DATE = "20250823"  # Málaga capital: suspension of new VUT registrations

CATEGORIES = [
    ("FOUND_CONSISTENT", "Found in register, details consistent"),
    ("FOUND_INCONSISTENT", "Found in Málaga, but location/details inconsistent"),
    ("FOUND_OTHER_MUNICIPALITY", "Code exists but is registered to a property in another municipality"),
    ("CANCELLED_OFFICIAL", "Explicitly cancelled/inactive per official source"),
    ("NOT_IN_REGISTER", "Junta code shown but not in current register (not currently valid)"),
    ("MALFORMED", "Malformed/invalid Junta-style number shown"),
    ("NO_CODE_IN_SCOPE", "No Junta code visible: likely in scope"),
    ("NO_CODE_POSSIBLY_EXEMPT", "No Junta code visible: possibly exempt"),
    ("INCONCLUSIVE", "Inconclusive (page/extraction/lookup failure, ambiguous)"),
]
DISCREPANCY = {"FOUND_INCONSISTENT", "FOUND_OTHER_MUNICIPALITY", "CANCELLED_OFFICIAL", "NOT_IN_REGISTER", "MALFORMED", "NO_CODE_IN_SCOPE"}
VERDICT = {
    "FOUND_CONSISTENT": "VALID", "FOUND_INCONSISTENT": "VALID_LOCATION_MISMATCH",
    "FOUND_OTHER_MUNICIPALITY": "NOT_VALID",
    "CANCELLED_OFFICIAL": "NOT_VALID", "NOT_IN_REGISTER": "NOT_VALID", "MALFORMED": "NOT_VALID",
    "NO_CODE_IN_SCOPE": "NOT_VALID", "NO_CODE_POSSIBLY_EXEMPT": "POSSIBLY_EXEMPT", "INCONCLUSIVE": "INCONCLUSIVE",
}
HOTELISH = re.compile(r"(?i)hotel|hostel|aparthotel|boutique|bed and breakfast|guesthouse|pension")


def lookup(item, index, official, home="MÁLAGA"):
    """Try variants in order. Returns dict(match_key, variant, records, official)."""
    tried, hits = [], []
    for key, variant in codes.variants(item):
        tried.append(key)
        if key in official:
            return {"match_key": key, "variant": variant, "records": index.get(key, []),
                    "official": official[key], "tried": tried}
        if key in index:
            hits.append({"match_key": key, "variant": variant, "records": index[key], "official": None})
    if not hits:
        return {"match_key": None, "variant": None, "records": [], "official": None, "tried": tried}
    # Prefer a correction that lands in the listings' own city over an earlier one that lands in another town
    # (e.g. VUT/MA/062057: 62057 exists elsewhere, 06205 + check digit is the Málaga licence).
    best = next((h for h in hits if (h["records"][0].get("municipalities") or "").upper() == home), hits[0])
    best["tried"] = tried
    return best


def location_check(rec, lat, lon, home="MÁLAGA"):
    """Return (distance_m or None, problems list)."""
    problems = []
    dist = None
    if lat is not None and lon is not None and rec.get("lat") is not None:
        dist = round(haversine_m(float(lat), float(lon), rec["lat"], rec["lon"]))
    other_mun = (rec.get("municipalities") or "").upper() != home
    if other_mun and (dist is None or dist > LOCATION_THRESHOLD_M):
        problems.append(f"register_municipality={rec.get('municipalities')}")
    elif other_mun:
        problems.append(f"soft:register_municipality_{rec.get('municipalities')}_but_within_{LOCATION_THRESHOLD_M}m")
    if dist is not None and dist > LOCATION_THRESHOLD_M and not other_mun:
        problems.append(f"distance_{dist}m>{LOCATION_THRESHOLD_M}m")
    return dist, problems


def type_problem(rec, room_type):
    t = rec.get("objects_type_id") or ""
    if t in ("Agencia de viajes", "Guía de turismo", "REST. Restauración y catering turístico", "Oficina de turismo"):
        return f"register_type_not_accommodation={t}"
    return None


def classify(view, index, official, max_issued, home="MÁLAGA"):
    """view: dict with registration_raw, lat, lon, room_type, property_type, min_nights. home: the listings' municipality
    as the register spells it ("MÁLAGA", "SEVILLA").
    Returns dict of result fields (no reuse flags — those are added after all listings)."""
    p = codes.parse(view.get("registration_raw") or "", max_issued)
    junta = [j for j in p["junta"]]
    # Only a national number shown, with the Junta code at its tail (…0000VUT/MA/117055): check that code.
    embedded_only = not junta and any(n["embedded_regional"] for n in p["national"])
    if embedded_only:
        junta = [j for n in p["national"] if n["embedded_regional"]
                 for j in codes.parse(n["embedded_regional"], max_issued)["junta"]]
    res = {
        "parsed_clean_text": p["clean"],
        "junta_codes_raw": "; ".join(j["raw"] for j in junta),
        "junta_codes_norm": "; ".join(j["key"] or "" for j in junta),
        "junta_code_problems": "; ".join(",".join(j["problems"]) for j in junta),
        "national_numbers": "; ".join(n["raw"] for n in p["national"]),
        "national_types": "; ".join(n["type"] for n in p["national"]),
        "national_embedded_regional": "; ".join(n["embedded_regional"] or "" for n in p["national"]),
        "other_numbers": "; ".join(f"{o['kind']}:{o['raw']}" for o in p["other"]),
        "exempt_text": p["exempt_text"],
        "flags": [],
    }
    flags = res["flags"]
    if embedded_only:
        flags.append("junta_code_from_national_number")
    if len(junta) > 1:
        flags.append("multiple_junta_codes")
    if any(n["type"] == "FCNT" for n in p["national"]) and junta:
        flags.append("national_nontourist_FCNT_with_junta_code")
    for n in p["national"]:
        if n["embedded_regional"] and junta:
            e = codes.parse(n["embedded_regional"])["junta"]
            if e and all(e[0]["num"][:-1].lstrip("0") != j["num"].lstrip("0") and e[0]["num"].lstrip("0") != j["num"].lstrip("0") for j in junta):
                flags.append("national_embedded_code_differs")
    if any(o["kind"] == "CTC_procedure_ref" for o in p["other"]):
        flags.append("ctc_reference_shown")
    if any(o["kind"] == "non_andalusian_province" for o in p["other"]):
        flags.append("other_region_code_shown")

    best = None
    results = []
    for j in junta:
        lk = lookup(j, index, official, home)
        results.append((j, lk))
    order = {"FOUND_CONSISTENT": 0, "FOUND_INCONSISTENT": 1, "FOUND_OTHER_MUNICIPALITY": 2, "CANCELLED_OFFICIAL": 3,
             "NOT_IN_REGISTER": 4, "MALFORMED": 5}
    for j, lk in results:
        if lk["official"] and lk["official"].get("status") == "cancelled":
            cat = "CANCELLED_OFFICIAL"
        elif lk["records"]:
            rec = lk["records"][0]
            dist, probs = location_check(rec, view.get("lat"), view.get("lon"), home)
            tp = type_problem(rec, view.get("room_type"))
            if tp:
                probs.append(tp)
            if any(x.startswith("register_municipality=") for x in probs):
                cat = "FOUND_OTHER_MUNICIPALITY"
            else:
                cat = "FOUND_INCONSISTENT" if [x for x in probs if not x.startswith("soft:")] else "FOUND_CONSISTENT"
            lk["distance_m"], lk["loc_problems"] = dist, probs
        else:
            cat = "MALFORMED" if j["malformed"] else "NOT_IN_REGISTER"
        if best is None or order[cat] < order[best[0]]:
            best = (cat, j, lk)

    if best:
        cat, j, lk = best
        res["category"] = cat
        res["primary_code_raw"] = j["raw"]
        res["primary_code_norm"] = j["key"]
        res["match_key"] = lk["match_key"]
        res["match_variant"] = lk["variant"]
        res["variants_tried"] = "; ".join(lk["tried"])
        if lk["match_key"] and j["malformed"]:
            flags.append("malformed_display_but_matched")
        if lk.get("official"):
            o = lk["official"]
            res["official_status"] = o.get("status")
            res["official_cancel_date"] = o.get("cancel_date")
            res["official_source"] = o.get("source")
        if lk["records"]:
            rec = lk["records"][0]
            res["register_record"] = rec
            res["distance_m"] = lk.get("distance_m")
            res["location_problems"] = "; ".join(lk.get("loc_problems") or [])
            if (rec.get("registration_date") or "") > SUSPENSION_DATE:
                flags.append("registered_after_2025-08-23")
        if cat == "NOT_IN_REGISTER":
            res["address_lookup"] = "not attempted: listing page shows no street address or cadastral reference"
        return res

    # No Junta code
    exempt_reasons = []
    pt = view.get("property_type") or ""
    if HOTELISH.search(pt) or view.get("room_type") == "Hotel room":
        exempt_reasons.append(f"property_type={pt or view.get('room_type')}")
    try:
        if int(view.get("min_nights") or 0) >= 60:
            exempt_reasons.append(f"min_nights={view.get('min_nights')}")
    except ValueError:
        pass
    if p["national"] and not junta:
        exempt_reasons.append("national_number_only")
    if any(n["type"] == "FCNT" for n in p["national"]):
        exempt_reasons.append("national_type_non_tourist")
    # "Exempt – tourist apartment" in the national slot exempts from the national register only;
    # a seasonal-rental claim is a claim to be outside tourist-rental rules altogether.
    if p["exempt_text"] and re.search(r"(?i)seasonal|temporada", p["exempt_text"]):
        exempt_reasons.append(f"claims_exempt:{p['exempt_text'][:40]}")
    if re.search(r"(?i)rural|cortijo|finca", pt):
        exempt_reasons.append("rural_property_type")
    res["category"] = "NO_CODE_POSSIBLY_EXEMPT" if exempt_reasons else "NO_CODE_IN_SCOPE"
    res["exempt_reasons"] = "; ".join(exempt_reasons)
    return res
