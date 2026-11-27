"""A timer set earlier must not send once Auto is turned OFF (owner report 2026-11-21)."""

import unittest

import server


class TimedSendNeedsAuto(unittest.TestCase):
    def ready(self, action, hold=False, auto=True, busy=False, wa=True):
        return server.timed_ready(action, hold, auto, busy, lambda: wa)

    def test_send_goes_only_when_auto_is_on(self):
        self.assertTrue(self.ready("send"))
        self.assertFalse(self.ready("send", auto=False))

    def test_send_still_waits_for_hold_busy_and_whatsapp(self):
        self.assertFalse(self.ready("send", hold=True))
        self.assertFalse(self.ready("send", busy=True))
        self.assertFalse(self.ready("send", wa=False))

    def test_switching_auto_on_or_off_is_not_blocked_by_auto_being_off(self):
        self.assertTrue(self.ready("auto_on", auto=False))
        self.assertTrue(self.ready("auto_off", auto=False, hold=True))
        self.assertTrue(self.ready("resume", auto=False, hold=True))
        self.assertFalse(self.ready("auto_on", hold=True))

    def test_setting_a_timed_send_while_auto_is_off_says_so_at_once(self):
        from unittest.mock import MagicMock, patch

        scheduler = MagicMock()
        scheduler.command.return_value = {"handled": True, "reply": "Done. Set for 9 pm."}
        with (
            patch.object(server, "fast_command_eligible", return_value=True),
            patch.object(server.timed_tasks, "parse", return_value=object()),
            patch.object(server, "timed_scheduler", return_value=scheduler),
            patch.object(server, "auto_on", return_value=False),
        ):
            sent = server.timed_chat_command("send the case at 9pm")["reply"]
            other = server.timed_chat_command("auto on at 9pm")["reply"]
        self.assertIn("Auto is OFF", sent)
        self.assertNotIn("Auto is OFF", other)


if __name__ == "__main__":
    unittest.main()
