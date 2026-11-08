"""Donors Auto toggle: every state, edit, crash, restart, gap and follow-up. Fake transport only; nothing real is sent."""

import copy, tempfile, threading, time, unittest

from donor_auto import DonorAuto, ORIGIN
from donor_book import DonorBook
from donor_delivery import DonorDelivery
from donor_integration import DonorIntegration


class Store:
    def __init__(self):
        self.data = {}

    def get(self, k, default=None):
        return copy.deepcopy(self.data.get(k, default))

    def put(self, k, v):
        self.data[k] = copy.deepcopy(v)


class AutoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store()
        self.book = DonorBook(self.tmp.name, self.store)
        self.sent = []
        self.replies = []
        self.alerts = []
        self.closed = False
        self.held = False
        self.blocked = set()
        self.on_send = None
        self.follow_text = "{name}, please do consider helping."
        self.jobs = self.make_jobs()
        self.auto = self.make_auto(self.jobs)

    def tearDown(self):
        self.jobs.stop.set()
        time.sleep(0.05)
        self.tmp.cleanup()

    def donor(self, name, phone, top=True):
        ident = self.book.add(name, phone)["donor"]["id"]
        if top:
            self.book.update(ident, important=True)
            self.book.update(ident, top_donor=True)
        return ident

    def send(self, body):
        self.sent.append(body)
        if self.on_send:
            self.on_send(body, len(self.sent))
        return self.replies.pop(0) if self.replies else {"code": "SUCCESS"}

    def make_jobs(self):
        jobs = DonorDelivery(
            self.tmp.name,
            self.store,
            self.book,
            self.send,
            lambda: "Case caption",
            lambda: True,
            lambda: self.held,
            lambda phone: phone not in self.blocked,
            lambda name: (name, "Brother"),
            case_closed=lambda: self.closed,
        )
        jobs._gap = lambda j: 0  # real gaps are minutes; tests only check the numbers
        jobs._rest = lambda j, b: 0
        return jobs

    def make_auto(self, jobs):
        return DonorAuto(
            self.store,
            jobs,
            lambda wanted: self.follow_text if wanted else None,
            self.alerts.append,
        )

    def wait_for(self, check, seconds=8):
        end = time.time() + seconds
        while time.time() < end:
            if check():
                return True
            time.sleep(0.02)
        return False

    def last(self, jobs=None):
        return (jobs or self.jobs).export_jobs()["jobs"][-1]

    def finish(self, jobs=None):
        jobs = jobs or self.jobs
        self.assertTrue(
            self.wait_for(
                lambda: (
                    jobs.status()["state"] in ("Completed", "Stopped", "Nothing sent")
                    and not jobs.active
                )
            ),
            jobs.status(),
        )

    def age_sends(self, seconds=3600):
        """Pretend the DMs sent so far went out `seconds` ago, so the real 5-minute gap has already passed."""
        data = self.jobs.export_jobs()
        for job in data["jobs"]:
            for r in job.get("receipts", []):
                if r.get("state") == "Sent":
                    r["time"] = r["time"] - seconds
                    self.book.delivery(r["id"], "Sent", r["time"])
        self.jobs.import_jobs(data)

    def phones(self, kind="phone"):
        return [b["phone"] for b in self.sent if b.get("kind") != "owner_text"]


