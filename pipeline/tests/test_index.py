"""Índice de presión de la vivienda turística (rta_audit/index.py, index_config.json): registration categories and severity,
the three components, the fixed baseline, missing data, the 300,000-inhabitant cohort, and agreement between the published
ranking.json and the formula. Also number parsing for Castilla y León (Valladolid)."""
import copy
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from rta_audit import cyl, index  # noqa: E402

CFG = index.load_config()
RANKING_JSON = os.path.join(os.path.dirname(HERE), "site", "data", "ranking.json")
METHOD_HTML = os.path.join(os.path.dirname(HERE), "site", "metodologia.html")


def items(**n):
    """n = {classify category: count} → [(category, verdict)]."""
    verdict = {"FOUND_CONSISTENT": "VALID", "FOUND_INCONSISTENT": "VALID_LOCATION_MISMATCH", "NO_CODE_POSSIBLY_EXEMPT": "POSSIBLY_EXEMPT",
               "INCONCLUSIVE": "INCONCLUSIVE"}
    return [(c, verdict.get(c, "NOT_VALID")) for c, k in n.items() for _ in range(k)]


def city(name, A, B, ver):
    return {"name": name, "housing": A, "concentration": B, "verification": ver}


class CategoryTests(unittest.TestCase):
    def test_every_category_maps_once(self):
        v = index.verification(items(FOUND_CONSISTENT=10, FOUND_INCONSISTENT=2, NO_CODE_IN_SCOPE=3, NOT_IN_REGISTER=4, MALFORMED=1,
                                     FOUND_OTHER_MUNICIPALITY=5, CANCELLED_OFFICIAL=6, NO_CODE_POSSIBLY_EXEMPT=7, INCONCLUSIVE=8), CFG)
        self.assertEqual(v["counts"], {"valid": 12, "missing": 3, "unmatched": 5, "invalid_other_town": 5, "invalid_cancelled": 6,
                                       "exempt": 7, "unresolved": 8})
        self.assertEqual(v["assessed"], 38)          # unresolved checks are not assessed
        self.assertEqual(v["invalid"], 11)

    def test_severity_formula(self):
        v = index.verification(items(FOUND_CONSISTENT=60, NO_CODE_IN_SCOPE=20, NOT_IN_REGISTER=10, FOUND_OTHER_MUNICIPALITY=5,
                                     NO_CODE_POSSIBLY_EXEMPT=5), CFG)
        self.assertAlmostEqual(v["R"], 100 * (1.00 * 5 + 0.75 * 10 + 0.35 * 20) / 100, places=2)   # 19.5
        self.assertAlmostEqual(sum(v["contributions"].values()), v["R"], places=1)
        self.assertEqual(v["no_verifiable_pct"], 35.0)   # unweighted: missing + unmatched + invalid

    def test_cancelled_needs_evidence(self):
        """A number that is simply absent from the open register is unmatched (0.75), not cancelled (1.00)."""
        absent = index.verification(items(NOT_IN_REGISTER=1), CFG)
        cancelled = index.verification(items(CANCELLED_OFFICIAL=1), CFG)
        self.assertEqual(absent["counts"]["invalid_cancelled"], 0)
        self.assertEqual(absent["R"], 75.0)
        self.assertEqual(cancelled["R"], 100.0)

    def test_other_municipality_is_confirmed_invalid(self):
        self.assertEqual(index.verification(items(FOUND_OTHER_MUNICIPALITY=1), CFG)["R"], 100.0)

    def test_corrected_formats_and_flags_dont_raise_R(self):
        """Approved corrections land in FOUND_*; shared / far / room-licence are flags only."""
        its = [("FOUND_CONSISTENT", "VALID_CODE_SHARED"), ("FOUND_INCONSISTENT", "VALID_LOCATION_MISMATCH"),
               ("FOUND_CONSISTENT", "VALID_TYPE_MISMATCH"), ("FOUND_CONSISTENT", "VALID")]
        v = index.verification(its, CFG)
        self.assertEqual(v["R"], 0.0)
        self.assertEqual(v["flags"], {"shared": 1, "far": 1, "room_with_flat_licence": 1})

    def test_exempt_stays_in_denominator(self):
        v = index.verification(items(NO_CODE_IN_SCOPE=10, NO_CODE_POSSIBLY_EXEMPT=90), CFG)
        self.assertEqual(v["assessed"], 100)
        self.assertEqual(v["R"], 3.5)

    def test_madrid_missing_left_out_of_R(self):
        """Madrid: showing the number isn't required, so adverts without one leave R (numerator and denominator) but are
        still reported in the unweighted share, labelled."""
        v = index.verification(items(NO_CODE_IN_SCOPE=500, FOUND_CONSISTENT=300, NOT_IN_REGISTER=100, NO_CODE_POSSIBLY_EXEMPT=100), CFG,
                               number_required=False)
        self.assertFalse(v["number_required"])
        self.assertTrue(v["missing_excluded"])
        self.assertEqual(v["r_assessed"], 500)
        self.assertEqual(v["R"], 15.0)                       # 0.75 × 100 / 500
        self.assertEqual(v["contributions"]["missing"], 0)
        self.assertEqual(v["no_verifiable_pct"], 60.0)       # 600 of 1,000, unweighted
        self.assertFalse(index.verification(items(NO_CODE_IN_SCOPE=500, FOUND_CONSISTENT=200), CFG, number_required=False)["sufficient"])

    def test_sample_labels(self):
        v = index.verification(items(FOUND_CONSISTENT=300, NO_CODE_IN_SCOPE=100), CFG, source="sample", checked=400, target=696,
                               frame=696, date="2026-10-17")
        self.assertEqual((v["checked"], v["target"], v["frame"], v["date"]), (400, 696, 696, "2026-10-17"))
        self.assertEqual(len(v["no_verifiable_ci"]), 2)
        self.assertTrue(v["sufficient"])
        self.assertFalse(index.verification(items(FOUND_CONSISTENT=299), CFG, source="sample")["sufficient"])


