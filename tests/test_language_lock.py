"""Versions keep the source language: English never gains Urdu, Urdu lines never become English."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dm_variants, focus_bank


class LanguageLock(unittest.TestCase):
    def test_english_gains_urdu(self):
        self.assertTrue(dm_variants.language_changed("Hello friends\nPlease help", "Hello\nمدد کریں"))

    def test_urdu_becomes_english(self):
        self.assertTrue(dm_variants.language_changed("*بچہ چلا گیا* 💔\nDetails", "*Child passed* 💔\nDetails"))

    def test_same_language_ok(self):
        self.assertFalse(dm_variants.language_changed("Hello friends\nPlease help", "Hi all\nKindly help"))

    def test_both_paths_reject(self):
        src = "Hello friends\nPlease help"
        self.assertIn("language", dm_variants.validate(src, "Hello\n" + "مدد کریں " * 30))
        self.assertIn("language", focus_bank.reject_reason(src, "Hello\nمدد کریں"))


if __name__ == "__main__":
    unittest.main()
