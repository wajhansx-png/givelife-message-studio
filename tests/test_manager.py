"""Unit tests for Central AI Manager and direct agent delegation."""

import unittest
from unittest.mock import patch, MagicMock
import test_manual_sends as fixture
from test_manual_sends import app
import manager


class ManagerAgentTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self.mgr = manager.ManagerAgent(app)

    def tearDown(self):
        fixture.SendTests.tearDown(self)

    def test_manager_system_health_inspection(self):
        health = self.mgr.get_system_health()
        self.assertIn("status", health)
        self.assertIn("agents", health)
        agents = health["agents"]
        for expected in ("auto", "writer", "checker", "replies", "dms", "volunteers", "plan"):
            self.assertIn(expected, agents)

    def test_ask_all_agents_for_progress(self):
        reply = self.mgr.chat("Ask all agents for their progress")
        self.assertIn("System Status & Agent Progress Briefing", reply)
        self.assertIn("Group Poster", reply)
        self.assertIn("Writer", reply)
        self.assertIn("Checker", reply)
        self.assertIn("Volunteer Guide", reply)
        self.assertIn("Case Plan", reply)

    def test_delegation_to_writer(self):
        reply = self.mgr.chat("Ask Writer to draft a new group message")
        self.assertIn("[AI Manager → Writer]", reply)
        self.assertIn("Writer's Response:", reply)
        self.assertIn("Easypaisa", reply)

    def test_delegation_to_checker(self):
        reply = self.mgr.chat("Ask Checker to review this message: Please help if you can danger Rs 5000")
        self.assertIn("[AI Manager → Checker]", reply)
        self.assertIn("FAILED", reply)

    def test_delegation_to_volunteer_guide(self):
        reply = self.mgr.chat("Tell Volunteer Guide to check pending volunteers")
        self.assertIn("[AI Manager → Volunteer Guide]", reply)
        self.assertIn("Volunteer Guide Status", reply)

    def test_recovery_protocol_execution(self):
        reply = self.mgr.chat("recover and retry failed tasks")
        self.assertIn("Recovery Protocol Executed", reply)

    def test_case_plan_mode_switch(self):
        reply = self.mgr.chat("switch to slow mode")
        self.assertIn("[AI Manager → Case Plan]", reply)
        self.assertIn("SLOW", reply)


if __name__ == "__main__":
    unittest.main()
