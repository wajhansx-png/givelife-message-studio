import hashlib, json, threading, time, unittest, urllib.request
from unittest.mock import patch
import batch_media
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
        cleaned = threading.Event()
        original_unwatch = app.unwatch_stop

        def unwatch(sid):
            original_unwatch(sid)
            cleaned.set()

        http = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            self.post(http.server_port, "/stop-send", {"stop_id": "stop-test-0001"})
            with (
                patch.object(app.workflow(), "options", return_value={"poster": False}),
                patch.object(app, "send_text") as send_text,
                patch.object(app, "unwatch_stop", side_effect=unwatch),
            ):
                result = self.post(
                    http.server_port, "/test", {"message": "Hi", "stop_id": "stop-test-0001"}
                )
            self.assertEqual(result["code"], "STOPPED")
            send_text.assert_not_called()
            self.assertTrue(cleaned.wait(1), "request cleanup did not complete")
            self.assertNotIn("stop-test-0001", app.STOP_EVENTS)
        finally:
            http.shutdown()
            http.server_close()

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

    def test_hold_blocks_custom_text_without_contacting_recipient(self):
        body = {
            "target": "phone",
            "phone": "923001230009",
            "message": "Hi",
            "kind": "volunteer_batch",
            "poster": False,
        }
        digest = hashlib.sha256(app.custom_recipient(body)[0].encode()).hexdigest()
        before = app.STORE.get("dm_daily", {})
        with (
            patch.object(app, "on_hold", return_value=True),
            patch.object(
                app, "api_result", return_value={"is_connected": True, "is_logged_in": True}
            ),
            patch.object(app.urllib.request, "urlopen") as send,
        ):
            with self.assertRaisesRegex(ValueError, "On hold"):
                app.send_custom(body)
            send.assert_not_called()
        self.assertFalse(app.STORE.get("dm_recipient_" + digest))
        self.assertEqual(app.STORE.get("dm_daily", {}), before)

    def test_hold_after_connection_check_blocks_custom_text(self):
        body = {
            "target": "phone",
            "phone": "923001230009",
            "message": "Hi",
            "kind": "volunteer_batch",
            "poster": False,
        }
        digest = hashlib.sha256(app.custom_recipient(body)[0].encode()).hexdigest()
        before = app.STORE.get("dm_daily", {})
        held = False

        def connected(_path):
            nonlocal held
            held = True
            return {"is_connected": True, "is_logged_in": True}

        with (
            patch.object(app, "on_hold", side_effect=lambda: held),
            patch.object(app, "api_result", side_effect=connected),
            patch.object(app.urllib.request, "urlopen") as send,
        ):
            with self.assertRaisesRegex(ValueError, "On hold"):
                app.send_custom(body)
            send.assert_not_called()
        self.assertFalse(app.STORE.get("dm_recipient_" + digest))
        self.assertEqual(app.STORE.get("dm_daily", {}), before)

    def test_stop_during_attachment_loading_prevents_upload(self):
        def load(*_args):
            app.REQUEST_STOP.fn = lambda: True
            return app.ATT / "synthetic.jpg", "image/jpeg"

        try:
            with (
                patch.object(batch_media, "load", side_effect=load),
                patch.object(app.subprocess, "run") as send,
                self.assertRaises(app.SendStopped),
            ):
                app.send_batch_attachment("923001230009", "Hi", "synthetic")
            send.assert_not_called()
        finally:
            app.REQUEST_STOP.fn = None

    def test_hold_while_waiting_for_wire_lock_restores_recipient(self):
        body = {
            "target": "phone",
            "phone": "923001230009",
            "message": "Hi",
            "kind": "volunteer_batch",
            "poster": False,
        }
        digest = hashlib.sha256(app.custom_recipient(body)[0].encode()).hexdigest()
        before = app.STORE.get("dm_daily", {})
        held = threading.Event()
        errors = []

        def dispatch():
            try:
                app.send_custom(body)
            except Exception as exc:
                errors.append(exc)

        with (
            patch.object(app, "on_hold", side_effect=held.is_set),
            patch.object(
                app, "api_result", return_value={"is_connected": True, "is_logged_in": True}
            ),
            patch.object(app.urllib.request, "urlopen") as send,
        ):
            with app.WIRE_LOCK:
                worker = threading.Thread(target=dispatch)
                worker.start()
                deadline = time.monotonic() + 3
                while not app.STORE.get("dm_recipient_" + digest) and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(
                    app.STORE.get("dm_recipient_" + digest), "send did not reach the wire lock"
                )
                held.set()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            send.assert_not_called()
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertIn("On hold", str(errors[0]))
        self.assertFalse(app.STORE.get("dm_recipient_" + digest))
        self.assertEqual(app.STORE.get("dm_daily", {}), before)

    def test_hold_during_attachment_loading_prevents_upload(self):
        held = False

        def load(*_args):
            nonlocal held
            held = True
            return app.ATT / "synthetic.jpg", "image/jpeg"

        with (
            patch.object(app, "on_hold", side_effect=lambda: held),
            patch.object(batch_media, "load", side_effect=load),
            patch.object(app.subprocess, "run") as send,
            self.assertRaisesRegex(ValueError, "On hold"),
        ):
            app.send_batch_attachment("923001230009", "Hi", "synthetic")
        send.assert_not_called()

    def test_hold_while_poster_waits_for_wire_restores_recipient(self):
        body = {
            "target": "phone",
            "phone": "923001230009",
            "message": "Hi",
            "kind": "volunteer_batch",
            "poster": True,
        }
        digest = hashlib.sha256(app.custom_recipient(body)[0].encode()).hexdigest()
        before = app.STORE.get("dm_daily", {})
        held = threading.Event()
        errors = []

        def dispatch():
            try:
                app.send_custom(body)
            except Exception as exc:
                errors.append(exc)

        with (
            patch.object(app, "on_hold", side_effect=held.is_set),
            patch.object(
                app, "api_result", return_value={"is_connected": True, "is_logged_in": True}
            ),
            patch.object(app, "post_media") as send,
        ):
            with app.WIRE_LOCK:
                worker = threading.Thread(target=dispatch)
                worker.start()
                deadline = time.monotonic() + 3
                while not app.STORE.get("dm_recipient_" + digest) and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(app.STORE.get("dm_recipient_" + digest))
                held.set()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            send.assert_not_called()
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], app.SendHeld)
        self.assertFalse(app.STORE.get("dm_recipient_" + digest))
        self.assertEqual(app.STORE.get("dm_daily", {}), before)

    def test_hold_during_image_preparation_prevents_upload(self):
        held = False

        def connected(_path):
            nonlocal held
            held = True
            return {"is_connected": True, "is_logged_in": True}

        with (
            patch.object(app, "on_hold", side_effect=lambda: held),
            patch.object(app, "api_result", side_effect=connected),
            patch.object(app, "post_media") as send,
            self.assertRaisesRegex(ValueError, "On hold"),
        ):
            app.send_image("923001230009", "Hi")
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
