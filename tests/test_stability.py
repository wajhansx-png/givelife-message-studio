"""Failure isolation and recovery: crashes mid-write, a failing GET, unbounded job tables."""

import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_manual_sends  # noqa: F401  (points DATA_DIR at a temporary folder before server loads)
import persist
import server as app


class AtomicWrite(unittest.TestCase):
    def test_crash_mid_write_keeps_the_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "drafts.json"
            persist.atomic_write(f, "old")
            with patch("persist.os.replace", side_effect=OSError("killed")):
                with self.assertRaises(OSError):
                    persist.atomic_write(f, "new")
            self.assertEqual(f.read_text(), "old")
            self.assertEqual([p.name for p in Path(d).iterdir()], ["drafts.json"])  # no temp litter
            persist.atomic_write(f, "new")
            self.assertEqual(f.read_text(), "new")


class GetIsolation(unittest.TestCase):
    def handler(self, path):
        h = app.Handler.__new__(app.Handler)
        out = []
        h.reply = lambda b, **k: (
            out.append((b, k.get("status", 200))),
            setattr(h, "response_sent", True),
        )
        h.path = path
        return h, out

    def test_failing_get_answers_500_instead_of_dropping_the_connection(self):
        h, out = self.handler("/health")
        with patch.object(app.Handler, "_get", side_effect=RuntimeError("boom")):
            h.do_GET()
        self.assertEqual(out[0][1], 500)

    def test_client_disconnect_is_quiet(self):
        h, out = self.handler("/health")
        with patch.object(app.Handler, "_get", side_effect=BrokenPipeError()):
            h.do_GET()
        self.assertEqual(out, [])

    def test_handler_has_a_socket_timeout(self):
        self.assertTrue(0 < app.Handler.timeout <= 300)


class Pruning(unittest.TestCase):
    def test_finished_entries_are_dropped_but_running_and_protected_stay(self):
        t = {str(i): {"done": True} for i in range(10)}
        t["run"] = {"done": False}
        app.prune_finished(t, 4, protect=("0",))
        self.assertIn("run", t)
        self.assertIn("0", t)
        self.assertLessEqual(len(t), 4)


class SingleRegistry(unittest.TestCase):
    def test_concurrent_first_calls_build_one_donor_registry(self):
        import threading, time, donor_integration

        built = []

        class Slow:
            def __init__(self, module):
                time.sleep(0.05)
                built.append(1)
                self.book = type("B", (), {"store": app.STORE})()

        with (
            patch.object(app, "DONORS", None),
            patch.object(donor_integration, "DonorIntegration", Slow),
        ):
            seen = []
            threads = [threading.Thread(target=lambda: seen.append(app.donors())) for _ in range(8)]
            [t.start() for t in threads]
            [t.join() for t in threads]
        self.assertEqual(len(built), 1)
        self.assertEqual(len({id(x) for x in seen}), 1)


class CorruptStateFiles(unittest.TestCase):
    def test_damaged_drafts_file_is_set_aside_and_never_breaks_a_screen(self):
        import json

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "drafts.json"
            f.write_text('{"group": "half a mess', encoding="utf-8")
            with patch.object(app, "DRAFT", f), patch.object(app, "STORE", None):
                self.assertEqual(app.read_drafts(), {})  # no crash
            self.assertTrue((Path(d) / "drafts.json.corrupt").exists())  # kept for inspection

            f.write_text("[1, 2]", encoding="utf-8")
            good = {"group": "saved text"}

            class Db:
                def get(self, key, default=None):
                    return json.dumps(good)

            with patch.object(app, "DRAFT", f), patch.object(app, "STORE", Db()):
                self.assertEqual(app.read_drafts(), good)  # restored from the database copy
                self.assertEqual(json.loads(f.read_text(encoding="utf-8")), good)
                self.assertEqual(app.read_drafts(), good)

    def test_missing_or_good_drafts_file_reads_normally(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "drafts.json"
            with patch.object(app, "DRAFT", f):
                self.assertEqual(app.read_drafts(), {})
                f.write_text('{"dm": "x"}', encoding="utf-8")
                self.assertEqual(app.read_drafts(), {"dm": "x"})

    def test_damaged_hold_still_blocks_sending_but_resume_clears_it(self):
        with tempfile.TemporaryDirectory() as d:
            hold = Path(d) / "hold.json"
            hold.write_text("{oops", encoding="utf-8")
            with patch.object(app, "HOLD", hold), patch.object(app, "STORE", None):
                self.assertTrue(app.on_hold())  # unreadable = nothing is sent
                app.set_hold(False)
                self.assertFalse(app.on_hold())

    def test_damaged_auto_and_variant_files_do_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            auto = Path(d) / "autopilot.json"
            auto.write_text("not json", encoding="utf-8")
            with patch.object(app, "AUTO", auto):
                self.assertFalse(app.auto_on())
            with patch.object(app, "DATA", Path(d)):
                (Path(d) / "variant-state.json").write_text("###", encoding="utf-8")
                self.assertEqual(app.variant(False), 0)


class StoreRecovery(unittest.TestCase):
    def test_sqlite_write_that_fails_is_kept_and_saved_by_itself(self):
        import time

        with tempfile.TemporaryDirectory() as d:
            store = persist.SqliteStore(Path(d) / "s.sqlite")
            store.initialize()
            real, calls = store.put, []

            def flaky(key, value):
                calls.append(1)
                if len(calls) == 1:
                    raise OSError("disk full")
                return real(key, value)

            store.put = flaky
            with self.assertRaises(OSError):  # the caller still hears about it
                store.put_retry("k", {"x": 1}, every=0.05)
            self.assertEqual(store.pending_writes, 1)
            end = time.monotonic() + 3
            while store.pending_writes and time.monotonic() < end:
                time.sleep(0.05)
            self.assertEqual(store.get("k"), {"x": 1})  # nothing lost
            self.assertEqual(store.pending_writes, 0)


class NoDoubleStart(unittest.TestCase):
    def test_two_quick_dm_list_requests_start_only_one_list(self):
        import threading, time

        started, gate, results = [], threading.Event(), []

        def slow_list(*args):
            started.append(1)
            gate.wait(5)
            app.CAMPAIGN["running"] = False

        body = {"people": [{"phone": "923001234567", "name": "Synthetic"}], "gap_seconds": 90}

        def go():
            try:
                results.append(app.start_campaign(dict(body)))
            except ValueError as exc:
                results.append(str(exc))

        with (
            patch.object(app, "dm_campaign", slow_list),
            patch.object(app, "DONORS", None),
            patch.dict(app.CAMPAIGN, {"running": False}),
        ):
            threads = [threading.Thread(target=go) for _ in range(6)]
            [t.start() for t in threads]
            [t.join(5) for t in threads]
            time.sleep(0.1)
            gate.set()
        self.assertEqual(len(started), 1)  # one list, never two sending to the same people
        self.assertEqual(sum("already sending" in r for r in results), 5)


class SourceHygiene(unittest.TestCase):
    def test_no_stray_control_characters_in_python_source(self):
        # A literal backspace inside a regex (instead of \\b) silently never matched.
        import re

        bad = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
        root = Path(__file__).resolve().parents[1]
        found = [p.name for p in root.glob("*.py") if bad.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
