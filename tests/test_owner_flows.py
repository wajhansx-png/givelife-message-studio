"""Owner's real conversation patterns: reply reading, volunteer steps, quality rules, TEST readiness.
All fake transports; no real WhatsApp sends."""

import time, unittest
from unittest.mock import patch
import test_manual_sends  # noqa: F401  (sets the import path)
import reply_intent as R
import quality, volunteer_flow as V

SHARE_ASK = "Please share his case in your class and friends' groups."


class ReplyIntent(unittest.TestCase):
    def test_owner_chat_and_risky_phrases(self):
        cases = [
            ("Yes, I've shared it.", "", "shared"),
            ("Yes, I've shared it & have sent how much I could right now.", "", "both"),
            ("Okies", "", "ack"),
            ("done", SHARE_ASK, "shared"),
            ("done", "Reply Done after you donate.", "donated"),
            ("done sharing", "", "shared"),
            ("sent to 5 groups", "", "shared"),
            ("sent it to my class group", "", "shared"),
            ("not done yet", "", "not_done"),
            ("will send tomorrow", "", "later"),
            ("Is this case verified? Which hospital?", "", "question"),
            ("stop messaging me", "", "opt_out"),
            ("Donated 1000", "", "donated"),
            ("", "", "other"),
        ]
        for text, last, want in cases:
            self.assertEqual(R.classify(text, "", last)[0], want, text)
        self.assertEqual(R.classify("", "image")[0], "donated")

    def test_ai_step_needs_valid_json_and_real_evidence(self):
        good = lambda p: '{"intent": "shared", "evidence": "put it on status"}'
        self.assertEqual(R.ai_classify(good, "I put it on status bro", [])[0], "shared")
        made_up = lambda p: '{"intent": "donated", "evidence": "I paid 5000"}'
        self.assertEqual(R.ai_classify(made_up, "I put it on status bro", [])[0], "other")
        self.assertEqual(R.ai_classify(lambda p: "nonsense", "hmm", [])[0], "other")


class Quality(unittest.TestCase):
    def test_hard_rules_only_for_new_phrases(self):
        self.assertIn("DANGER", quality.hard_reason("Help Yousaf.", "DANGER: help Yousaf."))
        self.assertTrue(quality.hard_reason("Help.", "Help. Please help if you can."))
        self.assertEqual(quality.hard_reason("Danger zone", "Danger zone now"), "")

    def test_batched_review_keeps_on_bad_answer_and_flags_low_scores(self):
        vs = ["a", "b"]
        self.assertEqual(quality.review(lambda p: "not json", "s", vs), ["", ""])
        bad = '{"scores":[{"i":1,"owner":5,"natural":2,"calm":5,"follows":5,"reason":"robotic"}]}'
        self.assertEqual(quality.review(lambda p: bad, "s", vs), ["", "review: robotic"])


class FakeEngine:
    def __init__(self, inbox=None):
        self.s, self.sent, self.logs, self.notes, self.inbox = {}, [], [], [], inbox or {}
        self.thanked, self.shared = [], []
        self.h = {
            "send_custom": lambda b: self.sent.append(b) or {"code": "SUCCESS"},
            "messages": lambda jid: self.inbox.get(jid.split("@")[0], []),
            "poster_caption": lambda: "CAPTION",
            "optout": lambda p: self.logs.append("optout " + p),
        }

    def log(self, t):
        self.logs.append(t)

    def notify(self, key, text, gap):
        self.notes.append(text)

    def thank(self, phone):
        self.thanked.append(phone)

    def share_thanks(self, phone, jid):
        self.shared.append(phone)


def msg(i, text, t):
    return {
        "id": i,
        "content": text,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
    }


