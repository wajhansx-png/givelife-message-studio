"""One page to run the whole case. Stubbed transport: nothing is ever sent."""

import datetime, time, unittest
from unittest.mock import patch

from test_manual_sends import app
import test_auto_controls as tac
import case_run

QUESTION = "Can you share this case in your class group?"


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Base(tac.Base):
    def setUp(self):
        super().setUp()
        self.cr = self.h.caserun
        self.h.set_follow_up(QUESTION)
        self.fast = patch.object(self.h.jobs, "_gap", return_value=0)
        self.shared, self.replies, self.share_result = [], {}, [None]

        def send_custom(body):
            outcome = self.share_result.pop(0) if self.share_result else None
            if isinstance(outcome, Exception):
                raise outcome
            self.shared.append((body["phone"], body["message"], body.get("poster")))
            return outcome or {
                "code": "SUCCESS",
                "results": {"message_id": "x%d" % len(self.shared)},
            }

        for name, fake in (
            ("send_custom", send_custom),
            ("recent_chats", lambda: [(p, "Person") for p in self.replies]),
            ("scan_messages", lambda jid: list(self.replies.get(jid.split("@")[0], []))),
        ):
            patcher = patch.object(app, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.cr._stop_engines)
        self.addCleanup(app.set_auto, False)

    def people(self, tops=2, giki=1):
        """tops Top donors, giki GIKI Top donors; returns (top ids, giki ids)."""
        out = []
        for i in range(tops + giki):
            row = self.h.book.add("Donor %02d" % i, "923001250%03d" % i)["donor"]
            self.h.book.update(row["id"], important=True)
            self.h.book.update(row["id"], top_donor=True)
            out.append(row["id"])
        data = self.h.book._load()
        for rec in data["records"]:
            if rec["id"] in out[tops:]:
                rec["group"] = "GIKI"
        self.h.book._save(data)
        return out[:tops], out[tops:]

    def phone(self, did):
        return self.h.book.resolve(did)["phone"]

    def approve(self):
        summary = self.cr.summary()
        self.assertEqual(summary["blockers"], [], summary["blockers"])
        return self.cr.start(summary["token"])

    def tick_until(self, check, n=300):
        for _ in range(n):
            self.cr.tick()
            if check():
                return True
            time.sleep(0.02)
        return False

    def state(self):
        return self.cr._read()

    def reply(self, did, text, mid):
        self.replies.setdefault(self.phone(did), []).append(
            {
                "id": mid,
                "content": text,
                "is_from_me": False,
                "timestamp": stamp(),
                "media_type": "",
            }
        )


class Plan(Base):
    def test_the_defaults_match_the_plan_and_nothing_starts(self):
        self.people()
        v = self.cr.view()
        self.assertEqual(
            (v["status"], [r["key"] for r in v["rows"]]), ("idle", list(case_run.ROWS))
        )
        plan = self.state()["plan"]
        self.assertEqual(plan["group"]["every_minutes"], 45)
        self.assertEqual(
            (plan["top"]["gap_minutes"], plan["top"]["batch_size"], plan["top"]["rest_minutes"]),
            (5, 10, 20),
        )
        self.assertFalse(plan["important"]["enabled"])
        self.assertEqual((self.h.jobs.export_jobs()["jobs"], self.sent, self.shared), ([], [], []))
        self.assertFalse(app.auto_on())

    def test_saving_settings_never_starts_sending_and_bad_values_are_refused(self):
        top, _ = self.people()
        self.cr.set_plan({"group": {"every_minutes": 30}, "top": {"gap_minutes": 4}})
        self.assertEqual(self.state()["plan"]["group"]["every_minutes"], 30)
        self.assertEqual((self.h.jobs.export_jobs()["jobs"], self.sent), ([], []))
        self.assertFalse(app.auto_on())
        for bad in ({"group": {"every_minutes": 5}}, {"top": {"gap_minutes": 11}}, {"nope": {}}):
            with self.assertRaises(ValueError):
                self.cr.set_plan(bad)
        with self.assertRaises(ValueError):  # Important stays off until people are chosen
            self.cr.set_plan({"important": {"enabled": True}})
        self.cr.set_plan({"important": {"ids": top, "enabled": True}})
        self.assertTrue(self.state()["plan"]["important"]["enabled"])

    def test_one_person_in_several_lists_gets_one_request_and_giki_is_split_out(self):
        top, giki = self.people(tops=3, giki=2)
        done = self.h.book.add("Done Already", "923001259999")["donor"]
        self.h.book.update(done["id"], important=True)
        self.h.book.update(done["id"], top_donor=True)
        self.h.book.delivery(done["id"], "Sent")
        self.cr.set_plan({"important": {"ids": [top[0], top[1]], "enabled": True}})
        aud = self.cr.audiences(self.state()["plan"])
        self.assertEqual(
            sorted(aud["top"]), sorted(top)
        )  # Top comes first: Important adds nobody twice
        self.assertEqual(aud["important"], [])
        self.assertEqual(sorted(aud["giki"]), sorted(giki))
        self.assertNotIn(done["id"], aud["top"] + aud["giki"])  # already contacted


