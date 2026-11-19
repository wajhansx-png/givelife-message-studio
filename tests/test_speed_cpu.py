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


class FastCopies(unittest.TestCase):
    def test_clone_is_a_private_copy_and_falls_back_for_odd_values(self):
        from decimal import Decimal
        from donor_book import _clone

        data = {"records": [{"id": "a", "amount": 1.5, "tags": ["x"], "n": None, "ok": True}]}
        copy = _clone(data)
        self.assertEqual(copy, data)
        copy["records"][0]["tags"].append("y")
        self.assertEqual(data["records"][0]["tags"], ["x"])  # never shared
        self.assertEqual(_clone({"d": Decimal("2")}), {"d": Decimal("2")})  # deepcopy fallback


@unittest.skipUnless(__import__("shutil").which("ffmpeg"), "needs ffmpeg")
class SmallerFiles(unittest.TestCase):
    """A big case video / picture is made smaller once, so every send uploads less."""

    def setUp(self):
        import json, tempfile

        self.dir = tempfile.mkdtemp()

        class Store(dict):
            def __bool__(self):
                return True

            def put(self, k, v):
                self[k] = json.loads(json.dumps(v))

        self.store = Store()

    def make(self, args, mime, name):
        import base64, os, subprocess

        path = os.path.join(self.dir, name)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args, path], check=True)
        import batch_media

        raw = open(path, "rb").read()
        return batch_media.save(self.store, f"data:{mime};base64," + base64.b64encode(raw).decode()), len(raw)

    def test_a_big_picture_becomes_a_small_jpeg_once(self):
        import os, batch_media

        ident, size = self.make(["-f", "lavfi", "-i", "mandelbrot=size=2400x2400", "-frames:v", "1"], "image/png", "p.png")
        self.assertGreater(size, batch_media.SHRINK_IMAGE_OVER)
        self.assertTrue(batch_media.shrink(self.store, ident, self.dir))
        path, mime = batch_media.load(self.store, ident, self.dir)
        self.assertEqual(mime, "image/jpeg")
        self.assertLess(os.path.getsize(path), size * 0.8)
        self.assertFalse(batch_media.shrink(self.store, ident, self.dir))  # never twice

    def test_a_small_file_is_left_alone(self):
        import batch_media

        ident, _ = self.make(["-f", "lavfi", "-i", "color=red:size=64x64", "-frames:v", "1"], "image/png", "s.png")
        self.assertFalse(batch_media.shrink(self.store, ident, self.dir))
        self.assertEqual(batch_media.load(self.store, ident, self.dir)[1], "image/png")
