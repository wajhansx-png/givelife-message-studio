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
            patch(
                "ai_call.chat", return_value=""
            ),  # memory and summary judges: no network in tests
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
        self.assertIn("Already saved", self.say("Post in main every 20 min.")[-1]["text"])

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


class Understanding(Base):
    def test_roman_urdu_and_typos_reach_the_right_agent(self):
        out = self.say("sab agents ka progress batao")
        self.assertEqual(len([m for m in out if m["who"] not in ("you", "manager")]), 7)
        with ai({"reply": "Better now.", "draft": ""}):
            out = self.say("ask writter to improv the group message")
        self.assertEqual(out[-1]["who"], "writer")

    def test_several_instructions_run_in_order(self):
        out = self.say("post in main every 20 min; then ask DM Guard for status")
        self.assertIn("2 steps", out[1]["text"])
        self.assertEqual([m["who"] for m in out if m["who"] in ("auto", "dms")], ["auto", "dms"])
        self.assertIn("Post in main every 20 min", [r["text"] for r in app.ENGINE.rule_list()])

    def test_a_changed_decision_replaces_the_old_one(self):
        self.say("Always put the Urdu hook first in slow messages")
        self.say("Never put the Urdu hook first in slow messages")
        active = [
            e["text"]
            for e in app.KNOWLEDGE.data["entries"]
            if e.get("active") and "Urdu hook" in e["text"]
        ]
        self.assertEqual(active, ["Never put the Urdu hook first in slow messages"])

    def test_condition_is_saved_honestly(self):
        out = self.say("agar donations slow hon to Urdu hook use karo")
        self.assertIn("do not run automatic actions on conditions", out[-1]["text"])

    def test_double_tap_is_handled_once(self):
        self.say("ask DM Guard for status")
        self.assertEqual(self.say("ask DM Guard for status"), [])


class Learning(Base):
    def test_rejection_is_learned_saved_and_becomes_a_regression_case(self):
        left = app.read_left()
        wrong = f"Help. Rs. {left:,} left. 3 people giving Rs. 2,000 cover it. 03097458815"
        self.m.ctx["draft"] = wrong
        fixed = {"reply": "Shorter.", "draft": f"Help today. Rs. {left:,} left. 03097458815"}
        with ai(fixed), patch.object(app, "mem_add", return_value="Saved.") as mem:
            out = self.say("no, the math is wrong and it is too long")
        self.assertEqual(out[-1]["who"], "writer")  # Writer revised it with the reason
        self.assertIn("math is wrong", mem.call_args.args[0])
        self.assertEqual(self.m.state["drafts"][-1]["status"], "rejected")
        self.assertTrue(self.m.state["regressions"])  # Checker saw the math mistake
        self.assertEqual(self.m.regression_failures(), [])  # and still catches it

    def test_math_and_repeated_drafts_are_caught(self):
        from agents_system import math_problem

        self.assertIn("math", math_problem("Rs. 17,500 needed. 5 people giving Rs. 2,000 each"))
        self.assertEqual(
            math_problem(
                "Rs. 17,500 needed. Only 10 people giving Rs. 2,000, or 20 people giving Rs. 1,000"
            ),
            "",
        )
        left = app.read_left()
        same = {
            "reply": "Again.",
            "draft": f"Help now. Rs. {left:,} left. 03097458815 EASYPAISA ONLY",
        }
        with ai(same, same, same):
            self.say("Ask Writer to write a group message")
            out = self.say("Ask Writer to rewrite it")
        self.assertIn("almost the same as the last draft", out[-1]["text"])
        self.assertIn("passed Checker first time", " ".join(self.m.quality_facts()))

    def test_a_restart_never_shows_an_unfinished_task_as_done(self):
        self.m.state["tasks"].append({"id": "t1", "status": "running", "agent": "writer"})
        self.m.save()
        again = Manager(app)
        self.assertEqual(again.state["tasks"][-1]["status"], "interrupted")
        self.assertFalse(again.state["tasks"][-1]["verified"])


