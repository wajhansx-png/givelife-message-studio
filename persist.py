from storage_crypto import ValueCipher
from pathlib import Path
import sqlite3
import json
import os, queue, threading, time
from contextlib import contextmanager

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # local preview without the cloud database
    psycopg = Jsonb = None


def atomic_write(path, text):
    """Write a state file so a crash or restart mid-write can never leave a truncated file:
    the new content goes to a temporary file first, then replaces the old one in one step."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


class CloudStore:
    def __init__(self, uri):
        self.uri = uri
        self._pool = queue.LifoQueue(maxsize=6)
        self._slots = threading.BoundedSemaphore(6)
        self._pending, self._wlock, self._retrying = {}, threading.RLock(), False

    @contextmanager
    def connection(self):
        if not self._slots.acquire(timeout=10):
            raise RuntimeError("Database is busy. Try again shortly.")
        db = None
        try:
            try:
                db = self._pool.get_nowait()
            except queue.Empty:
                pass
            if db is None or db.closed:
                db = psycopg.connect(self.uri, connect_timeout=15, autocommit=True)
            try:
                yield db
            except Exception:
                db.close()
                db = None
                while True:
                    try:
                        self._pool.get_nowait().close()
                    except queue.Empty:
                        break
                raise
        finally:
            if db is not None and not db.closed:
                self._pool.put_nowait(db)
            self._slots.release()

    def initialize(self):
        with self.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS givelife_studio_state (key TEXT PRIMARY KEY, value JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
            )

    def get(self, key, default=None):
        for attempt in range(2):
            try:
                with self.connection() as db:
                    row = db.execute(
                        "SELECT value FROM givelife_studio_state WHERE key=%s", (key,)
                    ).fetchone()
                break
            except psycopg.OperationalError:
                if attempt:
                    raise
        return row[0] if row else default

    def get_many(self, keys):
        for attempt in range(2):
            try:
                with self.connection() as db:
                    rows = db.execute(
                        "SELECT key,value FROM givelife_studio_state WHERE key = ANY(%s)",
                        (list(keys),),
                    ).fetchall()
                break
            except psycopg.OperationalError:
                if attempt:
                    raise
        return dict(rows)

    def put(self, key, value):
        with self.connection() as db:
            db.execute(
                "INSERT INTO givelife_studio_state (key,value) VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()",
                (key, Jsonb(value)),
            )

    def seed(self, key, value):
        with self.connection() as db:
            db.execute(
                "INSERT INTO givelife_studio_state (key,value) VALUES (%s,%s) ON CONFLICT(key) DO NOTHING",
                (key, Jsonb(value)),
            )

    def claim(self, key, value):
        """Reserve one occurrence across overlapping deploy processes, without replacing its owner."""
        with self.connection() as db:
            row = db.execute(
                "INSERT INTO givelife_studio_state (key,value) VALUES (%s,%s) ON CONFLICT(key) DO NOTHING RETURNING key",
                (key, Jsonb(value)),
            ).fetchone()
        return row is not None

    def lease_acquire(self, key, owner, ttl):
        """Take or refresh a single-owner lease. True if `owner` holds it now.
        Uses the database clock, so instances with different clocks agree."""
        with self.connection() as db:
            row = db.execute(
                "INSERT INTO givelife_studio_state AS s (key,value) VALUES (%s,%s) "
                "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW() "
                "WHERE s.value->>'owner'=%s OR s.updated_at < NOW() - %s::float8 * INTERVAL '1 second' "
                "RETURNING key",
                (key, Jsonb({"owner": owner}), owner, float(ttl)),
            ).fetchone()
        return row is not None

    def lease_release(self, key, owner):
        with self.connection() as db:
            db.execute(
                "UPDATE givelife_studio_state SET updated_at=to_timestamp(0) WHERE key=%s AND value->>'owner'=%s",
                (key, owner),
            )

    def put_retry(self, key, value, every=15):
        """put(), but a failed write is kept (latest value per key wins) and retried in
        the background until the database accepts it. Still raises so callers can report it."""
        with self._wlock:
            try:
                self.put(key, value)
            except Exception:
                self._pending[key] = value
                if not self._retrying:
                    self._retrying = True
                    threading.Thread(
                        target=self._retry_loop, args=(every,), daemon=True, name="db-retry"
                    ).start()
                raise
            self._pending.pop(key, None)  # a newer successful write supersedes older ones

    @property
    def pending_writes(self):
        return len(self._pending)

    def _retry_loop(self, every):
        try:
            while True:
                time.sleep(every)
                for key in list(self._pending):
                    with self._wlock:
                        if key not in self._pending:
                            continue
                        try:
                            self.put(key, self._pending[key])
                        except Exception:
                            break
                        self._pending.pop(key, None)
                with self._wlock:
                    if not self._pending:
                        self._retrying = False
                        return
        finally:
            self._retrying = (
                False  # if this thread ever dies, the next failed write starts a new one
            )

    def restore(self, data, root):
        self.initialize()
        for file, key in [
            ("drafts.json", "drafts"),
            ("state.md", "campaign"),
            ("variant-state.json", "variants"),
        ]:
            seed = (
                (root / file).read_text(encoding="utf-8")
                if (root / file).exists()
                else '{"index":0}'
            )
            self.seed(key, seed)
            (data / file).write_text(self.get(key), encoding="utf-8")


class SqliteStore:
    """Zero-dependency, thread-safe, crash-resilient store when cloud Postgres/Neon is absent.
    Preserves all knowledge, drafts, notes, and leases across restarts."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        self.cipher = ValueCipher()
        self._lock = threading.RLock()
        self._pending = {}

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        try:
            conn.execute("PRAGMA secure_delete=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        with self._lock, self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS givelife_studio_state ("
                "key TEXT PRIMARY KEY, "
                "value TEXT NOT NULL, "
                "updated_at REAL NOT NULL)"
            )
            # Automatic recovery: restore existing assistant-knowledge, drafts, etc.
            self._recover_records(conn)
            migrated = False
            if self.cipher.key:
                for key, raw in conn.execute("SELECT key,value FROM givelife_studio_state"):
                    # Leases must stay readable by the atomic ownership predicates.
                    try:
                        lease = (
                            set(json.loads(raw)) == {"owner"}
                            if isinstance(json.loads(raw), dict)
                            else False
                        )
                    except (ValueError, TypeError):
                        lease = False
                    if self.cipher.encrypted(raw):
                        self.cipher.decode(raw, key)  # reject a wrong key before serving anything
                    elif not lease:
                        migrated = True
                        conn.execute(
                            "UPDATE givelife_studio_state SET value=? WHERE key=?",
                            (self.cipher.encode(raw, key), key),
                        )
        if self.cipher.key and migrated:
            # Remove old plaintext cells, freelist pages and WAL remnants after migration.
            with self._lock, sqlite3.connect(self.db_path) as conn:
                conn.execute("VACUUM")
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _recover_records(self, conn):
        try:
            parent = Path(self.db_path).parent
            # 1. Recover assistant-knowledge
            row = conn.execute(
                "SELECT 1 FROM givelife_studio_state WHERE key='assistant_knowledge'"
            ).fetchone()
            if not row:
                for cand in (
                    parent / "assistant-knowledge.json",
                    parent.parent / "assistant-knowledge.json",
                ):
                    if cand.exists():
                        raw = cand.read_text(encoding="utf-8").strip()
                        if raw:
                            conn.execute(
                                "INSERT INTO givelife_studio_state (key, value, updated_at) VALUES (?, ?, ?)",
                                ("assistant_knowledge", raw, time.time()),
                            )
                            break
        except Exception:
            pass

    def get(self, key, default=None):
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM givelife_studio_state WHERE key=?", (key,)
            ).fetchone()
            if not row:
                return default
            val = self.cipher.decode(row[0], key)
            try:
                return json.loads(val)
            except Exception:
                return val

    def get_many(self, keys):
        if not keys:
            return {}
        with self._lock, self._conn() as conn:
            q = ",".join("?" for _ in keys)
            rows = conn.execute(
                f"SELECT key, value FROM givelife_studio_state WHERE key IN ({q})", list(keys)
            ).fetchall()
            out = {}
            for k, v in rows:
                v = self.cipher.decode(v, k)
                try:
                    out[k] = json.loads(v)
                except Exception:
                    out[k] = v
            return out

    def put(self, key, value):
        raw = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        raw = self.cipher.encode(raw, key)
        now = time.time()
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO givelife_studio_state (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, raw, now),
            )

    def seed(self, key, value):
        raw = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        raw = self.cipher.encode(raw, key)
        now = time.time()
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO givelife_studio_state (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO NOTHING",
                (key, raw, now),
            )

    def claim(self, key, value):
        raw = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        raw = self.cipher.encode(raw, key)
        now = time.time()
        with self._lock, self._conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO givelife_studio_state (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, raw, now),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def lease_acquire(self, key, owner, ttl=45):
        now = time.time()
        raw = json.dumps({"owner": owner})
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT value, updated_at FROM givelife_studio_state WHERE key=?", (key,)
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO givelife_studio_state (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, raw, now),
                )
                return True
            cur_val, updated_at = row
            try:
                cur_owner = json.loads(cur_val).get("owner")
            except Exception:
                cur_owner = None
            if cur_owner == owner or (now - updated_at) >= float(ttl):
                conn.execute(
                    "UPDATE givelife_studio_state SET value=?, updated_at=? WHERE key=?",
                    (raw, now, key),
                )
                return True
            return False

    def lease_release(self, key, owner):
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE givelife_studio_state SET updated_at=0 WHERE key=? AND value LIKE ?",
                (key, f'%"owner": "{owner}"%'),
            )

    def put_retry(self, key, value, every=15):
        """put(), but a failed write (disk briefly full or locked) is kept and retried in the background."""
        with self._lock:
            try:
                self.put(key, value)
            except Exception:
                self._pending[key] = value
                if not getattr(self, "_retrying", False):
                    self._retrying = True
                    threading.Thread(
                        target=self._retry_loop, args=(every,), daemon=True, name="db-retry"
                    ).start()
                raise
            self._pending.pop(key, None)

    @property
    def pending_writes(self):
        return len(self._pending)

    def _retry_loop(self, every):
        try:
            while True:
                time.sleep(every)
                with self._lock:
                    for key in list(self._pending):
                        try:
                            self.put(key, self._pending[key])
                        except Exception:
                            break
                        self._pending.pop(key, None)
                    if not self._pending:
                        return
        finally:
            self._retrying = False

    def restore(self, data, root):
        self.initialize()
        for file, key in [
            ("drafts.json", "drafts"),
            ("state.md", "campaign"),
            ("variant-state.json", "variants"),
        ]:
            seed = (
                (root / file).read_text(encoding="utf-8")
                if (root / file).exists()
                else '{"index":0}'
            )
            self.seed(key, seed)
            (data / file).write_text(str(self.get(key) or seed), encoding="utf-8")


def configured_store():
    uri = os.environ.get("DB_URI")
    if uri:
        return CloudStore(uri)
    # Resilient local persistent SQLite store when Neon/cloud Postgres was removed
    data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "studio_state.sqlite"
    store = SqliteStore(db_file)
    store.initialize()
    return store
