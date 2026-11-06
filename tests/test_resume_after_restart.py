"""A deploy/restart must not leave a running DM batch stopped. Synthetic jobs only; nothing is sent."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_manual_sends as fixture  # noqa: F401  (puts the app on the path)
from test_manual_sends import app


class FakeJobs:
    def __init__(self, link, result="job", boom=False):
        self.link, self.result, self.boom, self.calls = list(link), result, boom, 0

    def connected(self):
        return self.link.pop(0) if len(self.link) > 1 else self.link[0]

    def recover(self):
        self.calls += 1
        if self.boom:
            raise ValueError("start failed")
        return self.result


def registry(donor, volunteer):
    return SimpleNamespace(jobs=donor, volunteers=SimpleNamespace(jobs=volunteer))


class ResumeAfterRestartTests(unittest.TestCase):
    def run_resume(self, donor, volunteer, **kw):
        sleeps = []
        with patch.object(app, "donors", return_value=registry(donor, volunteer)):
            n = app.resume_batches_after_restart(wait=1, sleep=sleeps.append, **kw)
        return n, sleeps

    def test_waits_for_whatsapp_then_resumes_each_batch_once(self):
        donor, volunteer = FakeJobs([False, False, True]), FakeJobs([True], result=None)
        n, sleeps = self.run_resume(donor, volunteer)
        self.assertEqual((n, donor.calls, volunteer.calls), (1, 1, 1))
        self.assertEqual(len(sleeps), 2)  # waited while disconnected, never after

    def test_a_failing_resume_never_crashes_startup_or_repeats(self):
        donor, volunteer = FakeJobs([True], boom=True), FakeJobs([True])
        n, _ = self.run_resume(donor, volunteer)
        self.assertEqual((n, donor.calls, volunteer.calls), (1, 1, 1))

    def test_gives_up_when_whatsapp_never_connects(self):
        donor, volunteer = FakeJobs([False]), FakeJobs([False])
        n, sleeps = self.run_resume(donor, volunteer, tries=3)
        self.assertEqual((n, donor.calls, len(sleeps)), (0, 0, 3))


if __name__ == "__main__":
    unittest.main()


class BatchErrorTests(unittest.TestCase):
    """One bad recipient never stops a batch, and the chosen gap is never overridden."""

    def setUp(self):
        fixture.SendTests.setUp(self)
        app.donors().jobs.import_jobs({"jobs": []})
        app.donors().book._save({"version": 1, "records": []})

    tearDown = fixture.SendTests.tearDown

    def test_blocked_recipient_is_skipped_and_the_rest_still_send(self):
        h = app.donors()
        for i in range(3):
            h.book.add("Synthetic " + str(i), "92300123000" + str(i))
        replies = [
            ValueError("This recipient is blocked or opted out."),
            {"code": "SUCCESS"},
            {"code": "SUCCESS"},
        ]
        with patch.object(h.jobs, "connected", return_value=True):
            job = h.start_batch(scope="all", limit=3, run=False)["job"]
            with (
                patch.object(h.jobs, "_dispatch", side_effect=replies),
                patch.object(h.jobs, "_gap", return_value=0),
            ):
                h.jobs._run(h.jobs._load()["jobs"][-1])
        status = h.jobs.status()
        self.assertEqual((status["sent"], status["skipped"]), (2, 1), status.get("error"))
        self.assertNotEqual(status["state"], "Stopped")
        self.assertTrue(job)

    def test_no_minimum_gap_between_batch_sends(self):
        self.assertEqual(app.DM_MIN_GAP, 0)
