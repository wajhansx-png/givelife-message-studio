import json, threading, time, unittest, urllib.request
from unittest.mock import patch
import test_manual_sends as fixture

app = fixture.app


class GroupSendTimesTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_snapshot_uses_newest_confirmed_local_or_persisted_time(self):
        jid = app.GROUPS["main"][1]
        stamp = time.time() - 7200
        app.LAST_LOCAL[jid] = stamp
        app.STORE.put("last_sent", {jid: stamp + 60, "120363431210327603@g.us": stamp - 60})
        times = app.live_snapshot()["last_sent"]
        self.assertEqual(times["main"], stamp + 60)
        self.assertEqual(times["test"], stamp - 60)
        self.assertIsNone(times["community"])
        app.LAST_LOCAL.clear()
        self.assertEqual(
            app.dashboard_send_times()["main"],
            stamp + 60,
            "Persisted receipts survive local cache loss",
        )

    def test_invalid_or_future_records_are_not_displayed_as_sends(self):
        app.STORE.put(
            "last_sent",
            {
                app.GROUPS["main"][1]: "bad",
                app.GROUPS["community"][1]: float("nan"),
                app.GROUPS["fiverr"][1]: time.time() + 10000,
            },
        )
        self.assertTrue(all(v is None for v in app.dashboard_send_times().values()))

    def test_text_only_test_records_success_but_not_failure(self):
        http = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()

        def send():
            req = urllib.request.Request(
                "http://127.0.0.1:" + str(http.server_port) + "/test",
                data=json.dumps({"message": "Test caption"}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer test-only-studio-access-key",
                },
            )
            with urllib.request.urlopen(req, timeout=3) as r:
                return json.load(r)

        try:
            with (
                patch.object(app.workflow(), "options", return_value={"poster": False}),
                patch.object(
                    app, "send_text", return_value={"code": "ERROR", "message": "Uncertain"}
                ),
            ):
                self.assertEqual(send()["code"], "ERROR")
                self.assertIsNone(app.dashboard_send_times()["test"])
            with (
                patch.object(app.workflow(), "options", return_value={"poster": False}),
                patch.object(
                    app,
                    "send_text",
                    return_value={"code": "SUCCESS", "results": {"message_id": "fake"}},
                ),
            ):
                self.assertEqual(send()["code"], "SUCCESS")
                self.assertGreater(app.dashboard_send_times()["test"], time.time() - 5)
        finally:
            http.shutdown()
            http.server_close()
