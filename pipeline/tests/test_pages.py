"""Static pages (rta_audit/pages.py): every routed address gets a complete page of its own, from the published data."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rta_audit import pages  # noqa: E402

SITE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "site")


def copy_site(dst):
    """Templates, the hand-written llms.txt, _redirects and the published JSON the pages are built from."""
    for n in os.listdir(SITE):
        if n.endswith(".html") or n in ("llms.txt", "_redirects"):
            shutil.copy(os.path.join(SITE, n), dst)
    if os.path.isdir(os.path.join(SITE, "guias")):
        shutil.copytree(os.path.join(SITE, "guias"), os.path.join(dst, "guias"))
    src = os.path.join(SITE, "data")
    os.makedirs(os.path.join(dst, "data"))
    for n in ("areas.json", "meta.json", "ranking.json"):
        shutil.copy(os.path.join(src, n), os.path.join(dst, "data", n))
    for a in json.load(open(os.path.join(src, "areas.json")))["areas"]:
        os.makedirs(os.path.join(dst, "data", a["slug"]))
        shutil.copy(os.path.join(src, a["slug"], "summary.json"), os.path.join(dst, "data", a["slug"], "summary.json"))


class Formatting(unittest.TestCase):
    def test_numbers_and_shares_as_the_site_writes_them(self):
        self.assertEqual(pages.num(12616), "12.616")
        self.assertEqual(pages.num(763), "763")
        self.assertEqual(pages.num(12616, lang="en"), "12,616")
        self.assertEqual(pages.pct(4.83, 1), "4,8 %")
        self.assertEqual(pages.pct(38.0, 1), "38 %")
        self.assertEqual(pages.pct(31.3, 0, "en"), "31%")
        self.assertEqual(pages.day("2026-10-16T04:05:39.000Z"), "16 de octubre de 2026")


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        copy_site(cls.tmp)
        cls.written, cls.problems = pages.write_all(cls.tmp)
        cls.areas = json.load(open(os.path.join(cls.tmp, "data", "areas.json")))["areas"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def read(self, rel):
        return open(os.path.join(self.tmp, "data", "pages", rel), encoding="utf-8").read()

    def test_no_problems(self):
        self.assertEqual(self.problems, [])

    def test_every_routed_address_has_its_file(self):
        for line in open(os.path.join(SITE, "_redirects")):
            parts = line.split()
            if len(parts) == 3 and not parts[0].startswith("#") and "*" not in parts[0]:
                self.assertTrue(os.path.exists(os.path.join(self.tmp, parts[1].lstrip("/"))) or parts[1].startswith("/guias"),
                                f"{parts[0]} → {parts[1]} missing")

    def test_each_page_has_its_own_title_canonical_and_one_h1(self):
        titles = set()
        for a in self.areas:
            for rel, path in ((f"{a['slug']}/index.html", f"/{a['slug']}"), (f"{a['slug']}/zonas.html", f"/{a['slug']}/zonas"),
                              (f"{a['slug']}/mapa.html", f"/{a['slug']}/mapa")):
                h = self.read(rel)
                t = re.search(r"<title>(.*?)</title>", h).group(1)
                self.assertNotIn(t, titles, rel)
                titles.add(t)
                self.assertIn(f'<link rel="canonical" href="https://tienelicencia.com{path}">', h, rel)
                self.assertEqual(len(re.findall(r"<h1\b", h)), 1, rel)
                for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
                    json.loads(ld)
                self.assertNotRegex(h.lower(), r"\bilegal|\billegal", rel)

    def test_area_page_has_the_figures_in_the_html(self):
        a = next(x for x in self.areas if x["slug"] == "malaga")
        h = self.read("malaga/index.html")
        self.assertIn(pages.num(a["vut"]), re.search(r"<title>(.*?)</title>", h).group(1))
        self.assertIn('id="area-facts"', h)
        self.assertIn('href="/malaga/mapa"', h)                      # the map link is real, not "#"
        self.assertIn('href="/provincia"', h)                        # its province, and nearby areas
        self.assertIn("Fuente: Registro de Turismo de Andalucía", h)

    def test_madrid_doesnt_count_a_missing_number_as_a_problem(self):
        t = re.search(r"<title>(.*?)</title>", self.read("madrid/index.html")).group(1)
        self.assertNotIn("sin número", t)

    def test_zones_table_is_in_the_html(self):
        h = self.read("sevilla/zonas.html")
        self.assertGreater(h.count("<tr>"), 50)

    def test_map_lists_its_biggest_buildings(self):
        h = self.read("malaga/mapa.html")
        self.assertEqual(len(re.findall(r'<li><a href="/malaga/mapa\?b=', h)), pages.TOP_BUILDINGS)
        self.assertGreater(len(re.findall(r'<li><a href="/\w+/mapa\?b=', self.read("mapa.html"))), 0)

    def test_ranking_keeps_the_edge_function_containers_empty(self):
        # netlify/edge-functions/ssr-data.js fills these (only when empty) in the public repository
        h = self.read("ranking.html")
        for el in ("ix-sub", "ix-meta", "ix-lede", "ix"):
            self.assertRegex(h, rf'id="{el}"></')
        self.assertIn('id="tabla"', h)

    def test_sitemap_and_llms(self):
        sm = open(os.path.join(self.tmp, "data", "sitemap.xml")).read()
        for a in self.areas:
            self.assertIn(f"<loc>https://tienelicencia.com/{a['slug']}</loc>", sm)
        ll = open(os.path.join(self.tmp, "data", "llms.txt")).read()
        self.assertTrue(ll.startswith(open(os.path.join(SITE, "llms.txt")).read().rstrip()))
        self.assertIn("https://tienelicencia.com/malaga):", ll)

    def test_homepage_links_every_area(self):
        h = open(os.path.join(SITE, "index.html"), encoding="utf-8").read()
        block = h[h.index('id="todas"'):h.index('id="buscar"')]
        for a in self.areas:
            self.assertIn(f'href="/{a["slug"]}"', block, a["slug"])


class OnePageFailing(unittest.TestCase):
    def test_a_broken_summary_writes_the_bare_template_and_is_reported(self):
        tmp = tempfile.mkdtemp()
        try:
            copy_site(tmp)
            with open(os.path.join(tmp, "data", "malaga", "summary.json"), "w") as fh:
                json.dump({"registered": "broken", "subareas": 3}, fh)
            n, problems = pages.write_all(tmp)
            self.assertTrue(any(rel.startswith("malaga/") for rel, _ in problems))
            self.assertTrue(os.path.exists(os.path.join(tmp, "data", "pages", "malaga", "index.html")))
            self.assertIn("Viviendas turísticas en Sevilla", open(os.path.join(tmp, "data", "pages", "sevilla", "index.html")).read())
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
