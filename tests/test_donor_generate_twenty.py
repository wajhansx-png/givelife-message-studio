"""Offline Generate 20 regression: no AI calls or WhatsApp sending."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from donor_messages import MessageBank


class FakeStore:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def put(self, key, value):
        self.data[key] = copy.deepcopy(value)


class GenerateTwentyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = "*This is the owner's approved base*\nRs. 16,000 still needed.\nEASYPAISA ONLY"
        self.store = FakeStore()
        app = SimpleNamespace(
            DATA=Path(self.tmp.name),
            STORE=self.store,
            get_message=lambda kind: {"text": self.source},
            read_left=lambda: 16000,
        )
        self.bank = MessageBank(app)
        self.bank.cache = {
            "mode": "custom",
            "items": [{"id": "wording-01", "text": self.source, "enabled": True}],
            "origin": self.source,
            "left": 16000,
            "generation": {},
        }
        self.launched = []
        self.bank._launch_regeneration = lambda data: self.launched.append(copy.deepcopy(data))

    def test_generate_20_starts_from_saved_message_one(self):
        with patch("donor_messages.dm_composer.complete", return_value=True):
            result = self.bank.start_regeneration()
        self.assertEqual(result["generation"]["state"], "Generating")
        self.assertEqual(result["generation"]["target"], 20)
        self.assertEqual(result["generation"]["ready"], 1)
        self.assertEqual(result["items"][0]["text"], self.source)
        self.assertEqual(len(self.launched), 1)
        self.assertEqual(self.store.get("donor_messages")["generation"]["target"], 20)

    def test_repeated_tap_does_not_start_second_generation(self):
        with patch("donor_messages.dm_composer.complete", return_value=True):
            first = self.bank.start_regeneration()
            second = self.bank.start_regeneration()
        self.assertEqual(first["generation"]["id"], second["generation"]["id"])
        self.assertEqual(len(self.launched), 1)

    def test_incomplete_base_is_rejected_without_saving(self):
        with patch("donor_messages.dm_composer.complete", return_value=False):
            with self.assertRaisesRegex(ValueError, "complete message"):
                self.bank.start_regeneration()
        self.assertEqual(self.store.data, {})


class MobileButtonTest(unittest.TestCase):
    def test_generator_is_visible_in_action_area_not_header(self):
        root = Path(__file__).resolve().parents[1]
        javascript = (root / "donors.js").read_text()
        css = (root / "donors.css").read_text()
        self.assertIn("actions.append(baseBtn, testBtn, regen, regenProgress, nav)", javascript)
        self.assertNotIn("head.append(regen)", javascript)
        self.assertIn("action: 'regenerate'", javascript)
        self.assertIn("bank-regenerate-progress", javascript)
        self.assertIn(".bank-actions > .bank-regenerate {", css)
        self.assertIn("grid-column: 1 / -1;", css)
        self.assertIn("background: linear-gradient", css)


if __name__ == "__main__":
    unittest.main()
