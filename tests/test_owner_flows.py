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
