import tempfile
import unittest
from pathlib import Path

import donor_book


class ImportantStarOrderTests(unittest.TestCase):
    def test_all_audience_sends_important_in_star_order_then_the_rest(self):
        with tempfile.TemporaryDirectory() as folder:
            book = donor_book.DonorBook(Path(folder))
            ids = {
                name: book.add(name, phone)["donor"]["id"]
                for name, phone in (
                    ("Ahmed", "03001110001"),
                    ("Bilal", "03001110002"),
                    ("Zain", "03001110003"),
                    ("Umar", "03001110004"),
                )
            }
            for name in ("Zain", "Ahmed", "Bilal"):
                book.update(ids[name], important=True)
            names = [r["name"] for r in book.recipients("all")]
            self.assertEqual(names, ["Zain", "Ahmed", "Bilal", "Umar"])
            self.assertEqual(
                [r["name"] for r in book.recipients("important")], ["Zain", "Ahmed", "Bilal"]
            )

    def test_deselect_all_clears_every_star_and_restarts_the_order(self):
        with tempfile.TemporaryDirectory() as folder:
            book = donor_book.DonorBook(Path(folder))
            a = book.add("Ahmed", "03001110001")["donor"]["id"]
            b = book.add("Bilal", "03001110002")["donor"]["id"]
            book.update(a, important=True)
            book.update(b, important=True)
            self.assertEqual(book.clear_important()["cleared"], 2)
            self.assertEqual(book.recipients("important"), [])
            book.update(b, important=True)
            self.assertEqual(book.recipients("important")[0]["important_order"], 1)


if __name__ == "__main__":
    unittest.main()
