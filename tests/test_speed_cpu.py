"""Less CPU per send: old batches are slimmed past every resume window, donor lookups copy one record, not the book."""

import time, unittest
import test_manual_sends as fixture
from test_manual_sends import app


class Speed(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_old_batches_keep_their_record_but_drop_full_messages(self):
        jobs = app.donors().jobs
        old = time.time() - 3 * 86400
        heavy = {"caption": "x" * 1500, "captions": ["x" * 1500] * 3, "personal_names": {"a": ["A", "Brother"]}}
        receipt = {"id": "a", "name": "A", "state": "Sent", "after_ids": {"share": "3EB0"}, "steps": {"pdf": "Sent"}}
        data = {
            "jobs": [
                {"id": "old", "state": "Completed", "updated_at": old, "ids": ["a"], "receipts": [dict(receipt)], **heavy},
                {"id": "recent", "state": "Stopped", "updated_at": time.time(), "receipts": [dict(receipt)], **heavy},
                {"id": "last", "state": "Completed", "updated_at": old, "receipts": [dict(receipt)], **heavy},
            ]
        }
        with jobs.lock:
            jobs._save(data)
        out = {j["id"]: j for j in jobs.export_jobs()["jobs"]}
        self.assertNotIn("captions", out["old"])
        self.assertNotIn("after_ids", out["old"]["receipts"][0])
        self.assertEqual(out["old"]["receipts"][0]["state"], "Sent")  # the record stays
        self.assertEqual(out["old"]["receipts"][0]["steps"], {"pdf": "Sent"})
        self.assertEqual(out["old"]["ids"], ["a"])
        self.assertIn("captions", out["recent"])  # inside the resume window: untouched
        self.assertIn("after_ids", out["recent"]["receipts"][0])
        self.assertIn("captions", out["last"])  # the newest batch is never slimmed

    def test_lookup_returns_a_copy_and_still_finds_by_name_and_phone(self):
        book = app.donors().book
        row = book.add("Speed Test Donor", "923001234599")["donor"]
        found = book.resolve(row["id"])
        found["name"] = "changed"  # a caller changing its copy never changes the book
        self.assertEqual(book.resolve(row["id"])["name"], "Speed Test Donor")
        self.assertEqual(book.resolve("Speed Test Donor")["id"], row["id"])
        self.assertEqual(book.resolve("923001234599")["id"], row["id"])
        with self.assertRaises(ValueError):
            book.resolve("Nobody With This Name")
