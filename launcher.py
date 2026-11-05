import os, json, time, subprocess, signal, urllib.request, urllib.parse, uuid, shutil, threading, re
from pathlib import Path
from persist import configured_store

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DATA_DIR", "/data/studio"))
DATA.mkdir(parents=True, exist_ok=True)
if not os.environ.get("UI_ACCESS_KEY"):
    raise SystemExit("UI_ACCESS_KEY must be configured before startup.")
store = configured_store()
if store is None:
    raise SystemExit("DB_URI must be configured with the free persistent PostgreSQL database.")
for name in ("drafts.json", "poster.jpg", "state.md"):
    if not (DATA / name).exists():
        shutil.copyfile(ROOT / name, DATA / name)
store.restore(DATA, ROOT)
gowa_data = Path("/data/gowa")
gowa_data.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env.update(
    APP_HOST="127.0.0.1",
    APP_PORT="3000",
    APP_UI_ENABLED="false",
    APP_UI_AUTO_UPDATE="false",
    MCP_ENABLED="false",
    WHATSAPP_AUTO_DOWNLOAD_MEDIA="false",
    TZ="Asia/Karachi",
    # Render free plan has 512 MB for everything. Go keeps freed memory until its heap doubles,
    # so cap the WhatsApp gateway; glibc gives each Python thread its own arena, so limit those.
    GOMEMLIMIT=os.environ.get("GOMEMLIMIT", "220MiB"),
    GOGC=os.environ.get("GOGC", "50"),
    MALLOC_ARENA_MAX=os.environ.get("MALLOC_ARENA_MAX", "2"),
)
parsed = urllib.parse.urlsplit(env["DB_URI"])
query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
query = [(k, v) for k, v in query if k != "channel_binding"]
env["DB_URI"] = urllib.parse.urlunsplit(
    ("postgres", parsed.netloc, parsed.path, urllib.parse.urlencode(query), "")
)
children = []


def stop(*args):
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
gowa = subprocess.Popen(
    ["/usr/local/bin/whatsapp", "rest"],
    cwd=gowa_data,
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)
children.append(gowa)


def safe_logs():
    for line in gowa.stdout:
        line = line.replace(os.environ["DB_URI"], "[private database]").replace(
            env["DB_URI"], "[private database]"
        )
        print(
            re.sub(r"postgres(?:ql)?://[^\s'\"]+", "[private database]", line), end="", flush=True
        )


threading.Thread(target=safe_logs, daemon=True).start()
for attempt in range(90):
    try:
        with urllib.request.urlopen("http://127.0.0.1:3000/devices", timeout=3) as response:
            devices = json.load(response).get("results", [])
        if not devices:
            body = json.dumps({"device_id": str(uuid.uuid4())}).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:3000/devices",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                device = json.load(response)["results"]
        else:
            device = devices[0]
        env["WHATSAPP_DEVICE_ID"] = device["id"]
        break
    except Exception:
        if gowa.poll() is not None:
            raise SystemExit("WhatsApp process stopped during startup.")
        time.sleep(1)
else:
    stop()
server = subprocess.Popen(["python", "-u", str(ROOT / "server.py")], cwd=ROOT, env=env)
children.append(server)
while all(p.poll() is None for p in children):
    time.sleep(1)
stop()
