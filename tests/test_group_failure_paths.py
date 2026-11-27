"""Every way a group post can fail mid-job. Stubbed transport: nothing is ever sent."""

import unittest
from unittest.mock import patch, Mock, call
from urllib.error import URLError
import test_manual_sends as fixture
from test_manual_sends import app

OK = {"code": "SUCCESS"}
DOWN = {"code": "ERROR", "message": "WhatsApp disconnected. Log in again."}


class GroupFailurePaths(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def run_groups(self, replies, keys=("main", "community", "fiverr"), picture=True, elapsed=()):
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
        seconds = [0]
        durations = iter(elapsed)

        def send(jid, text, *a):
            calls.append(jid)
            seconds[0] += next(durations, 0)
            reply = replies.pop(0) if replies else OK
            if isinstance(reply, BaseException):
                raise reply
            return reply

        target = "send_image" if picture else "send_text"
        with (
            patch.object(app, target, side_effect=send),
            patch.object(app, "on_hold", return_value=False),
            patch.object(app, "record_delivery"),
            patch.object(app.time, "monotonic", side_effect=lambda: seconds[0]),
        ):
            app.run_job(ident, keys, "Original")
        return app.JOBS[ident], calls

    def test_partial_group_does_not_start_the_next_group(self):
        job, calls = self.run_groups(
            [{"code": "SUCCESS", "extras": [{"kind": "video", "code": "UNCERTAIN"}]}]
        )
        self.assertEqual(self.codes(job), ["PARTIAL"])
        self.assertEqual(calls, [app.GROUPS["main"][1]])
        self.assertIn("not confirmed", job["results"][0]["message"])
        self.assertIn("Completed 0/3 group posts", job["message"])

    def test_upload_uses_up_the_gap_and_groups_keep_selected_order(self):
        keys = ("fiverr", "main", "community")
        job, calls = self.run_groups([], keys=keys, elapsed=(80, 40))
        self.assertEqual(self.codes(job), ["SUCCESS"] * 3)
        self.assertEqual(calls, [app.GROUPS[key][1] for key in keys])
        event = app.JOB_CANCEL["group-failure-0"]
        self.assertEqual(event.wait.call_args_list, [call(20)])

    def test_auto_keeps_requested_order_when_starting_the_job(self):
        with patch.object(app, "start_send_job", return_value="job") as start:
            self.assertTrue(app.start_keys_job(["community", "main"], "Caption"))
        start.assert_called_once_with(["community", "main"], "Caption", manual=False)

    def codes(self, job):
        return [r.get("code") for r in job["results"]]

    def test_disconnect_blip_waits_and_sends_the_same_group(self):
        job, calls = self.run_groups([DOWN, DOWN])
        self.assertEqual(self.codes(job), ["SUCCESS"] * 3)
        self.assertEqual(
            calls[0], calls[2]
        )  # not sent twice: the first two attempts never left the phone

    def test_one_failed_group_leaves_the_next_groups_untouched(self):
        job, calls = self.run_groups([{"code": "ERROR", "message": "group not found"}])
        self.assertEqual(self.codes(job), ["ERROR"])
        self.assertEqual(len(calls), 1)

    def test_uncertain_group_is_never_retried(self):
        job, calls = self.run_groups([URLError("timed out")])
        self.assertEqual(self.codes(job), ["UNCERTAIN"])
        self.assertEqual(len(calls), 1)

    def test_text_post_transport_crash_becomes_a_result(self):
        job, _ = self.run_groups([OSError("broken pipe")], picture=False)
        self.assertEqual(self.codes(job), ["UNCERTAIN"])
        self.assertTrue(job["done"])

    def test_refused_connection_is_waited_out(self):
        job, calls = self.run_groups([URLError(ConnectionRefusedError())], picture=False)
        self.assertEqual(self.codes(job), ["SUCCESS"] * 3)
        self.assertEqual(calls[0], calls[1])

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
