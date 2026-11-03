"""Resume scheduling uses synthetic donors, persisted state and no WhatsApp transport."""

import datetime as dt
import unittest, threading, time
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
from donor_integration import DonorIntegration


class ResumeScheduleTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        app.donors().jobs.import_jobs({"jobs": []})

    tearDown = fixture.SendTests.tearDown
    NOW = 1800000000

    def stamp(self, offset=600):
        return dt.datetime.fromtimestamp(
            self.NOW + offset, dt.timezone(dt.timedelta(hours=5))
        ).strftime("%Y-%m-%dT%H:%M")

    def test_future_resume_stays_paused_survives_restart_and_runs_once(self):
        hub = app.donors()
        app.ENGINE.s.update(dm_enabled=True, dm_daily=25)
        hub.pause_personal()
        with patch("donor_integration.time.time", return_value=self.NOW):
            hub.schedule_resume(self.stamp(), "future")
        self.assertTrue(hub.paused)
        self.assertFalse(app.ENGINE.s["dm_enabled"])
        restored = DonorIntegration(app)
        self.assertEqual(restored.resume_status()["state"], "Pending")
        restored.tick_resume(self.NOW + 599)
        self.assertTrue(restored.paused)
        restored.tick_resume(self.NOW + 600)
        self.assertFalse(restored.paused)
        self.assertTrue(app.ENGINE.s["dm_enabled"])
        self.assertEqual(app.ENGINE.s["dm_daily"], 25)
        with patch.object(restored, "resume_all") as again:
            restored.tick_resume(self.NOW + 700)
            again.assert_not_called()

    def test_stop_cancels_a_pending_resume(self):
        hub = app.donors()
        hub.pause_personal()
        with patch("donor_integration.time.time", return_value=self.NOW):
            hub.schedule_resume(self.stamp(), "cancel")
        hub.pause_personal()
        hub.tick_resume(self.NOW + 700)
        self.assertTrue(hub.paused)
        self.assertEqual(hub.resume_status()["state"], "Cancelled")

    def test_invalid_or_past_time_keeps_dms_paused(self):
        hub = app.donors()
        hub.pause_personal()
        for value in ("bad", "2026-02-30T12:00", self.stamp(-60), "2030-01-01T12:00Z"):
            with (
                self.subTest(value=value),
                patch("donor_integration.time.time", return_value=self.NOW),
                self.assertRaises(ValueError),
            ):
                hub.schedule_resume(value, "bad")
        self.assertTrue(hub.paused)

    def test_resume_keeps_full_batch_setup_and_only_original_remaining_people(self):
        hub = app.donors()
        [hub.book.add("Donor " + str(i), "92300123%04d" % i)["donor"]["id"] for i in range(7)]
        with (
            patch.object(app, "wa_ok", return_value=True),
            patch.object(hub.jobs, "connected", return_value=True),
        ):
            job = hub.start_batch(
                scope="all",
                gap_seconds=180,
                chunk=2,
                rests=[120, 300],
                jitter={"min": -10, "max": 15},
                poster=False,
                limit=6,
                run=False,
            )["job"]
            raw = hub.jobs.export_jobs()["jobs"][-1]
            original = list(raw["ids"])
            hub.pause_personal()
            hub.jobs._update(
                job["id"],
                state="Stopped",
                receipts=[
                    {"id": original[0], "state": "Sent"},
                    {"id": original[1], "state": "Uncertain"},
                ],
            )
            hub.jobs.active = None
            start = hub.jobs.start
            with patch.object(hub.jobs, "start", side_effect=lambda **kw: start(**kw, run=False)):
                hub.resume_all()
            resumed = hub.jobs.export_jobs()["jobs"][-1]
        self.assertEqual(resumed["ids"], original[2:])
        self.assertEqual(resumed["gap_seconds"], 180)
        self.assertEqual(resumed["chunk"], 2)
        self.assertEqual(resumed["rests"], [120, 300])
        self.assertEqual(resumed["jitter"], {"min": -10, "max": 15})
        self.assertFalse(resumed["poster"])

    def test_stopped_bulk_batch_resumes_with_its_people_message_and_names(self):
        hub = app.donors()
        # Unique numbers: a number another test already DMed is (correctly) treated as already sent.
        base = 9230050000 + int(time.time() * 1000) % 90000
        ids = [hub.book.add("Donor " + str(i), str(base * 10 + i))["donor"]["id"] for i in range(4)]
        names = {i: ("Donor", "Brother") for i in ids}
        with (
            patch.object(app, "wa_ok", return_value=True),
            patch.object(hub.jobs, "connected", return_value=True),
        ):
            job = hub.jobs.start(
                scope="selected",
                ids=ids,
                personal_names=names,
                custom_template="Hi {name}, thanks.",
                limit=4,
                gap_seconds=180,
                poster=False,
                run=False,
                request_id="bulk-resume",
            )["job"]
            hub.pause_personal()
            hub.jobs._update(job["id"], state="Stopped", receipts=[{"id": ids[0], "state": "Sent"}])
            hub.jobs.active = None
            start = hub.jobs.start
            with patch.object(hub.jobs, "start", side_effect=lambda **kw: start(**kw, run=False)):
                reply = hub.resume_all()
        resumed = hub.jobs.export_jobs()["jobs"][-1]
        self.assertNotEqual(resumed["id"], job["id"])
        self.assertEqual(resumed["ids"], ids[1:])
        self.assertEqual(resumed["scope"], "selected")
        self.assertEqual(resumed["custom_template"], "Hi {name}, thanks.")
        self.assertEqual(resumed["gap_seconds"], 180)
        self.assertFalse(resumed["poster"])
        self.assertIn("continues", reply["reply"])

    def test_resume_refuses_while_stop_is_still_finishing(self):
        hub = app.donors()
        hub.pause_personal()
        hub.jobs.active = "inflight"
        with self.assertRaisesRegex(ValueError, "stopping"):
            hub.resume_all()
        self.assertTrue(hub.paused)
        hub.jobs.active = None

    def test_a_second_schedule_replaces_the_first_and_retries_do_not_duplicate(self):
        hub = app.donors()
        hub.pause_personal()
        with patch("donor_integration.time.time", return_value=self.NOW):
            first = hub.schedule_resume(self.stamp(600), "one")["resume"]["id"]
            second = hub.schedule_resume(self.stamp(1200), "two")["resume"]["id"]
            self.assertNotEqual(first, second)
            self.assertEqual(hub.schedule_resume(self.stamp(1200), "two")["resume"]["id"], second)
        hub.tick_resume(self.NOW + 600)
        self.assertTrue(hub.paused)
        hub.tick_resume(self.NOW + 1200)
        self.assertFalse(hub.paused)

    def test_schedule_does_not_replay_dispatch_after_a_restart(self):
        hub = app.donors()
        hub.pause_personal()
        app.STORE.put(hub.RESUME_KEY, {"state": "Dispatching", "due": self.NOW})
        with patch.object(hub, "resume_all") as resume:
            hub.tick_resume(self.NOW + 1)
            resume.assert_not_called()
        self.assertEqual(hub.resume_status()["state"], "Uncertain")
        self.assertTrue(hub.paused)

    def test_starting_a_new_batch_cancels_an_older_scheduled_resume(self):
        hub = app.donors()
        hub.pause_personal()
        with patch("donor_integration.time.time", return_value=self.NOW):
            hub.schedule_resume(self.stamp(), "old")
        hub.resume_personal()
        hub.tick_resume(self.NOW + 601)
        self.assertEqual(hub.resume_status()["state"], "Cancelled")

    def test_last_inflight_dm_completes_before_resume_and_auto_is_still_restored(self):
        hub = app.donors()
        app.ENGINE.s.update(dm_enabled=True, dm_daily=25)
        hub.book.add("Final donor", "923009991234")["donor"]["id"]
        with patch.object(hub.jobs, "connected", return_value=True):
            job = hub.start_batch(scope="all", limit=1, run=False)["job"]
            raw = hub.jobs.export_jobs()["jobs"][-1]
            hub.pause_personal()
            hub.jobs._update(
                job["id"], state="Completed", receipts=[{"id": raw["ids"][0], "state": "Sent"}]
            )
            hub.jobs.active = None
            with patch.object(hub.jobs, "start") as send:
                hub.resume_all()
                send.assert_not_called()
        self.assertFalse(hub.paused)
        self.assertTrue(app.ENGINE.s["dm_enabled"])
        self.assertEqual(app.ENGINE.s["dm_daily"], 25)

    def test_legacy_pause_record_uses_the_real_stopped_job_settings(self):
        hub = app.donors()
        hub.book.add("Legacy donor", "923009991234")["donor"]["id"]
        with patch.object(hub.jobs, "connected", return_value=True):
            job = hub.start_batch(
                scope="all",
                limit=3,
                chunk=2,
                rests=[180, 240],
                jitter={"min": -5, "max": 10},
                poster=False,
                run=False,
            )["job"]
            hub.pause_personal()
            hub.jobs._update(job["id"], state="Stopped")
            hub.jobs.active = None
            app.STORE.put(
                "donor_dm_resume",
                {"batch": {"scope": "all", "gap_seconds": 240, "chunk": 2, "poster": False}},
            )
            start = hub.jobs.start
            with patch.object(hub.jobs, "start", side_effect=lambda **kw: start(**kw, run=False)):
                hub.resume_all()
            last = hub.jobs.export_jobs()["jobs"][-1]
        self.assertEqual(last["rests"], [180, 240])
        self.assertEqual(last["jitter"], {"min": -5, "max": 10})
        self.assertFalse(last["poster"])

    def test_stop_does_not_wait_for_a_single_manual_dm_network_lock(self):
        hub = app.donors()
        done = threading.Event()
        worker = threading.Thread(target=lambda: (hub.pause_personal(), done.set()))
        with hub.manual_lock:
            worker.start()
            finished = done.wait(0.3)
        worker.join(2)
        self.assertTrue(finished, "Stop must remain responsive while one manual DM is in flight")


