"""The Message screen's versions row: a version that already went to the GiveLife group is marked as sent, even when
it went with a newer amount; other versions are not."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_manual_sends as fixture
from test_manual_sends import app


class SentVersionsTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)

    def test_sent_wording_is_marked_even_with_a_new_amount(self):
        jid = app.GROUPS["main"][1]
        app.record_delivery(jid, "Mirha needs oxygen now. Rs. 13,000 left.", {"code": "SUCCESS", "results": {}})
        row = {"source": "Mirha needs oxygen now. Rs. 11,000 left.", "items": ["A different wording for Mirha.", "Mirha needs oxygen now. Rs. 9,000 left."]}
        self.assertEqual(app.sent_versions(row, jid), {"source": True, "items": [False, True]})

    def test_failed_send_and_other_groups_do_not_count(self):
        jid = app.GROUPS["main"][1]
        app.record_delivery(jid, "Words that failed", {"code": "ERROR"})
        app.record_delivery(app.GROUPS["fiverr"][1], "Words for another group", {"code": "SUCCESS", "results": {}})
        row = {"source": "Words that failed", "items": ["Words for another group"]}
        self.assertEqual(app.sent_versions(row, jid), {"source": False, "items": [False]})


if __name__ == "__main__":
    unittest.main()
