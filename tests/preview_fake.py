"""Local full-stack preview. Every WhatsApp request goes to a fake server."""

import os, sys, tempfile, json, threading, shutil, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVENTS = ROOT.parent / "manual-preview-events.json"
events = []
incoming = []


def record(item):
    events.append(item)
    EVENTS.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")


class FakeWhatsApp(BaseHTTPRequestHandler):
    def response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if "/status" in self.path:
            return self.response(
                {"code": "SUCCESS", "results": {"is_connected": True, "is_logged_in": True}}
            )
        if "/messages" in self.path:
            return self.response({"results": {"data": list(incoming)}})
        if "/chats" in self.path or "/contacts" in self.path:
            return self.response(
                {
                    "results": {
                        "data": [
                            {
                                "id": "923001234567@s.whatsapp.net",
                                "name": "Jr Accounts",
                                "is_group": False,
                            }
                        ]
                    }
                }
            )
        return self.response({"results": []})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        fields = {}
        if "multipart/form-data" in self.headers.get("Content-Type", ""):
            msg = BytesParser(policy=default).parsebytes(
                (
                    "Content-Type: "
                    + self.headers["Content-Type"]
                    + "\r\nMIME-Version: 1.0\r\n\r\n"
                ).encode()
                + raw
            )
            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if name != "image":
                    fields[name] = part.get_payload(decode=True).decode("utf-8")
        else:
            try:
                fields = json.loads(raw)
            except Exception:
                fields = {}
        record({"path": self.path, "fields": fields, "time": time.time()})
        self.response(
            {"code": "SUCCESS", "results": {"message_id": "fake-message-" + str(len(events))}}
        )

    def log_message(self, *args):
        pass