if __name__ == "__main__":
    unittest.main()


class ResumeLoopCostTests(unittest.TestCase):
    """The once-a-second background loop must not query the database while nothing is scheduled."""

    setUp = ResumeScheduleTests.setUp
    tearDown = ResumeScheduleTests.tearDown
    NOW = ResumeScheduleTests.NOW
    stamp = ResumeScheduleTests.stamp

    def test_idle_loop_does_not_read_the_store_and_a_new_schedule_is_still_seen(self):
        hub = app.donors()
        reads = []
        real = app.STORE.get

        def spy(key, default=None):
            reads.append(key)
            return real(key, default)

        with patch.object(app.STORE, "get", side_effect=spy):
            for _ in range(50):
                hub.tick_resume()
            resume_reads = [k for k in reads if k == hub.RESUME_KEY]
            self.assertLessEqual(len(resume_reads), 1)
        hub.pause_personal()
        with patch("donor_integration.time.time", return_value=self.NOW):
            hub.schedule_resume(self.stamp(60), "loop")
        with patch("donor_integration.time.time", return_value=self.NOW + 30):
            hub.tick_resume()
            self.assertTrue(hub.paused)
        with patch("donor_integration.time.time", return_value=self.NOW + 61):
            hub.tick_resume()
        self.assertFalse(hub.paused)
        self.assertEqual(hub.resume_status()["state"], "Completed")
        with patch("donor_integration.time.time", return_value=self.NOW + 62):
            hub.tick_resume()
        self.assertFalse(hub._resume_due)
