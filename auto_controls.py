"""Reports > Auto: three independent ON/OFF controls. No second sending engine.

- Group Auto drives the existing Auto engine (its schedule, rotation and saved group messages).
- Donor DM Auto and Important Donors Auto each start ONE batch on the existing donor DM engine
  (donor_delivery), tagged with their name. That engine runs one batch at a time, so two controls
  can never contact the same donor at once. A batch that ends, for any reason, switches its control
  OFF: nothing restarts by itself and nothing is ever switched on without the owner pressing ON.
"""

import threading, time, uuid

GROUP, DONOR_DM, IMPORTANT = "group", "donor_dm", "important"
CONTROLS = (GROUP, DONOR_DM, IMPORTANT)
RUNNING = ("Starting", "Sending", "Waiting")
SETTINGS_KEY = "auto_controls_settings"
TITLES = {GROUP: "Group Auto", DONOR_DM: "Donor DM Auto", IMPORTANT: "Important Donors Auto"}
SCOPES = ("important", "top", "donated", "not_donated", "all")

# Important Donors Auto: 8 minutes between DMs, varied by up to 15 seconds either way, batches of 10.
IMPORTANT_GAP_MINUTES, IMPORTANT_BATCH, IMPORTANT_JITTER = 8, 10, {"min": -15, "max": 15}

DEFAULTS = {
    GROUP: {"main_every": None, "freelance_every": None},
    DONOR_DM: {"scope": "important", "follow_up": False, "gap_minutes": None, "batch_size": None},
    IMPORTANT: {
        "count": 20,
        "follow_up": False,
        "include_contacted": False,
        "gap_minutes": IMPORTANT_GAP_MINUTES,
    },
}
FIELDS = {
    GROUP: [
        {
            "key": "main_every",
            "label": "GiveLife group: minutes between posts",
            "type": "number",
            "min": 15,
            "max": 1440,
        },
        {
            "key": "freelance_every",
            "label": "Freelance groups: minutes between posts",
            "type": "number",
            "min": 15,
            "max": 1440,
        },
    ],
    DONOR_DM: [
        {"key": "scope", "label": "Who to message", "type": "select", "options": list(SCOPES)},
        {
            "key": "gap_minutes",
            "label": "Minutes between DMs (empty = your usual)",
            "type": "number",
            "min": 1,
            "max": 10,
        },
        {
            "key": "batch_size",
            "label": "DMs per batch (empty = your usual)",
            "type": "number",
            "min": 1,
            "max": 20,
        },
        {
            "key": "follow_up",
            "label": "Send the saved follow-up after each confirmed DM",
            "type": "check",
        },
    ],
    IMPORTANT: [
        {
            "key": "count",
            "label": "How many Important donors",
            "type": "number",
            "min": 1,
            "max": 1000,
        },
        {
            "key": "gap_minutes",
            "label": "Minutes between DMs (varies by up to 15 seconds)",
            "type": "number",
            "min": 1,
            "max": 10,
        },
        {
            "key": "include_contacted",
            "label": "Also include donors already contacted",
            "type": "check",
        },
        {
            "key": "follow_up",
            "label": "Send the saved follow-up after each confirmed DM",
            "type": "check",
        },
    ],
}


