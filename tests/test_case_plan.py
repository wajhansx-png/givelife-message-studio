import copy, datetime, os, time, unittest
from unittest.mock import patch, Mock
import test_manual_sends as fixture
from test_manual_sends import app
import case_plan, message_rules, team_rules as T

FACTS = {
    "name": "Yousaf",
    "age": "2",
    "gender": "boy",
    "what_happened": "has passed away",
    "money_for": "Janazah, kafan and burial fees",
    "deadline": "Janazah at 4 PM tomorrow",
    "hadith": "1",
}
PKT = T.PKT


def at(h, m):
    return datetime.datetime(2026, 11, 5, h, m, tzinfo=PKT)


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.facts = case_plan.clean_facts(FACTS)
        self.d = case_plan.build(self.facts, 22000)

    def test_built_messages_follow_pdf_exactly(self):
        for mode, text in self.d.items():
            self.assertEqual(message_rules.problems(text, 22000, self.facts), [], mode)
        n = self.d["normal"].split("\n\n")
        self.assertTrue(n[0].startswith("*") and n[0].endswith("* 💔"))
        self.assertTrue(n[1].startswith("_") and n[1].endswith("_"))
        self.assertIn(
            "Just 11 kind people donating Rs. 2,000 or 22 people donating Rs. 1,000", n[2]
        )
        self.assertEqual(n[3], "Please don't think someone else will help.")
        self.assertEqual(n[4], "\n".join(T.FOOTER))
        self.assertIn(T.HADITH[0], self.d["slow"])
        self.assertEqual(message_rules.mode_of(self.d["slow"]), "slow")

    def test_each_pdf_rule_is_enforced(self):
        good = self.d["normal"]
        bad = {
            "plain hook": good.replace("*2-year-old", "2-year-old", 1).replace(
                "Janazah.* 💔", "Janazah. 💔", 1
            ),
            "no emoji": good.replace(" 💔", "", 1),
            "price in hook": good.replace("parents cannot pay", "parents cannot pay Rs. 5,000", 1),
            "too long hook": good.replace("has passed away.", "has passed away " + "and " * 20, 1),
            "line 2 not italic": good.replace("_Yousaf,", "Yousaf,", 1).replace(
                "fees. Janazah at 4 PM tomorrow._", "fees. Janazah at 4 PM tomorrow.", 1
            ),
            "wrong math": good.replace("22 people", "23 people"),
            "wrong amount": good.replace("11 kind", "10 kind").replace("22 people", "20 people"),
            "line 4 changed": good.replace("Please don't", "Please do not"),
            "jazzcash": good + "\nJazzCash 0300",
            "other payment": good.replace("EASYPAISA ONLY", "EASYPAISA or HBL"),
            "footer changed": good.replace("03097458815", "03000000000"),
            "hashtag": good.replace("Please don't", "#help Please don't"),
            "emojis": good.replace("fees.", "fees. 😢😢😢"),
            "invented number": good.replace("Yousaf, 2 years", "Yousaf, 7 years"),
        }
        for name, text in bad.items():
            with self.subTest(name):
                self.assertTrue(message_rules.problems(text, 22000, self.facts), name)

    def test_hadith_must_be_exact(self):
        slow = self.d["slow"]
        self.assertTrue(message_rules.problems(slow.replace("مشکل", "مصیبت", 1), 22000, self.facts))
        self.assertTrue(
            message_rules.problems(
                slow.replace(T.HADITH[0], "نبی کریم ﷺ نے فرمایا: ایک نئی بات", 1), 22000, self.facts
            )
        )
        self.assertEqual(len(T.HADITH), 3)

    def test_slow_hook_must_be_urdu_and_short(self):
        slow = self.d["slow"]
        english = slow.replace(
            slow.split("\n\n")[0],
            "*Yousaf has passed away. His parents cannot pay for the Janazah.* 💔",
            1,
        )
        self.assertTrue(message_rules.problems(english, 22000, self.facts))

    def test_math_is_exact_when_possible_and_rounds_up_otherwise(self):
        with self.assertRaises(ValueError):
            case_plan.build(
                self.facts, 23500
            )  # strict PDF math refuses an amount that cannot split
        plan = case_plan.new_case(
            FACTS, 23500, "Yousaf"
        )  # the app's round-up is used for real amounts
        self.assertIn("12 kind people", plan["drafts"]["normal"])
        self.assertIn("Rs. 2,000 or 24 people", plan["drafts"]["normal"])
        live = case_plan.build(self.facts, 23500, exact=False)["normal"]
        self.assertIn("12 kind people", live)
        self.assertEqual(message_rules.problems(live, 23500, self.facts, exact=False), [])
        self.assertTrue(message_rules.problems(live, 23500, self.facts))  # strict mode refuses it

    def test_outdated_amount_is_caught_and_refreshed(self):
        old = self.d["normal"]
        self.assertTrue(message_rules.problems(old, 20000, self.facts))
        fresh = message_rules.refresh_amount(old, 20000)
        self.assertEqual(message_rules.problems(fresh, 20000, self.facts), [])
        self.assertIn("10 kind people", fresh)

    def test_facts_are_verified(self):
        for field, value in (
            ("name", "Yo*sa"),
            ("age", "abc"),
            ("age", "200"),
            ("gender", "x"),
            ("hadith", "9"),
            ("money_for", ""),
            ("what_happened", "a_b"),
        ):
            with self.subTest(field):
                with self.assertRaises(ValueError):
                    case_plan.clean_facts({**FACTS, field: value})
        with self.assertRaises(ValueError):  # the PDF hooks only fit a child who passed away
            case_plan.build(
                case_plan.clean_facts(
                    {**FACTS, "what_happened": "is in hospital", "money_for": "treatment"}
                ),
                22000,
            )
        with self.assertRaises(ValueError):
            case_plan.build(case_plan.clean_facts({**FACTS, "age": "40"}), 22000)

    def test_working_hours_boundaries(self):
        for h, m, ok in (
            (11, 59, False),
            (12, 0, True),
            (15, 29, True),
            (15, 30, False),
            (17, 59, False),
            (18, 0, True),
            (22, 29, True),
            (22, 30, False),
            (3, 0, False),
        ):
            with self.subTest(f"{h}:{m:02d}"):
                self.assertEqual(T.in_work_hours(at(h, m)), ok)
        utc = datetime.datetime(2026, 11, 5, 8, 0, tzinfo=datetime.timezone.utc)  # 13:00 PKT
        self.assertTrue(T.in_work_hours(utc))

    def test_state_logic(self):
        plan = case_plan.new_case(FACTS, 22000, "Yousaf")
        self.assertEqual(
            case_plan.advance(plan, 22000, 500, "Yousaf"), "draft"
        )  # not approved: nothing moves
        plan = case_plan.approve(plan, 22000)
        self.assertEqual(plan["state"], "ready")
        self.assertEqual(case_plan.advance(plan, 22000, 10, "Yousaf"), "normal")
        self.assertEqual(case_plan.advance(plan, 22000, 89, "Yousaf"), "normal")
        self.assertEqual(case_plan.advance(plan, 22000, 90, "Yousaf"), "slow")
        self.assertEqual(case_plan.advance(plan, 0, 90, "Yousaf"), "done")
        self.assertEqual(case_plan.advance(plan, 22000, 10, "Another case"), "stopped")
        case_plan.stop(plan, "x")
        self.assertEqual(case_plan.advance(plan, 22000, 10, "Yousaf"), "stopped")
        with self.assertRaises(ValueError):
            case_plan.approve(plan, 22000)  # only a draft can be approved
        self.assertEqual(case_plan.resume(plan)["state"], "ready")


class EngineTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self.engine_state = copy.deepcopy(
            app.ENGINE.s
        )  # restored in tearDown: other test files share it
        self.left = 22000  # patched below: set_left would rewrite the shared draft files
        self.sent = []
        self.bank = Mock()
        self.patches = [
            patch.object(app, "focus_bank", return_value=self.bank),
            patch.dict(
                app.ENGINE.h, {"send_text": lambda jid, text: self.sent.append((jid, text))}
            ),
            patch.dict(os.environ, {"AUTO_ALERT_PHONES": "923001112233, " + app.OWNER_PHONE}),
            patch.object(app, "active_case_name", return_value="Yousaf"),
            patch.object(app, "read_left", lambda: self.left),
            patch.dict(app.ENGINE.h, {"read_left": lambda: self.left}),
        ]
        for p in self.patches:
            p.start()
        app.ENGINE.s["notified"] = {}
        app.ENGINE.s["last_money"] = time.time()
        app.STORE.put("case_plan", {"state": "cleared"})

    def tearDown(self):
        for p in self.patches:
            p.stop()
        app.ENGINE.s.clear()
        app.ENGINE.s.update(self.engine_state)
        fixture.SendTests.tearDown(self)

    def approved(self):
        app.plan_mutate({"action": "create", "facts": FACTS})
        return app.plan_mutate({"action": "approve"})

    def test_create_then_approve_runs_normal_and_applies_message(self):
        view = app.plan_mutate({"action": "create", "facts": FACTS})
        self.assertEqual(view["plan"]["state"], "draft")
        self.bank.save.assert_not_called()  # nothing is applied before approval
        self.assertFalse(any(c["problems"] for c in view["checks"].values()))
        view = app.plan_mutate({"action": "approve"})
        self.assertEqual(view["plan"]["state"], "normal")
        self.bank.save.assert_called_once()
        self.assertEqual(self.bank.save.call_args.args, ("group", view["checks"]["normal"]["text"]))
        self.assertEqual(self.sent, [])  # nothing was sent

    def test_slow_switch_alerts_owner_and_listed_team_once(self):
        self.approved()
        app.ENGINE.s["last_money"] = time.time() - 100 * 60
        app.ENGINE.plan_tick()
        self.assertEqual(app.plan_get()["state"], "slow")
        self.assertIn("نبی کریم", self.bank.save.call_args.args[1])
        jids = [j for j, _ in self.sent]
        self.assertEqual(
            sorted(jids),
            sorted([app.OWNER_PHONE + "@s.whatsapp.net", "923001112233@s.whatsapp.net"]),
        )
        app.ENGINE.plan_tick()  # same state again: no duplicate apply or alert
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.bank.save.call_count, 2)
        app.ENGINE.s["last_money"] = time.time()  # money came: back to Normal
        app.ENGINE.plan_tick()
        self.assertEqual(app.plan_get()["state"], "normal")

    def test_no_alert_recipients_unless_owner_lists_them(self):
        with patch.dict(os.environ, {"AUTO_ALERT_PHONES": ""}):
            self.approved()
            app.ENGINE.s["last_money"] = time.time() - 100 * 60
            app.ENGINE.plan_tick()
        self.assertEqual([j for j, _ in self.sent], [app.OWNER_PHONE + "@s.whatsapp.net"])

    def test_gate_blocks_tampered_message_and_stops_plan(self):
        self.approved()
        good = app.plan_get()["drafts"]["normal"]
        bad = good.replace("03097458815", "03000000000")
        self.assertTrue(app.ENGINE._plan_gate(good))
        self.assertFalse(app.ENGINE._plan_gate(bad))
        self.assertEqual(app.plan_get()["state"], "stopped")
        self.assertTrue(any("Stopped before sending" in t for _, t in self.sent))
        sent = len(self.sent)
        self.assertTrue(
            app.ENGINE._plan_gate(bad)
        )  # stopped plan: gate no longer applies, tick will not post
        app.ENGINE.plan_tick()
        self.assertEqual(len(self.sent), sent)

    def test_post_if_due_does_not_send_when_check_fails(self):
        self.approved()
        bad = app.plan_get()["drafts"]["normal"].replace("EASYPAISA ONLY", "JAZZCASH")
        start = Mock(return_value=True)
        with (
            patch.dict(
                app.ENGINE.h,
                {
                    "start_job": start,
                    "caption_variant": lambda i: bad,
                    "busy": lambda: False,
                    "last_sent": lambda: {},
                },
            ),
            patch.object(app.ENGINE, "blocked", return_value=False),
            patch.object(app.ENGINE, "quiet_now", return_value=False),
            patch.object(app.ENGINE, "check_post_results"),
        ):
            app.ENGINE._post_if_due()
        start.assert_not_called()

    def test_live_amount_change_rounds_up_and_keeps_sending(self):
        self.approved()
        self.left = 23500  # part-donation: not a multiple of 2,000
        fresh = app.ENGINE.h["caption_now"](app.plan_get()["drafts"]["normal"])
        self.assertIn("12 kind people", fresh)
        self.assertTrue(app.ENGINE._plan_gate(app.plan_get()["drafts"]["normal"]))

    def test_work_hours_apply_only_while_a_plan_runs(self):
        with patch.object(T, "in_work_hours", return_value=False):
            self.assertFalse(app.ENGINE.quiet_now())  # no plan: unchanged behaviour
            self.approved()
            self.assertTrue(app.ENGINE.quiet_now())
            self.assertTrue(app.ENGINE._dm_quiet())
        with patch.object(T, "in_work_hours", return_value=True):
            self.assertFalse(app.ENGINE.quiet_now())
        app.plan_mutate({"action": "stop"})
        with patch.object(T, "in_work_hours", return_value=False):
            self.assertFalse(app.ENGINE.quiet_now())

    def test_status_text_outside_hours_does_not_crash(self):
        self.approved()
        app.ENGINE.s["quiet"] = None
        with patch.object(T, "in_work_hours", return_value=False):
            self.assertIn("Outside sending hours", app.ENGINE.status()["now"])

    def test_duplicate_and_invalid_actions_are_refused(self):
        self.approved()
        with self.assertRaises(ValueError):
            app.plan_mutate({"action": "create", "facts": FACTS})  # one running plan at a time
        with self.assertRaises(ValueError):
            app.plan_mutate({"action": "approve"})
        with self.assertRaises(ValueError):
            app.plan_mutate({"action": "clear"})
        with self.assertRaises(ValueError):
            app.plan_mutate({"action": "explode"})

    def test_case_change_and_completion(self):
        self.approved()
        with patch.object(app, "active_case_name", return_value="Another child"):
            app.ENGINE.plan_tick()
        self.assertEqual(app.plan_get()["state"], "stopped")
        self.assertTrue(any("no longer matches" in t for _, t in self.sent))
        app.plan_mutate({"action": "resume"})
        app.ENGINE.plan_tick()
        self.assertEqual(app.plan_get()["state"], "normal")
        self.left = 0
        app.ENGINE.plan_tick()
        self.assertEqual(app.plan_get()["state"], "done")

    def test_failed_apply_stops_with_reason_and_resume_retries(self):
        app.plan_mutate({"action": "create", "facts": FACTS})
        with patch.dict(
            app.ENGINE.h, {"plan_apply": lambda text, plan: "the message failed a check"}
        ):
            app.plan_mutate({"action": "approve"})
        self.assertEqual(app.plan_get()["state"], "stopped")
        self.assertEqual(app.plan_get()["reason"], "the message failed a check")
        view = app.plan_mutate({"action": "resume"})  # check passes now
        self.assertEqual(view["plan"]["state"], "normal")

    def test_storage_failure_changes_nothing(self):
        app.plan_mutate({"action": "create", "facts": FACTS})
        before = app.plan_get()
        with patch.object(
            app,
            "plan_put",
            side_effect=ValueError("Persistent storage is unavailable. Nothing was changed."),
        ):
            with self.assertRaises(ValueError):
                app.plan_mutate({"action": "approve"})
        self.assertEqual(app.plan_get(), before)

    def test_dm_gap_is_seven_minutes_between_messages(self):
        self.assertEqual(T.DM_GAP_SECONDS, 420)
        self.assertEqual(T.DM_BATCH, 5)
        sleeps, sent = [], []
        people = [("92300000000%d" % i, "Ali", "donor") for i in range(3)]
        h = {
            "outreach": lambda caps: people,
            "read_left": lambda: 22000,
            "enabled": lambda: True,
            "on_hold": lambda: False,
            "already_dmed": lambda d: False,
            "dm_text": lambda n, t: "hello",
            "send_dm": lambda p, t, d: sent.append(p) or {"code": "SUCCESS"},
            "note_dm": lambda p: None,
            "send_text": lambda *a: None,
            "owner_jid": lambda: "x@s.whatsapp.net",
        }
        with patch.dict(app.ENGINE.h, h), patch("autopilot.time.sleep", lambda s: sleeps.append(s)):
            app.ENGINE.s.update(dm_enabled=True, dms_today=0, dm_daily=30, dm_new=True)
            app.ENGINE.dm_batch()
        self.assertEqual(len(sent), 3)
        self.assertEqual(sleeps, [420, 420, 420])


if __name__ == "__main__":
    unittest.main()
