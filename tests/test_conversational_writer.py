"""Unit tests for Advanced Conversational Writer."""

import unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
import writer_agent


class ConversationalWriterTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self.writer = writer_agent.ConversationalWriter(app)

    def tearDown(self):
        fixture.SendTests.tearDown(self)

    def test_writer_conversation_intro(self):
        reply = self.writer.chat("")
        self.assertIn("GiveLife Writer", reply)

    def test_writer_generates_group_appeal_with_verified_checker(self):
        reply = self.writer.chat("Write a group appeal")
        self.assertIn("Verified with Checker", reply)
        self.assertIn("Easypaisa", reply)
        self.assertIn("03097458815", reply)
        self.assertIn("Wajdan Khan", reply)

    def test_writer_generates_dm_draft(self):
        reply = self.writer.chat("Write a DM for an existing donor")
        self.assertIn("Assalam-o-Alaikum", reply)
        self.assertIn("Easypaisa", reply)

    def test_writer_generates_volunteer_ask(self):
        reply = self.writer.chat("Write a volunteer request asking them to share the poster")
        self.assertIn("poster", reply.lower())
        self.assertIn("Shall I send the poster?", reply)

    def test_writer_preserves_verified_amount(self):
        with patch.object(app, "read_left", return_value=32000):
            writer = writer_agent.ConversationalWriter(app)
            reply = writer.chat("Draft an urgent update")
            self.assertIn("32,000", reply)


if __name__ == "__main__":
    unittest.main()
