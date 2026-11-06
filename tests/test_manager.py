"""Manager: real delegation to agents, verified results, quality gate, recovery and memory.
Fake WhatsApp and fake AI answers only; nothing is sent."""

import json, unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
from manager import Manager


def ai(*answers):
    """Fake DeepSeek: each call returns the next JSON answer."""
    queue = [a if isinstance(a, str) else json.dumps(a) for a in answers]
    return patch("assistant._chat_raw", side_effect=lambda *a, **k: {"content": queue.pop(0)})


class ManagerTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        app._MANAGER = None
        app.STORE.put("manager_state", {})
        (app.DATA / "manager.json").unlink(missing_ok=True)
        self.m = app.manager()
        self.key = patch("assistant.client", return_value="k")
        self.key.start()
        self.nosend = [
            patch.object(app, "send_custom", side_effect=AssertionError("Manager must not send")),
            patch.object(app, "send_text", side_effect=AssertionError("Manager must not send")),
        ]
        for p in self.nosend:
            p.start()

    def tearDown(self):
        for p in [self.key, *self.nosend]:
            p.stop()
        app._MANAGER = None
        fixture.SendTests.tearDown(self)

    def say(self, text, agent=None):
        return self.m.handle(text, agent)

    def test_all_agents_reply_with_their_real_progress(self):
        out = self.say("Ask all agents for their progress")
        who = [m["who"] for m in out]
        self.assertEqual(who[:2], ["you", "manager"])
        self.assertEqual(
            set(who[2:]), {"writer", "checker", "replies", "dms", "volunteers", "auto", "plan"}
        )
        tasks = self.m.state["tasks"]
        self.assertTrue(all(t["status"] == "done" and t["verified"] for t in tasks))
        auto = next(m["text"] for m in out if m["who"] == "auto")
        self.assertIn("Auto off", auto)  # real state, not a made-up summary

    def test_writer_draft_is_checked_revised_and_saved_only_on_request(self):
        left = app.read_left()
        bad = {
            "reply": "Here it is.",
            "draft": "Help now. Rs. 99,999 left. 03097458815 EASYPAISA ONLY",
        }
        good = {
            "reply": "Fixed.",
            "draft": f"Help now. Rs. {left:,} left. 03097458815 EASYPAISA ONLY",
        }
        with ai(bad, good) as call:
            out = self.say("Ask Writer to improve the group message")
        self.assertEqual(
            call.call_count, 2
        )  # Checker rejected the first draft, Writer revised once
        reply = out[-1]
        self.assertEqual(reply["who"], "writer")
        self.assertIn("Writer revised it and it now passes", reply["text"])
        self.assertNotIn("99,999", reply["text"].split("(Manager")[0])
        before = app.get_message("group")["text"]
        self.assertEqual(app.get_message("group")["text"], before)  # nothing saved by itself
        out = self.say("save this as the group message")
        self.assertIn("Saved as the GROUP base message", out[-1]["text"])
        self.assertEqual(app.get_message("group")["text"], good["draft"])
        self.assertTrue(self.m.state["tasks"][-1]["verified"])

    def test_follow_up_goes_to_the_same_agent_with_context(self):
        first = {"reply": "Draft.", "draft": ""}
        second = {"reply": "Shorter now.", "draft": ""}
        with ai(first, second) as call:
            self.say("Ask Writer what hook works best for a hospital case")
            out = self.say("tell it to make it shorter")
        self.assertEqual(out[-1]["who"], "writer")
        sent = call.call_args.args[3]
        self.assertTrue(any("hospital" in m["content"] for m in sent))  # earlier turn kept

    def test_invalid_ai_answer_is_never_shown_as_a_reply(self):
        with ai("not json"):
            out = self.say("Ask Writer to write a DM")
        self.assertIn("not valid", out[-1]["text"])
        self.assertEqual(self.m.state["tasks"][-1]["status"], "failed")

    def test_volunteer_guide_reports_real_pending_volunteers(self):
        app.ENGINE.s["vol_flow"] = {
            "923001234567": {"step": "waiting_owner"},
            "923009999999": {"step": "asked"},
        }
        out = self.say("Tell Volunteer Guide to check pending volunteers")
        self.assertEqual(out[-1]["who"], "volunteers")
        self.assertIn("…4567", out[-1]["text"])
        self.assertIn("1 asked", out[-1]["text"])

    def test_rule_goes_to_group_poster_and_is_verified(self):
        out = self.say("post in main every 20 min")
        self.assertEqual(out[-1]["who"], "auto")
        self.assertIn("Saved rule", out[-1]["text"])
        self.assertIn("Post in main every 20 min", [r["text"] for r in app.ENGINE.rule_list()])

    def test_checker_catches_wrong_amount_and_duplicates(self):
        out = self.say('Ask Checker to check "Rs. 12,345 left now 03097458815"')
        self.assertIn("12,345", out[-1]["text"])
        base = app.get_message("group")["text"]
        self.assertIn("same as the saved base message", "; ".join(self.m._problems(base)))

    def test_writer_generate_is_verified_from_real_state(self):
        bank = app.focus_bank()
        with patch.object(bank, "_spawn"):
            out = self.say("Ask Writer to generate 5 group versions")
        self.assertIn("Writing 5 new GROUP versions", out[-1]["text"])
        self.assertEqual(bank._load()["group"]["state"], "Generating")

    def test_a_broken_agent_never_stops_the_others(self):
        with patch.object(Manager, "_dms", side_effect=RuntimeError("boom")):
            out = self.say("ask all agents for their progress")
        dm = next(m for m in out if m["who"] == "dms")
        self.assertIn("could not do that", dm["text"])
        self.assertEqual(len([m for m in out if m["who"] not in ("you", "manager")]), 7)
        with patch.object(Manager, "view", side_effect=RuntimeError("down")):
            ids = [a["id"] for a in app.agents_view()["agents"]]
        self.assertEqual(ids[0], "manager")
        self.assertEqual(len(ids), 7)

    def test_conversation_and_tasks_survive_a_restart(self):
        self.say("ask all agents for their progress")
        again = Manager(app)
        self.assertEqual(len(again.state["chat"]), len(self.m.state["chat"]))
        self.assertEqual(len(again.state["tasks"]), 7)

    def test_memory_problems_are_reported(self):
        self.assertTrue(self.m.memory_status()["ok"])
        with patch.object(app.STORE, "put", side_effect=RuntimeError("db down")):
            m = self.m.memory_status()
        self.assertFalse(m["ok"])
        self.assertIn("db down", m["text"])

    def test_transient_writer_failure_is_retried_safely_and_rarely(self):
        bank = app.focus_bank()
        data = bank._load()
        data["group"] = dict(
            data.get("group") or {},
            source=app.get_message("group")["text"],
            revision="r",
            items=[],
            state="Partial",
            error="HTTP 503 temporarily unavailable",
            auto_failed=True,
        )
        bank._put(data)
        with patch.object(bank, "retry") as retry:
            self.m.watch()
            self.m.watch()  # 30 minutes have not passed
        self.assertEqual(retry.call_count, 1)
        notes = [d["text"] for d in self.m.state["decisions"]]
        self.assertEqual(sum("Retried Writer" in n for n in notes), 1)
        self.assertEqual(
            sum(n.startswith("Noticed: Writer (GROUP)") for n in notes), 1
        )  # no repeats

    def test_permanent_writer_failure_is_not_retried(self):
        bank = app.focus_bank()
        data = bank._load()
        data["group"] = dict(
            data.get("group") or {},
            source="x",
            revision="r",
            items=[],
            state="Partial",
            error="HTTP 401 bad key",
            auto_failed=True,
        )
        bank._put(data)
        with patch.object(bank, "retry") as retry:
            self.m.watch()
        retry.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class GroupMembership(unittest.TestCase):
    setUp = ManagerTests.setUp
    tearDown = ManagerTests.tearDown

    def test_manager_names_the_group_that_the_linked_number_is_not_in(self):
        with (
            patch.object(app, "wa_ok", return_value=True),
            patch.object(app, "check_groups", return_value={"missing": ["GiveLife Foundation"]}),
        ):
            texts = [i["text"] for i in self.m.issues()]
        self.assertTrue(any("not in: GiveLife Foundation" in t for t in texts))

    def test_a_pending_database_write_is_reported_not_crashing(self):
        with patch.object(type(app.STORE), "pending_writes", 3, create=True):
            self.assertIn("3 saves are waiting", self.m.memory_status()["text"])


class Preferences(unittest.TestCase):
    setUp = ManagerTests.setUp
    tearDown = ManagerTests.tearDown

    def test_preference_is_saved_permanently_and_reaches_writer(self):
        with patch.object(app, "mem_add", return_value="Saved for the future.") as mem:
            out = self.m.handle("Always put the Urdu hook first in slow messages")
        mem.assert_called_once()
        self.assertIn("Writer uses it", out[-1]["text"])
