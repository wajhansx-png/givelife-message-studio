"""Donor Top priority is an owner choice, not conditional on a receipt."""
import copy
import tempfile
import unittest
from pathlib import Path

from donor_book import DonorBook


class Store:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return copy.deepcopy(self.values.get(key, default))

    def put(self, key, value):
        self.values[key] = copy.deepcopy(value)


class PriorityWithoutReceiptTests(unittest.TestCase):
    def test_can_prioritize_without_receipt_or_known_amount(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store()
            book = DonorBook(folder, store)
            book.add(name="Person One", phone="923001234567")
            who = book.resolve("Person One")
            self.assertNotIn("receipt_total", who)
            book.update(who["id"], important=True)
            book.update(who["id"], top_donor=True)
            ranked = DonorBook(folder, store).list("top")
            self.assertEqual(ranked["counts"]["top"], 1)
            self.assertEqual(ranked["items"][0]["name"], "Person One")
            self.assertFalse(ranked["items"][0]["donated"])
            self.assertEqual(ranked["items"][0]["amount"], 0)

    def test_frontend_no_receipt_gate_for_priority(self):
        js = (Path(__file__).resolve().parents[1] / "donors.js").read_text()
        self.assertIn("change(d.id, { top_donor: true })", js)
        self.assertIn("Top is an owner-controlled priority, not a receipt requirement.", js)
        self.assertNotIn("Receipt evidence · Rs.", js)
        self.assertNotIn("Past recorded support · Rs.", js)  # owner: no receipt labels


if __name__ == "__main__":
    unittest.main()
