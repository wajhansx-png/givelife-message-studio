import os, queue, threading
from contextlib import contextmanager

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # local preview without the cloud database
    psycopg = Jsonb = None


class CloudStore:
    def __init__(self, uri):
        self.uri = uri
        self._pool = queue.LifoQueue(maxsize=6)
        self._slots = threading.BoundedSemaphore(6)

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


def configured_store():
    uri = os.environ.get("DB_URI")
    return CloudStore(uri) if uri else None
