"""The daily build must not fall over on one odd listing: a live check without a map position falls back to the
snapshot's, and a listing with no position anywhere is left out (counted), not a crash."""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import site_build  # noqa: E402


def row(i, lat, lon, licence="VT-1"):
    return {"id": i, "license": licence, "latitude": lat, "longitude": lon, "room_type": "Entire home/apt",
            "property_type": "Entire rental unit", "minimum_nights": 2, "host_id": "h", "calculated_host_listings_count": 1,
            "neighbourhood_cleansed": "X"}


class ClassifyListingsTests(unittest.TestCase):
    def test_live_check_without_position_uses_snapshot(self):
        now = datetime.now(timezone.utc).isoformat()
        st = {"1": {"live_status": "ok", "live_fetched_at": now, "checked_at": now, "registration_raw": "VT-1", "lat": None, "lon": None,
                    "room_type": None, "property_type": None}}
        fn = lambda v, r: {"category": "FOUND_CONSISTENT", "key": "VT-1", "group": None}
        out = site_build.classify_listings(None, {}, None, "2026-01-01", [row("1", "40.4", "-3.7"), row("2", None, None)], st, "MADRID", fn=fn)[0]
        self.assertEqual([o["id"] for o in out], ["1"])          # listing 2 has no position anywhere: left out
        self.assertEqual((out[0]["lat"], out[0]["lon"]), (40.4, -3.7))
        self.assertTrue(out[0]["entire"])


if __name__ == "__main__":
    unittest.main()