class ComputeTests(unittest.TestCase):
    def cities(self):
        V = lambda **n: index.verification(items(**n), CFG)
        return [city("Alfa", 3.0, 30.0, V(FOUND_CONSISTENT=700, NO_CODE_IN_SCOPE=300)),
                city("Beta", 1.5, 15.0, V(FOUND_CONSISTENT=800, NOT_IN_REGISTER=200)),
                city("Gamma", 1.0, None, V(FOUND_CONSISTENT=900, NO_CODE_IN_SCOPE=100)),            # no concentration
                city("Delta", 2.0, 10.0, V(FOUND_CONSISTENT=200, NO_CODE_IN_SCOPE=50))]             # too few assessed

    def test_components_and_leader(self):
        cs = self.cities()
        b = index.compute(cs, CFG)
        alfa, beta = cs[0], cs[1]
        self.assertEqual((b["housing_max"], b["concentration_max"], b["registration_max"]), (3.0, 30.0, 15.0))
        self.assertEqual(b["leader"], "Alfa")
        self.assertEqual(alfa["normalised"], {"housing": 100.0, "concentration": 100.0, "registration": 70.0})
        raw_b = 0.40 * 50 + 0.35 * 50 + 0.25 * 100
        raw_max = 0.40 * 100 + 0.35 * 100 + 0.25 * 70
        self.assertAlmostEqual(beta["index"], round(100 * raw_b / raw_max, 1))
        self.assertEqual(alfa["index"], 100.0)
        for c in (alfa, beta):
            self.assertAlmostEqual(sum(c["contributions"].values()), c["index"], delta=0.15)
        self.assertEqual([alfa["rank"], beta["rank"]], [1, 2])

    def test_missing_component_never_reweighted(self):
        cs = self.cities()
        index.compute(cs, CFG)
        gamma, delta = cs[2], cs[3]
        for c, missing in ((gamma, ["concentration"]), (delta, ["registration"])):
            self.assertIsNone(c["index"])
            self.assertEqual(c["status"], "unavailable")
            self.assertEqual(c["missing_components"], missing)
            self.assertIsNone(c["contributions"])
            self.assertNotIn("rank", c)

    def test_frozen_baseline_is_not_recalculated_and_can_exceed_100(self):
        cfg = copy.deepcopy(CFG)
        cfg["baseline"].update(frozen=True, housing_max=3.0, concentration_max=30.0, registration_max=15.0,
                               raw_max=0.40 * 100 + 0.35 * 100 + 0.25 * 70, leader="Alfa")
        V = lambda **n: index.verification(items(**n), CFG)
        cs = [city("Alfa", 6.0, 45.0, V(FOUND_CONSISTENT=500, NO_CODE_IN_SCOPE=500))]   # pressure doubled after the base
        b = index.compute(cs, cfg)
        self.assertEqual(b["housing_max"], 3.0)          # unchanged
        self.assertGreater(cs[0]["index"], 100)          # not clamped
        self.assertEqual(cs[0]["normalised"]["housing"], 200.0)
        self.assertEqual(cs[0]["status"], "final")

    def test_provisional_while_sample_incomplete(self):
        cfg = copy.deepcopy(CFG)
        cfg["baseline"].update(frozen=True, housing_max=3.0, concentration_max=30.0, registration_max=15.0, raw_max=92.5)
        v = index.verification(items(FOUND_CONSISTENT=300, NO_CODE_IN_SCOPE=100), CFG, source="sample", checked=400, target=1000)
        cs = [city("Beta", 1.5, 15.0, v)]
        index.compute(cs, cfg)
        self.assertEqual(cs[0]["status"], "provisional")

    def test_freeze_writes_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cfg.json")
            b = index.freeze(self.cities(), copy.deepcopy(CFG), "2026-10", p, "2026-10-31")
            saved = json.load(open(p))["baseline"]
            self.assertTrue(saved["frozen"])
            self.assertEqual(saved, b)
            self.assertEqual(saved["leader"], "Alfa")