class Talking(Base):
    def test_every_ai_agent_answers_free_questions_from_its_real_facts(self):
        for agent, words in (
            ("replies", "Reply Reader"),
            ("volunteers", "Volunteer Guide"),
            ("auto", "Group Poster"),
            ("dms", "DM Guard"),
            ("plan", "Case Plan"),
        ):
            with ai(f"{words} here: all good.") as call:
                out = self.say(f"tell me, what should I watch today in {agent}?", agent)
            self.assertEqual(out[-1]["who"], agent)
            self.assertIn("here: all good", out[-1]["text"])
            system = call.call_args.args[1]
            self.assertIn("LIVE FACTS", system)
            self.assertIn("Never say a task is done", system)

    def test_follow_up_with_an_agent_keeps_its_own_history(self):
        with ai("Two volunteers are waiting.", "Ask them one at a time.") as call:
            self.say("who is waiting?", "volunteers")
            self.say("what should I do about it?", "volunteers")
        sent = call.call_args.args[3]
        self.assertTrue(any("who is waiting" in m["content"] for m in sent))

    def test_status_words_stay_real_and_no_ai_falls_back_to_facts(self):
        out = self.say("status", "dms")
        self.assertIn("between DMs", out[-1]["text"])  # no AI needed for a status
        with patch("assistant.client", return_value=None):
            out = self.say("explain how you protect WhatsApp", "dms")
        self.assertIn("AI is not connected", out[-1]["text"])
        self.assertIn("between DMs", out[-1]["text"])

    def test_page_data_never_waits_for_slow_checks(self):
        import threading, time

        started = threading.Event()

        def slow():
            started.set()
            time.sleep(1.5)
            return []

        self.m._icache = (0.0, [])
        with patch.object(self.m, "issues", side_effect=slow):
            t0 = time.time()
            view = self.m.view()
            self.assertLess(time.time() - t0, 1.0)  # the page got its data at once
            self.assertTrue(started.wait(2))  # while the real checks ran in the background
        self.assertEqual([a["id"] for a in view["agents"]][0], "manager")


class StudiedPatterns(Base):
    """Mem0 memory events, Agents SDK handoff context and input guardrail, Letta-style summaries."""

    def entries(self, word):
        return [
            e["text"]
            for e in app.KNOWLEDGE.data["entries"]
            if e.get("active") and word in e["text"]
        ]

    def test_memory_ai_updates_a_reworded_decision(self):
        self.say("Always open slow messages with a hadith")
        with (
            patch(
                "ai_call.chat", return_value='{"memory": [{"id": 0, "event": "UPDATE"}]}'
            ) as judge,
            patch.object(app.KNOWLEDGE, "data", app.KNOWLEDGE.data),
        ):
            app.KNOWLEDGE.data["entries"] = [
                e for e in app.KNOWLEDGE.data["entries"] if "hadith" in e["text"]
            ]
            self.say(
                "Remember: slow messages should start with the Urdu hook, the hadith comes after"
            )
        self.assertTrue(judge.called)
        self.assertEqual(
            self.entries("hadith"),
            ["Remember: slow messages should start with the Urdu hook, the hadith comes after"],
        )

    def test_memory_ai_none_means_nothing_saved_and_bad_ids_are_ignored(self):
        self.say("Always keep the payment line last")
        before = len(app.KNOWLEDGE.data["entries"])
        with patch("ai_call.chat", return_value='{"memory": [{"event": "NONE"}]}'):
            out = self.say("Remember to keep the payment line last")
        self.assertIn("already saved", out[-1]["text"])
        self.assertEqual(len(app.KNOWLEDGE.data["entries"]), before)
        with patch(
            "ai_call.chat", return_value='{"memory": [{"id": 99, "event": "DELETE"}, {"id": "x"}]}'
        ):
            self.say("Always mention the Easypaisa number twice")
        self.assertTrue(self.entries("payment line last"))  # an invented id never deletes anything

    def test_handoff_gives_the_agent_the_recent_conversation(self):
        self.say("status", "dms")
        with ai("Use the DM numbers above.") as call:
            self.say("based on that, what should I do?", "volunteers")
        self.assertIn("RECENT CONVERSATION WITH OTHER AGENTS", call.call_args.args[1])
        self.assertIn("between DMs", call.call_args.args[1])

    def test_send_now_is_stopped_before_any_agent_acts(self):
        for text in ("send the poster to givelife now", "abhi dm bhejo sab ko now"):
            out = self.say(text)
            self.assertIn("I did not send anything", out[-1]["text"])
        out = self.say("Ask Writer to write versions to send now")
        self.assertNotIn("I did not send anything", out[-1]["text"])  # writing work is not blocked

    def test_long_agent_chat_is_summarised_not_forgotten(self):
        for i in range(12):
            self.say(f"status number {i}", "dms")
        with patch(
            "ai_call.chat",
            return_value='{"summary": "- Owner checked DM limits 12 times; cap is 40."}',
        ):
            self.say("status again please", "dms")
        self.assertIn("cap is 40", self.m.state["summaries"]["dms"]["text"])
        with ai("ok") as call:
            self.say("any advice?", "dms")
        self.assertIn("EARLIER CONVERSATION", call.call_args.args[1])
        again = Manager(app)
        self.assertIn("dms", again.state["summaries"])  # survives a restart
