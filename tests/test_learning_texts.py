"""Per-wording learning: real outcomes, credited only to the post before the money."""

import tempfile, time, unittest
from pathlib import Path

import dm_variants
import learning
from donor_book import DonorBook


class LearningTexts(unittest.TestCase):
    def setUp(self):
        self.saved = dm_variants.PROVEN

    def tearDown(self):
        dm_variants.PROVEN = self.saved

    def test_money_credits_the_exact_wording_posted_within_the_hour(self):
        L = learning.new()
        for i in range(3):
            learning.record_post(L, 0, ts=1000 + i, text="Wording A")
        learning.record_post(L, 0, ts=5000, text="Wording B")
        learning.credit_money(L, ts=1500)
        self.assertEqual(learning.proven_texts(L), ["Wording A"])
        learning.credit_money(L, ts=99999)  # no post in the last hour: nobody is credited
        self.assertEqual(L["texts"][learning._text_key("Wording B")]["wins"], 0)

    def test_too_few_posts_or_no_money_is_never_proven(self):
        L = learning.new()
        learning.record_post(L, 0, ts=1000, text="Only once")
        learning.credit_money(L, ts=1001)
        self.assertEqual(learning.proven_texts(L), [])

    def test_old_saved_posts_without_text_still_credit(self):
        L = learning.new()
        L["recent"] = [[1000, 2]]
        self.assertEqual(learning.credit_money(L, ts=1100), 2)

    def test_prompt_uses_proven_style_but_says_never_copy_facts(self):
        dm_variants.PROVEN = lambda: ["Only 22 hours left. Help now."]
        prompt = dm_variants._prompt("Line one\nRs. 5,000 left", 3, [])
        self.assertIn("PROVEN STYLE", prompt)
        self.assertIn("Never copy their facts", prompt)
        dm_variants.PROVEN = lambda: 1 / 0
        self.assertNotIn("PROVEN STYLE", dm_variants._prompt("a\nb", 2, []))


class DmLearning(unittest.TestCase):
    def test_dm_wording_is_credited_when_that_donor_donates(self):
        with tempfile.TemporaryDirectory() as folder:
            book = DonorBook(Path(folder))
            ids = [book.add("D%d" % i, "92311%07d" % (4000000 + i))["donor"]["id"] for i in range(5)]
            for i in ids:
                book.delivery(i, "Sent", time.time(), text="Wording X")
            book.update(ids[0], donated=True, amount=2000)
            self.assertEqual(book.proven_dm_texts(), ["Wording X"])

    def test_unconfirmed_or_old_dm_never_teaches(self):
        with tempfile.TemporaryDirectory() as folder:
            book = DonorBook(Path(folder))
            ids = [book.add("E%d" % i, "92311%07d" % (5000000 + i))["donor"]["id"] for i in range(5)]
            for i in ids:
                book.delivery(i, "Uncertain", text="Never sent")
                book.delivery(i, "Sent", time.time() - 30 * 86400, text="Old wording")
            book.update(ids[0], donated=True, amount=2000)
            self.assertEqual(book.proven_dm_texts(), [])


if __name__ == "__main__":
    unittest.main()