class CohortTests(unittest.TestCase):
    def test_threshold_rule(self):
        co = CFG["cohort"]
        self.assertEqual(co["min_population"], 300000)
        pops = [c["population"] for c in co["cities"]]
        self.assertTrue(all(p > 300000 for p in pops))
        self.assertEqual(pops, sorted(pops, reverse=True))
        self.assertEqual(len({c["ine"] for c in co["cities"]}), len(co["cities"]))
        names = [c["name"] for c in co["cities"]]
        self.assertEqual(len(names), 13)
        for n in ("Alicante", "Córdoba", "Valladolid", "Bilbao"):
            self.assertIn(n, names)

    def test_weights_and_severities(self):
        self.assertAlmostEqual(sum(CFG["weights"].values()), 1.0)
        self.assertEqual(CFG["weights"], {"housing": 0.40, "concentration": 0.35, "registration": 0.25})
        self.assertEqual(CFG["severity"], {"invalid": 1.00, "unmatched": 0.75, "missing": 0.35})
        self.assertEqual(CFG["baseline"]["period"], "2026-10")


@unittest.skipUnless(os.path.exists(RANKING_JSON), "no built ranking.json")
class PublishedRankingTests(unittest.TestCase):
    """What the page renders (ranking.json) agrees with the formula."""
    R = json.load(open(RANKING_JSON, encoding="utf-8")) if os.path.exists(RANKING_JSON) else {}

    def test_every_eligible_city_listed(self):
        self.assertEqual({c["name"] for c in self.R["cities"]}, {c["name"] for c in CFG["cohort"]["cities"]})
        self.assertEqual(self.R["cohort"]["eligible"], len(self.R["cities"]))
        self.assertEqual(self.R["cohort"]["with_index"], sum(1 for c in self.R["cities"] if c["index"] is not None))

    def test_index_matches_formula(self):
        b, w = self.R["baseline"], self.R["weights"]
        ranked = [c for c in self.R["cities"] if c["index"] is not None]
        for c in ranked:
            A, B, R_ = c["housing"], c["concentration"], c["verification"]["R"]
            raw = w["housing"] * 100 * A / b["housing_max"] + w["concentration"] * 100 * B / b["concentration_max"] \
                + w["registration"] * 100 * R_ / b["registration_max"]
            self.assertAlmostEqual(c["index"], 100 * raw / b["raw_max"], delta=0.06, msg=c["name"])
            self.assertAlmostEqual(sum(c["contributions"].values()), c["index"], delta=0.15, msg=c["name"])
        self.assertEqual([c["rank"] for c in ranked], list(range(1, len(ranked) + 1)))
        self.assertEqual([c["index"] for c in ranked], sorted((c["index"] for c in ranked), reverse=True))

    def test_no_invented_zeroes(self):
        for c in self.R["cities"]:
            if c["index"] is None:
                self.assertIsNone(c["contributions"])
                self.assertTrue(c["missing_components"])
            v = c.get("verification")
            if v and v["source"] == "sample":
                self.assertLessEqual(v["checked"], v["target"])
                self.assertLessEqual(v["target"], max(v["frame"], 1))


