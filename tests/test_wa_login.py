import io
import unittest
import urllib.error

import wa_lines
import wa_login

GATEWAY = "http://127.0.0.1:3000"
DEVICE = "main-device-id"


def http_error(body, code=500):
    return urllib.error.HTTPError(
        GATEWAY, code, "Internal Server Error", {}, io.BytesIO(body.encode())
    )


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class RequestCodeTests(unittest.TestCase):
    def setUp(self):
        wa_login._last[0] = 0.0
        self.clock = Clock()
        self.calls = []

    def post(self, url, device):
        self.calls.append((url, device))
        return {"code": "SUCCESS", "results": {"pair_code": "abcd1234"}}

    def ask(self, phone="0300 1234567", post=None):
        return wa_login.request_code(GATEWAY, DEVICE, phone, post=post or self.post, now=self.clock)

    def test_returns_the_code_for_the_normalised_number(self):
        self.assertEqual(self.ask(), {"code": "ABCD-1234"})
        url, device = self.calls[0]
        self.assertEqual(device, DEVICE)
        self.assertTrue(url.startswith(f"{GATEWAY}/devices/{DEVICE}/login/code?phone="))
        self.assertTrue(url.endswith("phone=923001234567"))

    def test_a_bad_number_never_reaches_whatsapp(self):
        with self.assertRaises(wa_lines.LineError):
            self.ask("hello")
        self.assertEqual(self.calls, [])

    def test_codes_are_rate_limited_then_allowed_again(self):
        self.ask()
        self.clock.t += 5
        with self.assertRaises(wa_lines.LineError) as caught:
            self.ask()
        self.assertIn("seconds", str(caught.exception))
        self.assertEqual(len(self.calls), 1)
        self.clock.t += wa_login.COOLDOWN
        self.assertEqual(self.ask(), {"code": "ABCD-1234"})
        self.assertEqual(len(self.calls), 2)

    def test_a_missing_code_is_a_readable_error(self):
        with self.assertRaises(wa_lines.LineError) as caught:
            self.ask(post=lambda url, device: {"code": "SUCCESS", "results": {}})
        self.assertIn("did not give a code", str(caught.exception))

    def test_gateway_failures_are_plain_words_without_internals(self):
        failures = [
            http_error(
                "GetQRChannel can only be called when there's no user ID in the client's Store"
            ),
            http_error(
                "your session have been saved, please wait to connect 2 second and refresh again"
            ),
            urllib.error.URLError("connection refused 127.0.0.1:3000"),
            http_error("boom"),
        ]
        for failure in failures:
            wa_login._last[0] = 0.0

            def broken(url, device, failure=failure):
                raise failure

            with self.assertRaises(wa_lines.LineError) as caught:
                self.ask(post=broken)
            text = str(caught.exception)
            self.assertNotIn("127.0.0.1", text)
            self.assertNotIn("Store", text)
            self.assertNotIn("GetQRChannel", text)


class ProblemTests(unittest.TestCase):
    def test_already_linked_is_explained(self):
        words = wa_login.problem(
            http_error("GetQRChannel can only be called when there's no user ID")
        )
        self.assertIn("already linked", words)
        self.assertIn("Check again", words)

    def test_unreachable_service(self):
        self.assertIn("reach", wa_login.problem(urllib.error.URLError("refused")))

    def test_anything_else_is_generic(self):
        self.assertIn("try again", wa_login.problem(RuntimeError("secret internals")).lower())
        self.assertNotIn("secret", wa_login.problem(RuntimeError("secret internals")))


if __name__ == "__main__":
    unittest.main()
