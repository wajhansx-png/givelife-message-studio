"""Preserve the local WhatsApp encryption-key cache across ephemeral-host restarts.

The local working SQLite database remains readable by GoWA; only its remote
checkpoint is encrypted. No relinking, deletion, sending or replay happens here.
"""

import base64
import logging
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from storage_crypto import ValueCipher

KEY = "gateway_key_checkpoint_v1"
LOG = logging.getLogger("givelife.ops")
MAX_BYTES = 64 * 1024 * 1024
_save_lock = threading.Lock()


def save(store, path):
    # The final shutdown snapshot must follow any in-flight periodic snapshot.
    with _save_lock:
        return _save(store, path)


def _save(store, path):
    path = Path(path)
    cipher = ValueCipher()
    if not path.exists() or cipher.key is None:
        return False
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "keys.sqlite"
        deadline = time.monotonic() + 15

        def progress(*args):
            if time.monotonic() > deadline:
                raise TimeoutError("Key checkpoint exceeded its time budget.")

        with (
            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as source,
            sqlite3.connect(copy) as target,
        ):
            source.backup(target, pages=128, progress=progress)
        if copy.stat().st_size > MAX_BYTES:
            raise ValueError("Key cache exceeds checkpoint limit.")
        encrypted = cipher.seal_bytes(copy.read_bytes(), "gateway-keys-v1")
    store.put(KEY, base64.b64encode(encrypted).decode())
    return True


def restore(store, path):
    path = Path(path)
    if path.exists():
        return False
    encoded = store.get(KEY) if hasattr(store, "get") else None
    if not encoded:
        return False
    if not isinstance(encoded, str) or len(encoded) > 2 * MAX_BYTES:
        raise ValueError("Invalid key checkpoint.")
    raw = ValueCipher().open_bytes(base64.b64decode(encoded, validate=True), "gateway-keys-v1")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        tmp = Path(folder) / "keys.sqlite"
        tmp.write_bytes(raw)
        os.chmod(tmp, 0o600)
        with sqlite3.connect(tmp) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Key checkpoint failed integrity validation.")
        # Caller restores before GoWA starts. Never overwrite an existing cache.
        if path.exists():
            return False
        os.replace(tmp, path)
    return True


def start(store, path):
    if not os.environ.get("GIVELIFE_STORAGE_KEY"):
        return

    def checkpoint():
        while True:
            try:
                save(store, Path(path))
            except Exception as exc:
                LOG.error("gateway_key_checkpoint_failed error_type=%s", type(exc).__name__)
            threading.Event().wait(60)

    threading.Thread(target=checkpoint, daemon=True, name="gateway-key-checkpoint").start()