class VolunteerGuide(unittest.TestCase):
    def test_one_message_then_wait_then_choose(self):
        e = FakeEngine()
        n = V.start_round(
            e,
            [
                {"phone": "923001112223", "name": "Hamza GIKI"},
                {"phone": "923004445556", "name": "Ali"},
            ],
            "c1",
        )
        self.assertEqual(n, 1)  # one ask per step, never a burst
        self.assertIn("class group", e.sent[0]["message"])
        V.tick(e)
        self.assertEqual(len(e.sent), 1)  # no reply: nothing more
        now = time.time() + 5
        e.inbox["923001112223"] = [msg("m1", "ok send", now)]
        V.tick(e, now)
        self.assertTrue(e.sent[-1]["poster"])
        self.assertEqual(e.s["vol_flow"]["923001112223"]["step"], "poster")
        e.inbox["923001112223"].append(msg("m2", "done", now + 10))
        V.tick(e, now + 20)
        self.assertEqual(e.shared, ["923001112223"])
        self.assertEqual(e.s["vol_flow"]["923001112223"]["step"], "done")
        self.assertEqual(len(e.sent), 2)

    def test_check_once_and_questions_go_to_owner(self):
        e = FakeEngine()
        e.s["vol_flow"] = {"92300": {"step": "poster", "at": 0, "case": "c", "seen": []}}
        V.tick(e, V.CHECK_AFTER + 10)
        V.tick(e, V.CHECK_AFTER + 20)
        self.assertEqual([b["message"] for b in e.sent], ["Brother, are you done?"])
        e.inbox["92300"] = [msg("q", "Which hospital is it?", time.time())]
        e.s["vol_flow"]["92300"]["at"] = 0
        V.tick(e)
        self.assertEqual(e.s["vol_flow"]["92300"]["step"], "waiting_owner")
        self.assertTrue(e.notes)
        self.assertEqual(len(e.sent), 1)

    def test_okies_gets_no_reply(self):
        e = FakeEngine({"92300": [msg("a", "Okies", time.time())]})
        e.s["vol_flow"] = {
            "92300": {"step": "poster", "at": 0, "case": "c", "seen": [], "checked": True}
        }
        V.tick(e)
        self.assertEqual(e.sent, [])


class ServerGuards(unittest.TestCase):
    def setUp(self):
        import test_manual_sends as fixture

        self.fx = fixture
        fixture.SendTests.setUp(self)
        self.app = fixture.app

    def tearDown(self):
        self.fx.SendTests.tearDown(self)

    def test_dm_daily_cap_and_gap_apply_to_batches(self):
        app = self.app
        day = (
            app.datetime.datetime.now(app.datetime.timezone(app.datetime.timedelta(hours=5)))
            .date()
            .isoformat()
        )
        app.STORE.put("dm_daily", {"day": day, "count": app.DM_DAILY_CAP, "last": 0})
        with self.assertRaisesRegex(ValueError, "daily limit"):
            app.send_custom(
                {
                    "target": "phone",
                    "phone": "923001234567",
                    "message": "Hi {name}",
                    "kind": "volunteer_batch",
                }
            )
        app.STORE.put("dm_daily", {"day": day, "count": 1, "last": time.time()})
        with self.assertRaisesRegex(ValueError, "minutes between DMs"):
            app.send_custom(
                {
                    "target": "phone",
                    "phone": "923001234567",
                    "message": "Hi",
                    "kind": "volunteer_flow",
                }
            )

    def test_test_button_refuses_to_repeat_when_versions_missing(self):
        app = self.app
        app.STORE.put("focus_wording", {})
        with patch.object(app.threading.Thread, "start"):
            row = app.focus_bank().get("group")
        self.assertEqual(row.get("items") or [], [])


if __name__ == "__main__":
    unittest.main()