class SwitchOn(AutoCase):
    def test_on_messages_only_uncontacted_top_donors_with_the_planned_pace(self):
        a = self.donor("Ali", "923001110001")
        b = self.donor("Bilal", "923001110002")
        self.donor("Chand", "923001110003", top=False)
        d = self.donor("Danish", "923001110004")
        self.book.delivery(d, "Sent", time.time() - 99)
        self.auto.set(True)
        self.finish()
        job = self.last()
        self.assertEqual(
            (job["scope"], job["gap_seconds"], job["chunk"], job["rests"], job["origin"]),
            ("top", 300, 10, [900.0], ORIGIN),
        )
        self.assertEqual(job["jitter"], {"min": -15.0, "max": 15.0})
        self.assertEqual(job["ids"], [a, b])
        self.assertEqual(sorted(self.phones()), ["923001110001", "923001110002"])

    def test_gap_is_five_minutes_give_or_take_fifteen_seconds(self):
        jobs = DonorDelivery.__new__(DonorDelivery)
        job = {"gap_seconds": 300, "origin": ORIGIN, "jitter": {"min": -15, "max": 15}}
        values = [DonorDelivery._gap(jobs, job) for _ in range(300)]
        self.assertTrue(all(285 <= v <= 315 for v in values), (min(values), max(values)))
        self.assertGreater(max(values) - min(values), 10)  # really random
        manual = {
            "gap_seconds": 300,
            "jitter": {"min": -15, "max": 15},
        }  # manual batches keep their old pacing
        self.assertTrue(all(285 <= DonorDelivery._gap(jobs, manual) <= 435 for _ in range(100)))

    def test_ten_per_batch_with_a_fifteen_minute_rest(self):
        for n in range(12):
            self.donor("D%d" % n, "92300222%04d" % n)
        rests = []
        self.jobs._rest = lambda j, b: rests.append((b, j["rests"])) or 0
        self.auto.set(True)
        self.finish()
        self.assertEqual(len(self.phones()), 12)
        self.assertEqual(rests[0], (1, [900.0]))  # one rest, after the first ten
        self.assertEqual(len(rests), 1)

    def test_nobody_to_message_is_a_clear_refusal(self):
        self.donor("Chand", "923001110003", top=False)
        with self.assertRaises(ValueError):
            self.auto.set(True)
        self.assertFalse(self.auto.status()["enabled"])

    def test_refused_while_held_or_another_batch_runs_or_case_closed(self):
        self.donor("Ali", "923001110001")
        self.held = True
        with self.assertRaises(ValueError):
            self.auto.set(True)
        self.held = False
        self.closed = True
        with self.assertRaises(ValueError):
            self.auto.set(True)
        self.closed = False
        self.jobs.active = "other"
        with self.assertRaises(ValueError):
            self.auto.set(True)
        self.assertFalse(self.auto.status()["enabled"])
        self.assertEqual(self.sent, [])

    def test_pressing_on_twice_never_starts_a_second_batch(self):
        self.donor("Ali", "923001110001")
        self.on_send = lambda body, n: time.sleep(0.2)
        self.auto.set(True)
        self.auto.set(True)
        self.finish()
        self.assertEqual(len(self.phones()), 1)
        self.assertEqual(len(self.jobs.export_jobs()["jobs"]), 1)


class Ending(AutoCase):
    def test_finished_batch_turns_itself_off_and_never_restarts_the_audience(self):
        self.donor("Ali", "923001110001")
        self.auto.set(True)
        self.finish()
        self.auto.tick()
        st = self.auto.status()
        self.assertFalse(st["enabled"])
        self.assertTrue(st["finished"])
        self.assertEqual(self.alerts, [])  # finishing needs nothing from the owner
        self.donor("Zain", "923001110009")  # a new Top donor appears later
        self.auto.tick()
        time.sleep(0.1)
        self.assertEqual(len(self.phones()), 1)  # nothing starts without the owner pressing On
        self.assertEqual(len(self.jobs.export_jobs()["jobs"]), 1)

    def test_off_stops_future_sends_and_on_again_continues_without_repeats(self):
        for n in range(4):
            self.donor("D%d" % n, "92300333000%d" % n)
        threading.Event()

        def on_send(body, n):
            if n == 2:
                self.auto.set(False)  # owner switches Auto off during the 2nd DM

        self.on_send = on_send
        self.auto.set(True)
        self.finish()
        self.assertEqual(len(self.phones()), 2)  # the one in flight finished, nothing after it
        self.assertFalse(self.auto.status()["enabled"])
        self.on_send = None
        self.age_sends()
        self.auto.set(True)
        self.finish()
        got = self.phones()
        self.assertEqual(len(got), 4)
        self.assertEqual(len(set(got)), 4, "nobody was messaged twice")

    def test_switching_on_again_still_waits_out_the_gap_since_the_last_dm(self):
        for n in range(3):
            self.donor("D%d" % n, "92300334000%d" % n)
        self.on_send = lambda body, n: n == 1 and self.auto.set(False)
        self.auto.set(True)
        self.finish()
        self.on_send = None
        self.auto.set(True)  # straight away: the 5-minute gap has not passed
        time.sleep(0.3)
        self.assertEqual(len(self.phones()), 1)
        job = self.last()
        self.assertGreater(job["hold_until"] - time.time(), 250)
        # The resumed batch is tracked by its own id, so it can be edited live and switched off again.
        self.assertEqual(self.jobs.active, job["id"])
        self.auto.set_options(poster=False)
        self.assertFalse(self.last()["poster"])
        self.auto.set(False)
        self.finish()
        self.assertEqual(self.last()["state"], "Stopped")
        self.assertEqual(len(self.phones()), 1)  # nothing was sent while it waited

    def test_uncertain_is_never_repeated_even_after_switching_on_again(self):
        a = self.donor("Ali", "923001110001")
        self.donor("Bilal", "923001110002")
        self.replies = [{"code": "TIMEOUT"}]
        self.auto.set(True)
        self.finish()
        self.auto.tick()
        self.assertEqual(self.book.resolve(a)["delivery"], "Uncertain")
        with self.assertRaises(ValueError):
            self.auto.set(True)  # Bilal is contacted, Ali is unconfirmed: nobody left to ask
        self.assertEqual(len(self.phones()), 2)

    def test_three_unconfirmed_in_a_row_stops_unsafe_sending_and_alerts_once(self):
        for n in range(5):
            self.donor("D%d" % n, "92300444000%d" % n)
        self.replies = [{"code": "TIMEOUT"}] * 5
        self.auto.set(True)
        self.finish()
        self.auto.tick()
        self.assertEqual(len(self.phones()), 3)
        self.assertFalse(self.auto.status()["enabled"])
        self.assertEqual(len(self.alerts), 1)
        self.assertIn("not confirmed", self.alerts[0])

    def test_case_completed_stops_quietly(self):
        for n in range(3):
            self.donor("D%d" % n, "92300555000%d" % n)

        def on_send(body, n):
            self.closed = True  # the last rupee arrives while DMs are going out

        self.on_send = on_send
        self.auto.set(True)
        self.finish()
        self.auto.tick()
        self.assertEqual(len(self.phones()), 1)
        self.assertFalse(self.auto.status()["enabled"])
        self.assertEqual(self.alerts, [])

    def test_opted_out_donor_is_skipped_not_messaged(self):
        self.donor("Ali", "923001110001")
        self.donor("Bilal", "923001110002")
        self.blocked = {"923001110001"}
        self.auto.set(True)
        self.finish()
        self.assertEqual(self.phones(), ["923001110002"])

    def test_stop_dms_button_switches_auto_off(self):
        self.donor("Ali", "923001110001")
        self.auto.set(True)
        self.finish()
        hub = DonorIntegration.__new__(DonorIntegration)
        self.auto._save(enabled=True)
        hub.auto = self.auto
        self.assertTrue(hub.auto.status()["enabled"])
        self.auto.disable("Auto is off: DMs were stopped.")
        self.assertFalse(self.auto.status()["enabled"])


