"""A Giki WhatsApp whose login the phone removed is not asked to reconnect every minute for ever.
Fake gateway only; nothing is sent."""

import unittest
from unittest.mock import patch

import wa_lines
from test_giki_line import FakeGateway, Store

DELETED = "device giki-x is not logged in (session deleted)"


class Gateway(FakeGateway):
    """The reconnect answers like the real gateway does for a removed login (or an unreachable one)."""

    def __init__(self, answer):
        super().__init__()
        self.answer = answer

    def __call__(self, method, path, device="", body=None, timeout=15, raw=False):
        if path.endswith("/reconnect"):
            self.calls.append((method, path, device))
            raise wa_lines.LineError(wa_lines._friendly(self.answer))
        return super().__call__(method, path, device, body, timeout, raw)


class WakeBackoff(unittest.TestCase):
    def make(self, answer=DELETED):
        self.gw = Gateway(answer)
        self.line = wa_lines.Line("giki", Store(), "http://gateway", call=self.gw)
        self.device = self.line.ensure()
        self.line.store.put(self.line.key, {**self.line._record(), "number": "923009998888"})

    def poll(self, start, seconds, every=30):
        for t in range(start, start + seconds, every):  # the Giki page asks every 30 s
            with patch("wa_lines.time.time", return_value=float(t)):
                self.line.status()

    def wakes(self):
        return sum(1 for c in self.gw.calls if c[1].endswith("/reconnect"))

    def test_a_removed_login_is_asked_less_and_less_often(self):
        self.make()
        self.poll(1000, 3 * 3600)
        self.assertLessEqual(self.wakes(), 10)  # was 180 in three hours (once a minute)
        self.assertGreaterEqual(
            self.wakes(), 5
        )  # still tried now and then: never given up for good
        self.assertEqual(self.line._wake_gap, 3600.0)

    def test_a_good_status_brings_back_the_quick_wake(self):
        self.make()
        self.poll(1000, 1800)
        self.assertGreater(self.line._wake_gap, 60)
        self.gw.logged.add(self.device)  # linked again with a QR or code
        with patch("wa_lines.time.time", return_value=5000.0):
            self.assertEqual(self.line.status()["state"], "ready")
        self.assertEqual(self.line._wake_gap, 60.0)

    def test_an_unreachable_gateway_keeps_the_one_minute_wake(self):
        self.make("dial tcp 127.0.0.1:3000: connection refused")
        self.poll(1000, 600)
        self.assertEqual(
            self.line._wake_gap, 60.0
        )  # a restart must not delay waking a sleeping login
        self.assertEqual(self.wakes(), 10)


if __name__ == "__main__":
    unittest.main()
