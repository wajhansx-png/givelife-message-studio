"""Versions keep the owner's concept and urgency: no invented danger words, the hook idea stays the owner's."""

import unittest

import dm_variants
import focus_bank

SOURCE = (
    "*Mirha's lungs are close to failing. Her mother is asking for help with folded hands.* 💔\n\n"
    "_Mirha is only 2. Her lungs are severely affected. Every breath is a struggle. Her life is at risk._ 💔\n\n"
    "🔴 Rs. 23,500 LEFT\n\n"
    "*Easypaisa ONLY*\n03097458815\n*Wajdan Khan (GiveLife Foundation account)*"
)


class Concept(unittest.TestCase):
    def test_alarm_words_not_in_the_source_are_rejected(self):
        scary = SOURCE.replace(
            "Her mother is asking for help with folded hands.", "She could die any moment."
        )
        self.assertIn("invented danger", focus_bank.reject_reason(SOURCE, scary))

    def test_alarm_words_the_owner_wrote_are_allowed(self):
        own = SOURCE.replace("Her life is at risk.", "She could die without oxygen.")
        self.assertEqual(dm_variants.alarm_terms(own), {"die"})
        reworded = own.replace("Every breath is a struggle.", "Each breath is hard for her.")
        self.assertNotIn("invented danger", focus_bank.reject_reason(own, reworded))

    def test_the_prompt_keeps_the_hook_idea_and_never_raises_urgency(self):
        prompt = dm_variants._prompt(SOURCE, 3, [])
        self.assertIn("say the source's own hook idea in new words", prompt)
        self.assertIn("never raise it and never lower it", prompt)
        self.assertNotIn("pattern interrupt", prompt)
        self.assertNotIn("loss aversion", prompt)
        self.assertTrue(all(a.startswith("keep the source's hook idea") for a in focus_bank.ANGLES))


if __name__ == "__main__":
    unittest.main()
