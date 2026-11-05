"""Unit tests for Checker Agent."""

import unittest
import test_manual_sends as fixture
from test_manual_sends import app
import checker_agent


class CheckerAgentTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self.checker = checker_agent.CheckerAgent(app)

    def tearDown(self):
        fixture.SendTests.tearDown(self)

    def test_checker_detects_empty(self):
        res = self.checker.audit("")
        self.assertFalse(res["passed"])
        self.assertIn("empty", res["problems"][0].lower())

    def test_checker_detects_banned_panic_words(self):
        bad_msg = "Please help if you can danger Rs 5000"
        res = self.checker.audit(bad_msg)
        self.assertFalse(res["passed"])
        self.assertTrue(any("never use" in p for p in res["problems"]))

    def test_checker_detects_prohibited_payment_methods(self):
        msg = "Donate via JazzCash or Bank Alfalah: 12345"
        res = self.checker.audit(msg)
        self.assertFalse(res["passed"])
        self.assertTrue(any("Easypaisa" in p for p in res["problems"]))

    def test_checker_detects_hashtags(self):
        msg = "Support this case #help #donate"
        res = self.checker.audit(msg)
        self.assertFalse(res["passed"])
        self.assertTrue(any("hashtag" in p.lower() for p in res["problems"]))

    def test_checker_detects_invented_facts(self):
        source = "Ali needs heart medicine. Rs. 20,000 left."
        text = "Ali needs brain surgery at Shaukat Khanum hospital."
        res = self.checker.audit(text, source=source)
        self.assertFalse(res["passed"])
        self.assertTrue(any("invented fact" in p.lower() for p in res["problems"]))

    def test_checker_chat_formatting(self):
        reply = self.checker.chat("Please help if you can danger Rs 5000")
        self.assertIn("FAILED", reply)
        self.assertIn("Issues found", reply)


if __name__ == "__main__":
    unittest.main()