class FollowUp(AutoCase):
    def kinds(self):
        return [("follow" if b["kind"] == "owner_text" else "dm") for b in self.sent]

    def test_checked_sends_the_saved_follow_up_after_each_confirmed_dm(self):
        self.donor("Ali", "923001110001")
        self.donor("Bilal", "923001110002")
        self.auto.set(True, follow_up=True)
        self.finish()
        self.assertEqual(self.kinds(), ["dm", "follow", "dm", "follow"])
        self.assertEqual(self.sent[1]["message"], "Ali Bhai, please do consider helping.")

    def test_unchecked_sends_no_follow_up(self):
        self.donor("Ali", "923001110001")
        self.auto.set(True, follow_up=False)
        self.finish()
        self.assertEqual(self.kinds(), ["dm"])

    def test_no_follow_up_after_an_unconfirmed_dm(self):
        self.donor("Ali", "923001110001")
        self.replies = [{"code": "TIMEOUT"}]
        self.auto.set(True, follow_up=True)
        self.finish()
        self.assertEqual(self.kinds(), ["dm"])

    def test_checked_without_a_saved_follow_up_is_refused(self):
        self.donor("Ali", "923001110001")
        self.follow_text = None

        def follow_for(wanted):
            if wanted and not self.follow_text:
                raise ValueError("Write the follow-up in Messages first.")
            return self.follow_text

        auto = DonorAuto(self.store, self.jobs, follow_for)
        with self.assertRaises(ValueError):
            auto.set(True, follow_up=True)
        self.assertEqual(self.sent, [])


