"""Failure isolation and recovery: crashes mid-write, a failing GET, unbounded job tables."""

import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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


if __name__ == "__main__":
    unittest.main()
