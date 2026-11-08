"""Reports > Auto: three controls over the existing engines. Stubbed transport: nothing is ever sent."""

import hashlib, time, unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
import auto_controls as ac

IMPORTANT = "important"


class Base(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self.h = app.donors()
        self.h.jobs.import_jobs({"jobs": []})
        self.h.book._save({"version": 1, "records": []})
        self.h.jobs.active = None
        self.h.jobs.stop.clear()
        self.c = ac.AutoControls(app)
        app.set_auto(False)
        app.CAMPAIGN.update(running=False, stop=False)
        self.fast = patch.object(
            self.h.jobs, "_gap", return_value=0
        )  # tests never wait out real gaps
        # A real wait would last minutes; the stop switch still ends it at once.

    tearDown = fixture.SendTests.tearDown

    def donors(self, n, important=None):
        ids = []
        for i in range(n):
            row = self.h.book.add("Synthetic %02d" % i, "923001230%03d" % i)["donor"]
            if important is None or i < important:
                self.h.book.update(row["id"], important=True)
            ids.append(row["id"])
        return ids

    def wait(self, check, seconds=6):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if check():
                return True
            time.sleep(0.02)
        return False

    def view(self, which):
        return self.c.view()["controls"][which]

    def stop_everything(self):
        self.h.jobs.cancel()
        self.wait(lambda: not self.h.jobs.active)

    def addCleanup_stop(self):
        self.addCleanup(self.stop_everything)


class Defaults(Base):
    def test_everything_is_off_and_nothing_starts_by_itself(self):
        self.donors(5)
        view = self.c.view()
        for which in ac.CONTROLS:
            self.assertFalse(view["controls"][which]["on"], which)
            self.assertEqual(view["controls"][which]["state"], "OFF")
            self.assertTrue(view["controls"][which]["fields"])
        self.assertEqual(self.h.jobs.export_jobs().get("jobs"), [])
        self.assertFalse(app.auto_on())
        self.assertEqual(self.sent, [])

    def test_cards_are_named_for_what_they_do(self):
        controls = self.c.view()["controls"]
        self.assertEqual(controls[ac.GROUP]["title"], "Group Auto")
        self.assertEqual(controls[ac.DONOR_DM]["title"], "DM Important Donors")
        self.assertEqual(controls[IMPORTANT]["title"], "Important Donors Auto")
        for scope, name in ac.SCOPE_TITLES.items():  # the name follows "Who to message"
            view = self.c.edit(ac.DONOR_DM, {"scope": scope})
            self.assertEqual(view["controls"][ac.DONOR_DM]["title"], name, scope)
        self.assertEqual(set(ac.SCOPE_TITLES), set(ac.SCOPES))


class GroupAuto(Base):
    def test_switches_the_existing_auto_engine(self):
        view = self.c.set(ac.GROUP, True)
        self.assertTrue(view["controls"][ac.GROUP]["on"])
        self.assertTrue(app.auto_on())
        self.assertFalse(self.c.set(ac.GROUP, False)["controls"][ac.GROUP]["on"])
        self.assertFalse(app.auto_on())

    def test_a_finished_case_cannot_be_switched_on(self):
        app.set_left(0)
        with self.assertRaises(ValueError):
            self.c.set(ac.GROUP, True)
        self.assertFalse(app.auto_on())

    def test_pace_can_be_edited_while_on(self):
        self.c.set(ac.GROUP, True)
        view = self.c.edit(ac.GROUP, {"main_every": 30, "freelance_every": 45})
        self.assertEqual(
            view["controls"][ac.GROUP]["settings"], {"main_every": 30, "freelance_every": 45}
        )
        self.assertTrue(app.auto_on())  # still on, never restarted
        with self.assertRaises(ValueError):
            self.c.edit(ac.GROUP, {"main_every": 2})


class ImportantDonors(Base):
    def test_starts_the_existing_engine_with_the_required_plan(self):
        self.donors(14)
        done = self.h.book.add("Already Done", "923009999999")["donor"]
        self.h.book.update(done["id"], important=True)
        self.h.book.delivery(done["id"], "Sent")  # contacted before: skipped by default
        usual = {
            "gap_seconds": 200,
            "chunk": 7,
            "rests": [900.0],
            "poster": True,
            "skip_contacted": True,
        }
        app.STORE.put(self.h.PREFS_KEY, dict(usual))
        self.c.set(
            IMPORTANT, True, {"count": 15}
        )  # asks for more than are left once the contacted one is skipped
        self.addCleanup(self.stop_everything)
        self.assertEqual(
            self.h.prefs(), usual
        )  # the owner's "usual way" is not rewritten by an Auto run
        job = self.h.jobs.export_jobs()["jobs"][-1]
        self.assertEqual(job["owner"], IMPORTANT)
        self.assertEqual((job["scope"], job["chunk"], job["gap_seconds"]), ("important", 10, 480.0))
        self.assertEqual(job["jitter"], {"min": -15.0, "max": 15.0})
        self.assertEqual(job["total"], 14)  # 15 asked, 14 not yet contacted
        self.assertEqual(job["batches"], 2)  # batches of 10
        self.assertEqual(job["rests"], [900.0])  # the existing pauses between batches
        self.assertNotIn(done["id"], job["ids"])  # already contacted: skipped by default
        self.assertTrue(self.wait(lambda: len(self.sent) >= 1))  # starts at once, no waiting
        view = self.view(IMPORTANT)
        self.assertTrue(view["on"])
        self.assertEqual((view["recipients"], view["sent"]), (14, 1))
        self.assertEqual(view["pending"], 13)
        self.assertTrue(view["next_at"] and view["next_at"] > time.time() + 400)

    def test_the_owner_chooses_how_many(self):
        self.donors(14)
        self.c.set(IMPORTANT, True, {"count": 5})
        self.addCleanup(self.stop_everything)
        job = self.h.jobs.export_jobs()["jobs"][-1]
        self.assertEqual((job["total"], job["batches"]), (5, 1))

    def test_the_gap_is_eight_minutes_give_or_take_fifteen_seconds(self):
        self.donors(3)
        self.c.set(IMPORTANT, True, {"count": 3})
        self.addCleanup(self.stop_everything)
        job = self.h.jobs.export_jobs()["jobs"][-1]
        gaps = [self.h.jobs._gap(job) for _ in range(300)]
        self.assertGreaterEqual(min(gaps), 480 - 15)
        self.assertLessEqual(max(gaps), 480 + 15)
        self.assertGreater(max(gaps) - min(gaps), 20)  # genuinely random, not a fixed number

    def test_opt_outs_and_unusable_numbers_are_never_messaged(self):
        ids = self.donors(4)
        phone = self.h.book.resolve(ids[0])["phone"]
        digest = hashlib.sha256((phone + "@s.whatsapp.net").encode()).hexdigest()
        app.STORE.put("optout_" + digest, {"at": time.time()})
        self.c.set(IMPORTANT, True, {"count": 4})
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.wait(lambda: len(self.sent) >= 1))
        self.stop_everything()
        self.assertNotIn(phone, [x["phone"].split("@")[0] for x in self.sent])

    def test_including_contacted_donors_is_an_explicit_choice(self):
        ids = self.donors(3)
        self.h.book.delivery(ids[0], "Sent")
        self.c.set(IMPORTANT, True, {"count": 3, "include_contacted": True})
        self.addCleanup(self.stop_everything)
        self.assertEqual(self.h.jobs.export_jobs()["jobs"][-1]["total"], 3)

    def test_follow_up_is_sent_after_a_confirmed_dm_and_only_when_saved(self):
        self.donors(2)
        with self.assertRaises(ValueError):  # ticked, but nothing saved
            self.c.set(IMPORTANT, True, {"count": 2, "follow_up": True})
        self.assertEqual(self.h.jobs.export_jobs()["jobs"], [])
        self.h.set_follow_up("Thank you for reading, Brother.")

        def send(
            body,
        ):  # the DM engine's own send step: record the poster DM and the follow-up in order
            self.sent.append(
                {"phone": body["phone"], "text": body["message"], "poster": body.get("poster")}
            )
            return {"code": "SUCCESS", "results": {"message_id": "fake-%d" % len(self.sent)}}

        patcher = patch.object(self.h.jobs, "send", side_effect=send)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.c.set(IMPORTANT, True, {"count": 2, "follow_up": True})
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.wait(lambda: len(self.sent) >= 2))
        self.assertEqual(
            self.h.jobs.export_jobs()["jobs"][-1]["follow_up"], "Thank you for reading, Brother."
        )
        self.assertTrue(self.sent[0]["poster"])  # the DM first
        self.assertIn(
            "Thank you for reading", self.sent[1]["text"]
        )  # then the follow-up, same person
        self.assertFalse(self.sent[1]["poster"])
        self.assertEqual(self.sent[0]["phone"], self.sent[1]["phone"])

    def test_a_finished_case_cannot_start_dms(self):
        self.donors(2)
        app.set_left(0)
        with self.assertRaises(ValueError):
            self.c.set(IMPORTANT, True, {"count": 2})
        self.assertEqual(self.sent, [])


