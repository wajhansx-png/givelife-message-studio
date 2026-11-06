"""Offline contact importer tests: fake database, no real contacts or WhatsApp."""
import base64
import copy
import json
import tempfile
import unittest
import zlib

from private_donor_import import _decode, import_from_environment


class FakeStore:
    def __init__(self):
        self.data = {}
        self.writes = 0

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def put(self, key, value):
        self.writes += 1
        self.data[key] = copy.deepcopy(value)


def payload(rows):
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.b64encode(zlib.compress(encoded, 9)).decode()


def records():
    return [
        {"name": "Person One Donor", "phone": "923001234561", "label": "Donor"},
        {"name": "Person Two Giki", "phone": "923001234562", "label": "GIKI"},
        {"name": "Person Three Donir", "phone": "923001234563", "label": "Donir"},
    ]


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = FakeStore()

    def test_all_labels_are_imported_as_unverified_contacts(self):
        receipt = import_from_environment(self.store, self.folder.name, payload(records()))
        self.assertEqual(receipt["input"], 3)
        self.assertEqual(receipt["added"], 3)
        self.assertEqual(receipt["already_existing"], 0)
        saved = self.store.get("donor_book")["records"]
        self.assertEqual(len(saved), 3)
        self.assertEqual({r["source"].split(": ")[-1] for r in saved}, {"Donor", "GIKI", "Donir"})
        self.assertTrue(all(not r["donated"] and not r["important"] for r in saved))

    def test_reimport_does_not_duplicate_or_reset_flags(self):
        first = import_from_environment(self.store, self.folder.name, payload(records()))
        self.assertEqual(first["added"], 3)
        current = self.store.get("donor_book")
        current["records"][0].update(donated=True, amount=1500, important=True, notes="Existing note")
        self.store.put("donor_book", current)
        second = import_from_environment(self.store, self.folder.name, payload(records()))
        self.assertEqual(second["added"], 0)
        self.assertEqual(second["already_existing"], 3)
        saved = self.store.get("donor_book")["records"]
        self.assertEqual(len(saved), 3)
        self.assertEqual(saved[0]["amount"], 1500)
        self.assertEqual(saved[0]["notes"], "Existing note")

    def test_invalid_entries_fail_before_any_write(self):
        for bad in (
            records() + [records()[0]],
            [{"name": "Bad", "phone": "123", "label": "Donor"}],
            [{"name": "Bad", "phone": "923001234565", "label": "Unknown"}],
        ):
            with self.subTest(data=bad), self.assertRaises(ValueError):
                import_from_environment(self.store, self.folder.name, payload(bad))
            self.assertEqual(self.store.writes, 0)

    def test_bad_or_oversized_payload_is_rejected(self):
        for bad in ("abc", "", "!" * 200000):
            with self.subTest(value=bad[:12]), self.assertRaises(Exception):
                _decode(bad)
        self.assertEqual(self.store.writes, 0)


if __name__ == "__main__":
    unittest.main()
