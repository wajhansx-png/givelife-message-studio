"""Real process crashes. server.py runs as a real process against a fake WhatsApp gateway, is killed with
SIGKILL in the middle of a donor DM batch, and is started again on the same data folder. Whatever happens,
nobody gets a second DM, and people not yet reached are sent to by the restarted server by itself.
Nothing here can reach real WhatsApp: the gateway is a local fake."""

import json, os, re, shutil, signal, socket, subprocess, sys, tempfile, threading, time, unittest
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = "crash-test-access-key"


class Gateway(BaseHTTPRequestHandler):
    sends, slow_first = [], 0.0
    lock = threading.Lock()

    def _reply(self, body):
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except OSError:
            pass  # the server that asked was killed

    def do_GET(self):
        self._reply(
            {"code": "SUCCESS", "results": {"is_connected": True, "is_logged_in": True, "data": []}}
        )

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        found = re.search(rb'name="phone"\r\n\r\n(\d+)', raw)
        phone = found.group(1).decode() if found else (json.loads(raw or b"{}").get("phone") or "")
        with Gateway.lock:
            first = not Gateway.sends
            Gateway.sends.append(phone.split("@")[0])
        if first and Gateway.slow_first:
            time.sleep(Gateway.slow_first)  # the message is accepted, the reply is still on its way
        self._reply({"code": "SUCCESS", "results": {"message_id": "fake-%d" % len(Gateway.sends)}})

    def log_message(self, *a):
        pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CrashRecovery(unittest.TestCase):
    def setUp(self):
        Gateway.sends, Gateway.slow_first = [], 0.0
        self.gateway = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
        self.gateway.daemon_threads = True
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()
        self.data = tempfile.mkdtemp()
        for name in ("drafts.json", "state.md"):
            shutil.copyfile(ROOT / name, Path(self.data) / name)
        (Path(self.data) / "poster.jpg").write_bytes(b"fake-poster")
        self.port, self.proc = free_port(), None
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.kill()
        self.gateway.shutdown()
        self.gateway.server_close()
        shutil.rmtree(self.data, ignore_errors=True)

    def boot(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("DB_URI", "DEEPSEEK_API_KEY", "RENDER_EXTERNAL_URL")
        }
        env.update(
            PORT=str(self.port),
            DATA_DIR=self.data,
            UI_ACCESS_KEY=KEY,
            GOWA_URL="http://127.0.0.1:%d" % self.gateway.server_port,
            WHATSAPP_DEVICE_ID="fake-device",
            NOTES_PASSWORD="crash-test-pin",
        )
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "server.py")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                self.call("/health")
                return
            except OSError:
                time.sleep(0.2)
        self.fail("server did not start")

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL)  # a real crash: no cleanup code runs
            self.proc.wait(10)

    def call(self, path, body=None):
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)

    def wait_for(self, check, seconds, message):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if check():
                return
            time.sleep(0.2)
        self.fail(message + " | sends so far: %s" % Gateway.sends)

    def start_batch(self):
        self.boot()
        for i in range(3):
            self.call(
                "/donors",
                {"action": "add", "name": "Crash Donor %d" % i, "phone": "0300123400%d" % i},
            )
        self.call(
            "/donor-delivery",
            {"scope": "all", "gap_seconds": 5, "limit": 3, "request_id": "crash-run-0001"},
        )

    def check_nobody_twice(self, expected):
        counts = Counter(Gateway.sends)
        self.assertEqual(sorted(counts), sorted(expected), counts)
        self.assertTrue(
            all(n == 1 for n in counts.values()), "someone got a second DM: %s" % counts
        )

    EVERYONE = ["9230012340%02d" % i for i in range(3)]

    def test_killed_while_the_gateway_has_the_message_but_the_reply_is_lost(self):
        Gateway.slow_first = 4.0
        self.start_batch()
        self.wait_for(lambda: len(Gateway.sends) == 1, 20, "first DM never reached the gateway")
        self.kill()  # the first DM was accepted; the server never learns whether it was delivered
        Gateway.slow_first = 0.0
        self.boot()
        self.wait_for(
            lambda: len(Gateway.sends) >= 3, 90, "restarted server did not finish the batch"
        )
        time.sleep(
            8
        )  # a duplicate, if there were going to be one, would arrive within a gap or two
        self.check_nobody_twice(self.EVERYONE)

    def test_killed_between_two_sends_resumes_with_the_rest_and_repeats_nobody(self):
        self.start_batch()
        self.wait_for(lambda: len(Gateway.sends) == 1, 20, "first DM never reached the gateway")
        time.sleep(1.5)  # reply received and recorded; now waiting out the gap
        self.kill()
        self.boot()
        self.wait_for(
            lambda: len(Gateway.sends) >= 3, 90, "restarted server did not finish the batch"
        )
        time.sleep(8)
        self.check_nobody_twice(self.EVERYONE)
        status = self.call("/donor-delivery")
        self.assertIn(status["state"], ("Completed", "Sending", "Waiting"), status)

    def test_an_auto_control_survives_a_crash_stays_on_and_never_repeats_anyone(self):
        self.boot()
        for i in range(3):
            added = self.call(
                "/donors",
                {"action": "add", "name": "Crash Donor %d" % i, "phone": "0300123400%d" % i},
            )
            ident = (added.get("donor") or {}).get("id")
            self.call("/donors", {"action": "update", "id": ident, "important": True})
        view = self.call(
            "/auto-controls", {"control": "important", "on": True, "settings": {"count": 3}}
        )
        self.assertTrue(view["controls"]["important"]["on"])
        self.wait_for(lambda: len(Gateway.sends) == 1, 20, "first DM never reached the gateway")
        time.sleep(1.5)
        self.kill()  # crash with 2 donors still to go
        self.boot()
        # Nothing was switched off by the crash, and the restarted server owns the run again.
        self.wait_for(
            lambda: self.call("/auto-controls")["controls"]["important"]["on"],
            40,
            "the control did not carry on",
        )
        mine = self.call("/auto-controls")["controls"]["important"]
        self.assertEqual((mine["recipients"], mine["sent"]), (3, 1))
        time.sleep(
            10
        )  # the 8-minute gap is honoured after a restart: no immediate second send, no repeat
        self.assertEqual(Gateway.sends, [Gateway.sends[0]])
        self.assertFalse(
            self.call("/auto-controls")["controls"]["group"]["on"]
        )  # others stayed OFF
        # Switching OFF afterwards stops it for good: a later restart does not bring it back.
        self.call("/auto-controls", {"control": "important", "on": False})
        self.wait_for(
            lambda: not self.call("/auto-controls")["controls"]["important"]["on"],
            20,
            "OFF did not stop it",
        )
        self.kill()
        self.boot()
        time.sleep(4)
        self.assertFalse(self.call("/auto-controls")["controls"]["important"]["on"])
        self.assertEqual(len(Gateway.sends), 1)


if __name__ == "__main__":
    unittest.main()
