"""Style fix: same words, the owner's structure. Nothing new is written; nothing is saved or sent."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import style_fix  # noqa: E402

HOOK = "آپ کے ایک قدم سے ایک غمزدہ باپ کا بوجھ ہلکا ہو سکتا ہے"
STORY = (
    "Yousaf was only 2 years old. He has passed away. His father borrowed money for the Janazah and burial. "
    "Now people come to his home asking for their money back. Your help is already making a difference. "
    "Only Rs. 2,000 is left. 💔"
)
VERSE = 'اللہ تعالیٰ کا ارشاد ہے:\n"نیکی اور تقویٰ میں ایک دوسرے کی مدد کرو۔"\n(سورة المائدة: 2)'
PAY = "03097458815\nEASYPAISA ONLY (Wajdan Khan)\n\n— GiveLife Foundation"
GOOD = "\n\n".join(
    [
        f"*{HOOK}*",
        f"_{STORY}_",
        VERSE,
        "🔴 Rs. 2,000 LEFT",
        "• *_Just 2 people donating Rs. 1,000 can help this grieving father._* 🤲",
        PAY,
    ]
)
# the same words with the wrong markers: nothing bold, nothing italic, bullet and amount unformatted
PLAIN = "\n\n".join(
    [
        HOOK,
        STORY,
        VERSE,
        "Rs. 2,000 LEFT",
        "- Just 2 people donating Rs. 1,000 can help this grieving father. 🤲",
        PAY,
    ]
)


def words(text):
    return re.findall(r"[^\W_]+", re.sub(r"[*_]", "", text).casefold())


class StyleFix(unittest.TestCase):
    def test_a_correct_message_is_left_exactly_as_it_is(self):
        out = style_fix.fix(GOOD, left=2000)
        self.assertFalse(out["changed"])
        self.assertEqual(out["text"], GOOD)
        self.assertEqual(out["changes"], [])

    def test_unformatted_message_gets_the_owners_bold_and_italic_and_nothing_else(self):
        out = style_fix.fix(PLAIN, left=2000)
        self.assertEqual(out["text"], GOOD)
        self.assertTrue(out["changed"])
        self.assertIn("Line 1 is bold", out["changes"])
        self.assertIn("Line 2 is italic", out["changes"])

    def test_not_one_word_changes_when_only_formatting_is_fixed(self):
        out = style_fix.fix(PLAIN, left=2000)
        self.assertEqual(words(out["text"]), words(PLAIN))

    def test_it_is_idempotent(self):
        once = style_fix.fix(PLAIN, left=2000)["text"]
        twice = style_fix.fix(once, left=2000)
        self.assertEqual(twice["text"], once)
        self.assertFalse(twice["changed"])

    def test_wrong_markers_are_replaced_not_stacked(self):
        messy = GOOD.replace(f"*{HOOK}*", f"_*{HOOK}*_").replace(f"_{STORY}_", f"*{STORY}*")
        out = style_fix.fix(messy, left=2000)
        self.assertEqual(out["text"], GOOD)

    def test_stray_markers_in_the_verse_are_removed(self):
        out = style_fix.fix(GOOD.replace("(سورة المائدة: 2)", "*(سورة المائدة: 2)*"), left=2000)
        self.assertEqual(out["text"], GOOD)

    def test_blank_lines_between_parts_are_made_even(self):
        spaced = GOOD.replace("\n\n", "\n\n\n\n")
        self.assertEqual(style_fix.fix(spaced, left=2000)["text"], GOOD)

    def test_missing_amount_help_line_and_payment_are_added_from_the_live_case(self):
        short = "\n\n".join([HOOK, STORY, VERSE])
        out = style_fix.fix(short, left=25000, saved=[GOOD])
        parts = out["text"].split("\n\n")
        self.assertEqual(parts[0], f"*{HOOK}*")
        self.assertEqual(parts[1], f"_{STORY}_")
        self.assertIn("🔴 Rs. 25,000 LEFT", parts)
        self.assertIn("• *_Just 5 people donating Rs. 5,000 can help this family._* 🤲", parts)
        self.assertTrue(out["text"].rstrip().endswith("— GiveLife Foundation"))
        self.assertIn("03097458815", out["text"])  # the owner's saved account, not invented
        self.assertTrue(any("Added the amount line" in c for c in out["changes"]))
        self.assertIn("Added the help line", out["changes"])
        self.assertIn("Added the payment account and signature", out["changes"])
        # amount comes before the help line, both before the payment block
        i = out["text"].index
        self.assertTrue(i("🔴 Rs. 25,000") < i("• *_Just") < i("03097458815"))

    def test_a_finished_case_adds_no_amount_or_donor_sum(self):
        short = "\n\n".join([HOOK, STORY, VERSE])
        out = style_fix.fix(short, left=0, saved=[GOOD])
        self.assertNotIn("LEFT", out["text"])
        self.assertNotIn("Just", out["text"])
        self.assertIn("03097458815", out["text"])

    def test_no_live_amount_means_nothing_that_needs_it_is_added(self):
        out = style_fix.fix("\n\n".join([HOOK, STORY]), left=None, saved=[GOOD])
        self.assertNotIn("LEFT", out["text"])

    def test_signature_is_added_when_only_the_account_is_there(self):
        out = style_fix.fix(GOOD.replace("\n\n— GiveLife Foundation", ""), left=2000)
        self.assertTrue(out["text"].rstrip().endswith("— GiveLife Foundation"))
        self.assertIn("Added the signature", out["changes"])

    def test_extra_lines_the_owner_wrote_stay_where_they_are(self):
        extra = GOOD + "\n\nReply Done after donating."
        out = style_fix.fix(extra, left=2000)
        self.assertEqual(out["text"], extra)

    def test_pdf_style_message_is_fixed_the_same_way(self):
        pdf = "\n\n".join(
            [
                "Parents sit with their child's body and have no money for the burial. 💔",
                "The father borrowed money and now people ask for it back.",
                "Just 2 kind people donating Rs. 2,000 or 4 people donating Rs. 1,000 can complete this amount.",
                "Please don't think someone else will help.",
                "03097458815\nEASYPAISA ONLY – Wajdan Khan (GiveLife Foundation account)\n— GiveLife Foundation",
            ]
        )
        out = style_fix.fix(pdf, left=4000)
        parts = out["text"].split("\n\n")
        self.assertEqual(parts[0], "*Parents sit with their child's body and have no money for the burial.* 💔")
        self.assertEqual(parts[1], "_The father borrowed money and now people ask for it back._")
        self.assertTrue(parts[2].startswith("• *_Just 2 kind people"))
        self.assertTrue(parts[2].endswith("_*"))
        self.assertNotIn("🔴", out["text"])  # the PDF layout has no separate amount line

    def test_lines_pasted_without_blank_lines_are_separated(self):
        crammed = "\n".join([HOOK, STORY, "Rs. 2,000 LEFT", "- Just 2 people donating Rs. 1,000 can help this father.", "03097458815", "EASYPAISA ONLY (Wajdan Khan)", "— GiveLife Foundation"])
        out = style_fix.fix(crammed, left=2000)
        self.assertTrue(out["text"].startswith(f"*{HOOK}*\n\n_{STORY}_\n\n🔴 Rs. 2,000 LEFT\n\n• *_Just 2 people"))

    def test_empty_message_is_refused_with_a_plain_reason(self):
        with self.assertRaises(ValueError):
            style_fix.fix("   \n ", left=1000)


if __name__ == "__main__":
    unittest.main()
