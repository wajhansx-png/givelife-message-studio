"""Agent logic, table-driven: each row is one rule from autopilot/rules/case_plan/team_rules.
A fake clock and fake WhatsApp hooks: nothing real is sent and nothing waits."""

import datetime, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import autopilot, case_plan, rules, team_rules

PKT = datetime.timezone(datetime.timedelta(hours=5))
T0 = datetime.datetime(2026, 11, 5, 14, 0, tzinfo=PKT).timestamp()  # 2 PM Pakistan time


class Clock:
    t = T0


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        Clock.t = T0
        self.ps = [
            patch.object(autopilot, "now", lambda: Clock.t),
            patch.object(autopilot, "pkt", lambda: datetime.datetime.fromtimestamp(Clock.t, PKT)),
            patch.object(autopilot.time, "sleep", lambda s: None),
            patch.object(
                team_rules, "pkt_now", lambda: datetime.datetime.fromtimestamp(Clock.t, PKT)
            ),
        ]
        for p in self.ps:
            p.start()
        self.sent, self.jobs, self.texts, self.dms, self.logs = [], [], [], [], []
        self.left, self.last, self.plan = 50000, {}, None
        self.h = {
            "DATA": Path(self.tmp.name),
            "store_get": lambda k: None,
            "persist": lambda *a: None,
            "log": self.logs.append,
            "owner_jid": lambda: "owner",
            "send_text": lambda jid, t: self.texts.append((jid, t)),
            "enabled": lambda: True,
            "on_hold": lambda: False,
            "read_left": lambda: self.left,
            "busy": lambda: False,
            "groups": lambda: ["main", "fiverr", "upwork"],
            "last_sent": lambda: self.last,
            "caption_variant": lambda i: f"caption {i}",
            "variant_pool": lambda: "b",
            "variant_count": lambda: 10,
            "start_job": lambda keys, cap: self.jobs.append((list(keys), cap)) or True,
            "goal": lambda: 100000,
            "milestone_text": lambda d, l: "milestone",
            "update_text": lambda c, l: "update",
            "share_text": lambda: "share",
            "plan_get": lambda: self.plan,
            "plan_put": lambda p: setattr(self, "plan", p),
            "case_name": lambda: "Case A",
            "plan_apply": lambda text, plan: "",
            "outreach": lambda caps: self.people,
            "already_dmed": lambda d: d in self.dmed,
            "dm_text": lambda name, tier: f"hi {name}",
            "send_dm": lambda phone, text, d: self.dms.append(phone) or {"code": "SUCCESS"},
            "note_dm": lambda p: None,
        }
        self.people, self.dmed = [], set()
        self.e = autopilot.Engine(self.h)
        self.e.s["rules"] = []

    def tearDown(self):
        for p in self.ps:
            p.stop()
        self.tmp.cleanup()

    def mins_without_money(self, m):
        self.e.s["last_money"] = Clock.t - m * 60


class Pace(Base):
    def test_ladder(self):
        for m, lvl, main, free in [
            (0, "L1", 20, 30),
            (39, "L1", 20, 30),
            (40, "L2", 15, 30),
            (89, "L2", 15, 30),
            (90, "L3", 15, 30),
            (359, "L3", 15, 30),
            (360, "L4", 30, 30),
        ]:
            with self.subTest(m=m):
                self.mins_without_money(m)
                self.assertEqual(self.e.level()[:3], (lvl, main, free))

    def test_gap_order(self):
        e = self.e
        self.assertEqual(e.gap_for("fiverr", 99), 30)  # freelance fixed at 30
        self.assertEqual(e.gap_for("main", 20), 20)  # 2 PM: normal hour
        Clock.t = T0 + 13 * 3600  # 3 AM: night, slower
        self.assertEqual(e.gap_for("main", 20), 30)
        Clock.t = T0 + 6 * 3600  # 8 PM: busy hour, faster but never under 15
        self.mins_without_money(0)
        self.assertEqual(e.gap_for("main", 15), 15)
        e.add_rule({"kind": "gap", "group": "free", "minutes": 45})
        self.assertEqual(e.gap_for("upwork", 30), 45)  # typed rule wins
        self.assertEqual(e.gap_for("main", 20), 17)  # "free" never touches main
        self.mins_without_money(400)
        Clock.t = T0 + 6 * 3600
        self.assertEqual(e.gap_for("main", 30), 30)  # L4 never speeds up


