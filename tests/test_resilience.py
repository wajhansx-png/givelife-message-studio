"""Failure scenarios for restarts, deploy overlap and database outages (all simulated)."""

import http.client
import os
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import supervisor
from persist import CloudStore


class FakeLeaseStore:
    """Same rules as CloudStore.lease_acquire: free, ours, or stale (older than ttl) can be taken."""

    def __init__(self):
        self.owner, self.beat, self.now, self.down = None, -1e9, 0.0, False
        self.lock = threading.Lock()

    def lease_acquire(self, key, owner, ttl):
        with self.lock:
            if self.down:
                raise OSError("database down")
            if self.owner in (None, owner) or self.now - self.beat > ttl:
                self.owner, self.beat = owner, self.now
                return True
            return False

    def lease_release(self, key, owner):
        with self.lock:
            if self.owner == owner:
                self.beat = -1e9

    def initialize(self):
        if self.down:
            raise OSError("database down")


class LeaseTests(unittest.TestCase):
    def test_new_instance_waits_for_old_one_then_takes_over(self):
        store = FakeLeaseStore()
        self.assertEqual(supervisor.acquire_lease(store, "old", max_wait=0), "acquired")
        ticks = []

        def sleep(_):
            ticks.append(1)
            if len(ticks) == 3:  # the old instance shuts down and releases
                store.lease_release("wa_lease", "old")

        clock = iter(range(1000)).__next__
        result = supervisor.acquire_lease(store, "new", max_wait=100, sleep=sleep, clock=clock)
        self.assertEqual(result, "acquired")
        self.assertEqual(store.owner, "new")
        self.assertEqual(len(ticks), 3)

    def test_crashed_instance_lease_goes_stale_and_is_taken(self):
        store = FakeLeaseStore()
        supervisor.acquire_lease(store, "dead", max_wait=0)
        store.now = 46  # no heartbeat for longer than the ttl
        self.assertEqual(supervisor.acquire_lease(store, "new", max_wait=0), "acquired")

    def test_live_old_instance_is_not_stolen_from(self):
        store = FakeLeaseStore()
        supervisor.acquire_lease(store, "old", max_wait=0)
        store.now = 20  # heartbeat still fresh
        self.assertEqual(supervisor.acquire_lease(store, "new", max_wait=0), "timeout")
        self.assertEqual(store.owner, "old")

    def test_wait_is_bounded_so_the_app_still_starts(self):
        store = FakeLeaseStore()
        supervisor.acquire_lease(store, "stuck", max_wait=0)
        clock = iter(range(1000)).__next__
        result = supervisor.acquire_lease(
            store, "new", max_wait=5, sleep=lambda _: None, clock=clock
        )
        self.assertEqual(result, "timeout")

    def test_broken_lease_table_fails_open(self):
        store = FakeLeaseStore()
        store.down = True
        result = supervisor.acquire_lease(store, "new", max_wait=100, sleep=lambda _: None)
        self.assertEqual(result, "unavailable")

    def test_keeper_heartbeats_and_reports_a_takeover(self):
        store, lost = FakeLeaseStore(), threading.Event()
        supervisor.acquire_lease(store, "me", max_wait=0)
        keeper = supervisor.LeaseKeeper(store, "me", every=0.01, on_lost=lost.set)
        keeper.start()
        time.sleep(0.1)
        self.assertFalse(lost.is_set())
        store.down = True  # a database blip is not a takeover
        time.sleep(0.05)
        self.assertFalse(lost.is_set())
        store.down = False
        store.owner = "someone-else"
        store.beat = store.now
        self.assertTrue(lost.wait(2))
        keeper.release()

    def test_release_lets_the_next_instance_in_at_once(self):
        store = FakeLeaseStore()
        keeper = supervisor.LeaseKeeper(store, "old")
        supervisor.acquire_lease(store, "old", max_wait=0)
        keeper.release()
        self.assertEqual(supervisor.acquire_lease(store, "new", max_wait=0), "acquired")


