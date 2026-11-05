"""Reply Reader, DM Guard, Volunteer Guide, Checker and Writer prompt. No real WhatsApp, no real AI."""

import json, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dm_variants, quality, reply_intent, volunteer_flow
from test_agent_logic import Base

GOLDENS = json.loads((Path(__file__).parent / "evals" / "reply_goldens.json").read_text("utf-8"))[
    "cases"
]
VERIFIED = ("received", "confirmed", "verified", "got your payment", "reached us")


class ReplyReader(unittest.TestCase):
    def test_goldens(self):
        for c in GOLDENS:
            with self.subTest(text=c["text"]):
                self.assertEqual(
                    reply_intent.classify(c["text"], c["media"], c["last_outgoing"])[0], c["expect"]
                )

    def test_ai_answer_needs_evidence_and_confidence(self):
        ask = lambda raw: reply_intent.ai_classify(
            lambda p: raw, "I sent it", [("us", "x"), ("them", "I sent it")]
        )
        self.assertEqual(
            ask('{"intent":"donated","evidence":"I sent it","confident":true}')[0], "donated"
        )
        self.assertEqual(
            ask('{"intent":"donated","evidence":"I sent it","confident":false}')[0], "other"
        )
        self.assertEqual(
            ask('{"intent":"donated","evidence":"I paid 5000"}')[0], "other"
        )  # not in the reply
        self.assertEqual(
            ask('{"intent":"verified","evidence":"I sent it"}')[0], "other"
        )  # not a label
        self.assertEqual(ask("not json")[0], "other")

    def test_ai_gets_the_real_chat_not_only_the_last_line(self):
        msgs = [
            {
                "id": str(i),
                "timestamp": f"2026-11-05T10:0{i}:00Z",
                "content": f"m{i}",
                "is_from_me": i % 2 == 0,
            }
            for i in range(8)
        ]
        hist = reply_intent.history_from(msgs, "6")
        self.assertEqual([t for _, t in hist], ["m1", "m2", "m3", "m4", "m5", "m6"])
        self.assertEqual(hist[-1][0], "us")

    def test_thank_you_texts_never_claim_payment_was_verified(self):
        import server

        texts = [server.thank_text()]
        for t in texts:
            self.assertFalse([w for w in VERIFIED if w in t.lower()])


