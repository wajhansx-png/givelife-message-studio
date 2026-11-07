"""Donors Auto toggle: one persistent switch that runs the existing donor batch engine on Top donors.

ON  -> DM every Top donor not yet contacted: 10 per batch, 5 min apart (+-15 s), 15 min rest between batches.
OFF -> stop future sends (a DM already in flight may still finish).
The engine does the sending, receipts, restart recovery and never repeating anyone. This class only starts the batch,
follows it, and switches itself OFF when the batch ends or becomes unsafe. It never restarts the whole audience."""

import threading
import time

KEY = "donor_auto"
ORIGIN = "auto_toggle"
GAP_SECONDS = 300
CHUNK = 10
REST_SECONDS = 900
JITTER = {"min": -15, "max": 15}
ALL_DONE = "Everyone in this audience was already contacted"
# Stops that are the owner's own doing or a finished case: nothing for them to do, so no alert.
QUIET_STOPS = ("Sending is on hold", "The case is complete")


class DonorAuto:
    def __init__(self, store, jobs, follow_for, notify=None, busy=None, clock=time.time):
        self.store = store
        self.jobs = jobs
        self.follow_for = follow_for  # True -> saved follow-up text (raises if none); False -> None
        self.notify = notify or (lambda text: None)
        self.busy = busy or (lambda: False)
        self.clock = clock
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ state
    def _state(self):
        raw = self.store.get(KEY) if self.store else None
        return dict(raw) if isinstance(raw, dict) else {}

    def _save(self, **fields):
        state = {**self._state(), **fields}
        if self.store:
            self.store.put(KEY, state)
        return state

    def _mine(self, since=0):
        """The newest job this switch started (or resumed) since it was switched on."""
        jobs = self.jobs.export_jobs().get("jobs", [])
        for job in reversed(jobs):
            if job.get("origin") == ORIGIN and job.get("created_at", 0) >= since:
                return job
        return None

    def _last_sent(self):
        times = [
            r.get("time", 0)
            for j in self.jobs.export_jobs().get("jobs", [])
            if j.get("origin") == ORIGIN
            for r in j.get("receipts", [])
            if r.get("state") == "Sent"
        ]
        return max(times) if times else 0

    def status(self):
        state = self._state()
        return {
            "enabled": bool(state.get("enabled")),
            "note": state.get("note", ""),
            "finished": bool(state.get("finished")),
            "plan": f"Top donors · {CHUNK} per batch · {GAP_SECONDS // 60} min apart · {REST_SECONDS // 60} min rest",
        }

    # ------------------------------------------------------------------ switch
    def set(self, enabled, follow_up=False, poster=True):
        with self.lock:
            if not enabled:
                return self._off()
            if type(poster) is not bool or type(follow_up) is not bool:
                raise ValueError("Poster and follow-up must be on or off.")
            if self._state().get("enabled"):
                return self.status()  # already on: never starts a second batch
            if self.busy():
                raise ValueError("Another DM campaign is running. Stop it first.")
            if self.jobs.active:
                raise ValueError(
                    "A donor batch is already running. Stop it or wait for it to finish, then turn Auto on."
                )
            follow_text = self.follow_for(follow_up)
            since = self.clock() - 1
            latest = self.jobs.export_jobs().get("jobs", [])
            latest = latest[-1] if latest else None
            job = None
            if (
                latest
                and latest.get("origin") == ORIGIN
                and latest.get("state")
                in (
                    "Stopped",
                    "Interrupted",
                )
            ):
                # Continue where Auto left off: people already sent or unconfirmed are skipped, rests are kept.
                job = self.jobs.recover(allow_stopped=True)
            if not job:
                hold = self._last_sent() + GAP_SECONDS
                try:
                    job = self.jobs.start(
                        "top",
                        GAP_SECONDS,
                        limit=1000,
                        chunk=CHUNK,
                        rests=[float(REST_SECONDS)],
                        jitter=dict(JITTER),
                        skip_contacted=True,
                        poster=poster,
                        follow_up=follow_text,
                        hold_until=hold if hold > self.clock() else None,
                        origin=ORIGIN,
                        request_id="auto-toggle-" + format(int(self.clock() * 1000), "x"),
                    )
                except ValueError as e:
                    if str(e).startswith(ALL_DONE):
                        raise ValueError(
                            "Every Top donor has already been contacted. Nothing was started."
                        ) from None
                    if "no donors" in str(e):
                        raise ValueError(
                            "There are no Top donors yet. Mark donors as Top first. Nothing was started."
                        ) from None
                    raise
            self._save(enabled=True, finished=False, note="", started_at=since)
            return {**self.status(), "reply": "Auto is on. Top donors are being messaged."}

    def _off(self):
        state = self._state()
        job = self._mine(state.get("started_at", 0))
        if self.jobs.active and job and job.get("id") == self.jobs.active:
            self.jobs.cancel()
        self._save(enabled=False, finished=False, note="Auto is off. Nothing more will be sent.")
        return {**self.status(), "reply": "Auto is off. Future sends are paused."}

    def disable(self, note, finished=False):
        self._save(enabled=False, finished=finished, note=note)

    def set_options(self, follow_up=None, poster=None):
        """Change follow-up / poster for the running Auto batch; applies to the next sends only."""
        with self.lock:
            state = self._state()
            if not state.get("enabled"):
                return {"applied": False}
            settings = {}
            if poster is not None:
                if type(poster) is not bool:
                    raise ValueError("Poster must be on or off.")
                settings["poster"] = poster
            if follow_up is not None:
                if type(follow_up) is not bool:
                    raise ValueError("Follow-up must be on or off.")
                settings["follow_up"] = self.follow_for(follow_up)
            job = self._mine(state.get("started_at", 0))
            if not settings or not job or self.jobs.active != job.get("id"):
                return {"applied": False}
            self.jobs.configure(job["id"], settings)
            return {"applied": True}

    # ------------------------------------------------------------------ watcher
    def tick(self):
        """Called every few seconds. Follows the batch; switches Auto OFF when it ends. Never starts a new audience."""
        with self.lock:
            state = self._state()
            if not state.get("enabled"):
                return
            self.jobs.status()  # marks a batch cut off by a restart as Interrupted
            job = self._mine(state.get("started_at", 0))
            if self.jobs.active:
                return
            if not job:
                return self.disable("Auto stopped: its batch was not found.")
            kind = job.get("state")
            if kind in ("Starting", "Sending", "Waiting"):
                return
            if kind == "Interrupted":
                try:
                    self.jobs.recover()
                except ValueError:
                    pass
                return
            if kind == "Completed":
                return self.disable(
                    f"Auto finished: {job.get('sent', 0)} Top donors messaged.", True
                )
            if kind == "Nothing sent":
                return self.disable("Auto finished: no Top donor could be messaged.", True)
            error = job.get("error") or ""
            self.disable(
                "Auto paused. " + error if error else "Auto is off. Nothing more will be sent."
            )
            if error and not error.startswith(QUIET_STOPS):
                self.notify("DM Auto stopped and needs you: " + error)
