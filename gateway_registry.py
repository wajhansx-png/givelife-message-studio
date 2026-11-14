"""Keep the gateway's device list across deploys.

Render wipes the local disk on every deploy. The WhatsApp logins stay in the database, but the gateway ties
each device name (the main WhatsApp, the Giki one) to its login in a local file (storages/chatstorage.db,
table `devices`). Without that list the Giki login comes back under another name and the Giki page shows
"Connect WhatsApp" again. A small copy of the file, with every other table emptied (no chats, messages or
scheduled sends), is kept in the database and put back before the gateway starts. Nothing is sent here."""

import base64, contextlib, hashlib, json, logging, os, sqlite3, tempfile, threading
from pathlib import Path
from storage_crypto import ValueCipher

KEY = "gateway_device_registry_v1"
KEEP = ("devices", "schema_info")  # every other table is emptied in the copy
LOG = logging.getLogger("givelife.ops")
MAX_BYTES = 4 * 1024 * 1024
PURPOSE = "gateway-registry-v1"
_lock = threading.Lock()
_last = {}  # file -> digest of the device rows last saved, so an unchanged list is not saved again


def _connect(path, readonly=False):
    if readonly:
        return contextlib.closing(
            sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=5)
        )
    return contextlib.closing(sqlite3.connect(path, timeout=5))


def _rows(db):
    try:
        return db.execute("SELECT * FROM devices ORDER BY device_id").fetchall()
    except sqlite3.Error:
        return None


def save(store, path):
    """Save the device list when it changed. True when a new copy was saved."""
    with _lock:
        return _save(store, Path(path))


def _save(store, path):
    if not path.exists():
        return False
    with _connect(path, readonly=True) as live:
        rows = _rows(live)
        if not rows:
            return False  # nothing linked yet, or the gateway has not made its tables
        digest = hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()
        if _last.get(str(path)) == digest:
            return False
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "registry.sqlite"
            with _connect(copy) as target:
                live.backup(target)
            with _connect(copy) as db:
                db.execute("PRAGMA journal_mode=DELETE")
                tables = db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                for (name,) in tables:
                    if name not in KEEP:
                        db.execute('DELETE FROM "' + name.replace('"', '""') + '"')
                db.commit()
                db.execute("VACUUM")
            raw = copy.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Device list copy is too large.")
    cipher = ValueCipher()
    sealed = cipher.key is not None
    data = cipher.seal_bytes(raw, PURPOSE) if sealed else raw
    store.put(KEY, {"v": 1, "sealed": sealed, "data": base64.b64encode(data).decode()})
    _last[str(path)] = digest
    return True


def restore(store, path):
    """Put the saved device list back. Only before the gateway starts, and never over an existing file."""
    path = Path(path)
    if path.exists():
        return False
    record = store.get(KEY) if hasattr(store, "get") else None
    if not isinstance(record, dict) or not isinstance(record.get("data"), str):
        return False
    if len(record["data"]) > 2 * MAX_BYTES:
        raise ValueError("Invalid device list copy.")
    raw = base64.b64decode(record["data"], validate=True)
    if record.get("sealed"):
        raw = ValueCipher().open_bytes(raw, PURPOSE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        tmp = Path(folder) / "chatstorage.db"
        tmp.write_bytes(raw)
        os.chmod(tmp, 0o600)
        with _connect(tmp) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or _rows(db) is None:
                raise ValueError("Device list copy failed validation.")
        if path.exists():
            return False
        os.replace(tmp, path)
    return True


def start(store, path, every=60):
    def checkpoint():
        while True:
            threading.Event().wait(every)
            try:
                save(store, path)
            except Exception as exc:
                LOG.error("gateway_registry_checkpoint_failed error_type=%s", type(exc).__name__)

    threading.Thread(target=checkpoint, daemon=True, name="gateway-registry-checkpoint").start()