class ClaudeFallback(unittest.TestCase):
    def setUp(self):
        import assistant

        self.a = assistant
        self.env = dict(__import__("os").environ)
        self.a._CLAUDE["down_until"] = 0.0
        self.a.NOTICE.update(id=0, text="", time=0.0)

    def tearDown(self):
        import os

        os.environ.clear()
        os.environ.update(self.env)
        self.a._CLAUDE["down_until"] = 0.0

    def test_poe_key_typo_is_fixed_and_claude_is_used_first(self):
        import os, io, json

        os.environ["POE_API_KEY"] = "gotsk-poe-abc"
        os.environ["DEEPSEEK_API_KEY"] = "ds"
        self.assertEqual(self.a.claude_key(), "sk-poe-abc")
        reply = io.BytesIO(
            json.dumps(
                {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
            ).encode()
        )
        with patch.object(self.a.urllib.request, "urlopen", return_value=reply) as op:
            msg = self.a._chat_raw("ds", "sys", [], [{"role": "user", "content": "x"}])
        self.assertEqual(msg["content"], "hi")
        self.assertIn("api.poe.com", op.call_args[0][0].full_url)
        self.assertEqual(self.a.ai_notice()["id"], 0)

    def test_failure_shifts_to_deepseek_with_a_notice_and_cooldown(self):
        import os

        os.environ["POE_API_KEY"] = "sk-poe-abc"
        os.environ["DEEPSEEK_API_KEY"] = "ds"
        calls = []

        def fake(req, timeout=0):
            calls.append(req.full_url)
            if "poe.com" in req.full_url:
                raise OSError("down")
            import io, json

            return io.BytesIO(
                json.dumps(
                    {"choices": [{"message": {"content": "ds"}, "finish_reason": "stop"}]}
                ).encode()
            )

        with patch.object(self.a.urllib.request, "urlopen", side_effect=fake):
            first = self.a._chat_raw("ds", "s", [], [{"role": "user", "content": "x"}])
            second = self.a._chat_raw("ds", "s", [], [{"role": "user", "content": "y"}])
        self.assertEqual((first["content"], second["content"]), ("ds", "ds"))
        self.assertEqual(
            sum("poe.com" in c for c in calls), 1
        )  # cooldown: Claude not retried at once
        n = self.a.ai_notice()
        self.assertEqual(n["id"], 1)
        self.assertIn("Shifting to DeepSeek", n["text"])


class ClaudeChat(unittest.TestCase):
    def test_tool_chat_uses_claude_via_poe_and_labels_it(self):
        import os, io, json
        import assistant as a

        env = dict(os.environ)
        try:
            os.environ["POE_API_KEY"] = "sk-poe-abc"
            a._CLAUDE["down_until"] = 0.0
            tc = [
                {"id": "1", "type": "function", "function": {"name": "nothing", "arguments": "{}"}}
            ]
            reply = io.BytesIO(
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {"content": None, "tool_calls": tc},
                                "finish_reason": "tool_calls",
                            }
                        ]
                    }
                ).encode()
            )
            msgs = [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "", "reasoning_content": "r"},
            ]
            with patch.object(a.urllib.request, "urlopen", return_value=reply) as op:
                out = a._chat_raw("ds", "s", [a.tool("nothing", "d", {}, [])], msgs)
            self.assertEqual(out["tool_calls"][0]["id"], "1")
            self.assertEqual(a.served_label(), "Sonnet 5.5")
            sent = json.loads(op.call_args[0][0].data)
            self.assertNotIn("reasoning_content", json.dumps(sent["messages"]))
            self.assertIn("tools", sent)
            a._CLAUDE["down_until"] = (
                __import__("time").time() + 99
            )  # Claude down: DeepSeek answers, no label
            ds = io.BytesIO(
                json.dumps(
                    {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
                ).encode()
            )
            with patch.object(a.urllib.request, "urlopen", return_value=ds):
                a._chat_raw("ds", "s", [], [{"role": "user", "content": "x"}])
            self.assertEqual(a.served_label(), "")
        finally:
            os.environ.clear()
            os.environ.update(env)
            a._CLAUDE["down_until"] = 0.0
