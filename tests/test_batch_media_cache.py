"""Immutable attachment materialization: fake storage, no network or WhatsApp."""

import base64
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
import unittest
import weakref
import gc
from unittest.mock import patch

import batch_media


IDENT = "a" * 32
PDF = b"%PDF-1.7\nprivate medical document"


class Store:
    def __init__(self, data=PDF, delay=0):
        self.rows = {IDENT: {"mime": "application/pdf", "data": base64.b64encode(data).decode()}}
        self.calls = 0
        self.delay = delay
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.rows.get(key.removeprefix("batch_media_"))


class MaterializationCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_repeated_attachment_uses_exact_existing_file_without_loading_or_decoding_again(self):
        store = Store()
        with patch("batch_media.base64.b64decode", wraps=base64.b64decode) as decode:
            first, mime = batch_media.load(store, IDENT, self.folder)
            stamp = first.stat()
            for _ in range(6):
                again, kind = batch_media.load(store, IDENT, self.folder)
                self.assertEqual((again, kind), (first, mime))
                self.assertEqual(again.read_bytes(), PDF)
            self.assertEqual(store.calls, 1)
            self.assertEqual(decode.call_count, 1)
            self.assertEqual(first.stat().st_mtime_ns, stamp.st_mtime_ns)

    def test_different_store_identity_never_replaces_another_stores_published_file(self):
        left, right = Store(), Store(b"%PDF-1.7\nother private document")
        first, _ = batch_media.load(left, IDENT, self.folder)
        second, _ = batch_media.load(right, IDENT, self.folder)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), PDF)
        self.assertEqual(second.read_bytes(), b"%PDF-1.7\nother private document")

    def test_different_identifiers_and_folders_are_isolated(self):
        store = Store()
        other_id = "b" * 32
        store.rows[other_id] = {
            "mime": "application/pdf",
            "data": base64.b64encode(b"%PDF-two").decode(),
        }
        other_folder = self.folder / "another-case"
        other_folder.mkdir()
        first, _ = batch_media.load(store, IDENT, self.folder)
        second, _ = batch_media.load(store, other_id, self.folder)
        third, _ = batch_media.load(store, IDENT, other_folder)
        self.assertEqual(len({first, second, third}), 3)
        self.assertEqual(second.read_bytes(), b"%PDF-two")
        self.assertEqual(third.read_bytes(), PDF)

    def test_missing_or_changed_local_file_is_restored_from_private_storage(self):
        store = Store()
        first, _ = batch_media.load(store, IDENT, self.folder)
        first.unlink()
        self.assertEqual(batch_media.load(store, IDENT, self.folder)[0].read_bytes(), PDF)
        first.write_bytes(b"x" * len(PDF))
        self.assertEqual(batch_media.load(store, IDENT, self.folder)[0].read_bytes(), PDF)
        self.assertEqual(store.calls, 3)

    def test_concurrent_cold_readers_materialize_once(self):
        store = Store(delay=0.02)
        start = threading.Barrier(8)

        def read():
            start.wait()
            path, mime = batch_media.load(store, IDENT, self.folder)
            return path, mime, path.read_bytes()

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: read(), range(8)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(store.calls, 1)
        self.assertEqual(results[0][2], PDF)

    def test_failed_publish_keeps_old_file_intact_and_removes_temporary_file(self):
        store = Store()
        path, _ = batch_media.load(store, IDENT, self.folder)
        path.write_bytes(b"tampered")
        with patch("batch_media.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                batch_media.load(store, IDENT, self.folder)
        self.assertEqual(path.read_bytes(), b"tampered")
        self.assertEqual(list(self.folder.glob("*.tmp")), [])
        self.assertEqual(batch_media.load(store, IDENT, self.folder)[0].read_bytes(), PDF)

    def test_invalid_identifier_and_missing_private_record_remain_rejected(self):
        store = Store()
        for invalid in ("../secret", "", None, "a" * 31):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                batch_media.load(store, invalid, self.folder)
        with self.assertRaises(ValueError):
            batch_media.load(store, "f" * 32, self.folder)
        batch_media.load(store, IDENT, self.folder)
        with self.assertRaises(ValueError):
            batch_media.load(None, IDENT, self.folder)

    def test_cache_has_bounded_small_metadata_and_does_not_keep_store_alive(self):
        store = Store()
        with (
            patch.object(batch_media, "_CACHE", OrderedDict()),
            patch.object(batch_media, "_CACHE_LIMIT", 2),
        ):
            for digit in "abc":
                ident = digit * 32
                store.rows[ident] = store.rows[IDENT]
                batch_media.load(store, ident, self.folder)
            self.assertEqual(len(batch_media._CACHE), 2)
            self.assertLess(len(repr(batch_media._CACHE)), 2000)
            batch_media.load(store, "c" * 32, self.folder)
            self.assertEqual(store.calls, 3)
            batch_media.load(store, IDENT, self.folder)  # evicted: safely reload its private source
            self.assertEqual(store.calls, 4)
            self.assertEqual(len(batch_media._CACHE), 2)
            ref = weakref.ref(store)
            del store
            gc.collect()
            self.assertIsNone(ref())

    def test_cold_file_is_not_visible_until_complete_atomic_publish(self):
        store = Store(data=PDF * 1000)
        publishing, release = threading.Event(), threading.Event()
        replace = batch_media.os.replace

        def publish(source, target):
            publishing.set()
            if not release.wait(2):
                raise TimeoutError("test did not release publish")
            replace(source, target)

        with (
            patch("batch_media.os.replace", side_effect=publish),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            future = pool.submit(batch_media.load, store, IDENT, self.folder)
            try:
                self.assertTrue(publishing.wait(2))
                self.assertEqual(list(self.folder.glob("bulk-*.pdf")), [])
            finally:
                release.set()
            path, _ = future.result(timeout=2)
        self.assertEqual(path.read_bytes(), PDF * 1000)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_private_source_cannot_return_a_changed_cached_file(self):
        store = Store()
        path, _ = batch_media.load(store, IDENT, self.folder)
        path.write_bytes(b"tampered")
        store.rows[IDENT]["data"] = "invalid base64!"
        with self.assertRaises(ValueError):
            batch_media.load(store, IDENT, self.folder)
        self.assertEqual(store.calls, 2)
        self.assertEqual(list(self.folder.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
