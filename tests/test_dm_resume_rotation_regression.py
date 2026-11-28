"""Actual resume/dispatch regressions with synthetic recipients only."""

import unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app


class ResumeRotationTests(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        app.donors().jobs.import_jobs({"jobs": []})
        app.donors().book._save({"version": 1, "records": []})

    tearDown = fixture.SendTests.tearDown

    def test_resume_uses_saved_job_id_not_latest_unrelated_job(self):
        h = app.donors()
        for i in range(3):
            h.book.add("Synthetic " + str(i), "92300123000" + str(i))
        with patch.object(h.jobs, "connected", return_value=True):
            job = h.start_batch(scope="all", limit=3, run=False)["job"]
            h.pause_personal()
            raw = h.jobs.export_jobs()["jobs"][-1]
            h.jobs._update(
                job["id"], state="Stopped", receipts=[{"id": raw["ids"][0], "state": "Sent"}]
            )
            h.jobs.active = None
            data = h.jobs.export_jobs()
            data["jobs"].append(
                {
                    "id": "later-other-job",
                    "scope": "selected",
                    "state": "Completed",
                    "ids": [],
                    "receipts": [],
                }
            )
            h.jobs.import_jobs(data)
            with patch("donor_delivery.threading.Thread"):
                result = h.resume_all()
            resumed = h.jobs.export_jobs()["jobs"][-1]
        self.assertFalse(result["paused"])
        self.assertEqual(resumed["scope"], "all")
        self.assertEqual(resumed["total"], 2)
        self.assertEqual(resumed["original_total"], 3)
        self.assertEqual(resumed["previous_sent"], 1)

    def fourth_step_scenario(self, count, restart=False):
        h = app.donors()
        for i in range(count):
            h.book.add("Synthetic " + str(i), "92300123000" + str(i))
        delivered = []
        blocked = True

        def transport(body):
            step = body.get("extra") or ("case" if body.get("poster") else body["message"])
            if step == "Fourth message" and blocked:
                raise ValueError("Account temporarily blocked before sending")
            delivered.append((body["phone"], step))
            return {"code": "SUCCESS"}

        h.set_follow_up("Fourth message")
        with (
            patch.object(h.jobs, "connected", return_value=True),
            patch.object(h.jobs, "send", side_effect=transport),
            patch.object(h.jobs, "_sleep_until", return_value=False),
            patch("donor_delivery.threading.Thread"),
        ):
            h.start_batch(scope="all", limit=count, run=False, follow_up=True, video=True, pdf=True)
            original = h.jobs.export_jobs()["jobs"][-1]
            phones = [h.book.resolve(i)["phone"] for i in original["ids"]]
            expected = [
                (phone, step)
                for phone in phones
                for step in ("case", "video", "pdf", "Fourth message")
            ]
            h.jobs._run(original)
            self.assertEqual(delivered, expected[:3])
            h.pause_personal()
            h.set_follow_up("Changed after the error")
            if restart:
                from donor_integration import DonorIntegration

                h = DonorIntegration(app)
            with (
                patch.object(h.jobs, "send", side_effect=transport),
                patch.object(h.jobs, "connected", return_value=True),
                patch.object(h.jobs, "_sleep_until", return_value=False),
            ):
                if count == 1:
                    with self.assertRaisesRegex(ValueError, "remaining recipients"):
                        h.resume_all()
                    self.assertEqual(delivered, expected[:3])
                blocked = False
                h.resume_all()
                if h.jobs.active:
                    resumed = h.jobs.export_jobs()["jobs"][-1]
                    self.assertEqual(resumed["captions"], original["captions"][1:])
                    h.jobs._run(resumed)
            self.assertEqual(delivered, expected)

    def test_restart_between_third_and_fourth_donor_messages(self):
        self.fourth_step_scenario(2, restart=True)

    def test_resume_fourth_step_before_next_donor(self):
        self.fourth_step_scenario(2)

    def test_resume_fourth_step_for_last_donor(self):
        self.fourth_step_scenario(1)

    def test_reserved_wording_survives_live_bank_peek(self):
        h = app.donors()
        job = {
            "ids": ["a", "b"],
            "caption": "fallback",
            "captions": ["Assigned version 8", "Assigned version 9"],
        }
        with patch.object(h.jobs, "variants", return_value=["Version 1", "Version 2"]):
            self.assertEqual(h.jobs._fresh_caption(job, 0), "Assigned version 8")
            self.assertEqual(h.jobs._fresh_caption(job, 1), "Assigned version 9")

    def test_preserved_wording_still_updates_balance(self):
        h = app.donors()
        job = {
            "ids": ["a"],
            "caption": "fallback",
            "captions": ["Unique hook\nRs. 25,000 LEFT\n13 people donating Rs. 2,000"],
        }
        app.set_left(23000)
        text = h.jobs._fresh_caption(job, 0)
        self.assertIn("Unique hook", text)
        self.assertIn("23,000", text)
        self.assertIn("12 people", text)

    def test_every_canonical_template_updates_without_losing_its_hook(self):
        import dm_templates

        h = app.donors()
        app.set_left(23000)
        for i in range(20):
            source = dm_templates.build(i, 25000)
            job = {"ids": ["a"], "caption": source, "captions": [source], "caption_balance": 25000}
            text = h.jobs._fresh_caption(job, 0)
            self.assertNotIn("25,000", text)
            self.assertIn("23,000", text)
            self.assertEqual(source.splitlines()[0], text.splitlines()[0])

    def test_restart_preserves_due_time_and_original_saved_messages(self):
        import time
        from donor_integration import DonorIntegration

        h = app.donors()
        for i in range(3):
            h.book.add("Synthetic " + str(i), "92300123000" + str(i))
        with patch.object(h.jobs, "connected", return_value=True):
            h.start_batch(scope="all", limit=3, run=False)
        raw = h.jobs.export_jobs()["jobs"][-1]
        due = time.time() + 450
        h.jobs._update(raw["id"], state="Waiting", boot="previous-process", next_at=due)
        later = DonorIntegration(app)
        with (
            patch.object(later.jobs, "connected", return_value=True),
            patch("donor_delivery.threading.Thread"),
        ):
            later.jobs.recover()
        resumed = later.jobs.export_jobs()["jobs"][-1]
        self.assertGreaterEqual(resumed.get("hold_until") or 0, due)
        self.assertEqual(resumed["captions"], raw["captions"])

    def test_crash_after_confirmed_book_write_never_repeats_that_recipient(self):
        h = app.donors()
        for i in range(2):
            h.book.add("Synthetic " + str(i), "92300123000" + str(i))
        with patch.object(h.jobs, "connected", return_value=True):
            h.start_batch(scope="all", limit=2, run=False)
        raw = h.jobs.export_jobs()["jobs"][-1]
        h.book.delivery(raw["ids"][0], "Sent", raw["created_at"] + 1)
        self.assertIn(raw["ids"][0], h.jobs._done(raw))

    def test_edit_running_settings_keeps_job_and_receipts(self):
        h = app.donors()
        h.book.add("Synthetic", "923001230001")
        with patch.object(h.jobs, "connected", return_value=True):
            h.start_batch(scope="all", run=False)
        j = h.jobs.export_jobs()["jobs"][-1]
        h.jobs.running_job = j
        result = h.jobs.configure(
            j["id"],
            {"gap_seconds": 180, "chunk": 5, "rests": [600], "poster": False, "jitter": None},
        )
        self.assertEqual(result["job"]["id"], j["id"])
        self.assertEqual(j["gap_seconds"], 180)
        self.assertEqual(len(h.jobs.export_jobs()["jobs"]), 1)
        self.assertFalse(h.paused)
        self.assertFalse(h.jobs.stop.is_set())
        self.assertEqual(j["receipts"], [])
        with self.assertRaises(ValueError):
            h.jobs.configure(j["id"], {"gap_seconds": 0})
        self.assertEqual(h.jobs.export_jobs()["jobs"][-1]["gap_seconds"], 180)


if __name__ == "__main__":
    unittest.main()
