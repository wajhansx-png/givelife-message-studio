"""Every way a group post can fail mid-job. Stubbed transport: nothing is ever sent."""

import unittest
from unittest.mock import patch, Mock
from urllib.error import URLError
import test_manual_sends as fixture
from test_manual_sends import app

OK = {"code": "SUCCESS"}
DOWN = {"code": "ERROR", "message": "WhatsApp disconnected. Log in again."}


class GroupFailurePaths(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def run_groups(self, replies, keys=("main", "community", "fiverr"), picture=True):
        ident = "group-failure-" + str(len(replies))
        keys = list(keys)
        app.JOBS[ident] = {
            "results": [],
            "manual": True,
            "captions": ["Wording " + k for k in keys],
            "with_picture": picture,
            "keys": keys,
            "caption": "Original",
        }
        event = Mock()
        event.is_set.return_value = False
        event.wait.return_value = False
        app.JOB_CANCEL[ident] = event
        app.ACTIVE = ident
        calls = []

        def send(jid, text, *a):
            calls.append(jid)
            reply = replies.pop(0) if replies else OK
            if isinstance(reply, BaseException):
                raise reply
            return reply

        target = "send_image" if picture else "send_text"
        with (
            patch.object(app, target, side_effect=send),
            patch.object(app, "on_hold", return_value=False),
            patch.object(app, "record_delivery"),
        ):
            app.run_job(ident, keys, "Original")
        return app.JOBS[ident], calls

    def codes(self, job):
        return [r.get("code") for r in job["results"]]

    def test_disconnect_blip_waits_and_sends_the_same_group(self):
        job, calls = self.run_groups([DOWN, DOWN])
        self.assertEqual(self.codes(job), ["SUCCESS"] * 3)
        self.assertEqual(
            calls[0], calls[2]
        )  # not sent twice: the first two attempts never left the phone

    def test_one_failed_group_does_not_cancel_the_others(self):
        job, _ = self.run_groups([{"code": "ERROR", "message": "group not found"}])
        self.assertEqual(self.codes(job), ["ERROR", "SUCCESS", "SUCCESS"])

    def test_uncertain_group_is_never_retried(self):
        job, calls = self.run_groups([URLError("timed out")])
        self.assertEqual(self.codes(job), ["UNCERTAIN", "SUCCESS", "SUCCESS"])
        self.assertEqual(len(calls), len(set(calls)))

    def test_text_post_transport_crash_becomes_a_result(self):
        job, _ = self.run_groups([OSError("broken pipe")], picture=False)
        self.assertEqual(self.codes(job), ["UNCERTAIN", "SUCCESS", "SUCCESS"])
        self.assertTrue(job["done"])

    def test_refused_connection_is_waited_out(self):
        job, calls = self.run_groups([URLError(ConnectionRefusedError())], picture=False)
        self.assertEqual(self.codes(job), ["SUCCESS"] * 3)
        self.assertEqual(calls[0], calls[1])

    def test_three_failures_in_a_row_stop_the_job(self):
        bad = [{"code": "ERROR", "message": "x"}] * 3
        job, calls = self.run_groups(bad, keys=("main", "community", "fiverr", "upwork"))
        self.assertEqual((self.codes(job), len(calls)), (["ERROR"] * 3, 3))

    def test_whatsapp_down_for_ten_minutes_stops_with_a_clear_result(self):
        with patch.object(app, "GROUP_RECONNECT_TRIES", 2):
            job, calls = self.run_groups([DOWN] * 10)
        self.assertEqual(self.codes(job), ["ERROR"])
        self.assertEqual(len(calls), 3)
        self.assertTrue(job["done"])

    def test_status_check_crash_in_send_image_is_a_disconnect(self):
        with patch.object(app, "api_result", side_effect=URLError("refused")):
            self.assertEqual(app.send_image("120363000000000000@g.us", "x")["code"], "ERROR")


if __name__ == "__main__":
    unittest.main()
