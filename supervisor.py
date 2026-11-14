"""Process supervision and WhatsApp single-owner lease for the Render container.

Why: during a deploy Render runs the new and old instance together. Two copies logged in to the
same WhatsApp device fight over it. The lease lets only one copy connect; the new one waits until
the old one has shut down (or its heartbeat went stale). Every helper here fails open: a problem
with the lease itself must never stop the app from starting.
"""

import http.server
import json
import threading
import time

LEASE_KEY = "wa_lease"


class Backoff:
    def __init__(self, base=2.0, cap=60.0):
        self.base, self.cap, self.n = base, cap, 0

    def next(self):
        delay = min(self.cap, self.base * (2**self.n))
        self.n += 1
        return delay

    def reset(self):
        self.n = 0


def wait_for_db(store, max_wait=600, sleep=None, clock=None, log=print):
    """Initialise the store, retrying while the database is unreachable. True on success."""
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    start, backoff = clock(), Backoff(2, 30)
    while True:
        try:
            store.initialize()
            return True
        except Exception as e:
            if clock() - start >= max_wait:
                return False
            delay = backoff.next()
            log("[launcher] database not ready (%s); retrying in %ds" % (type(e).__name__, delay))
            sleep(delay)


def acquire_lease(
    store,
    owner,
    ttl=45,
    max_wait=180,
    poll=3,
    on_wait=None,
    sleep=None,
    clock=None,
):
    """'acquired' | 'timeout' | 'unavailable'. Never raises, never waits longer than max_wait."""
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    start, errors = clock(), 0
    while True:
        try:
            if store.lease_acquire(LEASE_KEY, owner, ttl):
                return "acquired"
            errors = 0
        except Exception:
            errors += 1
            if errors >= 5:
                return "unavailable"
        if clock() - start >= max_wait:
            return "timeout"
        if on_wait:
            on_wait()
        sleep(poll)


class LeaseKeeper(threading.Thread):
    """Refreshes the lease while we run. Calls on_lost() if another instance took it over."""

    def __init__(self, store, owner, ttl=45, every=10, on_lost=None):
        super().__init__(daemon=True, name="lease-keeper")
        self.store, self.owner, self.ttl, self.every = store, owner, ttl, every
        self.on_lost = on_lost
        self.stopped = threading.Event()
        self.lost = False

    def run(self):
        while not self.stopped.wait(self.every):
            try:
                if not self.store.lease_acquire(LEASE_KEY, self.owner, self.ttl):
                    self.lost = True
                    if self.on_lost:
                        self.on_lost()
                    return
            except Exception:
                pass  # database blip: try again next beat

    def release(self):
        self.stopped.set()
        try:
            self.store.lease_release(LEASE_KEY, self.owner)
        except Exception:
            pass


class Waiting:
    """Answers Render's health check while this instance waits for the old one to let go.
    /health is 200 (so the deploy can finish and the old instance gets shut down); everything
    else is 503 so nobody sees a half-started app."""

    def __init__(self, port, host="0.0.0.0"):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                ok = self.path.split("?")[0] == "/health"
                body = json.dumps({"ok": ok, "starting": True}).encode()
                self.send_response(200 if ok else 503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "5")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_HEAD = do_GET

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer((host, port), H)
        threading.Thread(target=self.server.serve_forever, daemon=True, name="waiting").start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Child:
    """One supervised process. check() restarts it with backoff if it died, and gives up when
    it keeps crashing so the whole container is restarted instead of looping forever."""

    def __init__(
        self,
        name,
        start,
        proc=None,
        max_crashes=5,
        window=600,
        clock=None,
        sleep=None,
        log=print,
    ):
        self.name, self.start, self.max_crashes, self.window = name, start, max_crashes, window
        self.clock = clock or (lambda: time.monotonic())
        self.sleep = sleep or (lambda s: time.sleep(s))
        self.log = log
        self.crashes, self.backoff = [], Backoff(2, 30)
        self.proc = proc or start()

    def check(self):
        """'ok' | 'restarted' | 'giveup'"""
        if self.proc.poll() is None:
            return "ok"
        t = self.clock()
        self.crashes = [c for c in self.crashes if t - c < self.window] + [t]
        self.log("[launcher] %s exited (code %s)" % (self.name, self.proc.poll()))
        if len(self.crashes) >= self.max_crashes:
            return "giveup"
        self.sleep(self.backoff.next())
        try:
            self.proc = self.start()
        except Exception as exc:
            # The restart itself failed (no process slot, file gone). That is one more crash, not a reason
            # to take the supervisor down: try again next round, and give up only when it keeps failing.
            self.log("[launcher] %s could not start (%s)" % (self.name, type(exc).__name__))
            self.crashes.append(self.clock())
            return "giveup" if len(self.crashes) >= self.max_crashes else "failed"
        return "restarted"


def wa_state(status):
    """'ok' | 'dropped' (logged in, link down: reconnect) | 'logged_out' (needs a QR code)."""
    if not isinstance(status, dict):
        return "dropped"
    if not status.get("is_logged_in"):
        return "logged_out"
    return "ok" if status.get("is_connected") else "dropped"


class DropWatch:
    """For one WhatsApp link: if it dropped while still logged in, ask it to reconnect after 45 s down, and at most
    every 90 s. A logged-out link is left alone (it needs the owner to link it again)."""

    def __init__(self, wait=45, every=90):
        self.wait, self.every = wait, every
        self.since = None  # when the link was first seen down
        self.last = None  # when a reconnect was last asked for

    def step(self, state, now, reconnect):
        if state == "dropped":
            if self.since is None:
                self.since = now
            if now - self.since >= self.wait and (
                self.last is None or now - self.last >= self.every
            ):
                self.last = now
                reconnect()
                return "asked"
        elif state in ("ok", "logged_out"):
            self.since = None
        return None
