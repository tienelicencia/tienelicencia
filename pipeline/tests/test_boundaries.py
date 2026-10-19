"""Official barrio / district outlines for the sample cities and Palma (rta_audit/boundaries.py): names, merging, skipped
records, the Shapefile reader and ED50 conversion; and the build's helpers for them (Palma inside Mallorca, the sample
split by barrio, the listing-density layer)."""
import json
import os
import struct
import sys
import tempfile
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import boundaries, geo, register  # noqa: E402
import site_build  # noqa: E402


def square(lon, lat, d=0.01):
    return [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]


def fc(*feats):
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": p, "geometry": {"type": "Polygon", "coordinates": g} if g else None} for p, g in feats]}).encode()


class NamesTests(unittest.TestCase):
    def test_nice(self):
        self.assertEqual(boundaries.nice("SANTA CATALINA - CANTERAS"), "Santa Catalina - Canteras")
        self.assertEqual(boundaries.nice("CAMP D'EN SERRALTA"), "Camp d'en Serralta")
        self.assertEqual(boundaries.nice("SON RUL·LAN"), "Son Rul·lan")
        self.assertEqual(boundaries.nice("JUAN XXIII"), "Juan XXIII")
        self.assertEqual(boundaries.nice("PLAÇA DELS PATINS"), "Plaça dels Patins")
        self.assertEqual(boundaries.nice("STA. EULALIA"), "Santa Eulalia")
        self.assertEqual(boundaries.nice("00 Distrito CENTRO "), "Centro")                                # Córdoba
        self.assertEqual(boundaries.nice("08 Periurbano Oeste-Sierra: VILLARRUBIA"), "Villarrubia")
        self.assertEqual(boundaries.nice("Casco Histórico"), "Casco Histórico")                           # mixed case kept

    def test_every_source_is_documented(self):
        for slug, s in boundaries.SOURCES.items():
            self.assertIn(s["level"], ("barrio", "district"), slug)
            for k in ("url", "name", "es", "en", "page", "licence"):
                self.assertTrue(s.get(k), (slug, k))


class NormaliseTests(unittest.TestCase):
    def test_merge_skip_and_groups(self):
        raw = fc(({"NUCL_DS_NOMBRE": "VEGUETA", "DIST_CO_ID": 1}, square(-15.41, 28.10)),
                 ({"NUCL_DS_NOMBRE": "DISEMINADO", "DIST_CO_ID": 1}, square(-15.45, 28.05)),
                 ({"NUCL_DS_NOMBRE": "DISEMINADO", "DIST_CO_ID": 1}, square(-15.47, 28.05)),
                 ({"NUCL_DS_NOMBRE": "DISEMINADO", "DIST_CO_ID": 5}, square(-15.50, 28.08)),
                 ({"NUCL_DS_NOMBRE": "SIN GEOMETRIA", "DIST_CO_ID": 2}, None))
        out = boundaries.normalise("laspalmas", raw)
        self.assertEqual(set(out), {"Vegueta", "Diseminado (Vegueta, Cono Sur y Tafira)", "Diseminado (Tamaraceite-San Lorenzo-Tenoya)"})
        self.assertEqual(len(out["Diseminado (Vegueta, Cono Sur y Tafira)"]["polys"]), 2)   # pieces of one name merged
        self.assertEqual(out["Vegueta"]["group"], "Vegueta, Cono Sur y Tafira")

    def test_dropped_records(self):
        z = fc(({"nombre": "CASCO HISTÓ\u0093RICO", "estado": None}, square(-0.88, 41.65)),
               ({"nombre": "VILLAMAYOR DE GÁLLEGO", "estado": "BAJA"}, square(-0.77, 41.69)))
        self.assertEqual(list(boundaries.normalise("zaragoza", z)), ["Casco Histórico"])   # stray control character, BAJA
        c = fc(({"name": "00 Distrito CENTRO "}, square(-4.78, 37.88)), ({"name": "ZONA INDUSTRIAL"}, square(-4.80, 37.90)))
        self.assertEqual(list(boundaries.normalise("cordoba", c)), ["Centro"])

    def test_written_file_reads_as_barrios(self):
        raw = fc(({"barri": "SANTA CATALINA", "districte": "PONENT"}, square(2.62, 39.57)),
                 ({"barri": "LA SEU", "districte": "CENTRE"}, square(2.64, 39.56)))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "palma.geojson")
            boundaries.write(boundaries.normalise("palma", raw), p)
            B = geo.Barrios(p)
            self.assertEqual(B.lookup(39.575, 2.625)[1], "Santa Catalina")
            self.assertEqual(B.lookup(39.565, 2.645)[1], "La Seu")
            self.assertEqual(B.lookup(39.50, 2.50), (None, None))
            self.assertEqual({f["properties"]["group"] for f in B.features}, {"Ponent", "Centre"})