class LiveEditing(AutoCase):
    def test_changes_apply_to_future_sends_without_restarting(self):
        for n in range(3):
            self.donor("D%d" % n, "92300666000%d" % n)
        gate, entered = threading.Event(), threading.Event()

        def on_send(body, n):
            if n == 1:
                entered.set()
                gate.wait(5)

        self.on_send = on_send
        self.auto.set(True, follow_up=False, poster=True)
        self.assertTrue(entered.wait(5))
        before = self.last()["id"]
        self.auto.set_options(follow_up=True, poster=False)  # live: follow-up on, poster off
        self.jobs.configure(
            before, {"gap_seconds": 120, "chunk": 5, "rests": [600], "jitter": None}
        )
        gate.set()
        self.finish()
        job = self.last()
        self.assertEqual(job["id"], before, "the same batch kept running")
        self.assertEqual((job["gap_seconds"], job["chunk"], job["rests"]), (120, 5, [600]))
        self.assertEqual(job["batches"], 1)
        self.assertEqual(job["settings_revision"], 2)
        dms = [b for b in self.sent if b["kind"] != "owner_text"]
        self.assertEqual([b["poster"] for b in dms], [True, False, False])
        self.assertEqual(len([b for b in self.sent if b["kind"] == "owner_text"]), 3)
        self.assertEqual(len(set(self.phones())), 3)

    def test_follow_up_can_be_switched_off_mid_batch(self):
        for n in range(3):
            self.donor("D%d" % n, "92300777000%d" % n)

        def on_send(body, n):
            if n == 2:  # after the 1st DM and its follow-up
                self.auto.set_options(follow_up=False)

        self.on_send = on_send
        self.auto.set(True, follow_up=True)
        self.finish()
        self.assertEqual(
            [b["kind"] == "owner_text" for b in self.sent], [False, True, False, False]
        )

    def test_options_are_ignored_when_auto_is_off(self):
        self.assertEqual(self.auto.set_options(follow_up=True), {"applied": False})

    def test_configure_job_turns_the_follow_up_switch_into_the_saved_text(self):
        self.donor("Ali", "923001110001")
        self.jobs.start("top", 300, run=False, skip_contacted=False)
        job = self.last()["id"]
        hub = DonorIntegration.__new__(DonorIntegration)
        hub.jobs = self.jobs
        hub._follow_up_for = lambda wanted: "Saved follow-up" if wanted else None
        hub.configure_job(job, {"follow_up": True})
        self.assertEqual(self.last()["follow_up"], "Saved follow-up")
        hub.configure_job(job, {"follow_up": False})
        self.assertFalse(self.last()["follow_up"])
        with self.assertRaises(ValueError):
            self.jobs.configure(job, {"follow_up": "   "})


class RestartsAndCrashes(AutoCase):
    def test_restart_resumes_the_same_batch_and_never_repeats_anyone(self):
        ids = [self.donor("D%d" % n, "92300888000%d" % n) for n in range(4)]
        self.jobs._run = lambda j: None  # the process "dies" right after the batch was created
        self.auto.set(True)
        job = self.last()
        self.assertEqual(job["state"], "Starting")
        sent_at = time.time() - 3600
        self.book.delivery(ids[0], "Sent", sent_at)  # D0 was delivered just before the crash
        self.jobs.import_jobs(
            {
                "jobs": [
                    {
                        **job,
                        "state": "Sending",
                        "sent": 1,
                        "receipts": [
                            {"id": ids[0], "name": "D0", "state": "Sent", "time": sent_at}
                        ],
                    }
                ]
            }
        )
        reborn = self.make_jobs()  # new process, same database
        auto = self.make_auto(reborn)
        self.assertEqual(reborn.status()["state"], "Interrupted")
        self.assertTrue(auto.status()["enabled"], "the switch itself survives the restart")
        auto.tick()
        self.finish(reborn)
        got = self.phones()
        self.assertEqual(len(got), 3)
        self.assertNotIn("923008880000", got)
        self.assertEqual(len(set(got)), 3)
        auto.tick()
        self.assertTrue(auto.status()["finished"])

    def test_unsure_donor_caught_mid_send_is_not_sent_again_after_a_crash(self):
        ids = [self.donor("D%d" % n, "92300999000%d" % n) for n in range(2)]
        self.jobs._run = lambda j: None
        self.auto.set(True)
        job = self.last()
        self.book.delivery(ids[0], "Sending")
        self.jobs.import_jobs({"jobs": [{**job, "state": "Sending"}]})
        reborn = self.make_jobs()
        auto = self.make_auto(reborn)
        auto.tick()
        self.finish(reborn)
        self.assertEqual(self.phones(), ["923009990001"])

    def test_off_stays_off_after_a_restart(self):
        self.donor("Ali", "923001110001")
        self.auto.set(True)
        self.finish()
        self.auto.tick()
        reborn = self.make_jobs()
        auto = self.make_auto(reborn)
        auto.tick()
        time.sleep(0.1)
        self.assertFalse(auto.status()["enabled"])
        self.assertEqual(len(self.phones()), 1)


if __name__ == "__main__":
    unittest.main()
