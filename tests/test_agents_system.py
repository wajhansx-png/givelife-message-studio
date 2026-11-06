"""Manager and the seven agents: real delegation, verified results, quality gate, limits, recovery,
memory and the Agents-page API. Fake WhatsApp and fake AI answers only; nothing is sent."""

import json, unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
from agents_system import Manager, DMGuard

IDS = ["manager", "writer", "checker", "auto", "dms", "replies", "volunteers", "plan"]


def ai(*answers):
    queue = [a if isinstance(a, str) else json.dumps(a) for a in answers]
    return patch("assistant._chat_raw", side_effect=lambda *a, **k: {"content": queue.pop(0)})


class Base(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        app._AGENTS = None
        app.STORE.put("agents_state", {})
        (app.DATA / "agents.json").unlink(missing_ok=True)
        self._rules = list(app.ENGINE.rules())
        self.m = app.agents()
        self.patches = [
            patch("assistant.client", return_value="k"),
            patch.object(app, "send_custom", side_effect=AssertionError("agents must not send")),
            patch.object(app, "send_text", side_effect=AssertionError("agents must not send")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        app.ENGINE.s["rules"] = self._rules
        app._AGENTS = None
        fixture.SendTests.tearDown(self)

    def say(self, text, agent=None):
        return self.m.handle(text, agent)


class Delegation(Base):
    def test_all_agents_reply_with_their_real_progress(self):
        out = self.say("Ask all agents for their progress")
        self.assertEqual({m["who"] for m in out[2:]}, set(IDS[1:]))
        self.assertTrue(all(t["status"] == "done" and t["verified"] for t in self.m.state["tasks"]))
        self.assertIn("off", next(m["text"] for m in out if m["who"] == "auto").lower())

    def test_message_to_one_agent_stays_in_its_own_thread(self):
        out = self.say("what is your status", "dms")
        self.assertEqual([(m["who"], m["agent"]) for m in out], [("you", "dms"), ("dms", "dms")])
        self.assertIn("between DMs", out[-1]["text"])

    def test_volunteer_guide_reports_real_pending_volunteers(self):
        app.ENGINE.s["vol_flow"] = {
            "923001234567": {"step": "waiting_owner"},
            "923009999999": {"step": "asked"},
        }
        out = self.say("Tell Volunteer Guide to check pending volunteers")
        self.assertEqual(out[-1]["who"], "volunteers")
        self.assertIn("…4567", out[-1]["text"])

    def test_rule_goes_to_group_poster_once(self):
        out = self.say("post in main every 20 min")
        self.assertIn("Saved rule", out[-1]["text"])
        self.assertIn("Post in main every 20 min", [r["text"] for r in app.ENGINE.rule_list()])
        self.assertIn("Already saved", self.say("post in main every 20 min")[-1]["text"])

    def test_preference_is_saved_permanently(self):
        with patch.object(app, "mem_add", return_value="Saved for the future.") as mem:
            out = self.say("Always put the Urdu hook first in slow messages")
        mem.assert_called_once()
        self.assertIn("every new message", out[-1]["text"])

    def test_reply_reader_never_confuses_promise_share_and_claim(self):
        for text, label in (
            ('"I will pay tomorrow"', "later"),
            ('"shared in 3 groups"', "shared"),
            ('"Paid"', "donated"),
        ):
            out = self.say("Reply Reader, what does this mean: " + text)
            self.assertIn("reads as: " + label, out[-1]["text"])
            self.assertIn("never treated as verified", out[-1]["text"])


class Writing(Base):
    def test_draft_is_checked_revised_and_saved_only_on_request(self):
        left = app.read_left()
        bad = {
            "reply": "Here it is.",
            "draft": "Help now. Rs. 99,999 left. 03097458815 EASYPAISA ONLY",
        }
        good = {
            "reply": "Fixed.",
            "draft": f"Help now. Rs. {left:,} left. 03097458815 EASYPAISA ONLY",
        }
        before = app.get_message("group")["text"]
        with ai(bad, good) as call:
            out = self.say("Ask Writer to improve the group message")
        self.assertEqual(call.call_count, 2)
        self.assertIn("Writer revised it and it now passes", out[-1]["text"])
        self.assertEqual(app.get_message("group")["text"], before)
        out = self.say("save this as the group message")
        self.assertIn("Saved as the GROUP base message", out[-1]["text"])
        self.assertEqual(app.get_message("group")["text"], good["draft"])

    def test_follow_up_keeps_the_writer_conversation(self):
        with ai(
            {"reply": "Use the loss hook.", "draft": ""}, {"reply": "Shorter.", "draft": ""}
        ) as call:
            self.say("Ask Writer what hook works best for a hospital case")
            out = self.say("tell it to make it shorter")
        self.assertEqual(out[-1]["who"], "writer")
        self.assertTrue(any("hospital" in m["content"] for m in call.call_args.args[3]))

    def test_invalid_ai_answer_is_never_shown(self):
        with ai("not json"):
            out = self.say("Ask Writer to write a DM")
        self.assertIn("not valid", out[-1]["text"])
        self.assertEqual(self.m.state["tasks"][-1]["status"], "failed")

    def test_generate_is_verified_from_real_state(self):
        bank = app.focus_bank()
        with patch.object(bank, "_spawn"):
            out = self.say("Ask Writer to generate 5 group versions")
        self.assertIn("Writing 5 new GROUP versions", out[-1]["text"])
        self.assertEqual(bank._load()["group"]["state"], "Generating")

    def test_checker_catches_amount_format_and_duplicates(self):
        checker = self.m.agents["checker"]
        self.assertIn("12,345", "; ".join(checker.problems("Rs. 12,345 left 03097458815")))
        self.assertIn(
            "same as the saved base message",
            "; ".join(checker.problems(app.get_message("group")["text"])),
        )
        self.assertIn("unpaired", "; ".join(checker.problems("*Broken bold line\n03097458815")))


class Safety(Base):
    def test_dm_guard_reports_the_40_cap_and_consent(self):
        s = DMGuard(self.m).status()
        self.assertEqual(s["progress"]["max"], 40)
        self.assertTrue(any("consent first" in f for f in s["facts"]))
        self.assertLessEqual(app.ENGINE.s["dm_daily"], 40)

    def test_a_broken_agent_never_stops_the_others(self):
        with patch.object(DMGuard, "report", side_effect=RuntimeError("boom")):
            out = self.say("ask all agents for their progress")
        self.assertIn("could not do that", next(m for m in out if m["who"] == "dms")["text"])
        with patch.object(DMGuard, "status", side_effect=RuntimeError("down")):
            view = app.agents().view()
        self.assertEqual([a["id"] for a in view["agents"]], IDS)
        self.assertEqual(next(a for a in view["agents"] if a["id"] == "dms")["state"], "Error")

    def test_offline_whatsapp_shows_error_with_recovery(self):
        with (
            patch.object(app.ENGINE, "status", return_value={"state": "offline", "now": "x"}),
            patch.object(app, "auto_on", return_value=True),
        ):
            auto = next(a for a in app.agents().view()["agents"] if a["id"] == "auto")
        self.assertEqual(auto["state"], "Error")
        self.assertEqual(auto["errors"][0]["action"], "open_home")

    def test_manager_names_the_group_the_number_is_not_in(self):
        with (
            patch.object(app, "wa_ok", return_value=True),
            patch.object(app, "check_groups", return_value={"missing": ["GiveLife Foundation"]}),
        ):
            texts = [i["text"] for i in self.m.issues()]
        self.assertTrue(any("not in: GiveLife Foundation" in t for t in texts))

    def test_memory_problems_are_reported(self):
        self.assertTrue(self.m.memory_status()["ok"])
        with patch.object(app.STORE, "put", side_effect=RuntimeError("db down")):
            self.assertIn("db down", self.m.memory_status()["text"])
        with patch.object(type(app.STORE), "pending_writes", 3, create=True):
            self.assertIn("3 saves are waiting", self.m.memory_status()["text"])

    def test_transient_failure_retried_safely_and_rarely_permanent_never(self):
        bank = app.focus_bank()
        for error, calls in (("HTTP 503 temporarily unavailable", 1), ("HTTP 401 bad key", 0)):
            self.m.state["retries"] = {}
            data = bank._load()
            data["group"] = dict(
                data.get("group") or {},
                source=app.get_message("group")["text"],
                revision="r",
                items=[],
                state="Partial",
                error=error,
                auto_failed=True,
            )
            bank._put(data)
            with patch.object(bank, "retry") as retry:
                self.m.watch()
                self.m.watch()
            self.assertEqual(retry.call_count, calls, error)
        notes = [d["text"] for d in self.m.state["decisions"]]
        self.assertEqual(
            sum(n.startswith("Noticed: Writer (GROUP)") for n in notes), 1
        )  # no repeats


class PageAndMemory(Base):
    def test_page_actions(self):
        with patch.object(app, "set_auto", side_effect=lambda on: "on" if on else "off") as sa:
            self.assertEqual(self.m.act({"action": "auto", "on": True})["reply"], "on")
            self.m.act({"action": "auto", "on": False})
        self.assertEqual([c.args[0] for c in sa.call_args_list], [True, False])
        with patch.object(app.focus_bank(), "retry") as retry:
            self.m.act({"action": "fix", "fix": "retry_writer"})
        retry.assert_called_once_with("group")
        self.say("post in main every 20 min")
        rid = next(
            r["id"] for r in app.ENGINE.rule_list() if r["text"] == "Post in main every 20 min"
        )
        self.m.act({"action": "rule_delete", "id": rid})
        self.assertNotIn(rid, [r["id"] for r in app.ENGINE.rule_list()])
        for bad in ({"action": "nope"}, {"action": "fix", "fix": "nope"}):
            with self.assertRaises(ValueError):
                self.m.act(bad)

    def test_view_is_real_and_complete(self):
        app.auto_log("Answered …1234: hello")
        view = self.m.view()
        self.assertEqual([a["id"] for a in view["agents"]], IDS)
        for a in view["agents"]:
            self.assertIn(a["state"], ("Active", "Working", "Idle", "Error"))
        replies = next(a for a in view["agents"] if a["id"] == "replies")
        self.assertTrue(any("Answered" in f["text"] for f in replies["feed"]))

    def test_conversation_and_tasks_survive_a_restart(self):
        self.say("ask all agents for their progress")
        again = Manager(app)
        self.assertEqual(len(again.state["chat"]), len(self.m.state["chat"]))
        self.assertEqual(len(again.state["tasks"]), 7)


if __name__ == "__main__":
    unittest.main()
