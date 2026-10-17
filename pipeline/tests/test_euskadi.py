import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import euskadi as E  # noqa: E402

IDX = {"ESS00578": {"muni": "Donostia / San Sebastián", "lat": 43.3214, "lon": -1.9850, "group": "Completa"},
       "EBI00003": {"muni": "Bilbao", "lat": None, "lon": None, "group": "Completa"},
       "LBI00010": {"muni": "Bilbao", "lat": None, "lon": None, "group": "Por habitaciones"}}


class ParseTests(unittest.TestCase):
    def test_regional_formats(self):
        for raw in ["ESS00578", "ess-00578", "E SS 578", "Basque Country - Regional registration number<br />ESS00578", "ESS005789"]:
            self.assertEqual(E.parse(raw)["regional"], ["ESS00578"], raw)   # six digits: the last one is a check digit

    def test_embedded_in_national(self):
        p = E.parse("Spain - National registration number<br />ESFCTU0000200690000123450000000000000000ESS005789")
        self.assertEqual(p["regional"], [])
        self.assertEqual(p["embedded"], ["ESS00578"])

    def test_broken_accents(self):
        self.assertEqual(E.muni("Donostia-San SebastiÃ¡n"), E.muni("Donostia / San Sebastián"))


class ClassifyTests(unittest.TestCase):
    def cat(self, raw, lat=43.3215, lon=-1.9851, room="Entire home/apt", mn="2", muni="Donostia-San Sebastián"):
        return E.classify(raw, lat, lon, room, mn, IDX, muni)["category"]

    def test_found_and_location(self):
        self.assertEqual(self.cat("ESS00578"), "FOUND_CONSISTENT")
        self.assertEqual(self.cat("ESS00578", lat=43.30, lon=-1.95), "FOUND_INCONSISTENT")
        self.assertEqual(self.cat("EBI00003", muni="Bilbao", lat=43.26, lon=-2.93), "FOUND_CONSISTENT")   # no registered point
        self.assertEqual(self.cat("EBI00003"), "FOUND_OTHER_MUNICIPALITY")

    def test_not_in_register_and_exempt(self):
        self.assertEqual(self.cat("ESS99999"), "NOT_IN_REGISTER")
        self.assertEqual(self.cat(""), "NO_CODE_IN_SCOPE")
        self.assertEqual(self.cat("", mn="32"), "NO_CODE_POSSIBLY_EXEMPT")
        self.assertEqual(self.cat("", mn="31"), "NO_CODE_IN_SCOPE")
        self.assertEqual(self.cat("Spain - National registration number<br />ESFCNT0000200690000123450000000000000000"),
                         "NO_CODE_POSSIBLY_EXEMPT")   # a national number for a non-tourist (seasonal) let

    def test_groups(self):
        self.assertEqual(E.classify("ESS00578", 43.3215, -1.9851, "Private room", "2", IDX, "Donostia")["group"], "Completa")
        self.assertEqual(E.classify("LBI00010", 43.26, -2.93, "Private room", "2", IDX, "Bilbao")["group"], "Por habitaciones")


if __name__ == "__main__":
    unittest.main()
