"""Índice de presión de la vivienda turística: one composite index for the principal Spanish cities.

Three components, each normalised against its highest value in a fixed baseline (October 2026), then weighted:

  A  housing        tourist homes advertised on Airbnb, Booking and Vrbo (INE, de-duplicated) / all homes in the municipality
  B  concentration  Airbnb listings per 100 homes in the city's most affected circle 1 km across (500 m radius; circles with 3,000+ homes)
  C  registration   severity-weighted registration discrepancies among assessed Airbnb listings:
                      R = 100 × (1.00 × invalid + 0.75 × unmatched + 0.35 × missing) / assessed

  A' = 100 × A / A_max(baseline), B' and C' likewise
  raw = 0.40 A' + 0.35 B' + 0.25 C'
  index = 100 × raw / raw_max(baseline)

The baseline values are frozen in index_config.json; later months are measured against them, so a city can go above 100.
Until the baseline is frozen it is computed from the current data and labelled provisional. A city missing a component, or
with too few assessed listings, gets no index (status "unavailable"): we never reweight the other components or estimate it.

Registration categories (each listing counts once, at its highest defensible severity; secondary issues are kept as flags):
  valid      in the register (approved format corrections included); flags: shared, far, room_with_flat_licence
  missing    no usable number and no likely exemption                                                 severity 0.35
             (where showing the number isn't required, i.e. Madrid, these are left out of R: see verification())
  unmatched  a number that isn't in the published register                                           severity 0.75
  invalid    registered in another municipality, or officially cancelled (documented evidence)        severity 1.00
  exempt     possibly exempt (hotel, long minimum stay, seasonal claim backed by the stay, national number only):
             kept in the denominator with severity 0, because the exemption is likely but not established
"""
import json
import os

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index_config.json")

# rta_audit.classify categories → index categories
CATEGORY = {"FOUND_CONSISTENT": "valid", "FOUND_INCONSISTENT": "valid", "NO_CODE_IN_SCOPE": "missing",
            "NOT_IN_REGISTER": "unmatched", "MALFORMED": "unmatched", "FOUND_OTHER_MUNICIPALITY": "invalid_other_town",
            "CANCELLED_OFFICIAL": "invalid_cancelled", "NO_CODE_POSSIBLY_EXEMPT": "exempt", "INCONCLUSIVE": "unresolved"}
FLAGS = {"VALID_CODE_SHARED": "shared", "VALID_LOCATION_MISMATCH": "far", "VALID_TYPE_MISMATCH": "room_with_flat_licence"}


def load_config(path=CONFIG):
    return json.load(open(path, encoding="utf-8"))


