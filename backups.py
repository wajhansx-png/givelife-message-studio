"""Encrypted application-state snapshots. Off-site delivery requires an operator-owned HTTPS PUT destination.

Snapshots include the application state table, not GoWA's separate session tables or arbitrary files.
Restoration is offline, creates a NEW SQLite database and never starts any background jobs.
"""

import argparse
import datetime
import json
import logging
import os
import threading
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from persist import SqliteStore
from storage_crypto import ValueCipher

LOG = logging.getLogger("givelife.ops")
MAX_BYTES = 64 * 1024 * 1024
_lock = threading.Lock()
_last = {"local_at": None, "offsite_at": None, "error": None}


def _records(store):
    if isinstance(store, SqliteStore):
        with store._lock, store._conn() as conn:
            for key, raw in conn.execute(
                "SELECT key,value FROM givelife_studio_state ORDER BY key"
            ):
                raw = store.cipher.decode(raw, key)
                try:
                    value = json.loads(raw)
                except (ValueError, TypeError):
                    value = raw
                yield key, value
    else:
        with store.connection() as db, db.transaction():
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            with db.cursor(name="backup_" + uuid.uuid4().hex) as cursor:
                cursor.itersize = 100
                cursor.execute("SELECT key,value FROM givelife_studio_state ORDER BY key")
                yield from cursor


def create(store, directory):
    cipher = ValueCipher()
    if cipher.key is None:
        raise ValueError("Configure and preserve GIVELIFE_STORAGE_KEY before backing up.")
    with _lock:
        records, size = [], 0
        for key, value in _records(store):
            if key == "wa_lease":
                continue
            size += len(json.dumps([key, value], ensure_ascii=False).encode()) + 2
            if size > MAX_BYTES:
                raise ValueError(
                    "Application snapshot exceeds 64 MiB. Use the provider backup service."
                )
            records.append([key, value])
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        raw = json.dumps(
            {"format": 1, "created": stamp, "records": records}, ensure_ascii=False
        ).encode()
        encrypted = cipher.seal_bytes(raw, "backup-v1")
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / (
            "studio-" + stamp.replace(":", "-") + "-" + uuid.uuid4().hex[:8] + ".backup"
        )
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("xb") as f:
                os.chmod(tmp, 0o600)
                f.write(encrypted)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        _last.update(local_at=stamp, error=None)
        # This is local retention only, never a claim of independent off-site protection.
        for old in sorted(folder.glob("studio-*.backup"))[:-7]:
            old.unlink()
        return path


def restore(snapshot, target):
    target = Path(target)
    if target.exists():
        raise FileExistsError(
            "Restore only to a new database path; existing data is never overwritten."
        )
    if Path(snapshot).stat().st_size > MAX_BYTES + 1024:
        raise ValueError("Snapshot is too large.")
    raw = ValueCipher().open_bytes(Path(snapshot).read_bytes(), "backup-v1")
    obj = json.loads(raw)
    if obj.get("format") != 1 or not isinstance(obj.get("records"), list):
        raise ValueError("Unsupported snapshot format.")
    for row in obj["records"]:
        if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str):
            raise ValueError("Invalid snapshot record.")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive reservation prevents replacing a file created by another restore.
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        store = SqliteStore(target)
        store.initialize()
        with store._lock, store._conn() as conn:
            for key, value in obj["records"]:
                if key == "wa_lease":
                    continue
                encoded = store.cipher.encode(json.dumps(value, ensure_ascii=False), key)
                conn.execute(
                    "INSERT OR REPLACE INTO givelife_studio_state(key,value,updated_at) VALUES(?,?,0)",
                    (key, encoded),
                )
        return store
    except Exception:
        for p in [target, Path(str(target) + "-wal"), Path(str(target) + "-shm")]:
            p.unlink(missing_ok=True)
        raise


def status():
    return {
        **_last,
        "key_configured": bool(os.environ.get("GIVELIFE_STORAGE_KEY")),
        "offsite_configured": bool(os.environ.get("GIVELIFE_BACKUP_URL")),
        "scope": "application state only; gateway sessions/media require provider backups",
    }


def upload(path):
    url = os.environ.get("GIVELIFE_BACKUP_URL", "")
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or not p.netloc or p.username or p.query or p.fragment:
        raise ValueError(
            "Configure an HTTPS PUT directory endpoint without embedded credentials or query parameters."
        )
    headers = {"Content-Type": "application/octet-stream"}
    token = os.environ.get("GIVELIFE_BACKUP_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        url.rstrip("/") + "/" + path.name, data=path.read_bytes(), headers=headers, method="PUT"
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if not 200 <= response.status < 300:
            raise ValueError("Off-site backup was not accepted.")
    _last["offsite_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()


def start(store, data):
    if not os.environ.get("GIVELIFE_STORAGE_KEY") or not os.environ.get("GIVELIFE_BACKUP_URL"):
        LOG.warning("backup_not_configured: encrypted off-site backups are not active")
        return

    def run():
        while True:
            try:
                path = create(store, Path(data) / "encrypted-backups")
                upload(path)
                LOG.info("offsite_backup_completed")
            except Exception as exc:
                _last["error"] = type(exc).__name__
                LOG.error("offsite_backup_failed error_type=%s", type(exc).__name__)
            threading.Event().wait(24 * 3600)

    threading.Thread(target=run, daemon=True, name="encrypted-backup").start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p = sub.add_parser("create")
    p.add_argument("directory")
    p = sub.add_parser("restore")
    p.add_argument("snapshot")
    p.add_argument("new_database")
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(status(), indent=2))
    elif args.command == "restore":
        restore(args.snapshot, args.new_database)
        print("Restored into new database. No service was started; review pending jobs before use.")
    else:
        from persist import configured_store

        print(create(configured_store(), args.directory))