class Agents(Base):
    def setUp(self):
        super().setUp()
        self.out, self.optouts, self.blocked, self.chat = [], [], set(), []
        self.msgs = []
        self.h.update(
            send_text=lambda jid, t: self.out.append((jid, t)),
            is_opted_out=lambda p: p in self.blocked,
            optout=lambda p: (self.optouts.append(p), self.blocked.add(p)),
            ai_chat=lambda prompt: self.chat.pop(0) if self.chat else "",
            messages=lambda jid: self.msgs,
            send_custom=lambda b: (
                self.out.append((b["phone"], b["message"])) or {"code": "SUCCESS"}
            ),
            poster_caption=lambda: "poster",
            thank_text=lambda: "JazakAllah",
        )
        self.e.s["dm_enabled"] = True
        self.e.s["day"] = "d"

    # ---- DM Guard (code only)
    def test_guard_blocks_opted_out_hold_and_failed_check_but_not_groups(self):
        person, group = "9231@s.whatsapp.net", "123-456@g.us"
        self.blocked.add("9231")
        self.e._reply(person, "hi")
        self.assertEqual(self.out, [])
        self.e._reply(group, "hi")
        self.assertEqual(len(self.out), 1)
        self.e._reply(person, "bye", goodbye=True)  # the one confirmation after "stop"
        self.assertEqual(len(self.out), 2)
        self.h["is_opted_out"] = lambda p: 1 / 0  # a broken check never sends
        self.e._reply("9232@s.whatsapp.net", "hi")
        self.assertEqual(len(self.out), 2)
        self.h["is_opted_out"] = lambda p: False
        self.h["on_hold"] = lambda: True
        self.e._reply("9233@s.whatsapp.net", "hi")
        self.assertEqual(len(self.out), 2)

    def test_opted_out_person_gets_no_thank_you_or_saved_replies(self):
        self.blocked.add("9231")
        self.e.thank("9231")
        self.assertEqual(self.out, [])
        self.e.h["reply_setup"] = lambda: {"enabled": True, "replies": ["a", "b"], "since": 0}
        self.h["recent_chats"] = lambda: [("9231", "Ali")]
        self.msgs = [{"id": "m1", "content": "done", "timestamp": "2026-11-05T10:00:00Z"}]
        self.e.scan_reply_setup()
        self.assertEqual(self.out, [])

    def test_unclear_new_chat_reply_uses_ai_but_ai_cannot_skip_the_guard(self):
        self.h.update(
            reply_setup=lambda: {"enabled": True, "replies": ["thanks"], "since": 0},
            recent_chats=lambda: [("9231", "Ali")],
        )
        self.msgs = [{"id": "m1", "content": "I have sent it", "timestamp": "2026-11-05T10:00:00Z"}]
        self.chat = ['{"intent":"donated","evidence":"I have sent it","confident":true}']
        self.e.scan_reply_setup()
        self.assertEqual(self.out, [("9231@s.whatsapp.net", "thanks")])
        self.out.clear()
        self.e.s["reply_seen"], self.e.s["reply_by_phone"] = [], {}
        self.blocked.add("9231")
        self.chat = ['{"intent":"donated","evidence":"I have sent it","confident":true}']
        self.e.scan_reply_setup()
        self.assertEqual(self.out, [])

    def test_donation_claim_never_changes_the_amount_and_asks_owner_to_check(self):
        left = self.left
        m = {"id": "m9", "content": "Paid", "timestamp": "2026-11-05T10:00:00Z"}
        self.e._dm_message("9231", "9231@s.whatsapp.net", m, "Paid", "Ali")
        self.assertEqual(self.left, left)
        note = " ".join(t for to, t in self.out if to == "owner")
        self.assertIn("not verified", note)
        self.assertIn("Check Easypaisa", note)

    # ---- Volunteer Guide
    def test_wording_is_validated_in_code(self):
        base = volunteer_flow.ask_text("Ali")
        good = "Ali Bhai, a family needs help with a case we handle. Could you share it in your class and friends' groups? Even one share can reach someone. Shall I send the poster?"
        self.assertTrue(volunteer_flow.valid_wording(base, good, "Ali"))
        for bad in (
            good.replace("Ali", "Sam"),  # wrong name
            good + " Please donate Rs 500.",  # money ask
            good.replace("Shall I send the poster?", "Call me."),  # lost the poster question
            "Ali Bhai, share the poster 5 times?",  # number
            good + " http://x.co",  # link
            "Ali share poster?",  # far too short
            "Ali Bhai, کیا آپ share کر سکتے ہیں poster?",  # not the same language
        ):
            with self.subTest(bad=bad[:30]):
                self.assertFalse(volunteer_flow.valid_wording(base, bad, "Ali"))

    def test_natural_wording_is_occasional_and_falls_back(self):
        good = "Ali Bhai, a family needs help with a case we handle. Could you share it in your class and friends' groups? Even one share can reach someone. Shall I send the poster?"
        base = volunteer_flow.ask_text("Ali")
        phones = {
            p: sum(map(ord, p)) % 3 == 0 for p in ("92300111111", "92300111112", "92300111113")
        }
        used = 0
        for phone, uses_ai in phones.items():
            self.chat = [json.dumps({"message": good})]
            out = volunteer_flow.natural_ask(self.e, phone, "Ali")
            self.assertEqual(out, good if uses_ai else base)
            used += uses_ai
        self.assertEqual(used, 1)  # one in three
        ai_phone = next(p for p, u in phones.items() if u)
        for raw in ("not json", json.dumps({"message": "Please send Rs 500 now"}), ""):
            self.chat = [raw]
            self.assertEqual(volunteer_flow.natural_ask(self.e, ai_phone, "Ali"), base)
        self.h["ai_chat"] = lambda p: 1 / 0
        self.assertEqual(volunteer_flow.natural_ask(self.e, ai_phone, "Ali"), base)

    def test_volunteer_states_and_ai_for_complex_replies(self):
        st = lambda: {"step": "asked", "at": 0, "seen": [], "case": "c"}
        # complex reply -> AI sees the real chat, "shared" is thanked, state done
        s = st()
        self.chat = ['{"intent":"shared","evidence":"posted it","confident":true}']
        volunteer_flow.react(
            self.e,
            "9231",
            s,
            "posted it on my wall",
            history=[("us", "ask"), ("them", "posted it on my wall")],
        )
        self.assertEqual(s["step"], "done")
        # a question is never answered by AI: it waits for the owner
        s = st()
        volunteer_flow.react(self.e, "9232", s, "what is the case about?")
        self.assertEqual(s["step"], "waiting_owner")
        # opt-out stops the flow and records it
        s = st()
        volunteer_flow.react(self.e, "9233", s, "please stop")
        self.assertEqual((s["step"], self.optouts), ("stopped", ["9233"]))
        # "yes" to the ask sends the poster only through the guarded send path
        s = st()
        volunteer_flow.react(self.e, "9234", s, "yes")
        self.assertEqual((s["step"], self.out[-1]), ("poster", ("9234", "poster")))