def wilson(k, n, z=1.96):
    """95% interval for a share k/n, in percent."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(100 * max(0, c - h), 1), round(100 * min(1, c + h), 1)]


def verification(items, cfg, source="full", checked=None, target=None, date=None, number_required=True, live_checked=None, frame=None):
    """items: [(classify category, verdict)] for every assessed listing. Returns the registration breakdown and R."""
    counts = {k: 0 for k in ("valid", "missing", "unmatched", "invalid_other_town", "invalid_cancelled", "exempt", "unresolved")}
    flags = {k: 0 for k in set(FLAGS.values())}
    for cat, verdict in items:
        counts[CATEGORY.get(cat, "unresolved")] += 1
        if verdict in FLAGS:
            flags[FLAGS[verdict]] += 1
    n = len(items) - counts["unresolved"]
    invalid = counts["invalid_other_town"] + counts["invalid_cancelled"]
    sev = cfg["severity"]
    out = {"assessed": n, "counts": counts, "invalid": invalid, "flags": flags, "source": source,
           "number_required": number_required, "date": date}
    if source == "sample":
        out.update(checked=checked if checked is not None else n, target=target, frame=frame)
    else:
        out["live_checked"] = live_checked
    # Where no rule requires adverts to show the number (Madrid), adverts without one are left out of R entirely (numerator
    # and denominator): R then measures the numbers that are shown. They still count in no_verifiable_pct, labelled.
    m = counts["missing"] if number_required else 0
    nr = n - (0 if number_required else counts["missing"])
    out["r_assessed"] = nr
    if not number_required:
        out["missing_excluded"] = True
    if n:
        bad = invalid + counts["unmatched"] + counts["missing"]
        out["no_verifiable_pct"] = round(100 * bad / n, 1)
    if nr:
        out["R"] = round(100 * (sev["invalid"] * invalid + sev["unmatched"] * counts["unmatched"] + sev["missing"] * m) / nr, 2)
        out["contributions"] = {"invalid": round(100 * sev["invalid"] * invalid / nr, 2),
                                "unmatched": round(100 * sev["unmatched"] * counts["unmatched"] / nr, 2),
                                "missing": round(100 * sev["missing"] * m / nr, 2)}
        if source == "sample":
            out["no_verifiable_ci"] = wilson(bad, n)
    # Enough evidence: min_assessed listings, or (a town with fewer listings than that) nearly all of them checked, which
    # is a census rather than a sample. 0.9 allows for listings removed between listing and checking.
    out["sufficient"] = nr >= cfg["min_assessed"] or bool(source == "sample" and frame and frame < cfg["min_assessed"]
                                                          and n >= 0.9 * frame and nr >= 0.5 * cfg["min_assessed"])
    if source == "sample" and frame and checked is not None and checked >= 0.9 * frame:
        out["census"] = True
    return out


def compute(cities, cfg):
    """cities: [{"name", "housing": A or None, "concentration": B or None, "verification": {...} or None, ...}].
    Adds "index" (or None), "status", the normalised components and their contributions. Returns the baseline used."""
    def comps(c):
        v = c.get("verification") or {}
        return {"housing": c.get("housing"), "concentration": c.get("concentration"),
                "registration": v.get("R") if v.get("sufficient") else None}
    b = dict(cfg["baseline"])
    complete = [c for c in cities if all(x is not None for x in comps(c).values())]
    if not b.get("frozen"):   # provisional: today's maxima among cities with all three components
        for k in ("housing", "concentration", "registration"):
            b[f"{k}_max"] = max((comps(c)[k] for c in complete), default=None)
    w = cfg["weights"]

    def norm(c):
        return {k: (100 * v / b[f"{k}_max"] if v is not None and b.get(f"{k}_max") else None) for k, v in comps(c).items()}
    if not b.get("frozen"):
        raws = [(sum(w[k] * x for k, x in norm(c).items()), c["name"]) for c in complete]
        b["raw_max"], b["leader"] = max(raws) if raws else (None, None)
    for c in cities:
        n = norm(c)
        c["normalised"] = {k: (round(x, 1) if x is not None else None) for k, x in n.items()}
        missing = [k for k, x in n.items() if x is None]
        if missing or not b.get("raw_max"):
            c.update(index=None, status="unavailable", missing_components=missing, contributions=None)
            continue
        contrib = {k: 100 * w[k] * x / b["raw_max"] for k, x in n.items()}   # index points from each component
        c["contributions"] = {k: round(x, 1) for k, x in contrib.items()}
        c["index"] = round(sum(contrib.values()), 1)
        v = c.get("verification") or {}
        c["status"] = "provisional" if (v.get("source") == "sample" and (v.get("checked") or 0) < (v.get("target") or 0)) \
            or not b.get("frozen") else "final"
    ranked = sorted([c for c in cities if c["index"] is not None], key=lambda c: -c["index"])
    for i, c in enumerate(ranked, 1):
        c["rank"] = i
    return b


def freeze(cities, cfg, period, path=CONFIG, when=None):
    """Write the current maxima into the config as the frozen baseline (run once, after the cohort is validated)."""
    b = compute([dict(c) for c in cities], dict(cfg, baseline=dict(cfg["baseline"], frozen=False)))
    cfg = dict(cfg)
    cfg["baseline"] = {"period": period, "frozen": True, "housing_max": b["housing_max"], "concentration_max": b["concentration_max"],
                       "registration_max": b["registration_max"], "raw_max": b["raw_max"], "leader": b["leader"], "frozen_at": when}
    json.dump(cfg, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return cfg["baseline"]
