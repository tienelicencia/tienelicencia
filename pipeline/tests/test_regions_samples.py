"""Number parsing for the regions checked by sample (Zaragoza, Murcia, Las Palmas)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import aragon, canarias, murcia  # noqa: E402


class AragonTests(unittest.TestCase):
    IDX = {"ZA-19-112": {"zaragoza": True}, "ZA-17-11": {"zaragoza": True}, "HU-22-100": {"zaragoza": False}, "ZA-25-15": {"zaragoza": True}}

    def test_formats(self):
        for raw in ["Aragón – Número de registro autonómico VU-ZA-19-112", "VU-ZA19112", "VUZA-19-112"]:
            self.assertEqual(aragon.classify(raw, None, None, "Entire home/apt", None, self.IDX)["key"], "ZA-19-112", raw)
        self.assertEqual(aragon.classify("VU-ZA17011", None, None, "Entire home/apt", None, self.IDX)["key"], "ZA-17-11")
        self.assertEqual(aragon.classify("VUT-ZA-25-0015", None, None, "Entire home/apt", None, self.IDX)["category"], "FOUND_CONSISTENT")

    def test_other_town_and_missing(self):
        self.assertEqual(aragon.classify("VU-HU-22-100", None, None, "Entire home/apt", None, self.IDX)["category"], "FOUND_OTHER_MUNICIPALITY")
        self.assertEqual(aragon.classify("VU-ZA-20-999", None, None, "Entire home/apt", None, self.IDX)["category"], "NOT_IN_REGISTER")
        self.assertEqual(aragon.classify("", None, None, "Entire home/apt", "32", self.IDX)["category"], "NO_CODE_POSSIBLY_EXEMPT")


class MurciaTests(unittest.TestCase):
    IDX = {"VV.MU.6415-1": {"in_murcia": True, "lat": 37.98, "lon": -1.13}, "VV.MU.8373-1": {"in_murcia": True, "lat": None, "lon": None},
           "VV.MU.100-2": {"in_murcia": False, "lat": None, "lon": None}}

    def test_formats(self):
        for raw in ["VV.MU.6415-1", "VV MU 6415-1", "VV-MU-6415-1", "VVMU6415.1"]:
            self.assertEqual(murcia.classify(raw, 37.9801, -1.1301, "Entire home/apt", None, self.IDX)["category"], "FOUND_CONSISTENT", raw)
        r = murcia.classify("Spain - National registration number<br />ESFCTU0000300300001234560000000000000VV.MU.8373-15", 37.98, -1.13,
                            "Entire home/apt", None, self.IDX)
        self.assertEqual(r["key"], "VV.MU.8373-1")

    def test_other_town(self):
        self.assertEqual(murcia.classify("VV.MU.100-2", 37.98, -1.13, "Entire home/apt", None, self.IDX)["category"], "FOUND_OTHER_MUNICIPALITY")


class CanariasTests(unittest.TestCase):
    IDX = {"VV-35-1-0022236": {"muni": "Las Palmas De Gran Canaria", "lat": 28.12, "lon": -15.43},
           "VV---0000621": {"muni": "Las Palmas De Gran Canaria", "lat": None, "lon": None},
           "_short": {"VV-0022236": "VV-35-1-0022236", "VV-0000621": "VV---0000621"}}

    def test_formats_and_slips(self):
        for raw in ["Islas Canarias - Número de registro autonómico | VV-35-1-0022236", "VV-35-10022236", "VV3510022236", "VT-35-1-0022236",
                    "Spain - National registration number<br />ESFCTU000035016000123456000000000000000VV-35-1-00222367"]:
            self.assertEqual(canarias.classify(raw, 28.1201, -15.4301, "Entire home/apt", None, self.IDX)["category"], "FOUND_CONSISTENT", raw)
        self.assertEqual(canarias.classify("VV---0000621", 28.12, -15.43, "Private room", None, self.IDX)["category"], "FOUND_CONSISTENT")

    def test_missing(self):
        self.assertEqual(canarias.classify("VV-35-1-0099999", 28.12, -15.43, "Entire home/apt", None, self.IDX)["category"], "NOT_IN_REGISTER")
        self.assertEqual(canarias.classify("", 28.12, -15.43, "Entire home/apt", None, self.IDX)["category"], "NO_CODE_IN_SCOPE")


if __name__ == "__main__":
    unittest.main()