class ShapefileTests(unittest.TestCase):
    @staticmethod
    def shp_dbf(name, ring):
        """A one-polygon Shapefile (.shp, .dbf) with a single character field AAVV."""
        pts = b"".join(struct.pack("<dd", x, y) for x, y in ring)
        content = struct.pack("<i", 5) + struct.pack("<4d", 0, 0, 0, 0) + struct.pack("<ii", 1, len(ring)) + struct.pack("<i", 0) + pts
        shp = b"\0" * 100 + struct.pack(">ii", 1, len(content) // 2) + content
        val = name.encode("latin-1").ljust(20)
        dbf = struct.pack("<BBBBIHH", 3, 0, 0, 0, 1, 32 + 32 + 1, 1 + 20) + b"\0" * 20
        dbf += b"AAVV".ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([20]) + b"\0" * 15 + b"\x0d"
        dbf += b" " + val + b"\x1a"
        return shp, dbf

    def test_read(self):
        ring = [(447000, 4115000), (447000, 4116000), (448000, 4116000), (448000, 4115000), (447000, 4115000)]   # clockwise
        shp, dbf = self.shp_dbf("CASTAÑO - MIRASIERRA", ring)
        rows = boundaries.read_shp(shp, dbf)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0]["AAVV"], "CASTAÑO - MIRASIERRA")
        self.assertEqual(rows[0][1][0], ring)

    def test_ed50(self):
        """ED50 coordinates sit roughly 100–250 m from the same numbers read as ETRS89 (Granada: Catedral)."""
        x, y = 446700, 4114300
        a = boundaries.ed50_utm30_to_wgs84(x, y)
        b = register.utm30_to_wgs84(x, y)
        self.assertTrue(80 < register.haversine_m(*a, *b) < 300)
        self.assertLess(a[0], b[0])   # ED50 northings are larger: the WGS84 point lies south of the naive reading


class BuildHelpersTests(unittest.TestCase):
    def test_palma_rechecks_under_mallorca(self):
        self.assertEqual(site_build.state_path("palma"), site_build.state_path("mallorca"))
        self.assertIn("mallorca", site_build.LISTING_CITIES)
        self.assertNotIn("palma", site_build.LISTING_CITIES)
        self.assertEqual(site_build.SNAPSHOT_CITIES.count("mallorca"), 1)

    def test_sub_listings(self):
        class Munis:   # two municipalities split at lon 2.7
            def lookup(self, la, lo):
                return (1, "Palma de Mallorca") if lo < 2.7 else (2, "Alcúdia")
        o = lambda i, lo, keys=(): {"id": i, "lat": 39.6, "lon": lo, "keys": list(keys)}
        out = [o("1", 2.6, ["ETV/1"]), o("2", 2.8, ["ETV/1"]), o("3", 2.65)]
        rows = [{"id": i, "neighbourhood_cleansed": n} for i, n in (("1", "Palma de Mallorca"), ("2", "Alcúdia"), ("3", "Palma de Mallorca"),
                                                                    ("4", "Palma de Mallorca"))]   # 4: removed since the snapshot
        by_key = {"ETV/1": [out[0], out[1]]}
        r, d, out_, removed, bk = site_build.sub_listings((rows, "2026-09-19", out, 1, by_key), Munis(), "Palma de Mallorca")
        self.assertEqual([x["id"] for x in out_], ["1", "3"])
        self.assertEqual([x["id"] for x in r], ["1", "3"])
        self.assertEqual(removed, 1)
        self.assertEqual([x["id"] for x in bk["ETV/1"]], ["1"])
        self.assertIs(out_[0], out[0])   # the same classified listing: verdicts as on the Mallorca page

    def test_sample_by_barrio_and_wilson(self):
        class Two:
            def lookup(self, la, lo):
                return (1, "A") if lo < 0 else (2, "B")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            json.dump({"frame": [["a", 40, -1], ["b", 40, -1], ["c", 40, 1]]}, open(p, "w"))
            sm = {"_ids": ["a", "b", "c"], "_items": [("NO_CODE_IN_SCOPE", "NOT_VALID"), ("FOUND_CONSISTENT", "VALID"), ("X", "NOT_VALID")]}
            got = site_build.sample_by_barrio(p, sm, Two())
        self.assertEqual(got[1], Counter(n=2, NOT_VALID=1, VALID=1))
        self.assertEqual(got[2], Counter(n=1, NOT_VALID=1))
        lo, hi = site_build.wilson(12, 40)
        self.assertTrue(lo < 30 < hi and hi - lo < 30)
        self.assertIsNone(site_build.wilson(0, 0))

    def test_frame_hexes_only_where_enough(self):
        hexg = geo.Hex(90)
        frame = [[str(i), 39.47, -0.376] for i in range(12)] + [["x", 39.50, -0.30]]
        hx = {hexg.cell(39.47, -0.376): {"homes": 400}}
        fcol = site_build.frame_hexes(frame, hexg, hx)
        self.assertEqual(len(fcol["features"]), 1)   # the lone listing's hexagon isn't drawn
        self.assertEqual(fcol["features"][0]["properties"], {"n": 12, "homes": 400, "per100": 3.0})


if __name__ == "__main__":
    unittest.main()