class Run(Base):
    def test_start_needs_the_exact_summary_and_runs_only_the_approved_people(self):
        top, giki = self.people(2, 1)
        with self.assertRaises(ValueError):
            self.cr.start("not-the-token")
        self.assertEqual((self.h.jobs.export_jobs()["jobs"], app.auto_on()), ([], False))
        self.approve()
        self.addCleanup(self.stop_everything)
        late = self.h.book.add("Late Donor", "923001258888")["donor"]  # added after approval
        self.h.book.update(late["id"], important=True)
        self.h.book.update(late["id"], top_donor=True)
        self.assertTrue(app.auto_on())
        self.assertEqual(app.ENGINE.summary()["pace_override"][0], 45)
        self.assertTrue(self.tick_until(lambda: len(self.sent) >= 1))
        job = self.h.jobs.export_jobs()["jobs"][-1]
        self.assertEqual(
            (job["owner"], job["origin"], sorted(job["ids"])), ("case_top", "case_run", sorted(top))
        )
        self.assertNotIn(late["id"], job["ids"])
        self.assertEqual(
            len(self.h.jobs.export_jobs()["jobs"]), 1
        )  # GIKI waits: one DM queue at a time
        again = self.cr.start("anything")  # pressing Start twice never starts a second run
        self.assertEqual(again["status"], "running")
        self.assertEqual(len(self.h.jobs.export_jobs()["jobs"]), 1)

    def test_rows_run_one_after_another_and_giki_sends_the_question(self):
        top, giki = self.people(2, 1)
        self.fast.start()
        self.addCleanup(self.fast.stop)
        self.approve()
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.tick_until(lambda: self.state()["rows"]["giki"]["state"] == "running"))
        jobs = self.h.jobs.export_jobs()["jobs"]
        self.assertEqual([j["owner"] for j in jobs], ["case_top", "case_giki"])
        self.assertEqual((jobs[1]["ids"], jobs[1]["follow_up"]), (giki, QUESTION))
        self.assertEqual(self.state()["rows"]["top"]["state"], "done")

    def test_pause_all_stops_everything_and_resume_never_repeats_anyone(self):
        self.people(3, 0)
        self.approve()
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.tick_until(lambda: len(self.sent) >= 1))
        self.cr.pause()
        self.assertTrue(self.wait(lambda: not self.h.jobs.active))
        self.assertEqual((self.state()["status"], app.auto_on()), ("paused", False))
        sent_before = len(self.sent)
        self.cr.tick()
        time.sleep(0.2)
        self.assertEqual(len(self.sent), sent_before)  # nothing leaves while paused
        self.fast.start()
        self.addCleanup(self.fast.stop)
        self.cr.resume()
        self.assertTrue(self.tick_until(lambda: self.state()["rows"]["top"]["state"] == "done"))
        phones = [m["phone"] for m in self.sent]
        self.assertEqual(len(phones), len(set(phones)), "a person was messaged twice")
        self.assertEqual(len(phones), 3)

    def test_a_changed_plan_while_paused_needs_a_new_approval(self):
        self.people(2, 0)
        self.approve()
        self.addCleanup(self.stop_everything)
        with self.assertRaises(ValueError):
            self.cr.set_plan({"group": {"every_minutes": 60}})  # running: pause first
        self.cr.pause()
        self.cr.set_plan({"group": {"every_minutes": 60}})
        self.assertEqual((self.state()["status"], self.state()["approved"]), ("idle", None))

    def test_finish_asks_first_stops_everything_and_keeps_history(self):
        top, giki = self.people(1, 1)
        self.approve()
        self.addCleanup(self.stop_everything)
        ask = self.cr.finish(False)
        self.assertTrue(ask["confirm"])
        self.assertEqual(self.state()["status"], "running")  # asking changes nothing
        self.cr.finish(True)
        self.assertTrue(self.wait(lambda: not self.h.jobs.active))
        st = self.state()
        self.assertEqual(st["status"], "finished")
        self.assertFalse(app.auto_on())
        self.assertTrue(st["log"])
        with self.assertRaises(ValueError):
            self.cr.start(self.cr.summary()["token"])

    def test_a_restart_keeps_the_run_and_never_starts_a_second_job(self):
        self.people(2, 0)
        self.approve()
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.tick_until(lambda: len(self.sent) >= 1))
        revived = case_run.CaseRun(app, self.h)
        self.assertEqual(revived.view()["status"], "running")
        for _ in range(5):
            revived.tick()
        self.assertEqual(len(self.h.jobs.export_jobs()["jobs"]), 1)

    def test_a_wording_change_after_approval_is_shown_to_the_owner(self):
        self.people(2, 1)
        self.approve()
        self.addCleanup(self.stop_everything)
        changed = lambda: [i for i in self.cr.view()["needs"] if i["type"] == "changed"]  # noqa: E731
        self.assertEqual(changed(), [])
        self.h.set_follow_up("A different question about sharing?")
        items = changed()
        self.assertEqual(len(items), 1)
        self.assertIn("share question", items[0]["title"])
        self.cr.need_act(items[0]["id"], "review")
        self.assertEqual(changed(), [])

    def test_a_disconnected_whatsapp_is_on_the_needs_you_list(self):
        self.people(2, 0)
        self.approve()
        self.addCleanup(self.stop_everything)
        self.status_connected = False
        items = {i["id"]: i for i in self.cr.view()["needs"]}
        self.assertEqual(items["whatsapp"]["actions"], ["reconnect"])


