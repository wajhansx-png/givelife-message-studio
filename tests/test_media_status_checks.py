"""One fresh connection check per logical send, never shared between devices or requests."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_manual_sends as fixture
from test_manual_sends import app


CONNECTED = {"is_connected": True, "is_logged_in": True}


class MediaStatusChecks(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def body(self, phone="923001230090"):
        return dict(target="phone", phone=phone, message="Approved case message", poster=True,
                    kind="volunteer_batch")

    def test_poster_send_checks_connection_once(self):
        with patch.object(app, "api_result", return_value=CONNECTED) as status:
            self.assertEqual(app.send_custom(self.body())["code"], "SUCCESS")
        self.assertEqual(status.call_count, 1)
        self.assertEqual(len(self.sent), 1)

    def test_the_next_request_rechecks_and_refuses_a_disconnected_device(self):
        with patch.object(app, "api_result", return_value=CONNECTED) as status:
            self.assertEqual(app.send_custom(self.body())["code"], "SUCCESS")
            status.reset_mock()
            status.return_value = {}
            with self.assertRaisesRegex(ValueError, "disconnected"):
                app.send_custom(self.body("923001230091"))
            status.assert_called_once()
        self.assertEqual(len(self.sent), 1)

    def test_standalone_group_sends_still_check_each_time(self):
        with patch.object(app, "api_result", return_value=CONNECTED) as status:
            self.assertEqual(app.send_image(app.GROUPS["main"][1], "Approved case")["code"], "SUCCESS")
            status.return_value = {}
            self.assertEqual(app.send_image(app.GROUPS["main"][1], "Approved case")["code"], "ERROR")
        self.assertEqual(status.call_count, 2)
        self.assertEqual(len(self.sent), 1)

    def test_a_different_device_cannot_reuse_a_connection_check(self):
        first, second = SimpleNamespace(device=lambda: "first"), SimpleNamespace(device=lambda: "second")
        with patch.dict(app.LINES, {"giki": first, "giki2": second}), \
             patch.object(app, "api_result", return_value=CONNECTED) as status:
            token = app._CHECKED_MEDIA_DEVICE.set((app.GOWA_URL, "first"))
            try:
                with app.on_line("giki2"):
                    self.assertEqual(app.send_image("923001230092", "Approved case")["code"], "SUCCESS")
            finally:
                app._CHECKED_MEDIA_DEVICE.reset(token)
        self.assertEqual([c.args[0] for c in status.call_args_list],
                         ["/devices/second/status"])


if __name__ == "__main__":
    unittest.main()
