import os, json, time, subprocess, signal, urllib.request, urllib.parse, uuid, shutil, threading, re
from pathlib import Path
from persist import configured_store
import supervisor

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
# A database outage at boot is retried instead of crashing. If it never comes back, exit:
# on a deploy Render then keeps the previous working version running.
if not supervisor.wait_for_db(store):
    raise SystemExit("Database unreachable after 10 minutes.")
store.restore(DATA, ROOT)

# Only one instance may be logged in to WhatsApp. While Render overlaps old and new instances,
# wait here (answering /health) until the old one has stopped and released the lease.
OWNER = uuid.uuid4().hex
lease = supervisor.LeaseKeeper(store, OWNER, on_lost=lambda: stop())
state = supervisor.acquire_lease(store, OWNER, max_wait=0)
if state != "acquired":
    waiting = None
    try:
        waiting = supervisor.Waiting(int(os.environ.get("PORT", "10000")))
    except OSError:
        pass
    print(
        "[launcher] WhatsApp link is held by the previous instance; waiting for it to stop",
        flush=True,
    )
    state = supervisor.acquire_lease(store, OWNER, max_wait=240)
    if waiting:
        waiting.close()
print("[launcher] WhatsApp lease: " + state, flush=True)
if state == "acquired":  # otherwise carry on without it: the lease must never block the app
    lease.start()

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
stopping = threading.Event()


def stop(*args):
    if stopping.is_set():
        return
    stopping.set()
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
    lease.release()  # only after WhatsApp is stopped, so the next instance can take over safely
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def safe_logs(proc):
    for line in proc.stdout:
        line = line.replace(os.environ["DB_URI"], "[private database]").replace(
            env["DB_URI"], "[private database]"
        )
        print(
            re.sub(r"postgres(?:ql)?://[^\s'\"]+", "[private database]", line), end="", flush=True
        )


def start_gowa():
    proc = subprocess.Popen(
        [
            "/usr/local/bin/whatsapp",
            "rest",
            # Big groups need hundreds of encryption-key lookups per send. On the remote database
            # they time out ("context deadline exceeded ... prekey"), so the key cache lives in a
            # local SQLite file. The login session itself stays in the persistent database.
            "--db-keys-uri="
            + os.environ.get(
                "GOWA_DB_KEYS_URI",
                "file:" + str(gowa_data / "whatsapp-keys.db") + "?_foreign_keys=on",
            ),
        ],
        cwd=gowa_data,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(target=safe_logs, args=(proc,), daemon=True).start()
    return proc


def ensure_device(gowa):
    """Wait for the gateway, then reuse the saved WhatsApp device (create one only if none exists)."""
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
            return device["id"]
        except Exception:
            if gowa.poll() is not None:
                return None
            time.sleep(1)
    return None


def start_server():
    return subprocess.Popen(["python", "-u", str(ROOT / "server.py")], cwd=ROOT, env=env)


def gowa_ready():
    proc = start_gowa()
    device = ensure_device(proc)
    if device:
        env["WHATSAPP_DEVICE_ID"] = device
    return proc, device


gowa_proc, device_id = gowa_ready()
if not device_id:
    gowa_proc.terminate()
    raise SystemExit("WhatsApp gateway did not start.")
gowa = supervisor.Child("whatsapp", start_gowa, proc=gowa_proc)
server = supervisor.Child("server", start_server)
children.extend([gowa_proc, server.proc])


def whatsapp_status():
    req = urllib.request.Request(
        "http://127.0.0.1:3000/devices/" + env["WHATSAPP_DEVICE_ID"] + "/status",
        headers={"X-Device-Id": env["WHATSAPP_DEVICE_ID"]},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.load(r)
    return data.get("results") if isinstance(data.get("results"), dict) else {}


def reconnect_whatsapp():
    req = urllib.request.Request(
        "http://127.0.0.1:3000/app/reconnect", headers={"X-Device-Id": env["WHATSAPP_DEVICE_ID"]}
    )
    urllib.request.urlopen(req, timeout=15).read()


last_wa, dropped_since, last_try, last_report = 0.0, 0.0, 0.0, 0.0
while not stopping.is_set():
    time.sleep(2)
    # a crashed child is restarted alone; the other keeps running
    result = gowa.check()
    if result == "restarted":
        gowa_proc = gowa.proc
        new_id = ensure_device(gowa_proc)
        if new_id and new_id != env.get("WHATSAPP_DEVICE_ID"):
            env["WHATSAPP_DEVICE_ID"] = new_id
            server.proc.terminate()
        children.append(gowa_proc)
    elif result == "giveup":
        break
    result = server.check()
    if result == "restarted":
        children.append(server.proc)
    elif result == "giveup":
        break
    # WhatsApp watchdog: a dropped link (still logged in) is reconnected here, even if Auto is off
    t = time.time()
    if t - last_wa >= 30:
        last_wa = t
        try:
            state = supervisor.wa_state(whatsapp_status())
        except Exception:
            state = None  # gateway busy or restarting: judge next round
        if state == "dropped":
            dropped_since = dropped_since or t
            if t - dropped_since >= 45 and t - last_try >= 90:
                last_try = t
                try:
                    reconnect_whatsapp()
                    print("[watchdog] WhatsApp link was down; asked it to reconnect", flush=True)
                except Exception as e:
                    print("[watchdog] reconnect failed: " + type(e).__name__, flush=True)
        elif state in ("ok", "logged_out"):
            dropped_since = 0.0
        if state and t - last_report >= 600:
            last_report = t
            print("[watchdog] whatsapp=%s" % state, flush=True)
if not stopping.is_set():
    print("[launcher] a component keeps crashing; restarting the container", flush=True)
    stop()
