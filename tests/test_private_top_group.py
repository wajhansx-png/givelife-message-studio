"""Private Top-donor group import: numbers added, no duplicates, own numbering, safe to re-run."""

import base64
import json
import tempfile
import unittest

from donor_book import DonorBook
from private_top_names import import_top_group, import_top_names


def payload(*pairs):
    return base64.b64encode(
        json.dumps([{"name": n, "phone": p} for n, p in pairs]).encode()
    ).decode()


class TopGroup(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.book = DonorBook(self.dir)

    def fresh(self):
        return DonorBook(
            self.dir
        )  # the import runs before the server starts, so reads see a new book

    def test_name_only_rows_get_numbers_without_duplicates_and_own_order(self):
        import_top_names(None, self.dir, json.dumps(["Alpha Test", "Beta Test"]), import_id="n1")
        self.book.add(name="Zed Main", phone="923001110000")
        receipt = import_top_group(
            None,
            self.dir,
            payload(
                ("Beta Test", "+92 300 2220002"),
                ("Alpha Test", "+92 300 2220001"),
                ("New Test", "+92 300 2220003"),
            ),
        )
        self.assertEqual((receipt["added"], receipt["matched"]), (1, 2))
        rows = self.fresh().list("top")["items"]
        group = [r for r in rows if r.get("group") == "GIKI"]
        self.assertEqual([r["name"] for r in group], ["Beta Test", "Alpha Test", "New Test"])
        self.assertEqual([r["top_rank"] for r in group], [1, 2, 3])
        self.assertTrue(all(r["has_number"] for r in group))
        self.assertEqual(len(self.fresh().list("all")["items"]), 4)
        self.assertNotIn("phone", json.dumps(rows))

    def test_group_sorts_after_other_top_donors(self):
        self.book.add(name="Zed Main", phone="923001110000")
        zed = self.book.list("all")["items"][0]["id"]
        self.book.update(zed, important=True)
        self.book.update(zed, top_donor=True)
        import_top_group(None, self.dir, payload(("Giki One", "+92 300 2220001")))
        names = [r["name"] for r in self.fresh().list("top")["items"]]
        self.assertEqual(names, ["Zed Main", "Giki One"])

    def test_number_already_known_is_reused_and_rerun_does_nothing(self):
        self.book.add(name="Known Giki", phone="923002220001")
        data = payload(("Known Giki Renamed", "+92 300 2220001"))
        self.assertEqual(import_top_group(None, self.dir, data)["added"], 0)
        self.assertEqual(import_top_group(None, self.dir, data)["already_applied"], 1)
        self.assertEqual(len(self.fresh().list("all")["items"]), 1)

    def test_bad_payload_changes_nothing(self):
        with self.assertRaises(ValueError):
            import_top_group(None, self.dir, payload(("A", "12"), ("B", "+92 300 2220002")))
        self.assertEqual(self.book.list("all")["items"], [])


if __name__ == "__main__":
    unittest.main()
