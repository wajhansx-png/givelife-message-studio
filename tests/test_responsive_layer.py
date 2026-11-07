"""The responsive layer is loaded last, is served, and has a rule for every width band."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "responsive.css").read_text(encoding="utf-8")


class ResponsiveLayer(unittest.TestCase):
    def test_linked_after_every_other_stylesheet(self):
        links = re.findall(
            r'<link rel="stylesheet" href="(/[^"]+\.css)"',
            (ROOT / "index.html").read_text(encoding="utf-8"),
        )
        self.assertEqual(links[-1], "/responsive.css")

    def test_server_serves_it(self):
        self.assertIn('"/responsive.css"', (ROOT / "server.py").read_text(encoding="utf-8"))

    def test_every_width_band_has_rules(self):
        queries = set(re.findall(r"@media \(([^)]+)\)", CSS))
        for band in (
            "max-width: 299px",
            "max-width: 359px",
            "max-width: 380px",
            "max-width: 899px",
            "min-width: 900px",
        ):
            self.assertIn(band, queries, band)

    def test_rules_out_rank_the_older_layers(self):
        selectors = re.findall(r"^\s*(html body[^{]+)\{", CSS, re.M)
        self.assertTrue(selectors)
        for sel in selectors:
            self.assertIn(":not(#a):not(#b):not(#c)", sel)

    def test_every_declaration_is_important(self):
        body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
        for decl in re.findall(r"\{([^{}]*)\}", body):
            for line in filter(None, (x.strip() for x in decl.split(";"))):
                self.assertTrue(line.endswith("!important"), line)


if __name__ == "__main__":
    unittest.main()