class Rules(Base):
    def test_parser(self):
        for text, kind, group in [
            ("post in main every 20 min", "gap", "main"),
            ("post in main every 5 min", "gap", "main"),
            ("no posting 2am to 7am", "quiet", "all"),
            ("dont post at night", "quiet", "all"),
            ("never post in fiverr at night", "quiet", "fiverr"),
            ("pause fiverr for 2 hours", "pause", "fiverr"),
            ("max 10 posts a day in main", "cap", "main"),
            ("always use a polite tone", "note", None),
            ("send to main at 9pm", "schedule", None),
            ("Hi", None, None),
            ("post every 20 min", None, None),
        ]:
            with self.subTest(text=text):
                r, _ = rules.parse(text, now=T0)
                self.assertEqual(r and r["kind"], kind)
                if group:
                    self.assertEqual(r["group"], group)
        self.assertEqual(rules.parse("post in main every 5 min")[0]["minutes"], 15)

    def test_replace_block_and_unpause(self):
        e = self.e
        e.add_rule({"kind": "gap", "group": "main", "minutes": 20})
        e.add_rule({"kind": "gap", "group": "main", "minutes": 40})
        self.assertEqual([r["minutes"] for r in e.rules() if r["kind"] == "gap"], [40])
        r = e.add_rule(rules.parse("pause fiverr for 2 hours", now=T0)[0])
        self.assertTrue(e.blocked("fiverr"))
        e.delete_rule(r["id"])
        self.assertFalse(e.blocked("fiverr"))
        e.add_rule({"kind": "quiet", "group": "main", "start": 13, "end": 15})
        self.assertTrue(e.blocked("main"))
        e.add_rule({"kind": "cap", "group": "upwork", "per_day": 2})
        e.s["posts_by"] = {"upwork": 2}
        self.assertTrue(e.blocked("upwork"))
        self.assertEqual({r["kind"] for r in e.rule_list()}, {"gap", "quiet", "cap"})
        ids = [r["id"] for r in e.rules()]
        self.assertEqual(len(ids), len(set(ids)))  # same-millisecond rules still get unique ids


class Poster(Base):
    def test_posts_only_due_unblocked_groups(self):
        self.last = {"main": Clock.t - 19 * 60, "fiverr": Clock.t - 31 * 60}
        self.e.add_rule({"kind": "pause", "group": "upwork", "until": Clock.t + 60})
        self.e.post_if_due()
        self.assertEqual(self.jobs[0][0], ["fiverr"])
        self.assertEqual(self.e.s["posts_by"], {"fiverr": 1})

    def test_hold_and_busy_stop_posting(self):
        for key in ("on_hold", "busy"):
            with self.subTest(key=key), patch.dict(self.h, {key: lambda: True}):
                self.e.post_if_due()
        self.assertEqual(self.jobs, [])

    def test_three_failures_pause_group_six_hours(self):
        self.h["last_results"] = lambda: [("fiverr", "ERROR", "not a member")]
        for _ in range(3):
            self.e.s["pending_post"] = 1
            self.e.check_post_results()
        self.assertEqual(self.e.s["paused"]["fiverr"], Clock.t + 6 * 3600)

    def test_variant_not_reused_within_last_two(self):
        self.h["variant_count"] = lambda: 3
        for _ in range(20):
            self.e.s["learn"]["recent"] = [[0, 0], [1, 1]]
            self.assertEqual(self.e._pick_variant(), (2, 2))

    def test_money_update_milestone_share(self):
        e = self.e
        e.s["left_seen"] = 50000
        self.left = 48000
        with patch.object(e, "post_if_due"), patch.object(e, "dm_if_due"):
            for name in (
                "scan_group_replies",
                "scan_dm_replies",
                "scan_saved_chats",
                "scan_reply_setup",
                "volunteer_step",
                "daily_report",
                "_owner_todo",
                "run_followups",
            ):
                setattr(e, name, lambda *a: None)
            self.h["wa_ok"] = lambda: True
            e.tick()
        self.assertEqual(e.s["last_money"], Clock.t)
        self.assertIn((["main"], "update"), self.jobs)  # Rs. 2,000 came: stress update
        self.assertIn((["main"], "milestone"), self.jobs)  # 52% of goal reached
        self.assertEqual(e.s["milestones"], [0.25, 0.5])
        self.jobs.clear()
        e.milestone_if_due(48000)
        self.assertEqual(self.jobs, [])  # each milestone once
        e.s["update_due"] = {"came": 2000, "at": Clock.t - 5401}
        e.update_if_due(48000)
        self.assertIsNone(e.s["update_due"])  # dropped after 90 min
        self.assertEqual(self.jobs, [])
        e.s["day"] = "d"
        self.mins_without_money(30)
        e.share_if_due()
        self.assertEqual(self.jobs, [])  # not slow: no share
        self.mins_without_money(100)
        e.share_if_due()
        e.share_if_due()
        self.assertEqual(self.jobs, [(["main"], "share")])  # once a day

    def test_completed_case_stops_everything(self):
        self.left = 0
        with patch.object(self.e, "post_if_due") as post:
            self.e.tick()
        post.assert_not_called()
        self.assertEqual(self.jobs + self.texts, [])


