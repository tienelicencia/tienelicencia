import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import valencia as V  # noqa: E402

IDX = {"CV-VUT0052177-V": {"muni_code": "46250", "lat": 39.4700, "lon": -0.3760},
       "CV-VUT0012345-A": {"muni_code": "03014", "lat": 38.34, "lon": -0.48}}


class ValenciaTests(unittest.TestCase):
    def cat(self, raw, lat=39.4701, lon=-0.3761, room="Entire home/apt", mn="2"):
        return V.classify(raw, lat, lon, room, mn, IDX)["category"]

    def test_formats(self):
        for raw in ["CV-VUT0052177-V", "VT-52177-V", "VT52177V", "Valencia - Regional registration number<br />VT-52177-V", "VUT 52177 V"]:
            self.assertEqual(self.cat(raw), "FOUND_CONSISTENT", raw)
        self.assertEqual(self.cat("VT-52177"), "FOUND_CONSISTENT")   # no province letter: read as Valencia's

    def test_location_and_other_place(self):
        self.assertEqual(self.cat("VT-52177-V", lat=39.49, lon=-0.35), "FOUND_INCONSISTENT")
        self.assertEqual(self.cat("VT-12345-A"), "FOUND_OTHER_MUNICIPALITY")
        self.assertEqual(self.cat("VT-99999-V"), "NOT_IN_REGISTER")

    def test_embedded_and_exempt(self):
        self.assertEqual(V.classify("Spain - National registration number<br />ESFCTU0000460250000123450000000000000000VT-52177-V3",
                                    39.4701, -0.3761, "Entire home/apt", "2", IDX)["key"], "CV-VUT0052177-V")
        self.assertEqual(self.cat(""), "NO_CODE_IN_SCOPE")
        self.assertEqual(self.cat("HV-1234"), "NO_CODE_POSSIBLY_EXEMPT")   # hotel register: not open, not checked
        self.assertEqual(self.cat("Exempt - seasonal rental", mn=""), "NO_CODE_POSSIBLY_EXEMPT")
        self.assertEqual(self.cat("Exempt - seasonal rental", mn="2"), "NO_CODE_IN_SCOPE")
        self.assertEqual(self.cat("", mn=str(V.SEASONAL_NIGHTS)), "NO_CODE_POSSIBLY_EXEMPT")


if __name__ == "__main__":
    unittest.main()
