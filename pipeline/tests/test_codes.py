import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import classify, codes  # noqa: E402

MAX = {("VUT", "MA"): 102876, ("A", "MA"): 20000, ("H", "MA"): 7000}


def keys(text):
    return [j["key"] for j in codes.parse(text, MAX)["junta"]]


class ParserTests(unittest.TestCase):
    def test_separator_case_and_prefix_variants_share_key(self):
        for raw in ["VUT/MA/08150", "VUT-MA-08150", "vut/ma/08150", "VFT/MA/08150", "VFT MA 08150",
                    "VUTMA08150", "Vft/ma/8150", "VTF/MA/08150", "VUT/MA08150", "VUT_MA_08150"]:
            self.assertEqual(keys(raw), ["VUT/MA/8150"], raw)

    def test_other_andalusian_prefixes(self):
        self.assertEqual(keys("A/MA/01234"), ["A/MA/1234"])
        self.assertEqual(keys("H/MA/00598"), ["H/MA/598"])
        self.assertEqual(keys("VTAR/MA/01234"), ["VTAR/MA/1234"])

    def test_national_number_kept_separate(self):
        p = codes.parse("Spain – National registration number<br />ESFCTU0000290270005174700000000000000000VUT/MA/117055", MAX)
        self.assertEqual(p["junta"], [])
        self.assertEqual(len(p["national"]), 1)
        self.assertEqual(p["national"][0]["type"], "FCTU")
        self.assertEqual(p["national"][0]["embedded_regional"], "VUT/MA/117055")

    def test_ctc_and_other_regions_are_other(self):
        p = codes.parse("CTC-2018150102", MAX)
        self.assertEqual(p["junta"], [])
        self.assertEqual(p["other"][0]["kind"], "CTC_procedure_ref")
        p = codes.parse("H/MD/12345", MAX)
        self.assertEqual(p["junta"], [])
        self.assertEqual(p["other"][0]["kind"], "non_andalusian_province")
        self.assertTrue(codes.parse("VUT/MD/12345", MAX)["junta"][0]["malformed"])  # VUT/VFT is Andalusian-only

    def test_malformed(self):
        self.assertIn("exceeds_highest_issued", codes.parse("VUT/MA/807770", MAX)["junta"][0]["problems"])
        self.assertTrue(codes.parse("VFT/12345", MAX)["junta"][0]["malformed"])          # no province
        bad = codes.parse("VFT-AB-54678", MAX)["junta"][0]                               # invalid province
        self.assertTrue(bad["malformed"])
        self.assertEqual(codes.variants(bad)[0], ("VUT/MA/54678", "province_replaced_MA+prefix_swap_VFT_to_VUT"))
        self.assertTrue(codes.parse("VFT/MA/9999B", MAX)["junta"][0]["malformed"])       # letter suffix
        self.assertTrue(codes.parse("Regional registration number | 29123", MAX)["junta"][0]["malformed"])  # digits only
        self.assertFalse(codes.parse("VUT/MA/12345", MAX)["junta"][0]["malformed"])      # valid shape

    def test_check_digit_variant(self):
        item = codes.parse("VUT/MA/807770", MAX)["junta"][0]
        self.assertIn(("VUT/MA/80777", "exact+check_digit_stripped"), codes.variants(item))

    def test_inside_airbnb_licence_field(self):
        raw = ("Andalucia - Regional registration number<br />VUT/MA/12345<br /><br />Spain - National registration number"
               "<br />ESFCNT00002902000042691900000000000000000000000000003")
        p = codes.parse(raw, MAX)
        self.assertEqual([j["key"] for j in p["junta"]], ["VUT/MA/12345"])
        self.assertEqual(p["national"][0]["type"], "FCNT")


