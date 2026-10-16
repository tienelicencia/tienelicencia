import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import catalunya as C  # noqa: E402

IDX = {"HUTB-012345": {"type": "HUT", "lat": 41.3851, "lon": 2.1734, "barri": "el Barri Gòtic", "district": "Ciutat Vella", "places": 4},
       "HB-000123": {"type": "Hotel", "lat": None, "lon": None, "barri": None, "district": None, "places": 80}}


class ParseTests(unittest.TestCase):
    def test_regional_formats(self):
        for raw in ["HUTB-012345", "hutb 12345", "Barcelona - Regional registration number<br />HUTB-012345", "HUTB012345"]:
            self.assertEqual(C.parse(raw)["regional"], ["HUTB-012345"], raw)

    def test_embedded_in_national(self):
        p = C.parse("Spain - National registration number<br />ESFCTU0000080190001234560000000000000000HUTB-0123451")
        self.assertEqual(p["regional"], [])
        self.assertEqual(p["embedded"], ["HUTB-012345"])


class ClassifyTests(unittest.TestCase):
    def cat(self, raw, lat=41.3852, lon=2.1736, room="Entire home/apt", mn="3"):
        return C.classify(raw, lat, lon, room, mn, IDX)["category"]

    def test_found_and_location(self):
        self.assertEqual(self.cat("HUTB-012345"), "FOUND_CONSISTENT")
        self.assertEqual(self.cat("HUTB-012345", lat=41.40, lon=2.20), "FOUND_INCONSISTENT")

    def test_not_in_register(self):
        self.assertEqual(self.cat("HUTB-000000"), "NOT_IN_REGISTER")

    def test_regional_field_wins(self):
        raw = "HUTB-012345<br />ESFCTU0000080190009999990000000000000000HUTB-0999999"
        self.assertEqual(C.classify(raw, 41.3852, 2.1736, "Entire home/apt", "3", IDX)["key"], "HUTB-012345")

    def test_no_number_and_exempt(self):
        self.assertEqual(self.cat(""), "NO_CODE_IN_SCOPE")
        self.assertEqual(self.cat("", mn="32"), "NO_CODE_POSSIBLY_EXEMPT")
        self.assertEqual(self.cat("Barcelona - Regional registration number<br />Exempt - seasonal rental"), "NO_CODE_POSSIBLY_EXEMPT")


if __name__ == "__main__":
    unittest.main()