class DMs(Base):
    def setUp(self):
        super().setUp()
        self.people = [(f"9230000000{i:02d}", f"P{i}", "donor") for i in range(9)]

    def test_only_when_slow_daytime_spaced(self):
        e = self.e
        for mins, hour_offset, ok in [(30, 0, False), (100, 0, True), (100, 9 * 3600, False)]:
            with self.subTest(mins=mins, hour=hour_offset):
                Clock.t = T0 + hour_offset
                e.s["last_dm_batch"] = 0
                self.mins_without_money(mins)
                with patch.object(autopilot.threading, "Thread") as th:
                    e.dm_if_due()
                self.assertEqual(th.called, ok)
        e.s["last_dm_batch"] = Clock.t - 44 * 60
        with patch.object(autopilot.threading, "Thread") as th:
            e.dm_if_due()
        th.assert_not_called()  # 45 min between batches

    def test_batch_limits(self):
        e = self.e
        e.dm_batch()
        self.assertEqual(len(self.dms), 5)  # max 5 per batch
        self.people = [("923111111111", "M", "member"), ("923111111112", "S", "saved")]
        self.dms.clear()
        e.dm_batch()
        self.assertEqual(self.dms, [])  # "DM new people" off
        self.dmed = {autopilot.hashlib.sha256(b"923000000000@s.whatsapp.net").hexdigest()}
        self.people = [("923000000000", "P", "donor")]
        e.dm_batch()
        self.assertEqual(self.dms, [])  # never a second DM
        e.s["dms_by_tier"] = {"donor": 15}
        self.people = [("923000000099", "Q", "donor")]
        e.dm_batch()
        self.assertEqual(self.dms, [])  # donor cap 15

    def test_stops_on_failure_missing_bank_goal(self):
        for hook, val in [
            ("send_dm", lambda p, t, d: self.dms.append(p) or {"code": "ERROR"}),
            ("dm_text", lambda n, t: (_ for _ in ()).throw(ValueError("no bank"))),
        ]:
            with self.subTest(hook=hook), patch.dict(self.h, {hook: val}):
                self.dms.clear()
                self.e.s["notified"] = {}
                self.e.dm_batch()
                self.assertLessEqual(len(self.dms), 1)
                self.assertTrue(self.texts)
        self.dms.clear()
        self.left = 0
        self.e.dm_batch()
        self.assertEqual(self.dms, [])


class CasePlan(Base):
    def test_states(self):
        c = {"state": "ready", "case": "Case A"}
        for left, mins, name, want in [
            (5000, 10, "Case A", "normal"),
            (5000, 89, "Case A", "normal"),
            (5000, 90, "Case A", "slow"),
            (0, 10, "Case A", "done"),
            (5000, 10, "Case B", "stopped"),
        ]:
            with self.subTest(left=left, mins=mins, name=name):
                self.assertEqual(case_plan.advance(c, left, mins, name), want)
        self.assertEqual(case_plan.advance({"state": "draft"}, 1, 1, "x"), "draft")

    def test_work_hours_only_while_plan_runs(self):
        self.plan = {"state": "normal"}
        self.h["plan_active"] = lambda: True
        for hh, mm, ok in [
            (11, 59, False),
            (12, 0, True),
            (15, 29, True),
            (15, 30, False),
            (18, 0, True),
            (22, 29, True),
            (22, 30, False),
        ]:
            with self.subTest(t=f"{hh}:{mm}"):
                Clock.t = datetime.datetime(2026, 11, 5, hh, mm, tzinfo=PKT).timestamp()
                self.assertEqual(self.e.quiet_now(), not ok)

    def test_failed_check_stops_and_never_sends(self):
        self.plan = {"state": "normal", "facts": {}}
        with patch.object(autopilot.message_rules, "problems", return_value=["wrong amount"]):
            self.assertFalse(self.e._plan_gate("caption"))
        self.assertEqual(self.plan["state"], "stopped")


class Loop(Base):
    def test_auto_off_runs_nothing(self):
        calls = []
        self.h["enabled"] = lambda: False
        with (
            patch.object(self.e, "tick", lambda: calls.append(1)),
            patch.object(autopilot.time, "sleep", side_effect=[None, StopIteration]),
        ):
            with self.assertRaises(StopIteration):
                self.e._loop()
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
