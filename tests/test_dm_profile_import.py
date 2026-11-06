"""Offline tests for private donor DM name/address preferences. No WhatsApp sends."""
import base64
import copy
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

import dm_composer
from dm_profile_import import import_profiles
from donor_book import DonorBook
from donor_integration import DonorIntegration


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
    raw = json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.b64encode(zlib.compress(raw, 9)).decode()


class DonorProfileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = FakeStore()
        self.book = DonorBook(Path(self.folder.name), self.store)
        self.donors = [
            ("Amna Good Donor", "923001230001"),
            ("Noor 500 Donor", "923001230002"),
            ("Donor 106 Girl", "923001230003"),
        ]
        for label, phone in self.donors:
            self.book.add(name=label, phone=phone)
        self.entries = [
            {"phone": self.donors[0][1], "dm_name": "Amna", "dm_salutation": "Sister"},
            {"phone": self.donors[1][1], "dm_name": "Noor", "dm_salutation": "Neutral"},
            {"phone": self.donors[2][1], "dm_name": "", "dm_salutation": "Sister"},
        ]

    def test_import_saves_private_greetings_without_changes_to_donor_history(self):
        out = import_profiles(self.store, self.folder.name, payload(self.entries))
        self.assertEqual(out["verified"], 3)
        self.assertEqual(out["updated"], 3)
        records = self.store.get("donor_book")["records"]
        self.assertEqual(records[0]["name"], "Amna Good Donor")
        self.assertEqual(records[0]["dm_name"], "Amna")
        self.assertEqual(records[0]["dm_salutation"], "Sister")
        self.assertFalse(records[0]["donated"])
        self.assertEqual(records[1]["dm_salutation"], "Neutral")

    def test_saved_names_are_used_for_sister_and_neutral_greetings(self):
        import_profiles(self.store, self.folder.name, payload(self.entries))
        integration = DonorIntegration.__new__(DonorIntegration)
        integration.app = SimpleNamespace(
            clean_first_name=dm_composer.first_name,
            FEMALE=set(),
        )
        rows = self.store.get("donor_book")["records"]
        self.assertEqual(integration.personal_name(rows[0]), ("Amna", "Sister"))
        self.assertEqual(integration.personal_name(rows[1]), ("Noor", "Neutral"))
        self.assertEqual(integration.personal_name(rows[2]), ("", "Sister"))
        self.assertEqual(dm_composer.greeting("Amna", "Sister"), "Amna Sister")
        self.assertEqual(dm_composer.greeting("Noor", "Neutral"), "Noor")
        self.assertEqual(dm_composer.greeting("", "Sister"), "Sister")
        self.assertIn("Amna Sister,", dm_composer.personalize("Please help.", "Amna", "Sister"))
        self.assertIn("Noor,", dm_composer.personalize("Please help.", "Noor", "Neutral"))

    def test_owner_correction_survives_reimport(self):
        import_profiles(self.store, self.folder.name, payload(self.entries))
        new_book = DonorBook(self.folder.name, self.store)
        target = new_book.resolve(self.donors[0][1])
        new_book.update(target["id"], dm_name="Amina", dm_salutation="Neutral")
        second = import_profiles(self.store, self.folder.name, payload(self.entries))
        self.assertEqual(second["owner_preserved"], 1)
        saved = self.store.get("donor_book")["records"][0]
        self.assertEqual(saved["dm_profile_source"], "owner")
        self.assertEqual(saved["dm_name"], "Amina")
        self.assertEqual(saved["dm_salutation"], "Neutral")

    def test_invalid_or_duplicate_profiles_cannot_write(self):
        saved_writes = self.store.writes
        for records in (
            [self.entries[0], self.entries[0]],
            [{"phone": self.donors[0][1], "dm_name": "Donor 2", "dm_salutation": "Sister"}],
            [{"phone": self.donors[0][1], "dm_name": "Amna", "dm_salutation": "Wrong"}],
            [{"phone": "923001230009", "dm_name": "Amna", "dm_salutation": "Sister"}],
        ):
            with self.subTest(data=records), self.assertRaises(ValueError):
                import_profiles(self.store, self.folder.name, payload(records))
            self.assertEqual(self.store.writes, saved_writes)

    def test_editable_profile_appears_on_public_donor_screen_without_phone(self):
        import_profiles(self.store, self.folder.name, payload(self.entries))
        page = DonorBook(self.folder.name, self.store).list()
        entry = page["items"][0]
        self.assertTrue(entry["number_hidden"])
        self.assertNotIn("phone", entry)
        self.assertEqual(entry["dm_name"], "Amna")
        self.assertEqual(entry["dm_salutation"], "Sister")


if __name__ == "__main__":
    unittest.main()
