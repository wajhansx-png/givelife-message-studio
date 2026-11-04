"""A chat balance change must refresh every Group/DM copy without changing the case story."""

import unittest
from unittest.mock import patch

import test_manual_sends as fixture
from test_manual_sends import app
import caption_facts
import draft_workflow


GROUP = (
    "*Please help the family today.*\n\n"
    "Rs. 25,000 urgently needed.\n\n"
    "*_13 people donating Rs. 2,000_* OR *_25 people donating Rs. 1,000_*\n"
    "Treatment is urgent; the family's medical reports have been checked."
)
DM = (
    "Brother, please help this child.\n\n"
    "*_Rs. 25k left_*\n"
    "*_13 people donating Rs. 2,000_* OR *_25 people donating Rs. 1,000_*\n"
    "The family is waiting for help."
)


class BalanceSynchronisation(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def seed(self):
        app.write_left(25000)
        app.save_draft("group", GROUP)
        app.save_draft("dm", DM)
        app.STORE.put(
            "focus_wording",
            {
                kind: {
                    "source": source,
                    "items": [source.replace("please", "kindly", 1)],
                    "revision": "previous-revision",
                    "state": "Ready",
                }
                for kind, source in (("group", GROUP), ("dm", DM))
            },
        )
        app.STORE.put(
            "donor_messages",
            {
                "mode": "custom",
                "left": 25000,
                "items": [{"id": "wording-01", "text": DM, "enabled": True}],
                "previous_items": [{"id": "wording-old", "text": DM, "enabled": True}],
                "origin": DM,
                "base": DM,
                "generation": {"state": "Ready"},
            },
        )

    def test_chat_updates_drafts_and_all_saved_versions_preserving_wording(self):
        self.seed()
        with patch.object(app, "DONORS", None):
            response = app.manual_command("23k left now")
        self.assertTrue(response["handled"])
        self.assertEqual(response["left"], 23000)
        self.assertIn("Please help the family today", response["group"])
        self.assertIn("23,000 urgently needed", response["group"])
        self.assertIn("23,000 left", response["dm"])
        for text in (response["group"], response["dm"]):
            self.assertIn("12 people donating Rs. 2,000", text)
            self.assertIn("23 people donating Rs. 1,000", text)
        self.assertIn("medical reports have been checked", response["group"])
        self.assertIn("The family is waiting for help", response["dm"])
        for row in app.STORE.get("focus_wording").values():
            for text in [row["source"], *row["items"]]:
                self.assertIn("23,000", text)
                self.assertNotIn("25,000", text)
                self.assertNotIn("25k left", text)
        bank = app.STORE.get("donor_messages")
        for text in [
            *(row["text"] for row in bank["items"]),
            *(row["text"] for row in bank["previous_items"]),
            bank["origin"],
            bank["base"],
        ]:
            self.assertIn("23,000", text)
            self.assertNotIn("25k", text)
            self.assertIn("Rs. 2,000", text)
        self.assertEqual(bank["left"], 23000)

    def test_amount_update_does_not_replace_custom_copy_without_focus_bank(self):
        self.seed()
        app.STORE.put("focus_wording", {})
        with patch.object(app, "DONORS", None):
            app.set_left(22000)
        self.assertIn("Please help the family today", app.get_message("group")["text"])
        self.assertIn("22,000 urgently needed", app.get_message("group")["text"])
        self.assertIn("22,000 left", app.get_message("dm")["text"])
        self.assertEqual(app.read_left(), 22000)

    def test_send_time_refresh_replaces_stale_shorthand_but_not_giving_units(self):
        self.seed()
        app.write_left(23000)
        text = caption_facts.current(app, DM)
        self.assertIn("23,000 left", text)
        self.assertIn("12 people donating Rs. 2,000", text)
        self.assertIn("23 people donating Rs. 1,000", text)

    def test_small_balance_does_not_change_rs_2000_per_donor(self):
        text = "Rs. 2,000 left. 1 people donating Rs. 2,000 OR 2 people donating Rs. 1,000."
        changed = draft_workflow.update_amount(text, 2000, 1000)
        self.assertIn("Rs. 1,000 left", changed)
        self.assertIn("1 people donating Rs. 2,000", changed)
        self.assertIn("1 people donating Rs. 1,000", changed)

    def test_ambiguous_numbers_without_balance_do_not_change(self):
        text = "Medical bills: Rs. 2,000. Doctor visited 4 times."
        self.assertEqual(draft_workflow.update_amount(text, 2000, 1500), text)


if __name__ == "__main__":
    unittest.main()
