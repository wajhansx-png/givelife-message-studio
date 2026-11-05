"""Notes privacy and durability regressions; no real personal data or cloud calls."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import notes_store as N


class Store:
    def __init__(self):
        self.records = {}

    def get(self, key, default=None):
        return self.records.get(key, default)

    def put(self, key, value):
        self.records[key] = value


class NotesTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        N._attempts.clear()

    def test_private_lock_with_remembered_desktop_device(self):
        with patch.dict(os.environ, {"NOTES_PASSWORD": "only-for-tests"}):
            self.assertFalse(N.allowed(self.store, ""))
            with self.assertRaisesRegex(ValueError, "Incorrect"):
                N.unlock(self.store, "wrong")
            token = N.unlock(self.store, "only-for-tests")
            cookie = N.device_cookie(token)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            header = f"{N.COOKIE}={token}"
            self.assertTrue(N.allowed(self.store, header))
            self.assertFalse(N.allowed(Store(), header), "a different backend cannot unlock notes")
            self.assertFalse(N.allowed(self.store, f"{N.COOKIE}=fake"))
            N.lock_device(self.store, header)
            self.assertFalse(N.allowed(self.store, header))

    def test_bad_attempts_are_limited(self):
        with patch.dict(os.environ, {"NOTES_PASSWORD": "only-for-tests"}):
            for _ in range(5):
                with self.assertRaisesRegex(ValueError, "Incorrect"):
                    N.unlock(self.store, "no")
            with self.assertRaisesRegex(ValueError, "Too many attempts"):
                N.unlock(self.store, "only-for-tests")

    def test_safe_formatting_and_checkboxes_survive(self):
        source = '<h1>Hello</h1><p><strong>Bold</strong> and <em>italic</em></p><ol><li>First</li></ol><ul class="notes-checklist"><li data-checked="true">Done</li></ul><span style="color:#2563eb">Blue</span>'
        out = N.sanitize(source)
        self.assertIn("<h1>Hello</h1>", out)
        self.assertIn("<strong>Bold</strong>", out)
        self.assertIn("<ol><li>First</li></ol>", out)
        self.assertIn('class="notes-checklist"', out)
        self.assertIn('data-checked="true"', out)
        self.assertIn('style="color:#2563eb"', out)

    def test_never_persists_scripts_handlers_iframes_or_untrusted_links(self):
        out = N.sanitize(
            '<img src="x" onerror="alert(1)"><script>alert(2)</script><p onclick="evil()">Hi</p><iframe src="https://x"></iframe><a href="javascript:evil()">click</a><span style="color:red;background:url(javascript:evil())">bad style</span>'
        )
        for forbidden in (
            "<script",
            "alert(2)",
            "<iframe",
            "<img",
            "onclick",
            "href=",
            "javascript:",
            "<a ",
        ):
            self.assertNotIn(forbidden, out)
        self.assertIn("<p>Hi</p>", out)
        self.assertIn("click", out)

    def test_db_persists_across_instances_and_rejects_stale_edit(self):
        self.assertEqual(N.load(self.store)["revision"], 0)
        result = N.save(self.store, "<h2>Ideas</h2><ul><li>Reach students</li></ul>", 0)
        self.assertEqual(result["revision"], 1)
        self.assertIn("Reach students", N.load(self.store)["html"])
        with self.assertRaisesRegex(ValueError, "another window"):
            N.save(self.store, "overwrite", 0)
        self.assertIn("Reach students", N.load(self.store)["html"])

    def test_large_notes_rejected_without_erasing_previous(self):
        N.save(self.store, "<p>Original note</p>", 0)
        with self.assertRaisesRegex(ValueError, "too long"):
            N.save(self.store, "X" * 250001, 1)
        self.assertIn("Original note", N.load(self.store)["html"])


if __name__ == "__main__":
    unittest.main()
