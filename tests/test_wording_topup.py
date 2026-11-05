"""Stuck wording banks are topped up automatically (bounded); previews show the live amount."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as app


class FakeBank:
    def __init__(self, rows):
        self.rows, self.retried = rows, []

    def get(self, kind):
        if isinstance(self.rows[kind], Exception):
            raise self.rows[kind]
        return self.rows[kind]

    def retry(self, kind, fresh=False):
        self.retried.append(kind)


class Topup(unittest.TestCase):
    def test_only_stuck_banks_are_retried(self):
        bank = FakeBank(
            {
                "group": {"state": "Partial", "revision": "g1"},
                "dm": {"state": "Ready", "revision": "d1"},
            }
        )
        self.assertEqual(app.wording_topup(bank, tries={}), ["group"])
        self.assertEqual(bank.retried, ["group"])

    def test_gives_up_after_max_tries_for_the_same_revision(self):
        bank, tries = (
            FakeBank({"group": {"state": "Partial", "revision": "g1"}, "dm": {"state": "Ready"}}),
            {},
        )
        runs = [app.wording_topup(bank, tries=tries, max_tries=3) for _ in range(5)]
        self.assertEqual(runs, [["group"]] * 3 + [[]] * 2)

    def test_new_revision_gets_a_fresh_set_of_tries(self):
        tries = {("group", "g1"): 5}
        bank = FakeBank(
            {"group": {"state": "Needs retry", "revision": "g2"}, "dm": {"state": "Ready"}}
        )
        self.assertEqual(app.wording_topup(bank, tries=tries), ["group"])

    def test_one_broken_bank_does_not_stop_the_other(self):
        bank = FakeBank(
            {"group": RuntimeError("boom"), "dm": {"state": "Partial", "revision": "d1"}}
        )
        self.assertEqual(app.wording_topup(bank, tries={}), ["dm"])


class PreviewAmount(unittest.TestCase):
    def test_next_message_preview_uses_the_live_amount(self):
        old = "*Rs. 17,500 is still left to clear this debt.*\n\n03097458815"
        bank = mock.Mock()
        bank.get.return_value = {"revision": "r", "items": [old]}
        with (
            mock.patch.object(app, "STORE", object()),
            mock.patch.object(app, "focus_bank", return_value=bank),
            mock.patch.object(app, "save_draft"),
            mock.patch.object(
                app.caption_facts, "current", lambda _a, t: t.replace("17,500", "19,500")
            ),
        ):
            self.assertIn("19,500", app.next_message())


if __name__ == "__main__":
    unittest.main()
