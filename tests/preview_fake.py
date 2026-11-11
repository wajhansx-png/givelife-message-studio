"""Local full-stack preview. Every WhatsApp request goes to a fake server."""

import os, sys, tempfile, json, threading, shutil, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
events = []
incoming = []
events_lock = threading.Lock()


def record(item):
    with events_lock:
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
    UI_ACCESS_KEY="manual-fix-preview-key",
    WHATSAPP_DEVICE_ID="fake-device",
)
folder = tempfile.TemporaryDirectory()
EVENTS = Path(folder.name) / "manual-preview-events.json"
os.environ["DATA_DIR"] = folder.name
for name in ("drafts.json", "state.md"):
    shutil.copyfile(ROOT / name, Path(folder.name) / name)
poster = ROOT.parent / "cloud-service/poster.jpg"
(Path(folder.name) / "poster.jpg").write_bytes(
    poster.read_bytes() if poster.exists() else b"fake-poster"
)
import server


from persist import SqliteStore


class Store(SqliteStore):
    def __init__(self):
        super().__init__(Path(folder.name) / "preview.sqlite")
        self.initialize()


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
if "--giki" in sys.argv:
    # Fake Top donors plus a fake named group, to check the "GIKI Donors" heading at every width.
    book = server.donors().book
    for i in range(14):
        row = book.add("Demo donor " + str(i + 1), "1555" + str(1230000 + i))["donor"]
        book.update(row["id"], important=True)
        book.update(row["id"], top_donor=True)
        if i < 5:
            book.update(row["id"], normal_amount=(5 - i) * 1000)
    for i in range(3):  # name-only donors, waiting for their numbers (use "Add numbers")
        row = book.add("Name only Giki " + str(i + 1), "")["donor"]
        book.update(row["id"], important=True)
        book.update(row["id"], top_donor=True)
    data = book._load()
    for n, r in enumerate([x for x in data["records"] if x["top_donor"]][5:], 1):
        r["group"], r["group_order"] = "GIKI", 15 - n
    book._save(data)
if "--draft-task" in sys.argv:
    text = "*A short charity reminder.*\nYousuf needs treatment. *Rs. 25,000 left.* 💔\n*03097458815* EASYPAISA ONLY (Wajdan Khan)"
    server.chat_callbacks(
        "Make a message for givelife without poster only 3 lines", revision=server.OWNER_REVISION
    )["set_message"](kind="group", text=text)
if "--fake-ai" in sys.argv:
    # Scripted writer for the four message buttons only: every other feature still sees "AI not connected".
    import itertools

    _n = itertools.count()
    _URDU = [
        "ایک مجبور باپ کی فریاد سنیے",
        "گھر کے دروازے پر دستک ہے",
        "آج آپ کا ہاتھ ایک گھر بچا سکتا ہے",
        "یہ قرض اب برداشت سے باہر ہے",
        "ایک چھوٹی سی مدد بڑا بوجھ ہلکا کر دے گی",
        "اس باپ کے آنسو ہمیں پکارتے ہیں",
    ]
    _ENG = [
        "A helpless father needs you today",
        "One door knock after another",
        "Your small gift can lift this weight",
        "This debt is now too heavy",
        "Help before this family breaks",
        "A father is begging for time",
    ]
    _URDU_TAIL = [
        "آج",
        "ابھی",
        "فوراً",
        "پلیز",
        "دل سے",
        "اللہ کے نام پر",
        "فی الحال",
        "مل کر",
        "اب",
        "یہاں",
        "سب مل کر",
        "ہمت کریں",
        "جلدی",
        "دعا کے ساتھ",
        "اس ہفتے",
        "آخری بار",
    ]
    _ENG_TAIL = [
        "today",
        "now",
        "please",
        "together",
        "quickly",
        "with love",
        "this week",
        "for Allah",
        "right away",
        "step up",
        "be kind",
        "stand with us",
        "before night",
        "as one",
        "within hours",
        "from the heart",
    ]
    _STORY = [
        "People keep coming to the house for the borrowed money. The father has nothing to give them.",
        "The family is worried and tired. They need help to pay what is left.",
        "The loan was taken for a sad and urgent need. Now the family cannot pay it back.",
        "Neighbours are asking for their money. The father feels helpless.",
        "Each day the worry grows. A little help from many people can end it.",
        "The family trusts that good people will stand with them.",
    ]
    _VERSES = ["q34_39", "q2_261", "h_muslim_2699", "q2_245", "h_tirmidhi_2616", "q5_2"]
    _HELP = [
        "this helpless father",
        "this tired family",
        "this worried father",
        "this family",
        "this home",
        "this father",
    ]

    def _fake_raw(api, system, tools, messages, **k):
        i = next(_n)
        urdu = "in URDU (Urdu script)" in messages[-1]["content"]
        hooks = _URDU if urdu else _ENG
        tail = (_URDU_TAIL if urdu else _ENG_TAIL)[
            (i // 6) % 16
        ]  # 96 different openings, so a long test day never runs out
        return {
            "content": json.dumps(
                {
                    "hook": tail + " " + hooks[i % 6],
                    "story": _STORY[(i * 5 + 1) % 6],
                    "help": _HELP[i % 6],
                    "verse": _VERSES[(i * 3 + 2) % 6],
                    "concept": "scripted %d" % i,
                },
                ensure_ascii=False,
            )
        }

    _real_style = server.message_style

    def _style_with_fake_ai(body):
        client, raw = server.assistant.client, server.assistant._chat_raw
        server.assistant.client, server.assistant._chat_raw = (lambda: object()), _fake_raw
        try:
            return _real_style(body)
        finally:
            server.assistant.client, server.assistant._chat_raw = client, raw

    server.message_style = _style_with_fake_ai
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


server.Handler.do_GET = preview_get
server.Handler.do_POST = preview_post
port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 3003
http = PreviewHTTPServer(("127.0.0.1", port), server.Handler)
print(
    f"Local fake-WhatsApp preview: http://127.0.0.1:{port}/ (no real messages possible)", flush=True
)
http.serve_forever()
