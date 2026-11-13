"""Owner rule: a donation is never called a "gift" in a written message (gift, gifts, gifted, gifting)."""

import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dm_variants, focus_bank, message_styles, quality  # noqa: E402

SOURCE = "Mirha needs oxygen. Rs. 45,500 left. Please help."


class NoGift(unittest.TestCase):
    def test_every_spelling_is_refused_even_when_the_source_has_it(self):
        for text in (
            "ONE GIFT FROM YOU IS THE OXYGEN MIRHA NEEDS.",
            "Your gift can help.",
            "Two gifts of Rs. 2,000 cover it.",
            "She was gifted time by donors.",
            "Gifting Rs. 1,000 helps.",
        ):
            self.assertIn("never use", quality.hard_reason(SOURCE, text), text)
            self.assertIn("never use", quality.hard_reason(text, text), text)  # also when the source says it

    def test_normal_wording_and_other_words_are_fine(self):
        for text in (
            "One donation from you is the oxygen Mirha needs.",
            "23 people giving Rs. 2,000 each cover both cylinders.",
            "Giftedness is not a word we use, but gifford is a surname.",
        ):
            self.assertEqual(quality.hard_reason(SOURCE, text), "", text)

    def test_the_versions_bank_rejects_a_reworded_version_with_it(self):
        reason = focus_bank.reject_reason(SOURCE, "ONE GIFT FROM YOU IS THE OXYGEN MIRHA NEEDS. Rs. 45,500 left.")
        self.assertIn("gift", reason.lower())

    def test_a_written_message_with_it_fails_the_style_check_and_the_ai_is_told_not_to(self):
        ctx = {"facts": SOURCE, "left": 45500, "people": 23, "each": 2000}
        bad = message_styles.problems("english", "💔 One gift from you is the oxygen she needs.", {"hook": "One gift", "verse": "x"}, ctx)
        self.assertTrue(any("gift" in b for b in bad), bad)
        prompt = message_styles.build_prompt("english", dict(ctx, style_examples=[]), ("a", "an angle"), [], "", [])
        self.assertIn('Never use the word "gift"', prompt)

    def test_the_dm_writing_prompt_carries_the_rule_and_no_longer_suggests_gift(self):
        prompt = dm_variants._prompt(SOURCE, 3, [])
        self.assertIn('Never use the word "gift"', prompt)
        self.assertNotIn("small gift", prompt)


if __name__ == "__main__":
    unittest.main()
