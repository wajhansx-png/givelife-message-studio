"""One page to run the whole case. A saved, approved plan that is driven through the EXISTING engines.

Nothing here has its own sending loop: Group Auto, the donor DM engine and the volunteer DM engine do every send, so
their guards (opt-outs, gaps, receipts, restart recovery, "never repeat a person") all stay in force.
- Saving the plan never sends. "Start" needs the token of the exact summary the owner saw.
- The approved audience, timing and wording are stored; a restart or a later donor import cannot change them.
- Only one DM queue runs at a time (an engine rule), so approved DM rows run one after another.
- GIKI: DM + saved question first; after a clear "yes" the poster, the screenshot request and the share request.
  An unclear reply waits in "Needs you". Silence is never agreement. An uncertain send is never retried by itself.
- A payment claim is only a claim. Confirming it records the money and the amount left once."""

import copy, hashlib, json, re, threading, time

import autopilot, dm_composer, reply_intent
from donor_book import normalize_phone

KEY = "case_run"
ROWS = ("group", "top", "giki", "volunteers", "important")
DM_ORDER = ("top", "giki", "volunteers", "important")
TITLES = {
    "group": "GiveLife Group",
    "top": "Top Donors",
    "giki": "GIKI",
    "volunteers": "Volunteers",
    "important": "Important Donors",
}
DEFAULTS = {
    "group": {"enabled": True, "every_minutes": 45},
    "top": {"enabled": True, "gap_minutes": 5, "batch_size": 10, "rest_minutes": 20},
    "giki": {"enabled": True, "gap_minutes": 5, "batch_size": 10, "rest_minutes": 20},
    "volunteers": {"enabled": True, "gap_minutes": 5, "batch_size": 10, "rest_minutes": 15},
    "important": {
        "enabled": False,
        "gap_minutes": 8,
        "batch_size": 10,
        "rest_minutes": 20,
        "ids": [],
    },
}
RANGE = {
    "every_minutes": (15, 1440),
    "gap_minutes": (1, 10),
    "batch_size": (1, 20),
    "rest_minutes": (1, 120),
}
JITTER = {"min": -15, "max": 15}
RUNNING = ("Starting", "Sending", "Waiting")
AGREE = re.compile(
    r"(?i)^\W*(yes|yeah|yep|yup|ok(?:ay)?|sure|haan|han|ji|jee|g|theek|thik|zaroor|bilkul|of course|will do)\b"
)
DECLINE = re.compile(r"(?i)^\W*(no|nope|nahi|nahin|na|not now|sorry)\b")
GIKI_SHARES = 3  # poster + caption, screenshot request, share request


def _digest(text):
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def agreement(text):
    """'agree' only for a short, clear yes; 'decline' for a clear no; everything else is the owner's call."""
    t = str(text or "").strip()
    if len(t) > 60:
        return "unclear"
    if AGREE.match(t) and not re.search(r"(?i)\b(but|not|nahi|later)\b", t):
        return "agree"
    if DECLINE.match(t) and not AGREE.search(t):
        return "decline"
    return "unclear"


