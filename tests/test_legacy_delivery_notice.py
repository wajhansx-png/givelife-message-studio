import tempfile, unittest
from donor_book import DonorBook
from donor_delivery import DonorDelivery


class LegacyReceiptTests(unittest.TestCase):
    def test_old_generic_exclusion_gets_verified_reason_without_send(self):
        with tempfile.TemporaryDirectory() as folder:
            book = DonorBook(folder)
            row = book.add("Jr Accounts", "03001234567")["donor"]
            job = DonorDelivery(
                folder,
                None,
                book,
                lambda *a: self.fail("must not send"),
                lambda: "",
                lambda: True,
                lambda: False,
                lambda p: False,
                lambda n: ("", "Brother"),
            )
            job.exclusion_reason = lambda p: (
                "This is the connected account, which is excluded from donor batches."
            )
            job._save(
                {
                    "jobs": [
                        {
                            "id": "old",
                            "state": "Completed",
                            "sent": 0,
                            "skipped": 1,
                            "ids": [row["id"]],
                            "receipts": [
                                {
                                    "id": row["id"],
                                    "name": "Jr Accounts",
                                    "state": "Skipped: opted out or blocked",
                                }
                            ],
                        }
                    ]
                }
            )
            result = job.status()
            self.assertIn("connected account", result["receipts"][0]["state"])
            self.assertEqual(result["state"], "Nothing sent")
            self.assertEqual(
                job._load()["jobs"][0]["receipts"][0]["state"], "Skipped: opted out or blocked"
            )
