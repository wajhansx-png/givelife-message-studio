import unittest, time
from unittest.mock import patch
import autopilot
import test_restart_and_scheduling as fixture


class LiveStatusTests(unittest.TestCase):
    setUp = fixture.SchedulerTests.setUp

    def test_idle_is_not_presented_as_current_reading(self):
        st = self.eng.status()
        self.assertEqual(st["state"], "idle")
        self.assertEqual(st["now"], "Waiting for next reply check")
        self.assertIsNone(st["last_reply_read"])
        self.assertTrue(all("due_at" in n for n in st["next"]))

    def test_active_scan_is_observed_and_cleared_after_failure(self):
        self.eng.s.update(
            last_scan=0, last_dm_scan=time.time(), last_chat_scan=time.time(), left_seen=None
        )
        captured = []

        def scan():
            captured.append(self.eng.status())
            raise RuntimeError("fake scan failure")

        with (
            patch.object(self.eng, "scan_group_replies", scan),
            patch.object(self.eng, "level", return_value=("L1", 30, 30, 0)),
        ):
            with self.assertRaises(RuntimeError):
                self.eng.tick()
        self.assertEqual(captured[0]["state"], "reading")
        self.assertIsNone(self.eng.activity)

    def test_only_successful_response_updates_reply_read_time(self):
        self.eng.h["group_jids"] = lambda: {"main": "fake-main"}
        self.eng.h["messages"] = lambda jid: []
        with patch.object(autopilot, "now", return_value=12000):
            self.eng.scan_group_replies()
        self.assertEqual(self.eng.s["last_reply_read"], 12000)
        self.assertEqual(self.eng.worker_errors, {})

    def test_failed_or_malformed_scan_does_not_claim_success(self):
        self.eng.h["group_jids"] = lambda: {"main": "fake-main"}
        self.eng.h["messages"] = lambda jid: "invalid"
        self.eng.scan_group_replies()
        self.assertIsNone(self.eng.s.get("last_reply_read"))
        self.assertEqual(self.eng.status()["state"], "error")

    def test_hold_takes_priority_over_active_scan(self):
        self.eng.activity = {"label": "Reading group replies"}
        self.eng.h["on_hold"] = lambda: True
        self.assertEqual(self.eng.status()["state"], "paused")

    def test_read_error_clears_only_after_a_successful_scan(self):
        self.eng.h["group_jids"] = lambda: {"main": "fake-main"}
        self.eng.h["messages"] = lambda jid: None
        self.eng.scan_group_replies()
        self.assertIn("replies", self.eng.worker_errors)
        self.eng.h["messages"] = lambda jid: []
        self.eng.scan_group_replies()
        self.assertNotIn("replies", self.eng.worker_errors)


if __name__ == "__main__":
    unittest.main()