class Giki(Base):
    def giki_waiting(self):
        top, giki = self.people(1, 1)
        self.fast.start()
        self.addCleanup(self.fast.stop)
        self.approve()
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.tick_until(lambda: self.state()["giki"].get(self.phone(giki[0]))))
        return giki[0]

    def test_a_clear_yes_sends_the_poster_then_the_screenshot_request_then_the_share_request(self):
        did = self.giki_waiting()
        self.assertEqual(self.state()["giki"][self.phone(did)]["step"], "waiting")
        self.tick_until(lambda: False, 8)
        self.assertEqual(self.shared, [])  # silence is never agreement: nothing is sent
        self.reply(did, "Yes sure", "m1")
        self.assertTrue(self.tick_until(lambda: len(self.shared) >= 3))
        poster, shot, share = self.shared[:3]
        self.assertTrue(poster[2])  # poster with the GiveLife Group caption
        self.assertEqual(poster[1], app.get_message("group")["text"])
        self.assertIn("screenshot to 03097458815 after you donate", shot[1])
        self.assertIn("please share both messages above", share[1])
        self.assertTrue(share[1].startswith(("Donor", "Bhai", "Sister")))
        self.tick_until(lambda: False, 10)
        self.assertEqual(len(self.shared), 3)  # never repeated
        self.assertEqual(self.state()["giki"][self.phone(did)]["step"], "shared")

    def test_an_unclear_reply_waits_for_the_owner_who_can_mark_agreed(self):
        did = self.giki_waiting()
        self.reply(did, "I will think and tell you, what is this about?", "m2")
        self.assertTrue(
            self.tick_until(lambda: self.state()["giki"][self.phone(did)]["step"] == "needs")
        )
        items = [i for i in self.cr.view()["needs"] if i["type"] == "giki_reply"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["actions"], ["agreed", "not_agreed", "reply"])
        self.tick_until(lambda: False, 8)
        self.assertEqual(self.shared, [])
        self.cr.need_act(items[0]["id"], "agreed")
        self.assertTrue(self.tick_until(lambda: len(self.shared) >= 1))

    def test_a_clear_no_stops_and_a_send_that_may_have_gone_is_never_retried(self):
        did = self.giki_waiting()
        self.reply(did, "No", "m3")
        self.assertTrue(
            self.tick_until(lambda: self.state()["giki"][self.phone(did)]["step"] == "declined")
        )
        self.assertEqual(self.shared, [])
        self.cr.need_act(next(iter(self.state()["needs"]), "x"), "dismiss") if self.state()[
            "needs"
        ] else None
        self.cr.giki_decide(self.phone(did), "agreed")
        self.share_result[:] = [{"code": "UNCERTAIN"}]
        self.assertTrue(
            self.tick_until(lambda: self.state()["giki"][self.phone(did)]["step"] == "uncertain")
        )
        count = len(self.shared)
        self.tick_until(lambda: False, 10)
        self.assertEqual(len(self.shared), count)  # no automatic retry
        self.assertTrue(
            [i for i in self.cr.view()["needs"] if i["id"].startswith("giki-uncertain")]
        )

    def test_a_refused_send_is_tried_again_and_goes_out_once(self):
        did = self.giki_waiting()
        self.reply(did, "ok", "m4")
        self.share_result[:] = [ValueError("Wait at least 3 minutes between DMs.")]
        self.assertTrue(self.tick_until(lambda: len(self.shared) >= 1))
        self.assertEqual(self.shared[0][1], app.get_message("group")["text"])
        self.assertEqual(self.state()["giki"][self.phone(did)]["shared"], 1)


