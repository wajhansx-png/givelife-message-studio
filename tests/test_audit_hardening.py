import http.client
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import test_manual_sends as fixture
from persist import SqliteStore

app = fixture.app


class HttpHardening(unittest.TestCase):
    def test_every_response_blocks_untrusted_framing(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), app.Handler) as srv:
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                for path in ["/health", "/new", "/donors", "/ops/status", "/ops/backup"]:
                    c = http.client.HTTPConnection("127.0.0.1", srv.server_port)
                    c.request("GET", path)
                    r = c.getresponse()
                    r.read()
                    self.assertIn(
                        "frame-ancestors 'self'", r.getheader("Content-Security-Policy", "")
                    )
                    c.close()
                    if path.startswith("/ops/"):
                        self.assertEqual(r.status, 401)
            finally:
                srv.shutdown()

    def test_errors_are_logged_without_credentials_and_keep_safe_reply(self):
        h = app.Handler.__new__(app.Handler)
        h.path = "/donors?private=secret"
        h.command = "GET"
        h.response_sent = False
        out = []
        h.reply = lambda b, **kw: out.append((b, kw.get("status", 200)))
        with patch.object(h, "_get", side_effect=RuntimeError("DO_NOT_LOG_PRIVATE_CONTENT")):
            with self.assertLogs("givelife.ops", level="ERROR") as logs:
                h.do_GET()
        self.assertEqual(out[0][1], 500)
        self.assertIn("RuntimeError", " ".join(logs.output))
        self.assertNotIn("DO_NOT_LOG_PRIVATE_CONTENT", " ".join(logs.output))
        self.assertNotIn("private=secret", " ".join(logs.output))


class StorageHardening(unittest.TestCase):
    def test_private_value_encrypted_and_reopens(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "s" * 48}),
        ):
            p = Path(d) / "db.sqlite"
            s = SqliteStore(p)
            s.initialize()
            s.put("notes", {"text": "PRIVATE_NOTE_SENTINEL"})
            self.assertFalse(
                b"PRIVATE_NOTE_SENTINEL" in p.read_bytes(), "private note remains readable"
            )
            t = SqliteStore(p)
            t.initialize()
            self.assertEqual(t.get("notes"), {"text": "PRIVATE_NOTE_SENTINEL"})

    def test_existing_plaintext_migrates_without_losing_content_or_leases(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "db.sqlite"
            with patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": ""}):
                s = SqliteStore(p)
                s.initialize()
                s.put("notes", {"text": "LEGACY_PRIVATE_NOTE"})
                s.lease_acquire("wa_lease", "owner", 45)
            with patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "s" * 48}):
                t = SqliteStore(p)
                t.initialize()
                self.assertEqual(t.get("notes"), {"text": "LEGACY_PRIVATE_NOTE"})
                self.assertTrue(t.lease_acquire("wa_lease", "owner", 45))
                self.assertFalse(
                    b"LEGACY_PRIVATE_NOTE" in p.read_bytes(), "legacy note remains readable"
                )

    def test_wrong_key_does_not_erase_or_replace_private_data(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "db.sqlite"
            with patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "s" * 48}):
                s = SqliteStore(p)
                s.initialize()
                s.put("notes", {"text": "secret"})
            with patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "t" * 48}):
                with self.assertRaises(ValueError):
                    SqliteStore(p).initialize()
            with patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "s" * 48}):
                t = SqliteStore(p)
                t.initialize()
                self.assertEqual(t.get("notes"), {"text": "secret"})


class BackupHardening(unittest.TestCase):
    def test_snapshot_restores_to_new_database_and_never_overwrites_existing(self):
        import backups

        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "k" * 48}),
        ):
            p = Path(d)
            s = SqliteStore(p / "original.sqlite")
            s.initialize()
            s.put("notes", {"text": "BACKUP_PRIVATE_SENTINEL"})
            backup = backups.create(s, p / "backups")
            self.assertFalse(b"BACKUP_PRIVATE_SENTINEL" in backup.read_bytes())
            restored = backups.restore(backup, p / "restore.sqlite")
            self.assertEqual(restored.get("notes"), {"text": "BACKUP_PRIVATE_SENTINEL"})
            with self.assertRaises(FileExistsError):
                backups.restore(backup, p / "original.sqlite")

    def test_corrupt_backup_never_creates_a_destination(self):
        import backups

        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "k" * 48}),
        ):
            p = Path(d)
            s = SqliteStore(p / "source.sqlite")
            s.initialize()
            s.put("notes", {"text": "secret"})
            backup = backups.create(s, p / "backups")
            data = bytearray(backup.read_bytes())
            data[-1] ^= 1
            backup.write_bytes(data)
            with self.assertRaises(ValueError):
                backups.restore(backup, p / "restore.sqlite")
            self.assertFalse((p / "restore.sqlite").exists())


class LoadHardening(unittest.TestCase):
    def test_overload_is_rejected_and_capacity_recovers(self):
        from http.server import BaseHTTPRequestHandler
        import http_runtime

        entered = threading.Event()
        release = threading.Event()

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/wait":
                    entered.set()
                    release.wait(3)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass

        srv = http_runtime.BoundedHTTPServer(("127.0.0.1", 0), H, max_workers=1)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        c = http.client.HTTPConnection("127.0.0.1", srv.server_port)
        c.request("GET", "/wait")
        self.assertTrue(entered.wait(1))
        try:
            other = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=1)
            other.request("GET", "/")
            r = other.getresponse()
            r.read()
            self.assertEqual(r.status, 503)
            self.assertEqual(r.getheader("Retry-After"), "5")
            other.close()
            release.set()
            self.assertEqual(c.getresponse().status, 200)
        finally:
            c.close()
            release.set()
            srv.shutdown()
            srv.server_close()


class GatewayKeys(unittest.TestCase):
    def test_encrypted_gateway_cache_survives_a_new_instance(self):
        import key_cache

        class Store:
            data = {}

            def get(self, k, d=None):
                return self.data.get(k, d)

            def put(self, k, v):
                self.data[k] = v

        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "k" * 48}),
        ):
            p = Path(d)
            source = p / "keys.sqlite"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE keys(value TEXT)")
                db.execute("INSERT INTO keys VALUES('PRIVATE_GATEWAY_KEY')")
            s = Store()
            key_cache.save(s, source)
            self.assertNotIn("PRIVATE_GATEWAY_KEY", str(s.data))
            target = p / "new-instance.sqlite"
            self.assertTrue(key_cache.restore(s, target))
            with sqlite3.connect(target) as db:
                self.assertEqual(
                    db.execute("SELECT value FROM keys").fetchone()[0], "PRIVATE_GATEWAY_KEY"
                )
            self.assertFalse(
                key_cache.restore(s, target), "an existing working key cache is never replaced"
            )


if __name__ == "__main__":
    unittest.main()
