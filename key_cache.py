"""Preserve the local WhatsApp encryption-key cache across ephemeral-host restarts.

The local working SQLite database remains readable by GoWA; only its remote
checkpoint is encrypted. No relinking, deletion, sending or replay happens here.
"""

import base64
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from storage_crypto import ValueCipher

KEY = "gateway_key_checkpoint_v1"
LOG = logging.getLogger("givelife.ops")
MAX_BYTES = 64 * 1024 * 1024
_save_lock = threading.Lock()
_saved = {}  # path -> file signature of the last copy the database accepted


def _signature(path):
    """Size and modified time of the key file and its write-ahead log: changes whenever a key is written."""
    out = []
    for name in (str(path), str(path) + "-wal"):
        try:
            info = os.stat(name)
            out.append((info.st_size, info.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


def save(store, path):
    # The final shutdown snapshot must follow any in-flight periodic snapshot.
    with _save_lock:
        return _save(store, path)


def _save(store, path):
    path = Path(path)
    cipher = ValueCipher()
    if not path.exists() or cipher.key is None:
        return False
    signature = _signature(path)
    if _saved.get(str(path)) == signature:
        return False  # nothing changed since the last copy: do not rewrite the whole file to the database
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
    _saved[str(path)] = signature
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


def _apart(action, path, timeout=180):
    """Run save / restore in a short-lived process. Each one makes several full copies of the key file in memory
    (copy, encrypted, base64); a long-running process keeps that memory, so on a 512 MB host it grew until the host
    killed everything mid-send. A process that ends gives all of it back."""
    done = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), action, str(path)],
        cwd=str(Path(__file__).resolve().parent),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if done.returncode != 0:
        raise RuntimeError("key checkpoint " + action + " process failed")
    return (done.stdout.strip().splitlines() or [""])[-1] == "True"


def save_apart(path):
    """save(), in its own process, and only when the key file changed since the last copy."""
    path = Path(path)
    with _save_lock:
        if not path.exists():
            return False
        signature = _signature(path)
        if _saved.get(str(path)) == signature:
            return False
        saved = _apart("save", path)
        _saved[str(path)] = signature
        return saved


def restore_apart(path):
    return _apart("restore", path)


EVERY = 120  # seconds between checkpoints; a clean stop (deploy, memory guard) always saves the latest


def start(store, path):
    if not os.environ.get("GIVELIFE_STORAGE_KEY"):
        return

    def checkpoint():
        while True:
            try:
                save_apart(Path(path))
            except Exception as exc:
                LOG.error("gateway_key_checkpoint_failed error_type=%s", type(exc).__name__)
            threading.Event().wait(EVERY)

    threading.Thread(target=checkpoint, daemon=True, name="gateway-key-checkpoint").start()


if __name__ == "__main__":  # python key_cache.py save|restore <path>
    from persist import configured_store

    _action, _path = sys.argv[1], Path(sys.argv[2])
    print(save(configured_store(), _path) if _action == "save" else restore(configured_store(), _path))
