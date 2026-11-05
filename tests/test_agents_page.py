"""Agents page API: real state only, validated rules, corrections saved. No real WhatsApp calls."""

import unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app


class AgentsPageTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self._rules = list(app.ENGINE.rules())
        self._feedback = list(app.KNOWLEDGE.data["feedback"])

    def tearDown(self):
        app.ENGINE.s["rules"] = self._rules
        app.ENGINE.save()
        app.KNOWLEDGE.data["feedback"][:] = self._feedback
        fixture.SendTests.tearDown(self)

    def test_view_lists_real_agents_and_routes_log_lines(self):
        app.auto_log("Answered …1234: hello")
        app.auto_log("main: posting to 1 group(s): main.")
        view = app.agents_view()
        ids = [a["id"] for a in view["agents"]]
        self.assertEqual(
            ids, ["manager", "auto", "writer", "checker", "replies", "dms", "volunteers", "plan"]
        )
        self.assertEqual(ids[0], "manager")  # Manager is always first
        by = {a["id"]: a for a in view["agents"]}
        self.assertTrue(any("Answered" in f["text"] for f in by["replies"]["feed"]))
        self.assertTrue(any("posting" in f["text"] for f in by["auto"]["feed"]))
        for a in view["agents"]:
            self.assertIn(a["status"], ("Active", "Working", "Idle", "Error"))

    def test_offline_whatsapp_shows_error_with_recovery(self):
        with (
            patch.object(app.ENGINE, "status", return_value={"state": "offline", "now": "x"}),
            patch.object(app, "auto_on", return_value=True),
        ):
            auto = next(a for a in app.agents_view()["agents"] if a["id"] == "auto")
        self.assertEqual(auto["status"], "Error")
        self.assertEqual(auto["errors"][0]["action"], "open_home")

    def test_mode_toggle_switches_auto_both_ways_and_view_reports_it(self):
        with patch.object(app, "set_auto", side_effect=lambda on: "on" if on else "off") as sa:
            self.assertEqual(app.agents_mutate({"action": "auto_on"})["reply"], "on")
            self.assertEqual(app.agents_mutate({"action": "auto_off"})["reply"], "off")
            self.assertEqual([c.args[0] for c in sa.call_args_list], [True, False])
        for on in (True, False):
            with patch.object(app, "auto_on", return_value=on):
                self.assertIs(app.agents_view()["auto"], on)

    def test_dm_sender_is_not_active_while_auto_is_off(self):
        with patch.object(app.ENGINE, "summary", return_value={"dm_enabled": True}):
            for on, status in ((False, "Idle"), (True, "Active")):
                with patch.object(app, "auto_on", return_value=on):
                    dms = {a["id"]: a for a in app.agents_view()["agents"]}["dms"]
                self.assertEqual(dms["status"], status)
            with patch.object(app, "auto_on", return_value=False):
                self.assertIn(
                    "waiting for Auto",
                    {a["id"]: a for a in app.agents_view()["agents"]}["dms"]["now"],
                )

    def test_instruction_saved_only_when_valid(self):
        with self.assertRaises(ValueError):
            app.agents_mutate({"action": "instruct", "text": "hello there"})
        with self.assertRaises(ValueError):
            app.agents_mutate({"action": "instruct", "text": "send poster to main at 9pm"})
        out = app.agents_mutate({"action": "instruct", "text": "never post in fiverr at night"})
        self.assertTrue(out["reply"])
        self.assertTrue(out["rules"])
        with self.assertRaises(ValueError):
            app.agents_mutate({"action": "instruct", "text": "never post in fiverr at night"})

    def test_free_word_and_note_label(self):
        out = app.agents_mutate({"action": "instruct", "text": "post in free every 45 min"})
        self.assertIn({"gap"}, [{r["kind"]} for r in out["rules"]])
        out = app.agents_mutate({"action": "instruct", "text": "always use a polite tone"})
        self.assertIn("note", [r["kind"] for r in out["rules"]])

    def test_correction_saved_and_optionally_remembered(self):
        before = len(app.KNOWLEDGE.data["feedback"])
        with patch.object(app, "mem_add", return_value="Saved for the future: x") as mem:
            app.agents_mutate(
                {
                    "action": "correct",
                    "agent": "Reply Reader",
                    "decision": "d",
                    "text": "was sharing",
                    "remember": True,
                }
            )
            mem.assert_called_once_with("was sharing")
            app.agents_mutate({"action": "correct", "decision": "d", "text": "no memory"})
            self.assertEqual(mem.call_count, 1)
        self.assertEqual(len(app.KNOWLEDGE.data["feedback"]), before + 2)
        with self.assertRaises(ValueError):
            app.agents_mutate({"action": "correct", "text": " "})

    def test_manager_delegation_to_writer(self):
        res = app.agents_mutate(
            {"action": "chat", "agent": "manager", "text": "Ask Writer to write a group appeal"}
        )
        self.assertIn("reply", res)
        self.assertIn("Writer", res["reply"])
        self.assertIn("Easypaisa", res["reply"])

    def test_manager_progress_of_all_agents(self):
        res = app.agents_mutate(
            {"action": "chat", "agent": "manager", "text": "Ask all agents for their progress"}
        )
        self.assertIn("reply", res)
        self.assertIn("Group Poster", res["reply"])
        self.assertIn("Writer", res["reply"])
        self.assertIn("Checker", res["reply"])

    def test_conversational_writer_chat(self):
        res = app.agents_mutate(
            {"action": "chat", "agent": "writer", "text": "Draft a short Urdu message"}
        )
        self.assertIn("reply", res)
        self.assertIn("Easypaisa", res["reply"])

    def test_checker_agent_chat(self):
        bad_msg = "Please help if you can danger Rs 5000"
        res = app.agents_mutate(
            {"action": "chat", "agent": "checker", "text": bad_msg}
        )
        self.assertIn("reply", res)
        self.assertIn("FAILED", res["reply"])


if __name__ == "__main__":
    unittest.main()
