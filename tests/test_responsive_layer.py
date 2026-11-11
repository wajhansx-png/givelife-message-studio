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

    def test_critical_mobile_overrides_out_rank_the_older_layers(self):
        # Compare the selectors that actually compete for the repaired layouts.
        # Harmless rules do not need the same literal prefix. Computed geometry,
        # touch targets and menu behavior are verified on both routes by
        # donor_responsive_cascade.spec.cjs against the complete loaded cascade.
        older = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in ("donors.css", "comfort.css", "new-ui.css")
        ).replace(".UI2", "html body.ui2" + ":not(#ui)" * 8)

        def selectors(text, suffix):
            clean = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            return [
                selector.strip()
                for selector, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", clean)
                if selector.strip().endswith(suffix)
                and "," not in selector
            ]

        for suffix in (" .donor-tabs", " .donor-row"):
            old_rules = selectors(older, suffix)
            overrides = selectors(CSS, suffix)
            self.assertTrue(old_rules, suffix)
            self.assertTrue(overrides, suffix)
            # A higher ID specificity wins even when /new is loaded afterward.
            self.assertGreater(
                max(selector.count("#") for selector in overrides),
                max(selector.count("#") for selector in old_rules),
                suffix,
            )


if __name__ == "__main__":
    unittest.main()
