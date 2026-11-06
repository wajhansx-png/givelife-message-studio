"""Offline receipt ranking tests — synthetic names, no real contacts or sends."""
import base64
import copy
import json
import tempfile
import unittest
import zlib

from donor_book import DonorBook
from private_receipt_ranking import import_rankings


class FakeStore:
    def __init__(self):
        self.data = {}
        self.writes = 0

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def put(self, key, value):
        self.writes += 1
        self.data[key] = copy.deepcopy(value)


def fake_report():
    values = [6150, 4000, 3700, 3000, 2407] + [801] * 29 + [775]
    assert sum(values) == 43261
    return [{"name": f"Person {i:02d}", "total": v} for i, v in enumerate(values, 1)]


def payload(rows):
    raw = json.dumps(rows, separators=(",", ":")).encode()
    return base64.b64encode(zlib.compress(raw)).decode()


class ReceiptRankingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = FakeStore()
        self.book = DonorBook(self.temp.name, self.store)
        for i in range(1, 36):
            self.book.add(f"Person {i:02d}", f"92300234{i:04d}")
        self.book.update(self.book.resolve("Person 01")["id"], amount=9000, donated=True)
        self.previous = self.store.get("donor_book")["records"][0].copy()

    def test_ranked_top_and_preserves_donation_status(self):
        result = import_rankings(self.store, self.temp.name, payload(fake_report()))
        self.assertEqual(result["verified"], 35)
        self.assertEqual(result["receipt_total"], 43261)
        self.assertEqual(result["newly_saved"], 35)
        top = DonorBook(self.temp.name, self.store).list("top")
        self.assertEqual(top["counts"]["top"], 35)
        self.assertEqual(top["counts"]["receipt_total"], 43261)
        self.assertEqual(top["items"][0]["name"], "Person 01")
        self.assertEqual(top["items"][0]["receipt_total"], 6150)
        self.assertEqual(top["items"][-1]["receipt_rank"], 35)
        saved = self.store.get("donor_book")["records"][0]
        self.assertEqual(saved["amount"], 9000)
        self.assertTrue(saved["donated"])
        self.assertFalse(saved["important"])
        self.assertEqual(saved["receipt_rank"], 1)

    def test_idempotent_without_rewriting_owner_donor_data(self):
        first = import_rankings(self.store, self.temp.name, payload(fake_report()))
        self.assertEqual(first["newly_saved"], 35)
        before = self.store.writes
        second = import_rankings(self.store, self.temp.name, payload(fake_report()))
        self.assertEqual(second["newly_saved"], 0)
        self.assertEqual(self.store.writes, before)

    def test_unmatched_donor_does_not_partially_update(self):
        rows = fake_report()
        rows[0]["name"] = "Missing Person"
        before = self.store.writes
        with self.assertRaisesRegex(ValueError, "absent or ambiguous"):
            import_rankings(self.store, self.temp.name, payload(rows))
        self.assertEqual(self.store.writes, before)
        self.assertNotIn("receipt_rank", self.store.get("donor_book")["records"][0])

    def test_total_and_order_guard(self):
        rows = fake_report()
        rows[0]["total"] -= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            import_rankings(self.store, self.temp.name, payload(rows))
        rows = fake_report()
        rows[1]["total"] = rows[0]["total"] + 1
        with self.assertRaisesRegex(ValueError, "largest"):
            import_rankings(self.store, self.temp.name, payload(rows))


if __name__ == "__main__":
    unittest.main()
