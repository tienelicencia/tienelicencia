import os
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import buildings  # noqa: E402


class LabelTests(unittest.TestCase):
    def test_parcel_lists_every_street_number(self):
        # One parcel, several street numbers: the label must not pick only the most common one.
        addrs = Counter({("Calle Ejemplo", "29"): 5, ("Calle Ejemplo", "27"): 4, ("Calle Ejemplo", "19-21"): 1,
                         ("Calle Ejemplo", "24"): 1, ("Calle Ejemplo", ""): 1})
        self.assertEqual(buildings.label(addrs), "Calle Ejemplo 19-21, 24, 27, 29")

    def test_variants_merge_and_placeholders_drop(self):
        addrs = Counter({("Pacífico", "18"): 3, ("Pacifico", "020"): 1, ("De Pacifico", "S/N"): 1, ("Larios", "0"): 1})
        self.assertEqual(buildings.label(addrs), "Pacífico 18, 20 · Larios")

    def test_long_lists_are_capped(self):
        addrs = Counter({("Lila", str(n)): 1 for n in range(1, 12)})
        self.assertEqual(buildings.label(addrs), "Lila 1, 2, 3, 4 …")

    def test_building_key(self):
        self.assertEqual(buildings.building_key({"catastral_ref": "9549202UF7694N0001AB"}), "P:9549202UF7694N")
        a = buildings.building_key({"municipalities": "NERJA", "road_name": "Real", "km_num": "5"})
        b = buildings.building_key({"municipalities": "ESTEPONA", "road_name": "Real", "km_num": "5"})
        self.assertNotEqual(a, b)   # same street name in two towns is two buildings
        self.assertTrue(buildings.building_id(a).startswith("a"))


if __name__ == "__main__":
    unittest.main()