class NoOverlap(Base):
    def test_two_dm_controls_never_run_together(self):
        self.donors(6)
        self.c.set(IMPORTANT, True, {"count": 3})
        self.addCleanup(self.stop_everything)
        with self.assertRaises(ValueError) as caught:
            self.c.set(ac.DONOR_DM, True)
        self.assertIn("Important Donors Auto is sending now", str(caught.exception))
        self.assertEqual(len(self.h.jobs.export_jobs()["jobs"]), 1)
        self.assertTrue(self.wait(lambda: self.sent))
        self.assertEqual(len({x["phone"] for x in self.sent}), len(self.sent))  # nobody twice

    def test_the_overlap_message_uses_the_dm_card_name(self):
        self.donors(6)
        self.c.set(ac.DONOR_DM, True)
        self.addCleanup(self.stop_everything)
        with self.assertRaises(ValueError) as caught:
            self.c.set(IMPORTANT, True, {"count": 3})
        self.assertIn("DM Important Donors is sending now", str(caught.exception))
        self.assertEqual(len(self.h.jobs.export_jobs()["jobs"]), 1)

    def test_pressing_on_twice_starts_one_batch(self):
        self.donors(4)
        self.c.set(IMPORTANT, True, {"count": 4})
        self.addCleanup(self.stop_everything)
        self.c.set(IMPORTANT, True)
        self.assertEqual(len(self.h.jobs.export_jobs()["jobs"]), 1)

    def test_a_batch_started_by_hand_or_a_dm_list_blocks_the_controls(self):
        self.donors(4)
        app.CAMPAIGN["running"] = True
        with self.assertRaises(ValueError):
            self.c.set(IMPORTANT, True, {"count": 2})
        app.CAMPAIGN["running"] = False
        self.h.start_batch(scope="important", limit=2, chunk=1, gap_seconds=480)
        self.addCleanup(self.stop_everything)
        with self.assertRaises(ValueError) as caught:
            self.c.set(ac.DONOR_DM, True)
        self.assertIn("donor DM batch that you started", str(caught.exception))

    def test_ai_auto_dms_running_blocks_the_controls(self):
        self.donors(2)
        with patch.object(app.ENGINE, "dm_running", True):
            with self.assertRaises(ValueError):
                self.c.set(IMPORTANT, True, {"count": 2})


