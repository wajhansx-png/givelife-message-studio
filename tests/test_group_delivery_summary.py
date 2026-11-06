"""No network/WhatsApp calls. Verify group receipt interpretation."""

import unittest
from group_delivery import summarize


class GroupDeliverySummaryTests(unittest.TestCase):
    def test_success_requires_every_gateway_confirmation(self):
        self.assertEqual(
            summarize([{"group": "GiveLife", "code": "SUCCESS"}], ["main"]),
            "Confirmed sent to 1/1 groups.",
        )

    def test_failure_reports_actual_error_not_fake_success(self):
        result = summarize(
            [{"group": "GiveLife", "code": "ERROR", "message": "WhatsApp prekey timeout"}], ["main"]
        )
        self.assertIn("Not confirmed: 0/1", result)
        self.assertIn("GiveLife: WhatsApp prekey timeout", result)
        self.assertIn("Do not resend", result)
        self.assertNotIn("Confirmed sent to 0/1", result)

    def test_missing_receipts_not_success(self):
        result = summarize([], ["main"])
        self.assertIn("0/1", result)
        self.assertIn("no send attempt or receipt", result)

    def test_partial_success_shows_failure(self):
        result = summarize(
            [
                {"group": "A", "code": "SUCCESS"},
                {"group": "B", "code": "COOLDOWN", "message": "Recently posted"},
            ],
            ["a", "b"],
        )
        self.assertIn("Only 1/2", result)
        self.assertIn("B: Recently posted", result)


if __name__ == "__main__":
    unittest.main()
