"""In-depth scenarios built from the owner's complaints. Every AI call is captured, so each test
proves what the AI was actually given, and what the app actually did. Fake AI and WhatsApp only.

1 misunderstands me        2 forgets context          3 asks the same questions
4 says it understands but does nothing             5 ignores my decisions
6 repeats mistakes          7 weak messages
"""

import json, unittest
from unittest.mock import patch
from test_agents_system import Base, app
from agents_system import Manager


class Spy:
    """Fake DeepSeek that records every system prompt and message list it receives."""

    def __init__(self, *answers):
        self.answers = [a if isinstance(a, str) else json.dumps(a) for a in answers]
        self.calls = []

    def __call__(self, key, system, tools, messages, **k):
        self.calls.append({"system": system, "messages": messages})
        return {"content": self.answers.pop(0) if self.answers else '{"reply": "ok", "draft": ""}'}

    @property
    def last(self):
        return self.calls[-1]

    def seen(self):
        c = self.last
        return c["system"] + "\n" + "\n".join(m["content"] for m in c["messages"])


class Scenarios(Base):
    def talk(self, spy, *lines, agent=None):
        with patch("assistant._chat_raw", side_effect=spy):
            return [self.say(t, agent) for t in lines][-1]

    # ------------------------------------------------------------------ 1 misunderstanding
    def test_1_real_phrasings_reach_the_right_agent(self):
        cases = [
            ("ask writer to make the group message stronger", "writer"),
            ("writter ko bolo message behtar karo", "writer"),
            ("write a dm for past donors", "writer"),
            ("make the dm shorter", "writer"),
            ("generate 5 group versions", "writer"),
            ('check this: "Rs. 99,999 left 03097458815"', "checker"),
            ("kitne dms gaye aaj", "dms"),
            ("how many DMs today?", "dms"),
            ("which volunteers are waiting?", "volunteers"),
            ("volunteers ka kya haal hai", "volunteers"),
            ("what is the case plan state", "plan"),
            ("kitne paise reh gaye", "plan"),
            ("when is the next group post?", "auto"),
            ("who replied done today?", "replies"),
            ("post in fiverr every 30 min", "auto"),
        ]
        bank = app.focus_bank()
        for text, want in cases:
            with self.subTest(text=text), patch.object(bank, "_spawn"):
                out = self.talk(Spy({"reply": "ok", "draft": ""}, "ok"), text)
                agents = [m["who"] for m in out if m["who"] not in ("you", "manager")]
                self.assertEqual(agents[:1], [want], f"{text!r} went to {agents or 'Manager only'}")

    def test_1_several_instructions_and_a_correction_in_one_message(self):
        out = self.talk(Spy(), "post in main every 20 min; then how many DMs today?")
        self.assertEqual([m["who"] for m in out if m["who"] in ("auto", "dms")], ["auto", "dms"])

    # ------------------------------------------------------------------ 2 forgetting context
    def test_2_writer_keeps_the_whole_conversation_and_facts(self):
        spy = Spy({"reply": "Loss hook.", "draft": ""}, {"reply": "Shorter.", "draft": ""})
        self.talk(spy, "Ask Writer: the child passed away last night, focus on the Janazah debt")
        self.talk(spy, "now make it shorter")
        seen = spy.seen()
        self.assertIn("Janazah debt", seen)  # the earlier turn
        self.assertIn("Amount still needed now", seen)  # verified facts every time
        self.assertIn(app.get_message("group")["text"][:40], seen)

    def test_2_context_survives_a_restart(self):
        self.talk(
            Spy({"reply": "noted", "draft": ""}),
            "Ask Writer: use the hadith about charity extinguishing sins",
        )
        app._AGENTS = None
        self.m = app.agents()
        spy = Spy({"reply": "ok", "draft": ""})
        self.talk(spy, "Ask Writer to continue")
        self.assertIn("extinguishing sins", spy.seen())

    def test_2_other_agents_see_what_was_just_discussed(self):
        self.say("how many DMs today?")
        spy = Spy("Do volunteers first.")
        self.talk(spy, "given that, what should volunteers do?", agent="volunteers")
        self.assertIn("between DMs", spy.last["system"])

    # ------------------------------------------------------------------ 3 asking the same questions
    def test_3_known_facts_are_always_given_so_nothing_is_asked_again(self):
        spy = Spy({"reply": "ok", "draft": ""}, {"reply": "ok", "draft": ""})
        self.talk(spy, "Ask Writer for a new hook")
        self.talk(spy, "Ask Writer for another hook")
        for c in spy.calls:
            self.assertIn("Amount still needed now", c["system"])
            self.assertIn("Saved GROUP message", c["system"])
            self.assertIn("Case:", c["system"])

    # ------------------------------------------------------------------ 4 says it understands but does nothing
    def test_4_every_success_claim_matches_a_real_change(self):
        out = self.say("post in main every 20 min")
        self.assertIn("Saved rule", out[-1]["text"])
        self.assertIn("Post in main every 20 min", [r["text"] for r in app.ENGINE.rule_list()])
        out = self.say("Always end with the Easypaisa line")
        self.assertTrue(
            any(
                e.get("active") and e["text"] == "Always end with the Easypaisa line"
                for e in app.KNOWLEDGE.data["entries"]
            )
        )
        with patch.object(app.focus_bank(), "_spawn"):
            out = self.say("generate 5 group versions")
        self.assertEqual(app.focus_bank()._load()["group"]["state"], "Generating")
        for t in self.m.state["tasks"]:
            if t["status"] == "done":
                self.assertTrue(t["verified"], t)

    def test_4_send_requests_never_pretend(self):
        out = self.say("send the poster to givelife now")
        self.assertIn("did not send anything", out[-1]["text"])

    def test_4_failed_ai_never_claims_success(self):
        out = self.talk(Spy("garbage"), "Ask Writer to rewrite the group message")
        self.assertIn("not valid", out[-1]["text"])
        self.assertEqual(self.m.state["tasks"][-1]["status"], "failed")

    def test_4_saving_a_draft_really_saves_it(self):
        left = app.read_left()
        draft = f"Fresh hook. Rs. {left:,} left. 03097458815"
        self.talk(Spy({"reply": "Here.", "draft": draft}), "Ask Writer to write a group message")
        out = self.say("save this as the group message")
        self.assertIn("Saved", out[-1]["text"])
        self.assertEqual(app.get_message("group")["text"], draft)

    # ------------------------------------------------------------------ 5 ignoring decisions
    def test_5_newest_decision_is_the_only_one_writer_sees(self):
        self.say("Always start slow messages with the hadith")
        self.say("Never start slow messages with the hadith")
        spy = Spy({"reply": "ok", "draft": ""})
        self.talk(spy, "Ask Writer for a slow message")
        prefs = spy.last["system"].split("OWNER PREFERENCES")[-1]
        self.assertIn("Never start slow messages with the hadith", prefs)
        self.assertNotIn("Always start slow messages with the hadith", prefs)

    def test_5_decisions_reach_every_ai_agent_not_only_writer(self):
        self.say("Always answer me in Roman Urdu")
        spy = Spy("theek hai")
        self.talk(spy, "volunteers ke baare mein batao kya karna chahiye", agent="volunteers")
        self.assertIn("Always answer me in Roman Urdu", spy.last["system"])

    # ------------------------------------------------------------------ 6 repeating mistakes
    def test_6_a_rejected_draft_teaches_the_next_one(self):
        left = app.read_left()
        spy = Spy(
            {"reply": "v1", "draft": f"URGENT!!! Rs. {left:,} left. 03097458815"},
            {"reply": "v2", "draft": f"A calm, sad hook. Rs. {left:,} left. 03097458815"},
            {"reply": "v3", "draft": ""},
        )
        self.talk(spy, "Ask Writer to write a group message")
        self.talk(spy, "no, too shouty, I never want all caps urgency")
        seen = spy.seen()
        self.assertIn("too shouty", seen)  # the reason went straight into the revision
        self.talk(spy, "Ask Writer for another group message tomorrow")
        self.assertIn("REJECTED", spy.last["system"])
        self.assertIn("too shouty", spy.last["system"])  # and into every later draft

    def test_6_checker_mistakes_become_permanent_regression_cases(self):
        left = app.read_left()
        self.m.ctx["draft"] = (
            f"Help. Rs. {left:,} left. 2 people giving Rs. 2,000 finish it. 03097458815"
        )
        with patch("assistant._chat_raw", side_effect=Spy({"reply": "fixed", "draft": ""})):
            self.say("wrong, the math is off")
        self.assertTrue(self.m.state["regressions"])
        self.assertEqual(self.m.regression_failures(), [])

    # ------------------------------------------------------------------ 7 weak messages
    def test_7_bad_draft_is_fixed_before_you_see_it(self):
        left = app.read_left()
        bad = {"reply": "Draft.", "draft": "Help!! Rs. 12,345 left. *Broken bold. 03097458815"}
        good = {
            "reply": "Fixed.",
            "draft": f"Help today. Rs. {left:,} left. *Bold* line. 03097458815",
        }
        spy = Spy(bad, good)
        out = self.talk(spy, "Ask Writer to write a group message")
        self.assertIn("now passes", out[-1]["text"])
        revision = spy.calls[1]["messages"][-1]["content"]
        self.assertIn("12,345", revision)
        self.assertIn("unpaired", revision)

    def test_7_writer_is_given_the_owner_style_and_approved_drafts(self):
        left = app.read_left()
        self.talk(
            Spy({"reply": "x", "draft": f"Approved style line. Rs. {left:,} left. 03097458815"}),
            "Ask Writer to write a group message",
        )
        self.say("save this as the group message")
        spy = Spy({"reply": "ok", "draft": ""})
        self.talk(spy, "Ask Writer for a new one")
        self.assertIn("APPROVED", spy.last["system"])
        self.assertIn("Approved style line", spy.last["system"])