class Money(Base):
    def claim(self):
        top, _ = self.people(2, 0)
        self.fast.start()
        self.addCleanup(self.fast.stop)
        self.approve()
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.tick_until(lambda: len(self.sent) >= 1))
        sent_to = {m["phone"] for m in self.sent}
        did = next(i for i in top if self.phone(i) in sent_to)
        self.reply(did, "I have donated, sending the screenshot", "pay1")
        self.assertTrue(
            self.tick_until(lambda: [i for i in self.cr.view()["needs"] if i["type"] == "payment"])
        )
        return did, [i for i in self.cr.view()["needs"] if i["type"] == "payment"][0]

    def test_a_claim_is_only_a_claim_until_the_owner_confirms_and_it_counts_once(self):
        did, item = self.claim()
        self.assertEqual(item["actions"], ["check_payment", "not_paid"])
        left, row = app.read_left(), self.h.book.resolve(did)
        self.assertFalse(row.get("donated"))  # a claim is not money
        self.cr.need_act(item["id"], "check_payment", amount=2000)
        self.assertEqual(app.read_left(), left - 2000)
        row = self.h.book.resolve(did)
        self.assertEqual((row["donated"], row["amount"]), (True, 2000))
        with self.assertRaises(ValueError):
            self.cr.need_act(item["id"], "check_payment", amount=2000)  # no duplicate entry
        self.cr.tick()
        self.assertEqual(app.read_left(), left - 2000)
        thanks = [i for i in self.cr.view()["needs"] if i["type"] == "thank"]
        self.assertEqual(len(thanks), 1)  # the thank-you is prepared, not sent
        self.assertIn("JazakAllah", thanks[0]["text"])
        self.tick_until(lambda: False, 6)
        self.assertEqual(
            [i for i in self.cr.view()["needs"] if i["type"] == "payment"], []
        )  # seen once

    def test_a_bad_amount_changes_nothing(self):
        did, item = self.claim()
        left = app.read_left()
        for bad in (0, -5, "2000", None, True):
            with self.assertRaises(ValueError):
                self.cr.need_act(item["id"], "check_payment", amount=bad)
        self.assertEqual(app.read_left(), left)


class Amount(Base):
    def test_the_amount_left_changes_from_the_page_and_bad_values_change_nothing(self):
        self.cr.act({"action": "left", "left": 18000})
        self.assertEqual(app.read_left(), 18000)
        self.assertEqual(self.cr.view()["case"]["left"], 18000)
        for bad in (-1, "5000", None, True, 10**9):
            with self.assertRaises(ValueError):
                self.cr.act({"action": "left", "left": bad})
        self.assertEqual(app.read_left(), 18000)
        self.assertTrue(any(c["current"] for c in self.cr.view()["cases"]))


class Words(unittest.TestCase):
    def test_only_a_short_clear_yes_or_no_counts(self):
        for text in ("Yes", "yes sure", "ok", "Haan ji", "Jee zaroor"):
            self.assertEqual(case_run.agreement(text), "agree", text)
        for text in ("No", "nahi", "Not now"):
            self.assertEqual(case_run.agreement(text), "decline", text)
        for text in ("", "maybe", "Yes but not today", "who are you?", "ok " + "x" * 80):
            self.assertEqual(case_run.agreement(text), "unclear", text)


if __name__ == "__main__":
    unittest.main()