class WaitingTests(unittest.TestCase):
    def test_health_passes_while_waiting_but_nothing_else_is_served(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        waiting = supervisor.Waiting(port, host="127.0.0.1")
        try:
            for path, code in (("/health", 200), ("/", 503), ("/state", 503)):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                c.request("GET", path)
                self.assertEqual(c.getresponse().status, code, path)
        finally:
            waiting.close()
        with socket.socket() as s:  # port is free again for the real server
            s.bind(("127.0.0.1", port))


class FakeProc:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


class ChildTests(unittest.TestCase):
    def make(self, procs, **kw):
        it = iter(procs)
        return supervisor.Child(
            "x", lambda: next(it), sleep=lambda _: None, log=lambda *_: None, **kw
        )

    def test_crashed_process_is_restarted_and_healthy_one_left_alone(self):
        child = self.make([FakeProc(1), FakeProc()])
        self.assertEqual(child.check(), "restarted")
        self.assertEqual(child.check(), "ok")

    def test_crash_loop_gives_up_so_the_container_restarts(self):
        child = self.make([FakeProc(1)] * 10, max_crashes=3)
        results = [child.check() for _ in range(3)]
        self.assertEqual(results, ["restarted", "restarted", "giveup"])

    def test_old_crashes_do_not_count_forever(self):
        now = [0.0]
        it = iter([FakeProc(1)] * 20)
        child = supervisor.Child(
            "x",
            lambda: next(it),
            max_crashes=3,
            window=100,
            clock=lambda: now[0],
            sleep=lambda _: None,
            log=lambda *_: None,
        )
        for _ in range(6):
            now[0] += 200
            self.assertEqual(child.check(), "restarted")

    def test_backoff_grows_and_is_capped(self):
        b = supervisor.Backoff(2, 30)
        self.assertEqual([b.next() for _ in range(6)], [2, 4, 8, 16, 30, 30])
        b.reset()
        self.assertEqual(b.next(), 2)


class WhatsAppStateTests(unittest.TestCase):
    def test_states(self):
        w = supervisor.wa_state
        self.assertEqual(w({"is_logged_in": True, "is_connected": True}), "ok")
        self.assertEqual(w({"is_logged_in": True, "is_connected": False}), "dropped")
        self.assertEqual(w({"is_logged_in": False, "is_connected": False}), "logged_out")
        self.assertEqual(w({}), "logged_out")


class FlakyStore(CloudStore):
    def __init__(self):
        super().__init__("postgres://unused")
        self.rows, self.fail = {}, True

    def put(self, key, value):
        if self.fail:
            raise OSError("database down")
        self.rows[key] = value


class WriteRetryTests(unittest.TestCase):
    def wait_for(self, cond, secs=3):
        end = time.time() + secs
        while time.time() < end and not cond():
            time.sleep(0.01)
        return cond()

    def test_failed_write_is_kept_and_saved_when_database_returns(self):
        store = FlakyStore()
        with self.assertRaises(OSError):  # the caller still hears about the failure
            store.put_retry("drafts", "v1", every=0.02)
        self.assertEqual(store.pending_writes, 1)
        store.fail = False
        self.assertTrue(self.wait_for(lambda: store.rows.get("drafts") == "v1"))
        self.assertTrue(self.wait_for(lambda: store.pending_writes == 0))

    def test_only_latest_value_per_key_is_retried_and_never_overwrites_newer(self):
        store = FlakyStore()
        for v in ("v1", "v2"):
            with self.assertRaises(OSError):
                store.put_retry("campaign", v, every=0.02)
        store.fail = False
        store.put_retry("campaign", "v3")  # newer successful write supersedes the pending one
        time.sleep(0.15)
        self.assertEqual(store.rows["campaign"], "v3")
        self.assertEqual(store.pending_writes, 0)

    def test_healthy_database_needs_no_retry(self):
        store = FlakyStore()
        store.fail = False
        store.put_retry("hold", "x")
        self.assertEqual((store.rows, store.pending_writes), ({"hold": "x"}, 0))


class BootTests(unittest.TestCase):
    def test_boot_waits_out_a_database_outage(self):
        store, calls = FakeLeaseStore(), []
        store.down = True

        def sleep(_):
            calls.append(1)
            if len(calls) == 3:
                store.down = False

        self.assertTrue(
            supervisor.wait_for_db(
                store, sleep=sleep, clock=iter(range(1000)).__next__, log=lambda *_: None
            )
        )
        self.assertEqual(len(calls), 3)

    def test_boot_gives_up_if_database_never_returns(self):
        store = FakeLeaseStore()
        store.down = True
        self.assertFalse(
            supervisor.wait_for_db(
                store,
                max_wait=5,
                sleep=lambda _: None,
                clock=iter(range(1000)).__next__,
                log=lambda *_: None,
            )
        )


if __name__ == "__main__":
    unittest.main()