class RegressionFixture(unittest.TestCase):
    """Fictional case modelled on a real one: a licence cancelled per an official document and absent from open data,
    shown on two listings of the same host; one listing later showed another number that isn't in the register either."""
    index = {"VUT/MA/8552": [{"registration_code": "VUT/MA/08552", "municipalities": "MÁLAGA", "lat": 36.7215, "lon": -4.4245}]}
    official = {"VUT/MA/12345": {"status": "cancelled", "cancel_date": "2025-03-02", "source": "hoja registral"}}

    def view(self, raw):
        return {"registration_raw": raw, "lat": 36.7207, "lon": -4.4241, "room_type": "Entire home/apt",
                "property_type": "Entire rental unit", "min_nights": "3"}

    def test_both_listings_are_discrepancies(self):
        for raw in ["VUT/MA/12345", "Andalucia – Regional registration number<br />VUT/MA/12345"]:
            r = classify.classify(self.view(raw), self.index, self.official, MAX)
            self.assertEqual(r["category"], "CANCELLED_OFFICIAL")
            self.assertEqual(classify.VERDICT[r["category"]], "NOT_VALID")

    def test_without_official_source_it_is_not_in_register(self):
        r = classify.classify(self.view("VUT/MA/12345"), self.index, {}, MAX)
        self.assertEqual(r["category"], "NOT_IN_REGISTER")

    def test_live_number_not_in_register(self):
        r = classify.classify(self.view("VUT-MA-08151"), self.index, {}, MAX)
        self.assertEqual(r["category"], "NOT_IN_REGISTER")

    def test_found_and_location(self):
        r = classify.classify(self.view("VUT/MA/08552"), self.index, {}, MAX)
        self.assertEqual(r["category"], "FOUND_CONSISTENT")
        far = dict(self.view("VUT/MA/08552"), lat=36.75, lon=-4.40)
        self.assertEqual(classify.classify(far, self.index, {}, MAX)["category"], "FOUND_INCONSISTENT")

    def test_other_municipality(self):
        idx = {"VUT/MA/54678": [{"municipalities": "OJEN", "lat": 36.56, "lon": -4.85}]}
        r = classify.classify(self.view("VFT-AB-54678"), idx, {}, MAX)
        self.assertEqual(r["category"], "FOUND_OTHER_MUNICIPALITY")
        self.assertEqual(classify.VERDICT[r["category"]], "NOT_VALID")

    def test_prefers_malaga_correction(self):
        idx = {"VUT/MA/62057": [{"municipalities": "MARBELLA", "lat": 36.5, "lon": -4.9}],
               "VUT/MA/6205": [{"municipalities": "MÁLAGA", "lat": 36.7212, "lon": -4.4245}]}
        r = classify.classify(self.view("VUT/MA/062057"), idx, {}, MAX)
        self.assertEqual((r["category"], r["match_key"]), ("FOUND_CONSISTENT", "VUT/MA/6205"))

    def test_national_exempt_does_not_exempt_from_junta(self):
        v = self.view("Spain – National registration number<br />Exempt – tourist apartment")
        self.assertEqual(classify.classify(v, {}, {}, MAX)["category"], "NO_CODE_IN_SCOPE")

    def test_no_code_split(self):
        self.assertEqual(classify.classify(self.view(""), {}, {}, MAX)["category"], "NO_CODE_IN_SCOPE")
        v = dict(self.view("Spain - National registration number<br />ESFCTU00002902000042691900000000000000000000000000003"))
        self.assertEqual(classify.classify(v, {}, {}, MAX)["category"], "NO_CODE_POSSIBLY_EXEMPT")
        v = dict(self.view(""), min_nights="90")
        self.assertEqual(classify.classify(v, {}, {}, MAX)["category"], "NO_CODE_POSSIBLY_EXEMPT")


@unittest.skipUnless(os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audit.py")),
                     "audit.py (the original research tool) isn't part of the public code")
class ShareFlagFixture(unittest.TestCase):
    def test_shared_number_flagged_same_host(self):
        import audit
        rows = [{"listing_id": "1000000000000000001", "junta_codes_norm": "VUT/MA/12345", "live_host_id": "111111", "flags": []},
                {"listing_id": "1000000000000000002", "junta_codes_norm": "VUT/MA/12345", "live_host_id": "111111", "flags": []}]

        class C:
            def execute(self, *_):
                return []
        audit.add_reuse_flags(rows, {}, C(), MAX)
        for r in rows:
            self.assertIn("code_reused_same_host", r["flags"])


class AddressTests(unittest.TestCase):
    def test_street_and_number(self):
        from rta_audit import address
        recs = [{"road_name": "EJEMPLO", "km_num": "27", "registration_code": "VUT/MA/85549"},
                {"road_name": "EJEMPLO", "km_num": "21", "registration_code": "VUT/MA/33620"},
                {"road_name": "del TEATRO", "km_num": "3", "registration_code": "VUT/MA/00005"}]
        idx = address.StreetIndex(recs)
        c = idx.find("Lovely flat at Calle Ejemplo 27, 5A")[0]
        self.assertEqual((c["street"], c["number"]), ("EJEMPLO", "27"))
        self.assertEqual([r["registration_code"] for r in c["records_at_number"]], ["VUT/MA/85549"])
        c = idx.find("Steps from Plaza del Teatro")[0]
        self.assertEqual((c["street"], c["number"]), ("TEATRO", None))


if __name__ == "__main__":
    unittest.main()