class SwitchOff(Base):
    def test_off_stops_safely_and_on_again_never_repeats_anyone(self):
        self.donors(6)
        self.c.set(IMPORTANT, True, {"count": 6})
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.wait(lambda: len(self.sent) >= 1))
        self.c.set(IMPORTANT, False)
        self.assertTrue(self.wait(lambda: not self.h.jobs.active))
        view = self.view(IMPORTANT)
        self.assertFalse(view["on"])
        self.assertEqual(view["state"], "OFF")
        self.assertGreaterEqual(view["pending"], 1)  # the rest is kept
        self.assertIsNone(self.h.jobs.recover())  # an owner stop is never resumed by a restart
        first = {x["phone"] for x in self.sent}
        self.c.set(IMPORTANT, True, {"count": 6})
        self.assertTrue(self.wait(lambda: len(self.sent) >= len(first) + 1))
        self.stop_everything()
        phones = [x["phone"] for x in self.sent]
        self.assertEqual(len(phones), len(set(phones)))  # nobody got a second DM


class ContinuedBatch(Base):
    def test_a_batch_that_carries_on_an_earlier_one_is_tracked_under_its_own_id(self):
        # Root cause found by the Reports tests: a loop variable reused the batch id, so after "carrying on"
        # the engine's active marker held a donor id. OFF and live settings then missed the running batch.
        self.donors(6)
        self.c.set(IMPORTANT, True, {"count": 4})
        self.assertTrue(self.wait(lambda: self.sent))
        self.c.set(IMPORTANT, False)
        self.assertTrue(self.wait(lambda: not self.h.jobs.active))
        self.c.set(ac.DONOR_DM, True)
        self.addCleanup(self.stop_everything)
        job = self.h.jobs.export_jobs()["jobs"][-1]
        self.assertEqual(self.h.jobs.active, job["id"])
        self.c.edit(ac.DONOR_DM, {"gap_minutes": 3})  # live settings reach it
        self.assertEqual(self.h.jobs.export_jobs()["jobs"][-1]["gap_seconds"], 180.0)
        self.c.set(ac.DONOR_DM, False)  # and OFF really stops it
        self.assertTrue(self.wait(lambda: not self.h.jobs.active))
        self.assertEqual(self.h.jobs.export_jobs()["jobs"][-1]["state"], "Stopped")


