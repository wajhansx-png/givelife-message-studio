import unittest
import test_manual_sends as fixture
from test_manual_sends import app
import caption_facts, draft_workflow

SOURCE = "💔 *Yousaf has passed away.*\n\n_His Janazah time has not been announced because the family is short of funds._\n\nRs. 25,000 urgently needed.\n\n13 kind people donating Rs. 2,000 OR 25 × Rs. 1,000 can help the family.\n\n03097458815 Easypaisa / JazzCash Wajdan Khan"


class CaptionFactsTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def seed(self):
        app.write_left(25000)
        app.save_draft("group", SOURCE)
        app.save_draft("dm", "Brother, " + SOURCE)
        app.STORE.put(
            "focus_wording",
            {
                k: {
                    "source": app.get_message(k)["text"],
                    "items": [
                        app.get_message(k)["text"].replace("short of funds", "unable to pay")
                    ],
                    "revision": "old",
                    "state": "Ready",
                }
                for k in ("group", "dm")
            },
        )

    def test_dispatch_refreshes_amount_inside_whatsapp_italics(self):
        # '_' is a regex word character, so a -bounded pattern missed '*_Rs. 25,000 LEFT_*'
        # and reserved Group versions went out with the old balance.
        app.write_left(23000)
        for text in ("*_Rs. 25,000 LEFT_*", "_Rs. 25,000 needed_", "Rs. 25,000 left."):
            with self.subTest(text=text):
                self.assertIn("23,000", caption_facts.current(app, text))

    def test_amount_updates_every_saved_variant_without_rebuilding_old_case(self):
        self.seed()
        self.assertTrue(app.manual_command("23k left now")["handled"])
        for row in app.STORE.get("focus_wording").values():
            for text in [row["source"], *row["items"]]:
                self.assertIn("23,000 urgently needed", text)
                self.assertIn("12 kind people donating Rs. 2,000", text)
                self.assertIn("23 × Rs. 1,000", text)
                self.assertIn("passed away", text)
                self.assertNotIn("fluid", text)
        self.assertIn("passed away", app.get_message("group")["text"])

    def test_chat_balance_updates_both_saved_drafts_and_visible_response(self):
        self.seed()
        old_group = app.get_message("group")["text"]
        old_dm = app.get_message("dm")["text"]
        result = app.manual_command("23k left now")
        self.assertTrue(result["handled"])
        self.assertEqual(result["left"], 23000)
        for kind, old_text in (("group", old_group), ("dm", old_dm)):
            updated = app.get_message(kind)["text"]
            self.assertEqual(result[kind], updated)
            self.assertIn("23,000 urgently needed", updated)
            self.assertIn("12 kind people donating Rs. 2,000", updated)
            self.assertNotIn("25,000 urgently needed", updated)
            self.assertIn("passed away", updated)
            self.assertIn("Janazah", updated)

    def test_balance_in_whatsapp_formatting_updates_but_contribution_amount_stays(self):
        text = (
            "*_Rs. 2,000 LEFT_*\n\n"
            "*_1 people donating Rs. 2,000_*\n"
            "*_OR 2 people donating Rs. 1,000_*\n"
            "Earlier hospital bill was Rs. 2,000."
        )
        updated = draft_workflow.update_amount(text, 2000, 1000)
        self.assertIn("Rs. 1,000 LEFT", updated)
        self.assertIn("1 people donating Rs. 2,000", updated)
        self.assertIn("1 people donating Rs. 1,000", updated)
        self.assertIn("Earlier hospital bill was Rs. 2,000.", updated)

    def test_stale_balance_can_be_corrected_without_overwriting_other_rupee_facts(self):
        text = "Previous treatment cost Rs. 25,000.\n\n*_Rs. 30,000 LEFT_*\n\n15 people donating Rs. 2,000"
        updated = draft_workflow.update_amount(text, 28000, 22000)
        self.assertIn("Previous treatment cost Rs. 25,000.", updated)
        self.assertIn("Rs. 22,000 LEFT", updated)
        self.assertIn("11 people donating Rs. 2,000", updated)
        self.assertNotIn("30,000 LEFT", updated)

    def test_chat_time_updates_both_banks_and_pending_caption(self):
        self.seed()
        result = app.manual_command("Janazah time is 5:30 pm today")
        self.assertTrue(result["handled"])
        self.assertIn("5:30 PM today", result["reply"])
        for row in app.STORE.get("focus_wording").values():
            for text in [row["source"], *row["items"]]:
                self.assertIn("The Janazah is at 5:30 PM today.", text)
                self.assertNotIn("not been announced", text)
        self.assertIn("5:30 PM today", caption_facts.current(app, SOURCE))

    def test_unclear_questions_and_hypotheticals_do_not_set_time(self):
        for text in (
            "When is Janazah time?",
            "if Janazah time is 5 pm",
            "do not update Janazah time is 5 pm",
        ):
            self.assertIsNone(caption_facts.parse_time(text))
        with self.assertRaises(ValueError):
            caption_facts.parse_time("Janazah time is 5")

    def test_supported_count_styles(self):
        for old, expected in [
            ("25 people or Rs. 2,000", "24 people or Rs. 2,000"),
            ("50 × Rs. 1,000", "48 × Rs. 1,000"),
            ("Rs. 1000 by 50 people", "Rs. 1000 by 48 people"),
        ]:
            self.assertEqual(draft_workflow.update_amount(old, 50000, 48000), expected)