@unittest.skipUnless(os.path.exists(METHOD_HTML), "no methodology page")
class TranslationTests(unittest.TestCase):
    def test_index_section_in_both_languages(self):
        t = open(METHOD_HTML, encoding="utf-8").read()
        sec = t[t.index('<h2 id="indice">'):t.index('<h2 id="privacidad">')]
        es = sec[sec.index('<div lang="es">'):sec.index('<div lang="en">')]
        en = sec[sec.index('<div lang="en">'):]
        self.assertEqual(es.count("<h3>"), en.count("<h3>"))
        self.assertEqual(es.count("<li>"), en.count("<li>"))
        for s in (es, en):
            self.assertIn("300", s)
            self.assertTrue(re.search(r"0[.,]40", s) and re.search(r"0[.,]35", s) and re.search(r"0[.,]25", s))
        self.assertTrue(CFG["name"]["es"] and CFG["name"]["en"])


class CastillaLeonTests(unittest.TestCase):
    IDX = {"47/547": [{"muni": "Valladolid", "lat": 41.655, "lon": -4.723, "flat": True}],
           "47/43": [{"muni": "Valladolid", "lat": None, "lon": None, "flat": False},           # an apartment in town…
                     {"muni": "Peñafiel", "lat": None, "lon": None, "flat": True}],               # …and a flat elsewhere
           "24/3": [{"muni": "León", "lat": None, "lon": None, "flat": True}]}

    def cat(self, raw, lat=41.655, lon=-4.723):
        return cyl.classify(raw, lat, lon, "Entire home/apt", None, self.IDX)["category"]

    def test_formats(self):
        for raw in ["VUT-47/547", "Nº registro: VUT 47/000547", "47/547", "vut 47-547", "VUT 4700547"]:
            self.assertEqual(cyl.parse(raw)["regional"], ["47/547"], raw)
            self.assertEqual(self.cat(raw), "FOUND_CONSISTENT", raw)

    def test_shared_numbering_and_other_town(self):
        self.assertEqual(self.cat("47/000043"), "FOUND_CONSISTENT")      # one entry with that number is in Valladolid
        self.assertEqual(self.cat("VUT-24/3"), "FOUND_OTHER_MUNICIPALITY")
        self.assertEqual(self.cat("VUT-47/99999"), "NOT_IN_REGISTER")
        self.assertEqual(self.cat("VUT 47/547", 41.70, -4.60), "FOUND_INCONSISTENT")   # >800 m from the registered point

    def test_not_confused_with_andalusian_codes(self):
        self.assertEqual(cyl.parse("VUT/MA/12345")["regional"], [])
        self.assertEqual(self.cat(""), "NO_CODE_IN_SCOPE")
        self.assertEqual(cyl.classify("", None, None, "Entire home/apt", "32", self.IDX)["category"], "NO_CODE_POSSIBLY_EXEMPT")


if __name__ == "__main__":
    unittest.main()
