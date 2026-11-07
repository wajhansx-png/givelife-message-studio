"""Chaos: the WhatsApp gateway refuses, hangs, or answers garbage, and state files are damaged.
Real HTTP server, fake gateway, nothing is ever sent. Every screen's data call must still answer,
and features that do not need WhatsApp must keep working at full speed."""

import json, threading, time, unittest, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import test_manual_sends as fixture
from test_manual_sends import app

KEY = "test-only-studio-access-key"
# Data calls the screens make on load or on a timer.
SCREENS = [
    "/health", "/drafts", "/left", "/rules", "/memory", "/knowledge", "/campaign", "/autopilot",
    "/chat", "/groups", "/wa-status", "/wa-check", "/poster", "/dm-poster", "/donor-delivery",
    "/donors", "/volunteers", "/cases", "/reply-setup", "/suggestions", "/report",
    "/chat-next-actions", "/donor-messages",
]  # fmt: skip
# Screens that never need WhatsApp: they must answer 200 whatever the gateway does.
INDEPENDENT = [
    "/health",
    "/drafts",
    "/left",
    "/rules",
    "/donors",
    "/cases",
    "/memory",
    "/knowledge",
]


class Gateway(BaseHTTPRequestHandler):
    mode = "ok"
    hits = []

    def _answer(self):
        type(self).hits.append((self.command, self.path))
        mode = type(self).mode
        if mode == "hang":
            time.sleep(4)
        if mode == "garbage":
            body = b"<html>502 Bad Gateway</html>"
        elif mode == "500":
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        else:
            body = json.dumps(
                {
                    "code": "SUCCESS",
                    "results": {"is_connected": True, "is_logged_in": True, "data": []},
                }
            ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _answer

    def log_message(self, *a):
        pass


class Chaos(unittest.TestCase):
    def setUp(self):
        # Only the picture upload (curl) is faked, and it records instead of sending. All other
        # gateway traffic is real HTTP to the controllable Gateway above.
        fixture.SendTests.setUp(self)
        self.api.stop()
        self.sent_by_curl = self.sent

    def tearDown(self):
        self.api.start()  # the fixture's tearDown stops it again
        fixture.SendTests.tearDown(self)

    def start(self, mode):
        Gateway.mode, Gateway.hits = mode, []
        self.gateway = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
        self.gateway.daemon_threads = True
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()
        self.gowa = patch.object(app, "GOWA_URL", "http://127.0.0.1:%d" % self.gateway.server_port)
        self.gowa.start()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.http.daemon_threads = True
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.http.server_port
        self.addCleanup(self.stop)

    def stop(self):
        for server in (self.http, self.gateway):
            server.shutdown()
            server.server_close()
        self.gowa.stop()

    def get(self, path, timeout=20):
        req = urllib.request.Request(self.base + path, headers={"Authorization": "Bearer " + KEY})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        return code, raw, time.monotonic() - started

    def sweep(self, mode):
        self.start(mode)
        for path in SCREENS:
            code, raw, _ = self.get(path)
            self.assertLess(code, 600, path)
            if path != "/poster" and path != "/dm-poster":
                json.loads(raw)  # always a readable answer, never a dropped connection or HTML
        for path in INDEPENDENT:
            self.assertEqual(self.get(path)[0], 200, path + " broke while WhatsApp was " + mode)

    def test_gateway_refusing_connections(self):
        self.gowa.stop()
        self.gowa = patch.object(app, "GOWA_URL", "http://127.0.0.1:1")
        self.gowa.start()
        self.sweep("refused")

    def test_gateway_answering_garbage(self):
        self.sweep("garbage")

    def test_gateway_answering_500(self):
        self.sweep("500")

    def test_a_hanging_gateway_never_slows_features_that_do_not_use_it(self):
        self.start("hang")
        stuck = [
            threading.Thread(target=self.get, args=("/wa-check",), daemon=True) for _ in range(4)
        ]
        [t.start() for t in stuck]
        time.sleep(0.3)  # four requests are now waiting on WhatsApp
        for path in INDEPENDENT:
            code, _, took = self.get(path)
            self.assertEqual(code, 200, path)
            self.assertLess(took, 2.0, path + " waited on the stuck gateway")
        [t.join(15) for t in stuck]

    def test_damaged_state_files_do_not_take_screens_down(self):
        self.start("ok")
        for f in (
            app.DRAFT,
            app.HOLD,
            app.AUTO,
            app.DATA / "variant-state.json",
            app.DATA / "dm-state.json",
        ):
            f.write_text("{not json", encoding="utf-8")
        for path in ("/health", "/drafts", "/left", "/autopilot", "/campaign", "/chat", "/rules"):
            code, raw, _ = self.get(path)
            self.assertLess(code, 500, path + " failed on a damaged file")
            json.loads(raw)
        # A damaged hold is treated as ON: nothing may be sent while the file cannot be trusted.
        self.assertTrue(app.on_hold())

    def test_a_send_during_a_gateway_outage_sends_nothing(self):
        self.start("refused")
        self.gowa.stop()
        self.gowa = patch.object(app, "GOWA_URL", "http://127.0.0.1:1")
        self.gowa.start()
        result = app.send_image("120363431210327603@g.us", "caption")
        self.assertEqual(result["code"], "ERROR")
        self.assertEqual(self.sent_by_curl, [])  # the upload was never attempted


if __name__ == "__main__":
    unittest.main()