class CheckerAndWriter(unittest.TestCase):
    SOURCE = "Yousuf needs treatment. Rs. 25,000 left."

    def review(self, rows):
        return quality.review(lambda p: json.dumps({"scores": rows}), self.SOURCE, ["A", "B"])

    def test_invented_fact_is_rejected_only_when_really_in_the_version(self):
        versions = ["Yousuf is 5 years old. Rs. 25,000 left.", "Yousuf needs treatment."]
        calls = lambda rows: quality.review(
            lambda p: json.dumps({"scores": rows}), self.SOURCE, versions
        )
        out = calls(
            [{"i": 0, "invented": "5 years old"}, {"i": 1, "invented": "his mother is ill"}]
        )
        self.assertIn("new fact", out[0])
        self.assertEqual(out[1], "")  # the AI quoted words that are not in the version: ignored
        self.assertEqual(
            calls([{"i": 0, "invented": "needs treatment"}])[0], ""
        )  # already in the source

    def test_plain_rewording_flagged_by_ai_is_not_treated_as_a_new_fact(self):
        versions = [
            "Please do not scroll past. Rs. 25,000 left.",
            "His mother is ill. Rs. 25,000 left.",
        ]
        rows = [
            {"i": 0, "invented": "Please do not scroll past"},
            {"i": 1, "invented": "His mother is ill"},
        ]
        out = quality.review(lambda p: json.dumps({"scores": rows}), self.SOURCE, versions)
        self.assertEqual(out[0], "")
        self.assertIn("new fact", out[1])

    def test_bad_review_output_keeps_versions(self):
        self.assertEqual(quality.review(lambda p: "garbage", self.SOURCE, ["A", "B"]), ["", ""])
        self.assertEqual(quality.review(lambda p: "", self.SOURCE, ["A"]), [""])

    def test_hard_rule_banned_phrase_needs_no_ai(self):
        self.assertIn(
            "never use",
            quality.hard_reason(self.SOURCE, "Please help if you can. Rs. 25,000 left."),
        )
        self.assertEqual(
            quality.hard_reason("Please help if you can", "Please help if you can"), ""
        )

    def test_writer_prompt_carries_owner_examples_corrections_and_forbids_new_facts(self):
        with (
            patch.object(dm_variants, "OWNER_STYLE", lambda: ["OWNER EXAMPLE TEXT"]),
            patch.object(dm_variants, "CORRECTIONS", lambda: ["never say hurry"]),
            patch.object(dm_variants, "PROVEN", lambda: []),
        ):
            prompt = dm_variants._prompt(self.SOURCE, 3, [])
        self.assertIn("OWNER EXAMPLE TEXT", prompt)
        self.assertIn("never say hurry", prompt)
        self.assertIn("every fact must come from the SOURCE", prompt)


if __name__ == "__main__":
    unittest.main()
