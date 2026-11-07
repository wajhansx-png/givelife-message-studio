import hashlib, json, threading, unittest, urllib.request
from unittest.mock import patch
import test_manual_sends as fixture

app = fixture.app


class SendStopTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def post(self, port, path, body):
        req = urllib.request.Request(
            "http://127.0.0.1:" + str(port) + path,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test-only-studio-access-key",
            },
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.load(r)

    def test_stopped_test_sends_nothing(self):
        http = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            self.post(http.server_port, "/stop-send", {"stop_id": "stop-test-0001"})
            with (
                patch.object(app.workflow(), "options", return_value={"poster": False}),
                patch.object(app, "send_text") as send_text,
            ):
                result = self.post(
                    http.server_port, "/test", {"message": "Hi", "stop_id": "stop-test-0001"}
                )
            self.assertEqual(result["code"], "STOPPED")
            send_text.assert_not_called()
            self.assertNotIn("stop-test-0001", app.STOP_EVENTS)
        finally:
            http.shutdown()

    def test_unstopped_test_still_sends(self):
        http = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with (
                patch.object(app.workflow(), "options", return_value={"poster": False}),
                patch.object(app, "send_text", return_value={"code": "SUCCESS"}) as send_text,
            ):
                result = self.post(
                    http.server_port, "/test", {"message": "Hi", "stop_id": "stop-test-0002"}
                )
            self.assertEqual(result["code"], "SUCCESS")
            send_text.assert_called_once()
        finally:
            http.shutdown()

    def test_stop_job_only_stops_running_jobs(self):
        self.assertFalse(app.stop_job("missing"))
        app.JOBS["j1"] = {"done": False}
        app.JOB_CANCEL["j1"] = threading.Event()
        self.assertTrue(app.stop_job("j1"))
        self.assertTrue(app.JOB_CANCEL["j1"].is_set())
        self.assertEqual(app.JOBS["j1"]["cancel_reason"], "Stopped by owner.")
        app.JOBS["j1"]["done"] = True
        self.assertFalse(app.stop_job("j1"))

    def test_stopped_dm_leaves_no_contacted_record(self):
        body = {
            "target": "phone",
            "phone": "923001230009",
            "message": "Hi",
            "kind": "volunteer_batch",
            "poster": True,
        }
        jid = app.custom_recipient(body)[0]
        digest = hashlib.sha256(jid.encode()).hexdigest()
        ledger_before = app.STORE.get("dm_daily", {})

        def stopped_upload(*args, **kwargs):
            app.REQUEST_STOP.fn = lambda: True
            app.check_stop()

        try:
            with (
                patch.object(
                    app, "api_result", return_value={"is_connected": True, "is_logged_in": True}
                ),
                patch.object(app, "send_image", side_effect=stopped_upload),
                self.assertRaises(app.SendStopped),
            ):
                app.send_custom(body)
        finally:
            app.REQUEST_STOP.fn = None
        self.assertFalse(app.STORE.get("dm_recipient_" + digest))
        self.assertEqual(
            app.STORE.get("dm_daily", {}).get("count", 0), ledger_before.get("count", 0)
        )


if __name__ == "__main__":
    unittest.main()