class Restart(Base):
    def test_a_restart_keeps_the_control_on_and_the_resumed_batch_keeps_its_name(self):
        self.donors(5)
        with patch("donor_delivery.threading.Thread"):  # the batch exists but its worker never runs
            self.c.set(IMPORTANT, True, {"count": 5})
        self.h.jobs.active = None  # a new process has no worker
        self.h.jobs.boot = "after-restart"
        self.h.jobs.status()  # the old process's batch is marked Interrupted
        view = self.view(IMPORTANT)
        self.assertTrue(view["on"])
        self.assertIn("restarted", view["note"])
        with self.assertRaises(ValueError):  # the other control cannot grab the queue meanwhile
            self.c.set(ac.DONOR_DM, True)
        with patch("donor_delivery.threading.Thread"):
            resumed = self.h.jobs.recover()
        self.assertIsNotNone(resumed)
        self.assertEqual(self.h.jobs.export_jobs()["jobs"][-1]["owner"], IMPORTANT)
        self.assertTrue(self.view(IMPORTANT)["on"])
        self.assertEqual(self.sent, [])  # recovery itself sent nothing

    def test_off_while_waiting_after_a_restart_cancels_the_resume(self):
        self.donors(3)
        with patch("donor_delivery.threading.Thread"):
            self.c.set(IMPORTANT, True, {"count": 3})
        self.h.jobs.active = None
        self.h.jobs.boot = "after-restart"
        self.h.jobs.status()
        self.c.set(IMPORTANT, False)
        self.assertFalse(self.view(IMPORTANT)["on"])
        self.assertIsNone(self.h.jobs.recover())


class LiveEdit(Base):
    def test_new_settings_reach_the_running_batch_without_a_restart_or_a_repeat(self):
        self.donors(6)
        self.c.set(IMPORTANT, True, {"count": 6})
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.wait(lambda: len(self.sent) >= 1))
        before = self.h.jobs.export_jobs()["jobs"][-1]
        sent_before = list(self.sent)
        self.h.set_follow_up("A short thank you.")
        view = self.c.edit(IMPORTANT, {"gap_minutes": 5, "follow_up": True})
        jobs = self.h.jobs.export_jobs()["jobs"]
        self.assertEqual(len(jobs), 1)  # still the same batch
        self.assertEqual(jobs[-1]["id"], before["id"])
        self.assertEqual(jobs[-1]["gap_seconds"], 300.0)
        self.assertEqual(jobs[-1]["follow_up"], "A short thank you.")
        self.assertGreater(jobs[-1]["settings_revision"], before.get("settings_revision", 0))
        self.assertTrue(view["controls"][IMPORTANT]["on"])
        self.assertEqual(view["controls"][IMPORTANT]["settings"]["gap_minutes"], 5.0)
        self.assertEqual(self.sent[: len(sent_before)], sent_before)  # nothing re-sent
        self.c.edit(IMPORTANT, {"follow_up": False})
        self.assertIsNone(self.h.jobs.export_jobs()["jobs"][-1]["follow_up"])

    def test_invalid_edits_change_nothing(self):
        self.donors(3)
        self.c.set(IMPORTANT, True, {"count": 3})
        self.addCleanup(self.stop_everything)
        job = self.h.jobs.export_jobs()["jobs"][-1]
        for bad in ({"gap_minutes": 99}, {"count": 0}, {"follow_up": "yes"}, {"nonsense": 1}, {}):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.c.edit(IMPORTANT, bad)
        self.assertEqual(self.h.jobs.export_jobs()["jobs"][-1]["gap_seconds"], job["gap_seconds"])
        self.assertEqual(self.c.settings(IMPORTANT)["count"], 3)

    def test_edits_for_the_next_run_are_saved_while_off(self):
        view = self.c.edit(IMPORTANT, {"count": 7})
        self.assertEqual(view["controls"][IMPORTANT]["settings"]["count"], 7)
        self.assertFalse(view["controls"][IMPORTANT]["on"])
        self.assertEqual(self.h.jobs.export_jobs()["jobs"], [])


class DonorDmAuto(Base):
    def test_uses_the_owners_usual_settings_and_leaves_them_unchanged(self):
        self.donors(3)
        usual = {
            "gap_seconds": 200,
            "chunk": 7,
            "rests": [900.0],
            "poster": True,
            "skip_contacted": True,
        }
        app.STORE.put(self.h.PREFS_KEY, dict(usual))
        self.c.set(ac.DONOR_DM, True)
        self.addCleanup(self.stop_everything)
        job = self.h.jobs.export_jobs()["jobs"][-1]
        self.assertEqual(
            (job["owner"], job["scope"], job["chunk"], job["gap_seconds"]),
            (ac.DONOR_DM, "important", 7, 200.0),
        )
        self.assertEqual(job["rests"], [900.0])
        self.assertEqual(self.h.prefs(), usual)  # an Auto run never rewrites "how I usually do it"
        self.assertTrue(self.wait(lambda: self.sent))


if __name__ == "__main__":
    unittest.main()
