import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import baleares as B  # noqa: E402

IDX = {"ETV/1234": {"municipi": "SÓLLER", "lat": 39.7667, "lon": 2.7150, "places": 6},
       "ETVPL/5678": {"municipi": "ALCÚDIA", "lat": None, "lon": None, "places": 4},
       "H/12": {"municipi": "PALMA", "lat": 39.57, "lon": 2.65, "places": 80}}


class ParseTests(unittest.TestCase):
    def test_regional_formats(self):
        for raw in ["ETV/1234", "etv/01234", "ETV 1234", "Mallorca - Regional registration number<br />ETV/1234", "ET/1234"]:
            self.assertEqual(B.parse(raw)["regional"], ["ETV/1234"], raw)
        self.assertEqual(B.parse("ETVPL/5678")["regional"], ["ETVPL/5678"])
        self.assertEqual(B.parse("VT/123")["regional"], ["VT/123"])

    def test_not_valencia(self):
        self.assertEqual(B.parse("VT-12345-V")["regional"], [])   # Valencia's format, not a Balearic VT/123

    def test_embedded_in_national(self):
        p = B.parse("Spain - National registration number<br />ESFCTU00000703500012345600000000000000000ETV/12347")
        self.assertEqual(p["regional"], [])
        self.assertEqual(p["embedded"], ["ETV/1234"])   # the last digit is a check digit


class ClassifyTests(unittest.TestCase):
    def cat(self, raw, lat=39.7668, lon=2.7152, room="Entire home/apt", mn="3", muni="Sóller"):
        return B.classify(raw, lat, lon, room, mn, IDX, muni)["category"]

    def test_found_and_location(self):
        self.assertEqual(self.cat("ETV/1234"), "FOUND_CONSISTENT")
        self.assertEqual(self.cat("ETV/1234", lat=39.78, lon=2.74), "FOUND_INCONSISTENT")            # same town, 2.5 km away
        self.assertEqual(self.cat("ETV/1234", lat=39.57, lon=2.65, muni="Palma de Mallorca"), "FOUND_OTHER_MUNICIPALITY")

    def test_no_register_point(self):
        self.assertEqual(self.cat("ETVPL/5678", muni="Alcúdia"), "FOUND_CONSISTENT")
        self.assertEqual(self.cat("ETVPL/5678", muni="Sóller"), "FOUND_OTHER_MUNICIPALITY")

    def test_not_in_register(self):
        self.assertEqual(self.cat("ETV/999999"), "NOT_IN_REGISTER")

    def test_no_number_and_exempt(self):
        self.assertEqual(self.cat(""), "NO_CODE_IN_SCOPE")
        self.assertEqual(self.cat("", mn="31"), "NO_CODE_POSSIBLY_EXEMPT")   # a tourist stay is at most 30 nights
        self.assertEqual(self.cat("", mn="30"), "NO_CODE_IN_SCOPE")
        self.assertEqual(self.cat("Mallorca - Regional registration number<br />Exempt - seasonal rental"), "NO_CODE_POSSIBLY_EXEMPT")
        self.assertEqual(self.cat("", room="Hotel room"), "NO_CODE_POSSIBLY_EXEMPT")

    def test_whole_home_group(self):
        self.assertEqual(B.classify("ETV/1234", 39.7668, 2.7152, "Private room", "2", IDX, "Sóller")["group"], "Completa")
        self.assertIsNone(B.classify("H/12", 39.57, 2.65, "Hotel room", "1", IDX, "Palma")["group"])

    def test_muni_names(self):
        self.assertEqual(B.muni("Palma de Mallorca"), B.muni("PALMA"))
        self.assertEqual(B.muni("Deyá"), B.muni("DEIÀ"))
        self.assertEqual(B.muni("Pollença"), B.muni("POLLEN A"))   # Catastro's spelling


if __name__ == "__main__":
    unittest.main()