class PreviewHTTPServer(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True
    block_on_close = False


fake = PreviewHTTPServer(("127.0.0.1", 0), FakeWhatsApp)
threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ.pop("DB_URI", None)
os.environ.pop("RENDER_EXTERNAL_URL", None)
os.environ.pop("DEEPSEEK_API_KEY", None)
os.environ.setdefault("NOTES_PASSWORD", "test-preview-only-pin")
os.environ.update(
    GOWA_URL="http://127.0.0.1:" + str(fake.server_port),
    UI_ACCESS_KEY=os.environ.get("UI_ACCESS_KEY", "Rwp3ukx/crSBiJ2bVHkd9zONnbiw22VXRtNAm96dyTg="),
    WHATSAPP_DEVICE_ID="fake-device",
)
folder = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = folder.name
for name in ("drafts.json", "state.md"):
    shutil.copyfile(ROOT / name, Path(folder.name) / name)
poster = ROOT.parent / "cloud-service/poster.jpg"
(Path(folder.name) / "poster.jpg").write_bytes(
    poster.read_bytes() if poster.exists() else b"fake-poster"
)
import server


class Store:
    def __init__(self):
        self.data = {}
        self.lock = threading.RLock()

    def get(self, k, d=None):
        import copy

        with self.lock:
            return copy.deepcopy(self.data.get(k, d))

    def put(self, k, v):
        import copy

        with self.lock:
            self.data[k] = copy.deepcopy(v)


server.STORE = Store()
server.set_left(25000)
server.ENGINE.s["dm_enabled"] = False
type(server.donors().team).JITTER = (0, 0)
if "--donors" in sys.argv:
    for i in range(20):
        row = server.donors().book.add("Demo donor " + str(i + 1), "1555" + str(1230000 + i))[
            "donor"
        ]
        if i < 3:
            server.donors().book.update(row["id"], important=True)
if "--draft-task" in sys.argv:
    text = "*A short charity reminder.*\nYousuf needs treatment. *Rs. 25,000 left.* 💔\n*03097458815* EASYPAISA ONLY (Wajdan Khan)"
    server.chat_callbacks(
        "Make a message for givelife without poster only 3 lines", revision=server.OWNER_REVISION
    )["set_message"](kind="group", text=text)
# No engine/background AI loops are started. The only sends are explicit preview actions.
server.Handler.log_message = lambda *a: None
original_get = server.Handler.do_GET
original_post = server.Handler.do_POST


def preview_get(self):
    if self.path == "/mobile-preview":
        return self.reply((ROOT / "tests/mobile_preview.html").read_bytes(), "text/html")
    if "--test-api" in sys.argv and self.path == "/__test/events":
        if not self.authorized():
            return self.reply({"error": "Access key required"}, status=401)
        return self.reply({"events": events})
    return original_get(self)


def preview_post(self):
    if "--test-api" in sys.argv and self.path == "/__test/shutdown":
        if not self.authorized():
            return self.reply({"error": "Access key required"}, status=401)
        self.reply({"ok": True})
        threading.Thread(target=self.server.shutdown, daemon=True).start()
        return
    if "--test-api" in sys.argv and self.path == "/__test/seed":
        if not self.authorized():
            return self.reply({"error": "Access key required"}, status=401)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if body.get("reset_notes"):
            # Reset only test database, never production. Keep browser security sessions.
            server.STORE.put("foundation_notes_v1", {"html": "", "revision": 0, "updated_at": 0})
        if "reply" in body:
            server.chat_add("app", str(body["reply"]), turn_id="test-reply-" + str(time.time()))
        if "group" in body:
            server.save_draft("group", str(body["group"]))
        if "incoming" in body:
            incoming.append(
                {
                    "id": "in-" + str(len(incoming) + 1),
                    "content": str(body["incoming"]),
                    "is_from_me": False,
                    "timestamp": __import__("datetime")
                    .datetime.now(__import__("datetime").timezone.utc)
                    .isoformat(),
                }
            )
        if body.get("team_tick"):
            server.donors().team.tick()
        if body.get("team_demo"):
            import uuid as _u

            t = server.donors().team
            d = t._load()
            now = time.time()
            d["member"] = {"name": "Bilal Ahmed", "phone": "923001234567", "since": now}
            d["tasks"] = []
            d["feed"] = []
            d["plan"] = None
            long = "Update the donors sheet with every confirmed donation, check the totals twice and message the owner a photo of the final page"
            for i, (n, st) in enumerate(body["team_demo"]):
                for k in range(n):
                    tid = _u.uuid4().hex
                    d["tasks"].append(
                        {
                            "id": tid,
                            "no": len(d["tasks"]) + 1,
                            "text": (long if k % 2 else "Post the caption in group %d" % (k + 1)),
                            "start_at": now - 3600,
                            "due_at": now + 3600 * (k + 1),
                            "status": st,
                            "created_at": now,
                            "attempts": 1,
                            "next_try": 0,
                            "asked_at": now - 3000,
                            "reminded": False,
                            "checked": False,
                            "final_sent": False,
                            "acked": True,
                            "proof": k % 2 == 0,
                            "proof_asked": False,
                            "blocked_replied": False,
                            "report_text": "done, please check it",
                            "reported_at": now - 60,
                            "verified_at": None,
                            "jit": 9,
                        }
                    )
            for k in range(6):
                d["feed"].append(
                    {
                        "id": "e%d" % k,
                        "at": now - k * 60,
                        "kind": "update",
                        "text": "Bilal: working on the sheet now, almost there, will send a photo soon %d"
                        % k,
                        "task": None,
                    }
                )
            t._save()
        return self.reply({"ok": True})
    return original_post(self)


orig_authorized = server.Handler.authorized
def preview_authorized(self):
    hdr = self.headers.get("Authorization", "")
    allowed = {
        "Bearer manual-fix-preview-key",
        "Bearer Rwp3ukx/crSBiJ2bVHkd9zONnbiw22VXRtNAm96dyTg=",
    }
    env_k = os.environ.get("UI_ACCESS_KEY")
    if env_k:
        allowed.add("Bearer " + env_k)
    if hdr in allowed:
        return True
    return orig_authorized(self)

server.Handler.authorized = preview_authorized
server.Handler.do_GET = preview_get
server.Handler.do_POST = preview_post
port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 3003
http = PreviewHTTPServer(("127.0.0.1", port), server.Handler)
print(
    f"Local fake-WhatsApp preview: http://127.0.0.1:{port}/ (no real messages possible)", flush=True
)
http.serve_forever()
