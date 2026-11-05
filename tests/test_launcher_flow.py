"""Runs launcher.py against fakes (no database, no WhatsApp, no real processes)."""

import io
import json
import os
import runpy
import signal
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import persist  # noqa: E402,F401  (import before patching so module defaults stay real)
import supervisor  # noqa: E402,F401


class Proc:
    def __init__(self, kind, world):
        self.kind, self.world, self.code, self.stdout = kind, world, None, iter(())
        world.procs.append(self)

    def poll(self):
        return self.code

    def terminate(self):
        self.code = 0
        self.world.events.append("terminate:" + self.kind)

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.code = -9


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class World:
    """One simulated Render container. `script` can act on each 2-second tick."""

    def __init__(self, lease_ok=True):
        self.procs, self.events, self.t, self.ticks = [], [], 1000.0, 0
        self.status = {"is_logged_in": True, "is_connected": True}
        self.lease_ok, self.script, self.max_ticks = lease_ok, None, 60
        self.owner = None
        world = self

        class Store:
            def initialize(s):
                world.events.append("db-init")

            def restore(s, data, root):
                world.events.append("restore")

            def lease_acquire(s, key, owner, ttl):
                world.owner = owner
                if world.lease_ok is True or world.lease_ok == "after-wait" and world.t > 1010:
                    world.events.append("lease-acquired")
                    return True
                return False

            def lease_release(s, key, owner):
                world.events.append("lease-released")

        self.store = Store()

    def sleep(self, secs):
        self.t += secs
        if secs == 2:
            self.ticks += 1
            if self.script:
                self.script(self)
            if self.ticks >= self.max_ticks:
                raise SystemExit("end of simulation")

    def popen(self, args, **kw):
        kind = "gowa" if "whatsapp" in str(args[0]) else "server"
        self.events.append("start:" + kind)
        return Proc(kind, self)

    def urlopen(self, req, timeout=None):
        url = getattr(req, "full_url", req)
        if url.endswith("/devices"):
            return Reply(json.dumps({"results": [{"id": "dev1"}]}).encode())
        if url.endswith("/status"):
            return Reply(json.dumps({"results": self.status}).encode())
        if url.endswith("/app/reconnect"):
            self.events.append("reconnect")
            return Reply(b"{}")
        raise OSError("unexpected " + url)

    def run(self):
        env = {
            "UI_ACCESS_KEY": "k",
            "DB_URI": "postgresql://u:p@db.example/x",
            "DATA_DIR": tempfile.mkdtemp(),
            "PORT": "0",
        }
        handlers = {}
        with (
            mock.patch.dict(os.environ, env),
            mock.patch("persist.configured_store", lambda: self.store),
            mock.patch("subprocess.Popen", self.popen),
            mock.patch("urllib.request.urlopen", self.urlopen),
            mock.patch("time.sleep", self.sleep),
            mock.patch("time.time", lambda: self.t),
            mock.patch("pathlib.Path.mkdir", lambda *a, **k: None),
            mock.patch("shutil.copyfile", lambda *a, **k: None),
            mock.patch("signal.signal", lambda sig, fn: handlers.__setitem__(sig, fn)),
            mock.patch("supervisor.time.monotonic", lambda: self.t),
            mock.patch("supervisor.time.sleep", self.sleep),
            redirect_stdout(io.StringIO()) as out,
        ):
            self.handlers = handlers
            try:
                runpy.run_path(str(ROOT / "launcher.py"), run_name="launcher_under_test")
            except SystemExit:
                pass
        self.out = out.getvalue()
        return self


class LauncherFlowTests(unittest.TestCase):
    def test_normal_boot_starts_gateway_then_server_and_holds_lease(self):
        w = World().run()
        starts = [e for e in w.events if e.startswith("start:")]
        self.assertEqual(starts, ["start:gowa", "start:server"])
        self.assertLess(w.events.index("lease-acquired"), w.events.index("start:gowa"))
        self.assertNotIn("reconnect", w.events)

    def test_gateway_crash_restarts_only_the_gateway(self):
        def crash(w):
            if w.ticks == 5:
                w.procs[0].code = 1

        w = World()
        w.script = crash
        w.run()
        self.assertEqual(w.events.count("start:gowa"), 2)
        self.assertEqual(w.events.count("start:server"), 1)
        self.assertIsNone(w.procs[1].code)  # server kept running

    def test_server_crash_restarts_only_the_server(self):
        def crash(w):
            if w.ticks == 5:
                w.procs[1].code = 1

        w = World()
        w.script = crash
        w.run()
        self.assertEqual(w.events.count("start:server"), 2)
        self.assertEqual(w.events.count("start:gowa"), 1)

    def test_crash_loop_ends_the_container_so_render_restarts_it(self):
        def crash(w):
            for p in w.procs:
                if p.kind == "server" and p.code is None:
                    p.code = 1

        w = World()
        w.script = crash
        w.max_ticks = 500
        w.run()
        self.assertLess(w.ticks, 500)
        self.assertIn("lease-released", w.events)
        self.assertIn("restarting the container", w.out)

    def test_dropped_whatsapp_link_is_reconnected_after_a_grace_period(self):
        def drop(w):
            if w.ticks == 3:
                w.status = {"is_logged_in": True, "is_connected": False}
            if "reconnect" in w.events:
                w.status = {"is_logged_in": True, "is_connected": True}

        w = World()
        w.script = drop
        w.run()
        self.assertEqual(w.events.count("reconnect"), 1)

    def test_logged_out_whatsapp_is_not_hammered_with_reconnects(self):
        w = World()
        w.status = {"is_logged_in": False, "is_connected": False}
        w.run()
        self.assertNotIn("reconnect", w.events)

    def test_brief_blip_is_ignored(self):
        def blip(w):
            w.status = (
                {"is_logged_in": True, "is_connected": False}
                if w.ticks == 15
                else {"is_logged_in": True, "is_connected": True}
            )

        w = World()
        w.script = blip
        w.run()
        self.assertNotIn("reconnect", w.events)

    def test_new_instance_waits_for_old_one_before_starting_whatsapp(self):
        w = World(lease_ok="after-wait").run()
        self.assertIn("waiting for it to stop", w.out)
        self.assertLess(w.events.index("lease-acquired"), w.events.index("start:gowa"))

    def test_shutdown_stops_whatsapp_before_releasing_the_lease(self):
        def term(w):
            if w.ticks == 5:
                w.handlers[signal.SIGTERM]()

        w = World()
        w.script = term
        w.run()
        e = w.events
        self.assertLess(e.index("terminate:gowa"), e.index("lease-released"))
        self.assertLess(e.index("terminate:server"), e.index("lease-released"))


if __name__ == "__main__":
    unittest.main()