class CaseRun:
    def __init__(self, app, hub, clock=time.time):
        self.app, self.hub, self.clock = app, hub, clock
        self.lock = threading.RLock()
        self.worker = threading.Lock()

    # ------------------------------------------------------------------ saved state (one record per case)
    def _cid(self):
        return self.hub.cases._load()["current"]

    def _blank(self):
        return {
            "status": "idle",
            "plan": copy.deepcopy(DEFAULTS),
            "approved": None,
            "rows": {},
            "starts": 0,
            "giki": {},
            "needs": {},
            "resolved": [],
            "seen": [],
            "payments": {},
            "checks": {},
            "log": [],
            "cursor": 0,
            "finished": None,
        }

    def _read(self):
        store = self.app.STORE
        raw = (store.get(KEY) if store else None) or {}
        st = raw.get(self._cid()) if isinstance(raw, dict) else None
        blank = self._blank()
        if not isinstance(st, dict):
            return blank
        blank.update(st)
        for key, base in DEFAULTS.items():
            blank["plan"][key] = {**base, **(blank["plan"].get(key) or {})}
        return blank

    def _write(self, st):
        store = self.app.STORE
        if not store:
            raise ValueError("Persistent storage is unavailable. Nothing was saved.")
        raw = store.get(KEY)
        raw = dict(raw) if isinstance(raw, dict) else {}
        st["log"] = st["log"][-60:]
        st["seen"] = st["seen"][-2000:]
        st["resolved"] = st["resolved"][-300:]
        done = [k for k, v in st["needs"].items() if v["state"] != "open"]
        for k in done[:-100]:
            st["needs"].pop(k, None)
        raw[self._cid()] = st
        store.put(KEY, raw)

    def _edit(self, fn):
        with self.lock:
            st = self._read()
            out = fn(st)
            self._write(st)
            return out

    def _log(self, st, text):
        st["log"].append({"at": self.clock(), "text": text})

    # ------------------------------------------------------------------ the plan (saving never sends)
    def set_plan(self, changes):
        if not isinstance(changes, dict):
            raise ValueError("Choose plan settings to save.")

        def apply(st):
            if st["status"] == "running":
                raise ValueError("The plan is running. Pause all first, then change it.")
            if st["status"] == "finished":
                raise ValueError("This case is finished. Start a new case to plan again.")
            plan = st["plan"]
            for key, raw in changes.items():
                if key not in ROWS or not isinstance(raw, dict):
                    raise ValueError("Unknown plan row.")
                row = dict(plan[key])
                for name, value in raw.items():
                    if name == "enabled":
                        if type(value) is not bool:
                            raise ValueError("Use on or off for " + TITLES[key] + ".")
                        row["enabled"] = value
                    elif name == "ids" and key == "important":
                        if not isinstance(value, list) or len(value) > 1000:
                            raise ValueError("Choose the Important donors again.")
                        row["ids"] = [str(i) for i in value]
                    elif name in RANGE and name in DEFAULTS[key]:
                        lo, hi = RANGE[name]
                        if type(value) not in (int, float) or isinstance(value, bool):
                            raise ValueError(f"{TITLES[key]}: enter a number for {name}.")
                        if not lo <= value <= hi:
                            raise ValueError(f"{TITLES[key]}: choose {lo} to {hi}.")
                        row[name] = int(value)
                    else:
                        raise ValueError("Unknown setting for " + TITLES[key] + ".")
                if key == "important" and row["enabled"] and not row["ids"]:
                    raise ValueError("Select the Important donors first, then turn this row on.")
                plan[key] = row
            if st["status"] == "paused":
                st["approved"], st["status"] = None, "idle"  # a changed plan needs a new approval
                self._log(st, "Plan changed while paused: approve it again to continue.")

        self._edit(apply)
        return self.view()

    # ------------------------------------------------------------------ who would be messaged, and with what
    def _excluded(self, row):
        try:
            return bool(self.hub.exclusion_reason(normalize_phone(row["phone"])))
        except Exception:
            return True

    def _fresh(self, book, row):
        return not book.contacted(row) and row.get("delivery") not in ("Uncertain", "Sending")

    def audiences(self, plan):
        """Ids per row. A person in several lists is in the first one only (donation request once per case)."""
        book, seen, out = self.hub.book, set(), {k: [] for k in ROWS}
        top = book.recipients("top")
        giki = [r for r in top if "giki" in str(r.get("group") or "").lower()]
        gids = {r["id"] for r in giki}
        rest = [r for r in top if r["id"] not in gids]
        wanted = set(plan["important"].get("ids") or [])
        chosen = [r for r in book.recipients("important") if r["id"] in wanted]
        for key, rows in (("top", rest), ("giki", giki), ("important", chosen)):
            if not plan[key]["enabled"]:
                continue
            for r in rows:
                phone = normalize_phone(r["phone"])
                if phone in seen or not self._fresh(book, r) or self._excluded(r):
                    continue
                seen.add(phone)
                out[key].append(r["id"])
        if plan["volunteers"]["enabled"]:
            vb = self.hub.volunteers.book
            out["volunteers"] = [r["id"] for r in vb.recipients("all") if self._fresh(vb, r)]
        return out

    def _messages(self):
        a = self.app
        group = str(a.get_message("group")["text"] or "")
        dm = str(a.get_message("dm")["text"] or "")
        follow = str(self.hub.follow_up_text() or "")
        vol = str(self.hub.volunteers.message() or "")
        poster = (a.DATA / "poster.jpg").exists() or (a.DATA / "poster.mp4").exists()
        return {
            "group": {"text": group, "digest": _digest(group)},
            "dm": {"text": dm, "digest": _digest(dm)},
            "question": {"text": follow, "digest": _digest(follow)},
            "volunteers": {"text": vol, "digest": _digest(vol)},
            "poster": poster,
        }

    def _dm_busy(self):
        h, a = self.hub, self.app
        return bool(
            h.jobs.active
            or h.volunteers.jobs.active
            or a.CAMPAIGN.get("running")
            or getattr(a.ENGINE, "dm_running", False)
            or getattr(getattr(h, "thanks", None), "active", False)
        )

    def checks(self, st=None, messages=None):
        """Prepare checklist. A kind is 'Check again' when its wording changed after it was checked."""
        st = st or self._read()
        m = messages or self._messages()
        saved = st["checks"]

        def kind(name, digest):
            c = saved.get(name)
            return "check" if not c else ("again" if c.get("digest") != digest else "ok")

        return {
            "case": "ok" if self.app.read_left() > 0 else "check",
            "poster": "ok" if m["poster"] else "check",
            "group": kind("group", m["group"]["digest"]),
            "donor": kind("donor", _digest(m["dm"]["digest"] + m["question"]["digest"])),
        }

    def mark_checked(self, name):
        if name not in ("group", "donor"):
            raise ValueError("Choose group or donor messages.")
        m = self._messages()
        digest = m["group"]["digest"] if name == "group" else _digest(
            m["dm"]["digest"] + m["question"]["digest"]
        )
        self._edit(lambda st: st["checks"].__setitem__(name, {"digest": digest, "at": self.clock()}))
        return self.view()

    def summary(self):
        st = self._read()
        plan = st["plan"]
        aud = self.audiences(plan)
        m = self._messages()
        blockers, warnings = [], []
        left = self.app.read_left()
        if st["status"] == "finished":
            blockers.append("This case is finished. Start a new case.")
        if left <= 0:
            blockers.append("The case is complete (Rs. 0 left).")
        if not self.app.wa_ok():
            blockers.append("WhatsApp is disconnected. Reconnect it first.")
        if self.app.on_hold():
            blockers.append("Sending is on hold. Resume it first.")
        if st["status"] != "paused" and self._dm_busy():
            blockers.append("A DM queue is sending now. Stop it first: two queues never run together.")
        if plan["group"]["enabled"] and not m["group"]["text"].strip():
            blockers.append("The GiveLife Group message is empty.")
        dm_rows = [k for k in ("top", "giki", "important") if plan[k]["enabled"]]
        if dm_rows and not m["dm"]["text"].strip():
            blockers.append("The donor message is empty.")
        if plan["giki"]["enabled"] and not m["question"]["text"].strip():
            blockers.append("Write the share question first (Messages → Follow-Up Message).")
        if plan["volunteers"]["enabled"] and not m["volunteers"]["text"].strip():
            warnings.append("No saved volunteer share message: volunteers get the case and poster only.")
        if not any(plan[k]["enabled"] and aud[k] for k in DM_ORDER) and not plan["group"]["enabled"]:
            blockers.append("Nobody is selected and no group is on.")
        for name, label in (("group", "Group messages"), ("donor", "Donor messages")):
            if self.checks(st, m)[name] != "ok":
                warnings.append(f"{label}: check again before you start.")
        rows = {}
        for key in ROWS:
            rows[key] = {
                "title": TITLES[key],
                "enabled": plan[key]["enabled"],
                "count": len(aud[key]) if key != "group" else None,
                "plan": {k: v for k, v in plan[key].items() if k not in ("enabled", "ids")},
            }
        names, by = {}, {r["id"]: r["name"] for r in self.hub.book.recipients("all")}
        for key in ("top", "giki", "important"):
            names[key] = [by.get(i, "") for i in aud[key]][:40]
        names["volunteers"] = [
            r["name"] for r in self.hub.volunteers.book.recipients("all") if r["id"] in aud["volunteers"]
        ][:40]
        body = {
            "case": self._cid(),
            "plan": plan,
            "aud": aud,
            "msg": {k: m[k]["digest"] for k in ("group", "dm", "question", "volunteers")},
            "left": left,
        }
        token = _digest(json.dumps(body, sort_keys=True))
        return {
            "token": token,
            "rows": rows,
            "names": names,
            "messages": {k: m[k]["text"][:400] for k in ("group", "dm", "question", "volunteers")},
            "blockers": blockers,
            "warnings": warnings,
            "audiences": aud,
        }

    # ------------------------------------------------------------------ run control
    def start(self, token):
        with self.lock:
            st = self._read()
            if st["status"] == "running":
                return self.view()
            if st["status"] == "paused" and st["approved"]:
                return self.resume()
            s = self.summary()
            if s["blockers"]:
                raise ValueError(s["blockers"][0])
            if token != s["token"]:
                raise ValueError("The plan changed since you looked at it. Review it again.")
            plan = copy.deepcopy(st["plan"])
            st["approved"] = {
                "at": self.clock(),
                "token": token,
                "plan": plan,
                "ids": s["audiences"],
                "left": self.app.read_left(),
            }
            st["starts"] += 1
            st["status"] = "running"
            st["rows"] = {
                k: {"state": "queued" if plan[k]["enabled"] and (k == "group" or s["audiences"][k]) else "off", "starts": 0}
                for k in ROWS
            }
            self._log(st, "Case started with the approved plan.")
            self._write(st)
        self.tick()
        return self.view()

    def _stop_engines(self):
        """Stop every automatic sender. A message already sent cannot be recalled; one being sent finishes."""
        a, h = self.app, self.hub
        try:
            if a.auto_on():
                a.set_auto(False)
        except Exception:
            pass
        for jobs in (h.jobs, h.volunteers.jobs):
            try:
                if jobs.active:
                    jobs.cancel()
            except Exception:
                pass
        for part in (getattr(h, "thanks", None),):
            try:
                if part and part.active:
                    part.stop()
            except Exception:
                pass
        try:
            if h.auto.status()["enabled"]:
                h.auto.disable("Paused with the case.")
        except Exception:
            pass

    def pause(self):
        with self.lock:
            st = self._read()
            if st["status"] != "running":
                return self.view()
            self._stop_engines()
            st["status"] = "paused"
            for row in st["rows"].values():
                if row["state"] in ("running", "queued"):
                    row["state"] = "paused"
            self._log(st, "Pause all: no more sends. Messages already sent stay sent.")
            self._write(st)
        return self.view()

    def resume(self):
        with self.lock:
            st = self._read()
            if st["status"] != "paused" or not st["approved"]:
                raise ValueError("Nothing is paused.")
            if not self.app.wa_ok():
                raise ValueError("WhatsApp is disconnected. Reconnect it first.")
            if self.app.on_hold():
                raise ValueError("Sending is on hold. Resume it first.")
            st["status"] = "running"
            for row in st["rows"].values():
                if row["state"] == "paused":
                    row.update(state="queued", starts=row.get("starts", 0) + 1, job=None)
            self._log(st, "Resumed. Nobody already contacted is repeated.")
            self._write(st)
        self.tick()
        return self.view()

    def row_op(self, key, op):
        if key not in ROWS or op not in ("pause", "start"):
            raise ValueError("Choose a row and Start or Pause.")
        with self.lock:
            st = self._read()
            row = st["rows"].get(key)
            if st["status"] != "running" or not row or row["state"] == "off":
                raise ValueError("Start the case first. Only approved rows can run.")
            if op == "pause":
                if key == "group":
                    self.app.set_auto(False)
                else:
                    self._cancel_row(row)
                row["state"] = "paused"
            elif row["state"] in ("paused", "stopped"):
                row.update(state="queued", starts=row.get("starts", 0) + 1, job=None, error="")
            self._write(st)
        self.tick()
        return self.view()

    def finish(self, confirm=False):
        st = self._read()
        done = self._confirmed()
        if confirm is not True:
            return {"confirm": True, "confirmed": done, "left": self.app.read_left(), "view": self.view()}
        with self.lock:
            st = self._read()
            self._stop_engines()
            try:
                self.app.ENGINE.set_pace(None, None)
            except Exception:
                pass
            for f in st["giki"].values():
                if f["step"] in ("waiting", "agreed", "needs") and f.get("shared", 0) < GIKI_SHARES:
                    f["step"] = "cancelled"
            for row in st["rows"].values():
                if row["state"] in ("running", "queued", "paused"):
                    row["state"] = "done"
            st.update(status="finished", finished=self.clock())
            st["drafts"] = self._drafts(done)
            self._log(st, "Case finished. History is kept.")
            self._write(st)
        return self.view()

    def _confirmed(self):
        recs = self.hub.book._load()["records"]
        return int(sum(float(r.get("amount") or 0) for r in recs if r.get("donated") and not r.get("deleted")))

    def _drafts(self, came):
        try:
            return {"update": self.app.update_text(came, self.app.read_left()), "thanks": self.app.thank_text()}
        except Exception:
            return {}

    # ------------------------------------------------------------------ engines: start one row, follow its job
    def _cancel_row(self, row):
        jobs = self.hub.volunteers.jobs if row.get("engine") == "volunteers" else self.hub.jobs
        try:
            if jobs.active and jobs.active == row.get("job"):
                jobs.cancel()
        except Exception:
            pass

    def _job(self, row):
        jobs = self.hub.volunteers.jobs if row.get("engine") == "volunteers" else self.hub.jobs
        for j in reversed(jobs.export_jobs().get("jobs", [])):
            if row.get("request_id") and j.get("request_id") == row["request_id"]:
                return j
        return None

    def _start_row(self, st, key):
        a, h = self.app, self.hub
        ap, row = st["approved"], st["rows"][key]
        cfg = ap["plan"][key]
        book = h.volunteers.book if key == "volunteers" else h.book
        wanted = set(ap["ids"][key])
        ids = [r["id"] for r in book.recipients("all") if r["id"] in wanted and self._fresh(book, r)]
        if key != "volunteers":
            ids = [i for i in ids if not self._excluded(book.resolve(i))]
        if not ids:
            row.update(state="done", note="Nobody left to message.")
            return
        rid = f"case-{self._cid()[:8]}-{st['starts']}-{key}-{row.get('starts', 0)}"
        plan = dict(
            ids=ids,
            chunk=int(cfg["batch_size"]),
            gap_seconds=float(cfg["gap_minutes"]) * 60,
            rests=[float(cfg["rest_minutes"]) * 60],
            jitter=dict(JITTER),
            skip_contacted=False,
            request_id=rid,
            owner="case_" + key,
            origin="case_run",
        )
        try:
            if key == "volunteers":
                case = a.get_message("group")["text"]
                share = (h.volunteers.message() or "").strip()
                h.volunteers.jobs.start(
                    "selected", poster=True, custom_template=case, follow_up=share or None, **plan
                )
                row["engine"] = "volunteers"
            else:
                follow = (h.follow_up_text() or "").strip() if key == "giki" else ""
                h.jobs.start(
                    "selected",
                    poster=h.prefs().get("poster", True),
                    follow_up=follow or None,
                    **plan,
                )
                row["engine"] = "donors"
        except ValueError as e:
            row.update(error=str(e)[:200], tries=row.get("tries", 0) + 1)
            if row["tries"] >= 40:
                row["state"] = "stopped"
            return  # stays queued: it is tried again on the next tick
        row.update(state="running", request_id=rid, error="", tries=0)
        job = self._job(row)
        row["job"] = (job or {}).get("id")

    def _follow(self, st, key, row):
        job = self._job(row)
        if not job:
            if self.clock() - row.get("started_at", self.clock()) > 120:
                row["state"] = "queued"  # the start was lost before it was saved: ids are filtered again
            return
        state = job.get("state", "")
        row["job"] = job.get("id")
        if state in RUNNING or (state == "Interrupted" and job.get("auto", True)):
            row["state"] = "running"
        elif state in ("Completed", "Nothing sent"):
            row["state"] = "done"
        elif state == "Stopped":
            row.update(state="stopped", error=str(job.get("error") or "")[:200])
        if key == "giki":
            self._giki_sync(st, job)

    def _group_tick(self, st):
        row, a = st["rows"]["group"], self.app
        if row["state"] == "queued":
            every = int(st["approved"]["plan"]["group"]["every_minutes"])
            now = a.ENGINE.summary()
            a.ENGINE.set_pace(every, now.get("freelance_every") or 60)
            a.set_auto(True)
            row["state"] = "running"
        elif row["state"] == "running" and not a.auto_on():
            row["state"] = "paused"  # switched off elsewhere: we never switch it back on by ourselves

    def _advance(self, st):
        if st["status"] != "running" or not st["approved"]:
            return
        if st["rows"].get("group", {}).get("state") in ("queued", "running"):
            self._group_tick(st)
        for key in DM_ORDER:
            row = st["rows"].get(key)
            if row and row["state"] == "running":
                self._follow(st, key, row)
        if self.app.read_left() <= 0:
            return
        if any(st["rows"][k]["state"] == "running" for k in DM_ORDER if k in st["rows"]):
            return
        if self._dm_busy():
            return
        for key in DM_ORDER:
            row = st["rows"].get(key)
            if row and row["state"] == "queued":
                row["started_at"] = self.clock()
                self._start_row(st, key)
                if row["state"] == "running":
                    self._follow(st, key, row)
                break

    # ------------------------------------------------------------------ GIKI sharing
    def _giki_sync(self, st, job):
        by = {r["id"]: r for r in self.hub.book.recipients("all")}
        for rec in job.get("receipts", []):
            r = by.get(rec.get("id"))
            if rec.get("state") != "Sent" or not r:
                continue
            phone = normalize_phone(r["phone"])
            st["giki"].setdefault(
                phone,
                {
                    "step": "waiting",
                    "at": rec.get("time") or self.clock(),
                    "id": r["id"],
                    "name": r["name"],
                    "shared": 0,
                    "seen": [],
                },
            )

    def giki_decide(self, phone, decision):
        if decision not in ("agreed", "not_agreed"):
            raise ValueError("Choose Agreed or Not agreed.")

        def apply(st):
            f = st["giki"].get(phone)
            if not f or f["step"] in ("agreed", "shared", "cancelled"):
                raise ValueError("That person is already handled.")
            f["step"] = "agreed" if decision == "agreed" else "declined"
            for item in st["needs"].values():
                if item.get("phone") == phone and item["type"] == "giki_reply":
                    item["state"] = "done"

        self._edit(apply)
        return self.view()

    def _donor(self, did):
        try:
            return self.hub.book.resolve(did) if did else None
        except Exception:
            return None

    def _address(self, row):
        name = str(row.get("dm_name") or "").strip()
        title = {"Sister": "Sister", "Neutral": "Neutral"}.get(row.get("dm_salutation"), "Brother")
        return dm_composer.greeting(name, title) if name else "Bhai"

    def _send(self, phone, text, poster=False, kind="volunteer_flow"):
        """('ok'|'retry'|'uncertain', note). A refusal means nothing was sent; anything unclear is never retried."""
        try:
            r = self.app.send_custom(
                {"target": "phone", "phone": phone, "message": text, "kind": kind, "poster": poster}
            )
        except ValueError as e:
            return ("blocked" if "opted out" in str(e) or "blocked" in str(e) else "retry"), str(e)[:160]
        except Exception:
            return "uncertain", "Send not confirmed. Check WhatsApp before retrying."
        if (r or {}).get("code") == "SUCCESS":
            return "ok", ""
        return "uncertain", "Send not confirmed. Check WhatsApp before retrying."

    def _flow(self):
        """At most one share message per tick (the DM guard keeps its own gap). Reserved before sending."""
        st = self._read()
        if st["status"] != "running" or st["rows"].get("giki", {}).get("state") == "paused":
            return
        for phone, f in st["giki"].items():
            if f["step"] != "agreed" or f.get("inflight") is not None or f["shared"] >= GIKI_SHARES:
                continue
            n = f["shared"]
            row = self._donor(f.get("id")) or {}
            if n == 0:
                text, poster = self.app.get_message("group")["text"], True
            elif n == 1:
                text, poster = f"Please send a screenshot to {autopilot.ACCOUNT} after you donate.", False
            else:
                text, poster = f"{self._address(row)}, please share both messages above.", False
            self._edit(lambda s: s["giki"][phone].__setitem__("inflight", n))
            result, note = self._send(phone, text, poster)

            def done(s):
                g = s["giki"][phone]
                g["inflight"] = None
                if result == "ok":
                    g["shared"] = n + 1
                    if g["shared"] >= GIKI_SHARES:
                        g["step"] = "shared"
                elif result == "uncertain":
                    g["step"] = "uncertain"
                    g["note"] = note
                elif result == "blocked":
                    g["step"] = "declined"
                    g["note"] = note

            self._edit(done)
            return

    # ------------------------------------------------------------------ replies: GIKI answers, claims, questions
    def _participants(self, st):
        out, books = {}, (self.hub.book, self.hub.volunteers.book)
        names = {}
        for b in books:
            for r in b.recipients("all"):
                names[r["id"]] = r
        for row in st["rows"].values():
            job = self._job(row) if row.get("request_id") else None
            for rec in (job or {}).get("receipts", []):
                r = names.get(rec.get("id"))
                if rec.get("state") == "Sent" and r:
                    out[normalize_phone(r["phone"])] = {
                        "at": rec.get("time") or 0,
                        "name": r["name"],
                        "id": r["id"],
                    }
        return out

    def _scan(self):
        st = self._read()
        if st["status"] != "running":
            return
        people = self._participants(st)
        if not people:
            return
        try:
            chats = [p for p, _ in self.app.recent_chats() if p in people]
        except Exception:
            return
        if not chats:
            return
        start = st["cursor"] % len(chats)
        batch = (chats[start:] + chats[:start])[:6]
        events = []
        for phone in batch:
            try:
                msgs = self.app.scan_messages(phone + "@s.whatsapp.net") or []
            except Exception:
                continue
            info = people[phone]
            for m in msgs:
                mid = m.get("id")
                if not mid or m.get("is_from_me") or mid in st["seen"] or autopilot._stamp(m) < info["at"]:
                    continue
                events.append((phone, info, mid, str(m.get("content") or ""), m.get("media_type", ""), msgs, m))

        def apply(s):
            s["cursor"] = start + len(batch)
            for phone, info, mid, text, media, msgs, m in events:
                if mid in s["seen"]:
                    continue
                s["seen"].append(mid)
                try:
                    last = autopilot._last_ours(msgs, m)
                except Exception:
                    last = ""
                label, _ = reply_intent.classify(text, media, last)
                f = s["giki"].get(phone)
                if label == "opt_out":
                    try:
                        self.app.optout(phone)
                    except Exception:
                        pass
                    if f:
                        f["step"] = "declined"
                    continue
                if label in ("donated", "both"):
                    self._need(s, f"pay:{mid}", "payment", f"{info['name']} says they donated", text, phone, info, ["check_payment", "not_paid"], mid)
                    continue
                if f and f["step"] == "waiting":
                    verdict = agreement(text)
                    if verdict == "agree":
                        f["step"] = "agreed"
                    elif verdict == "decline":
                        f["step"] = "declined"
                    else:
                        f["step"] = "needs"
                        self._need(s, f"giki:{mid}", "giki_reply", f"{info['name']}: GIKI reply is unclear", text, phone, info, ["agreed", "not_agreed", "reply"], mid)
                elif label == "question":
                    self._need(s, f"q:{mid}", "question", f"{info['name']} asked a question", text, phone, info, ["reply", "dismiss"], mid)

        self._edit(apply)

    def _need(self, st, nid, kind, title, text, phone, info, actions, mid=None):
        st["needs"].setdefault(
            nid,
            {
                "id": nid,
                "type": kind,
                "title": title,
                "text": text[:300],
                "phone": phone,
                "donor_id": info.get("id"),
                "name": info.get("name"),
                "claim": mid,
                "at": self.clock(),
                "actions": actions,
                "state": "open",
            },
        )

    # ------------------------------------------------------------------ Needs you
    def needs(self, st=None):
        st = st or self._read()
        items = [dict(i) for i in st["needs"].values() if i["state"] == "open"]
        running = st["status"] in ("running", "paused")
        if running and not self.app.wa_ok():
            items.append({"id": "whatsapp", "type": "whatsapp", "title": "WhatsApp is disconnected", "actions": ["reconnect"]})
        for key, row in st["rows"].items():
            job = self._job(row) if row.get("request_id") else None
            for rec in (job or {}).get("receipts", []):
                nid = "uncertain:" + str(rec.get("id"))
                if rec.get("state") == "Uncertain" and nid not in st["resolved"]:
                    items.append({"id": nid, "type": "uncertain", "title": "A delivery is uncertain. Check WhatsApp before retrying.", "donor_id": rec.get("id"), "actions": ["mark_sent", "mark_not_sent"]})
            if row["state"] == "done" and ("done:" + key) not in st["resolved"] and st["status"] == "running":
                items.append({"id": "done:" + key, "type": "audience_done", "title": f"{TITLES[key]} finished", "actions": ["wait", "choose_audience"]})
            if row["state"] == "stopped" and row.get("error") and (f"stopped:{key}:{row.get('starts', 0)}") not in st["resolved"]:
                items.append({"id": f"stopped:{key}:{row.get('starts', 0)}", "type": "stopped", "title": f"{TITLES[key]} stopped: {row['error']}", "actions": ["review"]})
        for phone, f in st["giki"].items():
            if f["step"] == "uncertain":
                items.append({"id": "giki-uncertain:" + phone, "type": "uncertain", "title": f"{f['name']}: share message not confirmed", "phone": phone, "actions": ["giki_checked"]})
        if running and self.app.read_left() <= 0:
            items.append({"id": "goal", "type": "goal", "title": "The amount is complete.", "actions": ["finish"]})
        return items

    def need_act(self, nid, op, amount=None, text=None):
        st = self._read()
        item = st["needs"].get(nid)
        if op == "check_payment":
            return self._pay(nid, amount)
        if op in ("agreed", "not_agreed"):
            if not item:
                raise ValueError("That item is already handled.")
            return self.giki_decide(item["phone"], op)
        if op == "reply" or op == "send_thanks":
            if not item or not str(text or "").strip():
                raise ValueError("Write the message first.")
            res, note = self._send(item["phone"], str(text).strip(), kind="owner_text")
            if res != "ok":
                raise ValueError(note or "Not sent. Nothing was changed.")
            if item["type"] == "giki_reply":  # a reply keeps the question open: their next answer is read again
                self._edit(lambda s: s["giki"].get(item["phone"], {}).update(step="waiting"))
            return self._resolve(nid)
        if op in ("not_paid", "dismiss", "wait", "choose_audience", "review", "mark_sent", "mark_not_sent", "giki_checked", "reconnect", "finish"):
            if op == "reconnect":
                try:
                    self.app.api("/app/reconnect")
                except Exception:
                    raise ValueError("Could not reconnect from here. Tap WhatsApp.") from None
                return self.view()
            if op == "finish":
                return self.finish(False)
            if op in ("mark_sent", "mark_not_sent"):
                did = nid.split(":", 1)[1]
                try:
                    self.hub.book.delivery(did, "Sent" if op == "mark_sent" else "Not contacted")
                except Exception:
                    pass
            if op == "giki_checked":
                self._edit(lambda s: s["giki"].get(nid.split(":", 1)[1], {}).update(step="declined"))
            return self._resolve(nid)
        raise ValueError("Choose one of the actions shown.")

    def _resolve(self, nid):
        def apply(st):
            if nid in st["needs"]:
                st["needs"][nid]["state"] = "done"
            elif nid not in st["resolved"]:
                st["resolved"].append(nid)

        self._edit(apply)
        return self.view()

    # ------------------------------------------------------------------ money: confirmed once, left updated once
    def _pay(self, nid, amount):
        if type(amount) not in (int, float) or isinstance(amount, bool) or not 1 <= amount <= 100000000 or amount != amount:
            raise ValueError("Enter the amount you received.")
        amount = int(amount)
        with self.lock:
            st = self._read()
            item = st["needs"].get(nid)
            if not item or item["type"] != "payment" or item["state"] != "open":
                raise ValueError("That payment was already handled.")
            claim = item["claim"]
            pay = st["payments"].get(claim)
            if not pay:
                rec = self._donor(item.get("donor_id"))
                before = float(rec.get("amount") or 0) if rec and rec.get("donated") else 0.0
                left = self.app.read_left()
                pay = st["payments"][claim] = {
                    "amount": amount,
                    "donor_id": rec["id"] if rec else None,
                    "total": before + amount,
                    "left": max(0, left - amount),
                    "at": self.clock(),
                }
                self._write(st)  # targets are fixed first, so a retry after a crash cannot add twice
            if pay.get("donor_id"):
                self.hub.book.update(pay["donor_id"], donated=True, amount=pay["total"])
            if self.app.read_left() != pay["left"]:
                self.app.set_left(pay["left"])
            st = self._read()
            item = st["needs"][nid]
            item["state"] = "done"
            greet = self._address(self._donor(item.get("donor_id")) or {})
            thanks = f"{greet},\n\n{self.app.thank_text()}"
            st["needs"]["thank:" + claim] = {
                "id": "thank:" + claim,
                "type": "thank",
                "title": f"Thank {item['name']}",
                "text": thanks,
                "phone": item["phone"],
                "donor_id": item.get("donor_id"),
                "name": item["name"],
                "claim": claim,
                "at": self.clock(),
                "actions": ["send_thanks", "dismiss"],
                "state": "open",
            }
            self._write(st)
        return self.view()

    # ------------------------------------------------------------------ the page
    def tick(self):
        """Called every few seconds. Follows the engines, starts the next approved row, reads replies."""
        if not self.worker.acquire(blocking=False):
            return
        try:
            if self._read()["status"] != "running":
                return
            self._edit(self._advance)
            self._flow()
            self._scan()
        finally:
            self.worker.release()

    def _row_view(self, st, key, aud):
        plan, ap, row = st["plan"][key], st["approved"], st["rows"].get(key)
        out = {
            "key": key,
            "title": TITLES[key],
            "enabled": plan["enabled"],
            "state": (row or {}).get("state", "idle"),
            "plan": {k: v for k, v in plan.items() if k not in ("enabled", "ids")},
            "sent": 0,
            "left": None,
            "next_at": None,
            "note": (row or {}).get("error") or (row or {}).get("note") or "",
        }
        if key == "group":
            s = self.app.ENGINE.summary()
            out["sent"] = s.get("posts_today", 0)
            nxt = [n.get("due_at") for n in (self.app.ENGINE.status().get("next") or []) if n.get("due_at")]
            out["next_at"] = min(nxt) if nxt and out["state"] == "running" else None
        else:
            job = self._job(row) if row and row.get("request_id") else None
            ids = (ap["ids"][key] if ap else aud.get(key, []))
            if job:
                seen = {r.get("id") for r in job.get("receipts", [])}
                out["sent"] = (job.get("previous_sent") or 0) + (job.get("sent") or 0)
                out["left"] = len([i for i in job.get("ids", []) if i not in seen])
                out["next_at"] = (job.get("next_at") or job.get("next_batch_at")) if out["state"] == "running" else None
            else:
                out["left"] = len(ids) if plan["enabled"] else 0
        if key == "giki":
            steps = [f["step"] for f in st["giki"].values()]
            out["giki"] = {
                "waiting": steps.count("waiting"),
                "agreed": steps.count("agreed"),
                "shared": steps.count("shared"),
                "needs": steps.count("needs") + steps.count("uncertain"),
                "declined": steps.count("declined"),
                "people": [
                    {"name": f["name"], "step": f["step"]} for f in list(st["giki"].values())[:60]
                ],
            }
        action = "review"
        if out["state"] == "running":
            action = "pause"
        elif out["state"] in ("paused", "stopped", "queued") and st["status"] == "running":
            action = "start"
        elif st["status"] in ("finished", "paused") or not plan["enabled"]:
            action = "review" if plan["enabled"] else "none"
        out["action"] = action
        return out

    def view(self):
        st = self._read()
        aud = self.audiences(st["plan"]) if st["status"] in ("idle", "paused") else {}
        reg = self.hub.cases._load()
        cur = next((c for c in reg["cases"] if c["id"] == reg["current"]), {})
        m = self._messages()
        status = st["status"]
        return {
            "status": status,
            "case": {
                "id": reg["current"],
                "name": cur.get("name", ""),
                "left": self.app.read_left(),
                "confirmed": self._confirmed(),
            },
            "whatsapp": bool(self.app.wa_ok()),
            "rows": [self._row_view(st, k, aud) for k in ROWS],
            "needs": self.needs(st),
            "checks": self.checks(st, m),
            "approved": bool(st["approved"]),
            "plan_ids": {"important": list(st["plan"]["important"].get("ids") or [])},
            "log": st["log"][-8:],
            "drafts": st.get("drafts"),
            "payment": {"number": autopilot.ACCOUNT},
        }

    def act(self, body):
        op = body.get("action")
        if op == "plan":
            return self.set_plan(body.get("plan"))
        if op == "summary":
            return self.summary()
        if op == "start":
            return self.start(body.get("token"))
        if op == "resume":
            return self.resume()
        if op == "pause":
            return self.pause()
        if op == "row":
            return self.row_op(body.get("key"), body.get("op"))
        if op == "finish":
            return self.finish(body.get("confirm"))
        if op == "check":
            return self.mark_checked(body.get("name"))
        if op == "need":
            return self.need_act(body.get("id"), body.get("op"), body.get("amount"), body.get("text"))
        raise ValueError("Unknown action.")