class AutoControls:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()

    # ---- saved settings -------------------------------------------------------------------------
    def _saved(self):
        store = self.app.STORE
        saved = store.get(SETTINGS_KEY) if store else None
        return saved if isinstance(saved, dict) else {}

    def settings(self, which):
        merged = dict(DEFAULTS[which])
        merged.update({k: v for k, v in (self._saved().get(which) or {}).items() if k in merged})
        return merged

    def _normalise(self, which, raw):
        """Only known keys, each checked. Raises ValueError with a plain reason."""
        if not isinstance(raw, dict):
            raise ValueError("Choose settings to change.")
        out = {}
        for field in FIELDS[which]:
            key = field["key"]
            if key not in raw:
                continue
            value = raw[key]
            if field["type"] == "check":
                if type(value) is not bool:
                    raise ValueError("Use the tick box for: " + field["label"])
                out[key] = value
            elif field["type"] == "select":
                if value not in field["options"]:
                    raise ValueError("Choose one of: " + ", ".join(field["options"]))
                out[key] = value
            else:
                if value in (None, ""):
                    if (
                        key in ("gap_minutes", "batch_size", "main_every", "freelance_every")
                        and which != IMPORTANT
                    ):
                        out[key] = None
                        continue
                    raise ValueError("Enter a number for: " + field["label"])
                if type(value) not in (int, float) or isinstance(value, bool) or value != value:
                    raise ValueError("Enter a number for: " + field["label"])
                if not field["min"] <= value <= field["max"]:
                    raise ValueError(f"{field['label']}: choose {field['min']} to {field['max']}.")
                out[key] = int(value) if key != "gap_minutes" else float(value)
        if not out:
            raise ValueError("Choose settings to change.")
        return out

    def _store_settings(self, which, new):
        store = self.app.STORE
        if not store:
            raise ValueError("Persistent storage is unavailable. Settings were not saved.")
        saved = self._saved()
        saved[which] = {**(saved.get(which) or {}), **new}
        store.put(SETTINGS_KEY, saved)

    # ---- reading state --------------------------------------------------------------------------
    def _job(self, which):
        """The newest batch started by this control (it survives restarts: the owner tag is kept)."""
        jobs = self.app.donors().jobs.export_jobs().get("jobs", [])
        return next((j for j in reversed(jobs) if j.get("owner") == which), None)

    def _running_owner(self):
        """Which control (or 'manual') owns the donor DM engine right now, else ''."""
        jobs = self.app.donors().jobs
        if jobs.active:
            job = next(
                (j for j in jobs.export_jobs().get("jobs", []) if j.get("id") == jobs.active), {}
            )
            return job.get("owner") or "manual"
        last = (jobs.export_jobs().get("jobs") or [{}])[-1]
        if last.get("state") == "Interrupted" and last.get("auto"):
            return last.get("owner") or "manual"  # about to resume by itself after a restart
        return ""

    def _dm_view(self, which):
        job, settings = self._job(which), self.settings(which)
        view = {
            "on": False,
            "recipients": 0,
            "sent": 0,
            "pending": 0,
            "next_at": None,
            "state": "OFF",
            "note": "",
        }
        if not job:
            view["note"] = "Not started yet."
            return view
        total = job.get("original_total") or job.get("total") or 0
        seen = {r.get("id") for r in job.get("receipts", [])}
        mine_ids = job.get("ids", [])
        pending = len([i for i in mine_ids if i not in seen])
        state = job.get("state", "")
        running = state in RUNNING or (state == "Interrupted" and job.get("auto"))
        jobs = self.app.donors().jobs
        stopping = running and jobs.active == job.get("id") and jobs.stop.is_set()
        view.update(
            on=running and not stopping,
            recipients=total,
            sent=(job.get("previous_sent") or 0) + (job.get("sent") or 0),
            pending=pending if running else (pending if state in ("Stopped", "Interrupted") else 0),
            next_at=(job.get("next_at") or job.get("next_batch_at")) if running else None,
            state="STOPPING" if stopping else "ON" if running else "OFF",
        )
        if stopping:
            view["note"] = "Switching off after the DM that is being sent."
        elif running:
            view["note"] = {
                "Starting": "Starting now.",
                "Sending": "Sending.",
                "Waiting": "Waiting for the next send.",
                "Interrupted": "The service restarted. It carries on by itself.",
            }.get(state, "")
            if job.get("current"):
                view["note"] = job["current"]
        else:
            view["note"] = {
                "Completed": "Finished.",
                "Stopped": job.get("error")
                or "Switched off. Switch ON to carry on; nobody already contacted is repeated.",
                "Nothing sent": job.get("error") or "Nobody was eligible.",
            }.get(state, job.get("error") or state)
            if any(r.get("state") == "Uncertain" for r in job.get("receipts", [])):
                view["note"] = (
                    view["note"] + " Check the unconfirmed DMs in WhatsApp before sending again."
                ).strip()
        view["batch"] = job.get("batch")
        view["batches"] = job.get("batches")
        return view

    def _group_view(self):
        app = self.app
        on = bool(app.auto_on())
        summary = app.ENGINE.summary()
        paused = summary.get("paused") or {}
        nexts = [n for n in (app.ENGINE.status().get("next") or []) if n.get("due_at")]
        groups = [k for k in (summary.get("group_intervals") or {}) if k not in paused]
        view = {
            "on": on,
            "state": "ON" if on else "OFF",
            "recipients": len(groups),
            "sent": summary.get("posts_today", 0),
            "pending": len(nexts) if on else 0,
            "next_at": min((n["due_at"] for n in nexts), default=None) if on else None,
            "note": "Posts to your groups on the Auto schedule, rotating your saved group messages."
            if on
            else "Switched off. Nothing is posted by Auto.",
        }
        if on and app.read_left() <= 0:
            view["note"] = "The case is complete. Nothing will be posted."
        elif on and app.on_hold():
            view["note"] = "On hold. Nothing is sent until you resume."
        return view

    def view(self):
        out = {"left": self.app.read_left(), "controls": {}}
        for which in CONTROLS:
            body = self._group_view() if which == GROUP else self._dm_view(which)
            settings = self.settings(which)
            if which == GROUP:
                summary = self.app.ENGINE.summary()
                override = summary.get("pace_override")  # the owner's own pace wins over the ladder
                settings = {
                    "main_every": override[0] if override else summary.get("main_every"),
                    "freelance_every": override[1] if override else summary.get("freelance_every"),
                }
            out["controls"][which] = {
                "id": which,
                "title": TITLES[which],
                "settings": settings,
                "fields": FIELDS[which],
                **body,
            }
        return out

    # ---- changing state -------------------------------------------------------------------------
    def set(self, which, on, settings=None):
        if which not in CONTROLS:
            raise ValueError("Unknown control.")
        if type(on) is not bool:
            raise ValueError("Choose ON or OFF.")
        with self.lock:
            if which == GROUP:
                return self._set_group(on)
            return self._start_dm(which, settings) if on else self._stop_dm(which)

    def _set_group(self, on):
        if on and self.app.read_left() <= 0:
            raise ValueError(
                "The case is complete (Rs. 0 left), so Group Auto was not switched on."
            )
        self.app.set_auto(on)
        return self.view()

    def _busy_message(self, which):
        owner = self._running_owner()
        if not owner:
            return ""
        if owner == which:
            return "same"
        name = TITLES.get(owner, "A donor DM batch that you started")
        return (
            f"{name} is sending now. Switch it OFF first: two DM queues never run at the same time."
        )

    def _start_dm(self, which, settings):
        app = self.app
        busy = self._busy_message(which)
        if busy == "same":
            return self.view()  # already ON: pressing ON again never starts a second batch
        if busy:
            raise ValueError(busy)
        if app.CAMPAIGN.get("running"):
            raise ValueError(
                "A DM list is sending now. Stop it first: two DM queues never run at the same time."
            )
        if getattr(app.ENGINE, "dm_running", False):
            raise ValueError(
                "Auto is sending DMs right now. Wait for it to finish, then switch this ON."
            )
        if app.read_left() <= 0:
            raise ValueError("The case is complete (Rs. 0 left), so no DMs were started.")
        if settings:
            self._store_settings(which, self._normalise(which, settings))
        cfg = self.settings(which)
        donors = app.donors()
        follow = True if cfg.get("follow_up") else None
        if follow and not donors.follow_up_text():
            raise ValueError(
                "Write the follow-up in Messages → Follow-Up Message first, or untick it."
            )
        rid = f"auto-{which}-{uuid.uuid4().hex}"
        if which == IMPORTANT:
            minutes = float(cfg.get("gap_minutes") or IMPORTANT_GAP_MINUTES)
            prefs = donors.prefs()
            plan = dict(
                scope="important",
                limit=int(cfg["count"]),
                chunk=IMPORTANT_BATCH,
                gap_seconds=minutes * 60,
                jitter=dict(IMPORTANT_JITTER),
                skip_contacted=not cfg.get("include_contacted"),
                poster=prefs.get("poster", True),
            )
            if prefs.get("rests"):
                plan["rests"] = prefs["rests"]  # the owner's usual pauses between batches
        else:
            prefs = donors.prefs()
            plan = dict(
                scope=cfg.get("scope", "important"),
                chunk=int(cfg["batch_size"] or prefs.get("chunk") or 20),
                gap_seconds=(
                    float(cfg["gap_minutes"]) * 60
                    if cfg.get("gap_minutes")
                    else prefs.get("gap_seconds") or 240
                ),
                poster=prefs.get("poster", True),
                skip_contacted=prefs.get("skip_contacted", True),
            )
            for key in ("rests", "jitter"):
                if prefs.get(key):
                    plan[key] = prefs[key]
        if follow:
            plan["follow_up"] = True
        donors.start_batch(**plan, request_id=rid, owner=which)
        return self.view()

    def _stop_dm(self, which):
        donors = self.app.donors()
        job = self._job(which)
        if not job:
            return self.view()
        if donors.jobs.active and donors.jobs.active == job.get("id"):
            donors.jobs.cancel()  # the DM being sent finishes; the rest stays saved
        elif job.get("state") == "Interrupted":
            donors.jobs._update(job["id"], state="Stopped", error="Switched off by the owner.")
        return self.view()

    def edit(self, which, settings):
        """Save new settings. For a batch that is sending, the changes apply to the sends still to come: the
        same batch carries on, nothing is restarted and nobody is sent to twice."""
        if which not in CONTROLS:
            raise ValueError("Unknown control.")
        with self.lock:
            if which == GROUP:
                clean = self._normalise(which, settings)
                now = self.app.ENGINE.summary()
                self.app.ENGINE.set_pace(
                    clean.get("main_every") or now.get("main_every"),
                    clean.get("freelance_every") or now.get("freelance_every"),
                )
                return self.view()
            clean = self._normalise(which, settings)
            donors = self.app.donors()
            job = self._job(which)
            live = bool(job and donors.jobs.active and donors.jobs.active == job.get("id"))
            patch = {}
            if "gap_minutes" in clean and clean["gap_minutes"]:
                patch["gap_seconds"] = clean["gap_minutes"] * 60
            if "batch_size" in clean and clean["batch_size"]:
                patch["chunk"] = clean["batch_size"]
            if "follow_up" in clean:
                if clean["follow_up"] and not donors.follow_up_text():
                    raise ValueError(
                        "Write the follow-up in Messages → Follow-Up Message first, or untick it."
                    )
                patch["follow_up"] = donors.follow_up_text() if clean["follow_up"] else None
            if live and patch:
                donors.jobs.configure(job["id"], patch)
            self._store_settings(
                which, clean
            )  # saved only after the live batch accepted the change
            return self.view()