if __name__ == "__main__":
    unittest.main()


class ApproveFlow(Base):
    """Writer shows one draft card; you read it; "approved" (any phrasing) puts it in the Group message."""

    def write(self, draft=None, reply="Here you go."):
        left = app.read_left()
        draft = draft or f"*A calm hook.* Rs. {left:,} left. 03097458815 EASYPAISA ONLY"
        spy = Spy({"reply": reply, "draft": draft})
        with patch("assistant._chat_raw", side_effect=spy):
            out = self.say("Ask Writer to write a group message")
        return draft, out[-1], spy

    def test_the_draft_is_a_card_not_chat_text_and_nothing_is_saved_yet(self):
        before = app.get_message("group")["text"]
        draft, item, _ = self.write()
        self.assertEqual(item["draft"]["text"], draft)
        self.assertEqual(item["draft"]["kind"], "group")
        self.assertNotIn(draft, item["text"])  # the text is only Writer's comment
        self.assertEqual(app.get_message("group")["text"], before)  # read first, then approve
        self.assertEqual(self.m.view()["pending"], item["draft"]["id"])

    def test_many_ways_of_saying_approved_save_it_to_the_group_message(self):
        for phrase in (
            "approved",
            "Approve",
            "ok",
            "okay save it",
            "theek hai",
            "haan perfect",
            "bilkul sahi hai",
            "yes",
            "daal do group mein",
            "love it",
        ):
            with self.subTest(phrase=phrase):
                draft, item, _ = self.write(
                    f"*Hook for {phrase.replace(' ', '-')}.* Rs. {app.read_left():,} left. 03097458815"
                )
                out = self.say(phrase)
                self.assertIn("Saved as your GROUP message", out[-1]["text"])
                self.assertEqual(app.get_message("group")["text"], draft)
                self.assertEqual(self.m.view()["pending"], "")
                saved = next(
                    m
                    for m in self.m.state["chat"]
                    if (m.get("draft") or {}).get("id") == item["draft"]["id"]
                )
                self.assertEqual(saved["draft"]["saved"], "group")
                self.m.state["chat"].clear()

    def test_feedback_is_never_mistaken_for_approval(self):
        before = app.get_message("group")["text"]
        for phrase in (
            "ok but make it shorter",
            "haan lekin hook badlo",
            "no",
            "not good",
            "approved but change the ending",
        ):
            with self.subTest(phrase=phrase):
                self.write()
                with patch(
                    "assistant._chat_raw", side_effect=Spy({"reply": "Changed.", "draft": ""})
                ):
                    self.say(phrase)
                self.assertEqual(app.get_message("group")["text"], before)

    def test_next_option_is_genuinely_different_and_remembers_what_was_shown(self):
        first, item1, _ = self.write()
        left = app.read_left()
        second = (
            f"Imagine his parents tonight. Rs. {left:,} is still needed. 03097458815 EASYPAISA ONLY"
        )
        spy = Spy({"reply": "Another angle.", "draft": second})
        with patch("assistant._chat_raw", side_effect=spy):
            out = self.say("next option")
        self.assertEqual(out[-1]["draft"]["text"], second)
        self.assertIn("OPTIONS ALREADY SHOWN", spy.last["system"])
        self.assertIn("A calm hook", spy.last["system"])
        self.assertNotEqual(out[-1]["draft"]["id"], item1["draft"]["id"])
        self.assertEqual(self.m.view()["pending"], out[-1]["draft"]["id"])
        self.say("approved")
        self.assertEqual(
            app.get_message("group")["text"], second
        )  # approving saves the option you are looking at

    def test_next_option_that_repeats_is_revised_before_you_see_it(self):
        first, _, _ = self.write()
        spy = Spy(
            {"reply": "Again.", "draft": first},
            {"reply": "Fresh.", "draft": f"A new angle. Rs. {app.read_left():,} left. 03097458815"},
        )
        with patch("assistant._chat_raw", side_effect=spy):
            out = self.say("another one")
        self.assertIn("A new angle", out[-1]["draft"]["text"])
        self.assertEqual(len(spy.calls), 2)

    def test_dm_draft_is_approved_into_the_dm_message(self):
        left = app.read_left()
        draft = f"Brother, please read. Rs. {left:,} left. 03097458815"
        with patch("assistant._chat_raw", side_effect=Spy({"reply": "DM.", "draft": draft})):
            out = self.say("Ask Writer to write a dm for past donors")
        self.assertEqual(out[-1]["draft"]["kind"], "dm")
        self.say("approved")
        self.assertEqual(app.get_message("dm")["text"], draft)

    def test_a_draft_with_a_problem_is_not_saved_on_approval(self):
        self.write()
        self.m.ctx["draft"] = "Help. Rs. 99,999 left."  # something changed it behind the card
        out = self.say("approved")
        self.assertIn("I will not save it", out[-1]["text"])
        self.assertNotEqual(app.get_message("group")["text"], "Help. Rs. 99,999 left.")

    def test_approving_with_no_draft_does_not_pretend_and_pending_survives_restart(self):
        out = self.say("approved")
        self.assertNotIn("Saved as your", out[-1]["text"])
        self.write()
        again = Manager(app)
        self.assertTrue(again.ctx["draft_pending"])
        out = again.handle("approved")
        self.assertIn("Saved as your GROUP message", out[-1]["text"])
