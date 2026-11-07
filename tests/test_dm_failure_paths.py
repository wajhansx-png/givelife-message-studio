"""Every way a DM can fail mid-batch. Synthetic donors, stubbed transport: nothing is ever sent."""

import unittest
from unittest.mock import patch
from urllib.error import URLError
import test_manual_sends as fixture
from test_manual_sends import app

OK = {"code": "SUCCESS"}


class DmFailurePaths(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self.h = app.donors()
        self.h.jobs.import_jobs({"jobs": []})
        self.h.book._save({"version": 1, "records": []})

    tearDown = fixture.SendTests.tearDown

    def batch(self, replies, people=3):
        """Run a real batch of `people` donors; each send() consumes the next reply (exception = raised)."""
        h = self.h
        for i in range(people):
            h.book.add("Synthetic " + str(i), "92300123000" + str(i))
        calls = []

        def send(body):
            calls.append(body["phone"])
            reply = replies.pop(0) if replies else OK
            if isinstance(reply, BaseException):
                raise reply
            return reply

        waits = []

        def no_wait(timeout=None):
            waits.append(timeout)
            if len(waits) > 500:
                raise AssertionError("busy wait loop in the batch runner")
            return False

        with patch.object(h.jobs, "connected", return_value=True):
            h.start_batch(scope="all", limit=people, run=False)
            with (
                patch.object(h.jobs, "send", side_effect=send),
                patch.object(h.jobs, "_gap", return_value=0),
                patch.object(h.jobs.stop, "wait", new=no_wait),
            ):
                h.jobs._run(h.jobs._load()["jobs"][-1])
        st = h.jobs.status()
        return st, calls

    def test_a_failed_final_save_never_leaves_the_registry_stuck_busy(self):
        real = self.h.jobs._update

        def update(ident, **fields):
            if fields.get("state") in ("Completed", "Stopped"):
                raise ValueError("Persistent send records are unavailable.")
            return real(ident, **fields)

        with (
            patch.object(self.h.jobs, "_update", side_effect=update),
            patch.object(app.time, "sleep"),  # the settle retries must not slow the test
            patch.object(__import__("donor_delivery").time, "sleep"),
        ):
            st, calls = self.batch([])
        self.assertEqual(len(calls), 3)  # the sends themselves all happened exactly once
        self.assertIsNone(self.h.jobs.active)  # and a new batch can start
        self.assertEqual(self.h.jobs.status()["state"], "Completed")  # the screen tells the truth

    def test_whatsapp_blips_are_waited_out_not_fatal(self):
        st, calls = self.batch([ValueError("WhatsApp is disconnected. Tap WhatsApp to reconnect.")])
        self.assertEqual((st["state"], st["sent"]), ("Completed", 3), st.get("error"))

    def test_disconnected_error_code_is_retried_for_the_same_person(self):
        st, calls = self.batch(
            [{"code": "ERROR", "message": "WhatsApp disconnected. Log in again."}]
        )
        self.assertEqual((st["state"], st["sent"]), ("Completed", 3), st.get("error"))
        self.assertEqual(calls[0], calls[1])  # not sent the first time, so tried again

    def test_storage_hiccup_is_waited_out(self):
        st, _ = self.batch(
            [ValueError("Persistent send records are unavailable. Try again later.")]
        )
        self.assertEqual((st["state"], st["sent"]), ("Completed", 3), st.get("error"))

    def test_own_number_and_bad_number_are_skipped_batch_continues(self):
        st, _ = self.batch(
            [
                ValueError("Your own account is excluded from donor sending."),
                ValueError("Enter a valid phone number with country code, such as +92…"),
            ]
        )
        self.assertEqual((st["state"], st["sent"], st["skipped"]), ("Completed", 1, 2))

    def test_unconfirmed_delivery_is_never_retried_and_batch_goes_on(self):
        st, calls = self.batch([URLError("timed out")])
        self.assertEqual((st["sent"], st["failed"]), (2, 1), st.get("error"))
        self.assertEqual(len(calls), len(set(calls)), "nobody may be sent to twice")
        self.assertNotEqual(st["state"], "Stopped")

    def test_unconfirmed_result_code_goes_on_too(self):
        st, calls = self.batch([{"code": "UNCERTAIN", "message": "Send not confirmed."}])
        self.assertEqual((st["sent"], st["failed"]), (2, 1))
        self.assertEqual(len(calls), len(set(calls)))

    def test_three_unconfirmed_in_a_row_pause_the_batch(self):
        bad = [URLError("down")] * 3
        st, calls = self.batch(bad, people=5)
        self.assertEqual((st["state"], st["failed"], len(calls)), ("Stopped", 3, 3))
        self.assertIn("in a row", st["error"])

    def test_a_success_resets_the_unconfirmed_streak(self):
        replies = [URLError("x"), URLError("x"), OK, URLError("x"), URLError("x"), OK]
        st, _ = self.batch(replies, people=6)
        self.assertEqual((st["state"], st["sent"], st["failed"]), ("Completed", 2, 4))

    def test_on_hold_stops_cleanly(self):
        st, calls = self.batch([{"code": "ERROR", "message": "On hold: you told me to wait."}])
        self.assertEqual((st["state"], len(calls)), ("Stopped", 1))
        self.assertEqual(st["failed"], 0)  # not counted as a failed delivery

    def test_batch_wide_refusal_still_stops_with_its_reason(self):
        st, _ = self.batch([ValueError("DMs paused for today: 2 people asked not to be messaged.")])
        self.assertEqual(st["state"], "Stopped")
        self.assertIn("paused for today", st["error"])

    def test_unexpected_crash_is_reported_not_hung(self):
        st, _ = self.batch(
            [RuntimeError("boom")], people=2
        )  # treated as unconfirmed, then carries on
        self.assertEqual(st["sent"], 1)

    def test_status_check_failure_is_a_disconnect_not_a_crash(self):
        with (
            patch.object(app, "api_result", side_effect=URLError("refused")),
            self.assertRaisesRegex(ValueError, "WhatsApp is disconnected"),
        ):
            app.send_custom(
                {
                    "target": "phone",
                    "phone": "923001230009",
                    "message": "Hi",
                    "kind": "volunteer_batch",
                }
            )

    def test_one_damaged_saved_version_does_not_block_all_dms(self):
        import copy

        bank = app.donors().messages
        original = copy.deepcopy(bank.get())
        try:
            good = bank._rotation_texts()
            data = bank.get()
            data["items"] = bank._entries(good + ["Brother, incomplete"])
            data.pop("generation", None)
            bank._save(data)
            self.assertEqual(bank._rotation_texts(), good)
        finally:
            bank._save(original)


if __name__ == "__main__":
    unittest.main()
