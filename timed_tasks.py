"""Explicit timed chat actions. Single-worker, persisted, and never retried after dispatch uncertainty."""

import datetime as dt
import hashlib, json, re, threading, time, uuid
import manual_commands

PKT = dt.timezone(dt.timedelta(hours=5))


def requested(text):
    text = str(text)
    if re.search(r"(?i)\bevery\s+\d", text) and not re.search(
        r"(?i)\bat\s*\d|\d\s*(?:am|pm)\b", text
    ):
        return False
    return bool(
        re.search(
            r"(?i)\b(?:schedul\w*|at\s+\d{1,2}|tomorrow|daily|every day|(?:in|after)\s+\d+(?:\.\d+)?\s*(?:sec\w*|min\w*|hour\w*|hr\w*))\b|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
            text,
        )
    )


ORDINALS = {
    "first": 0,
    "1st": 0,
    "one": 0,
    "second": 1,
    "2nd": 1,
    "two": 1,
    "third": 2,
    "3rd": 2,
    "three": 2,
    "fourth": 3,
    "4th": 3,
    "last": -1,
    "latest": -1,
    "newest": -1,
    "recent": -1,
}
DUPLICATE = r"\b(?:duplicates?|duplicated|redundant|extra|twice|double|same (?:one|task|thing)|copy|copies)\b"


def cancel_request(text):
    """Owner text that asks to remove timed tasks, by id, position, duplicate or all."""
    low = re.sub(r'"[^"\n]*"|“[^”\n]*”', " ", str(text)).casefold()
    if re.search(r"\b(?:don'?t|dont|do not|never)\s+(?:cancel|delete|remove)\b", low):
        return False
    if re.match(r"^(?:what|how|why|when|can|could|should|did|do|does|is|are)\b", low.strip()):
        return False
    verb = re.search(r"\b(?:cancel|delete|remove|undo|clear)\b", low)
    if not verb:
        return False
    if re.search(ALL_CANCEL, low.strip()):
        return True
    if re.search(
        r"\b(?:last|latest|recent)\s+(?:message|msg|post|dm)\b|\b(?:message|msg|post|dm)s?\b.*\b(?:from|in|on)\s+(?:the\s+)?(?:group|main|fiverr|upwork|community|uet|toprated)\b",
        low,
    ):
        return False
    if re.search(PRONOUN_CANCEL, low.strip()):
        return True
    about = re.search(r"\bschedul\w*|\btasks?\b|\b(?:resume|timer|timed)\b|#?\b[a-f0-9]{8}\b", low)
    if about:
        return True
    if re.search(DUPLICATE, low):
        return True
    return bool(
        re.search(r"\bcancel\b", low)
        and re.search(r"\b(?:1st|2nd|3rd|4th|first|second|third|fourth|last|latest|newest)\b", low)
    )


LIST_WORDS = r"(?:please\s+)?(?:(?:what(?:'s| is| are)?|whats|show|list|view|any|anything|do i have(?: any)?)\s+(?:is\s+)?(?:scheduled|pending|queued|upcoming|coming up)(?:\s+(?:tasks?|sends?|posts?|messages?))?|(?:my\s+|the\s+|all\s+)?(?:pending|queued|upcoming)\s+(?:tasks?|sends?|posts?|messages?)|(?:what(?:'s| is)?|whats)\s+next|(?:my\s+)?tasks|(?:any|anything)\s+(?:pending|scheduled|queued)|kya\s+scheduled\s+hai)(?:\s+(?:now|today|please))?[?.!]*"
ALL_CANCEL = r"^(?:please\s+)?(?:cancel|clear|remove|delete)\s+(?:all|everything)(?:\s+(?:of\s+)?(?:them|these|it))?(?:\s+please)?[.!]*$"
PRONOUN_CANCEL = r"^(?:please\s+)?(?:ok\s+|okay\s+)?(?:cancel|remove|delete|undo)\s+(?:it|that|this|that one|this one|the other one|the other)(?:\s+please)?[.!]*$"


def parse_cancel(text):
    low = re.sub(r'"[^"\n]*"|“[^”\n]*”', " ", str(text)).casefold()
    ident = re.search(r"#?\b([a-f0-9]{8})\b", low)
    if ident and re.search(r"\d", ident[1]) or ident and re.search(r"#" + ident[1], low):
        return {"command": "cancel", "id": ident[1]}
    if re.search(PRONOUN_CANCEL, low.strip()):
        return {"command": "cancel_by", "which": "only", "soft": True}
    if re.search(ALL_CANCEL, low.strip()):
        return {"command": "cancel_by", "which": "all"}
    if re.search(r"\b(?:all|every|everything)\b", low) and re.search(
        r"schedul|task|timer|resume", low
    ):
        return {"command": "cancel_by", "which": "all"}
    if re.search(DUPLICATE, low):
        return {"command": "cancel_by", "which": "duplicate"}
    for word, index in ORDINALS.items():
        if re.search(r"\b" + word + r"\b", low) and not (
            word in ("one", "two", "three")
            and not re.search(
                r"\b" + word + r"\s+(?:schedule|task)|(?:schedule|task)\s+" + word + r"\b", low
            )
        ):
            return {"command": "cancel_by", "which": "position", "index": index}
    return {"command": "cancel_by", "which": "only"}


def parse(text, now=None):
    """Only owner-authored, explicit actions; no inferred recipient or LLM-selected clock."""
    now = time.time() if now is None else now
    t = str(text).strip()
    instruction = re.sub(r'"[^"\n]*"|“[^”\n]*”', " ", t)
    low = re.sub(r"\b(continye|contine|contiune)\b", "continue", instruction.casefold())
    if re.fullmatch(
        r"(?:please\s+)?(?:(?:show|list|view|see|check)\s+)?(?:me\s+)?(?:(?:my|the|all|our)\s+)?(?:scheduled?\s+(?:tasks|messages|sends)|schedules|scheduler)(?:\s+(?:please|now))?[?.!]*",
        low,
    ):
        return {"command": "list"}
    if re.fullmatch(
        r"(?:what(?:'s| is| are)?\s+)?(?:my|the|our)\s+(?:schedules?|scheduled tasks?)[?.!]*", low
    ):
        return {"command": "list"}
    if re.fullmatch(LIST_WORDS, low.strip()):
        return {"command": "list"}
    if cancel_request(instruction):
        return parse_cancel(instruction)
    if not requested(instruction):
        return None
    if (
        re.match(
            r"^(?:what|how|when|why|did|can|could|explain|review|summarize|analyse|analyze)\b", low
        )
        or re.search(r"\b(?:don't|dont|do not|never)\b", low)
        or t.startswith((">", "```", '"', "“"))
    ):
        return None
    if (manual_commands.parse(instruction) or {}).get("kind") == "refuse_target":
        raise ValueError("That group is excluded. Nothing was scheduled.")
    if re.search(r"\b(utc|gmt|est|ist|pst)\b", low):
        raise ValueError(
            "Use Pakistan time (PKT) for schedules. Convert the time and send it again."
        )
    auto = bool(re.search(r"\b(auto|autopilot)\b", low))
    resume = bool(re.search(r"\b(resume|continue|restart)\b|\bstart\s+(?:sending|posting)\b", low))
    if resume:
        action = "resume"
        keys = manual_commands.groups(instruction)
        if "test" in keys:
            raise ValueError(
                "The test group has no automatic posting. Schedule a single send to it instead."
            )
        if (
            not keys
            and not auto
            and not re.match(
                r"^(?:please\s+)?(?:resume|continue|restart)\s+(?:at|by|in|after)\b", low
            )
        ):
            raise ValueError("Which groups should resume? For example: resume freelance at 11am.")
    elif auto:
        if manual_commands.SEND.search(instruction):
            raise ValueError("Schedule one action at a time: a group send or an Auto change.")
        if not re.search(r"\b(start|turn|enable|disable|stop|on|off)\b", low):
            return None
        if re.search(r"\b(start|enable|on)\b", low) and re.search(r"\b(stop|disable|off)\b", low):
            raise ValueError("Schedule one Auto change at a time: ON or OFF.")
        action = "auto_off" if re.search(r"\b(stop|disable|off)\b", low) else "auto_on"
        keys = []
    else:
        if not re.search(r"\b(send|post|share|message|msg|schedule|schedul)\b", low):
            return None
        action = "send"
        keys = manual_commands.groups(instruction)
        if not keys:
            raise ValueError(
                "Which group should I schedule? For example: send to GiveLife main tomorrow at 9pm."
            )
    if (
        len(
            re.findall(
                r"(?:\bat\s*|@\s*)\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
                low,
            )
        )
        > 1
    ):
        raise ValueError("Schedule one time at a time. Nothing was scheduled.")
    if re.search(r"\bevery\s+\d", low):
        raise ValueError(
            "Use one timed send or daily at a clock time. Keep interval rules, such as every 30 minutes, separate."
        )
    quote = re.search(r'"([^"\n]+)"|“([^”\n]+)”', t)
    body = next((x for x in quote.groups() if x), "") if quote else ""
    daily = bool(re.search(r"\b(daily|every day|each day)\b", low))
    current = dt.datetime.fromtimestamp(now, PKT)
    relative = re.search(
        r"\b(?:in|after)\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|mnts?|hours?|hrs?)\b",
        low,
    )
    if relative:
        if daily:
            raise ValueError("For a daily task, give a clock time, for example daily at 9pm.")
        seconds = float(relative[1]) * (
            3600 if relative[2].startswith("h") else 60 if relative[2].startswith("m") else 1
        )
        if not 1 <= seconds <= 366 * 86400:
            raise ValueError("Choose a delay from 1 second to 366 days.")
        when = current + dt.timedelta(seconds=seconds)
    else:
        clock = re.search(r"\b(?:at\s*|@\s*)(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", low) or re.search(
            r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low
        )
        if not clock:
            raise ValueError(
                "What time? For example: send to GiveLife main at 9pm, or in 10 minutes. Times use Pakistan time (PKT)."
            )
        hour, minute = int(clock[1]), int(clock[2] or 0)
        ampm = clock[3]
        if minute > 59 or (ampm and not 1 <= hour <= 12) or (not ampm and not 0 <= hour <= 23):
            raise ValueError("That clock time is invalid. Use 9pm or 21:00 (PKT).")
        if ampm:
            hour = hour % 12 + (12 if ampm == "pm" else 0)
        when = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        date = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", low)
        if date:
            try:
                date = dt.date.fromisoformat(date[1])
                when = when.replace(year=date.year, month=date.month, day=date.day)
            except ValueError:
                raise ValueError("That date is invalid. Use YYYY-MM-DD.") from None
        elif "tomorrow" in low:
            when += dt.timedelta(days=1)
        elif when.timestamp() <= now and "today" not in low:
            when += dt.timedelta(days=1)
        if when.timestamp() <= now:
            raise ValueError("That time has passed. Choose a future time.")
    return {
        "command": "create",
        "action": action,
        "targets": list(dict.fromkeys(keys)),
        "text": body,
        "due": when.timestamp(),
        "daily": daily,
        "clock": when.strftime("%H:%M"),
    }


class Scheduler:
    def __init__(
        self, path, store, dispatch, receipt, ready, cancel_job=lambda ident: None, clock=time.time
    ):
        self.path = path
        self.store = store
        self.dispatch = dispatch
        self.receipt = receipt
        self.ready = ready
        self.cancel_job = cancel_job
        self.clock = clock
        self.lock = threading.RLock()
        self.tick_lock = threading.Lock()
        saved = store.get("timed_tasks", None) if store else None
        if saved is None:
            saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if isinstance(saved, str):
            saved = json.loads(saved)
        if not isinstance(saved, list) or any(not isinstance(x, dict) for x in saved):
            raise ValueError("Saved schedules need repair. No scheduled action was started.")
        self.tasks = saved
        for task in self.tasks:
            if task.get("state") == "dispatching":
                task.update(
                    state="uncertain",
                    result="Restarted during dispatch. Check WhatsApp; this task will not repeat.",
                )
        self.save()

    def save(self):
        if self.store:
            self.store.put("timed_tasks", self.tasks)
        else:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.tasks, ensure_ascii=False), encoding="utf-8")
            temp.replace(self.path)

    def describe(self, task):
        at = dt.datetime.fromtimestamp(task["due"], PKT).strftime("%d %b %Y %I:%M:%S %p PKT")
        action = (
            "poster + "
            + ("your quoted caption" if task.get("text") else "the saved caption at send time")
            + " to "
            + ", ".join(task["targets"])
            if task["action"] == "send"
            else (
                "Resume "
                + (", ".join(task["targets"]) or "Auto")
                + "; release hold and turn Auto ON"
                if task["action"] == "resume"
                else "Auto " + ("ON" if task["action"] == "auto_on" else "OFF")
            )
        )
        return (
            f"#{task['id']} · {task['state']} · {'Daily' if task.get('daily') else 'Once'} · {at} · {action}"
            + ((" · " + task["result"]) if task.get("result") else "")
        )

    def active(self):
        return [x for x in self.tasks if x["state"] in ("pending", "running", "dispatching")]

    def summary(self):
        """Short facts for the assistant's context: what is really queued, by position."""
        with self.lock:
            return [
                {
                    "position": i + 1,
                    "id": x["id"],
                    "state": x["state"],
                    "what": self.describe(x).split(" · ", 2)[-1],
                }
                for i, x in enumerate(self.active())
            ][:20]

    def list(self):
        with self.lock:
            active = self.active()
            lines = [f"{i + 1}. " + self.describe(x) for i, x in enumerate(active)]
            lines += [self.describe(x) for x in self.tasks[-30:] if x not in active][-10:]
            return "\n".join(lines) or "No timed tasks. Try: send to GiveLife main tomorrow at 9pm."

    def same_job(self, a, b):
        return (
            a["action"] == b["action"]
            and sorted(a["targets"]) == sorted(b["targets"])
            and a.get("text", "") == b.get("text", "")
            and bool(a.get("daily")) == bool(b.get("daily"))
            and abs(a["due"] - b["due"]) < 60
        )

    def cancel_task(self, task):
        if self.store and hasattr(self.store, "claim"):
            self.store.claim(self.claim_key(task), {"state": "cancelled"})
        task.update(
            state="cancelled", result="Cancelled. Already dispatched messages cannot be undone."
        )
        self.save()
        if task.get("job_id"):
            self.cancel_job(task["job_id"])

    def cancel_by(self, plan):
        pending = [x for x in self.tasks if x["state"] == "pending"]
        if not pending:
            return "There is nothing to cancel. No schedule is pending."
        which = plan["which"]
        if which == "all":
            chosen = pending
        elif which == "duplicate":
            chosen = [
                x for i, x in enumerate(pending) if any(self.same_job(x, y) for y in pending[:i])
            ]
            if not chosen:
                return "I found no duplicate schedules. Say show schedules to see them."
        elif which == "position":
            index = plan["index"]
            if not -len(pending) <= index < len(pending):
                return f"There are only {len(pending)} pending schedule(s). Say show schedules."
            chosen = [pending[index]]
        else:
            if len(pending) > 1:
                raise ValueError(
                    "Which one? "
                    + str(len(pending))
                    + " are pending:\n"
                    + "\n".join(f"{i + 1}. " + self.describe(x) for i, x in enumerate(pending))
                    + "\nSay cancel 1st, cancel 2nd, or cancel schedule <id>."
                )
            chosen = pending
        for task in chosen:
            self.cancel_task(task)
        kept = [x for x in self.tasks if x["state"] == "pending"]
        return (
            "Cancelled: "
            + "; ".join(self.describe(x) for x in chosen)
            + ". "
            + (
                "Still pending: " + "; ".join(self.describe(x) for x in kept)
                if kept
                else "Nothing else is pending."
            )
        )

    def command(self, text, request_id=None):
        plan = parse(text, self.clock())
        if plan is None:
            return None
        with self.lock:
            if plan["command"] == "list":
                return self.list()
            if plan["command"] == "cancel_by":
                if plan.get("soft") and not any(x["state"] == "pending" for x in self.tasks):
                    return None
                return self.cancel_by(plan)
            if plan["command"] == "cancel":
                task = next((x for x in self.tasks if x["id"] == plan["id"]), None)
                if not task:
                    raise ValueError("No schedule with that ID. Say show schedules.")
                if task["state"] in ("completed", "failed", "uncertain", "cancelled", "missed"):
                    return (
                        "That task is already "
                        + task["state"]
                        + ". Check its receipt before sending again."
                    )
                self.cancel_task(task)
                return "Cancelled: " + self.describe(task)
            sig = hashlib.sha256(re.sub(r"\s+", " ", text.strip().casefold()).encode()).hexdigest()
            old = next(
                (
                    x
                    for x in self.tasks
                    if request_id
                    and x.get("request_id") == request_id
                    or x.get("signature") == sig
                    and self.clock() - x.get("created", 0) < 30
                    and x["state"] == "pending"
                ),
                None,
            )
            if old:
                return "Already scheduled: " + self.describe(old)
            twin = next(
                (x for x in self.tasks if x["state"] == "pending" and self.same_job(x, plan)), None
            )
            if twin:
                return (
                    "You already have this exact task, so I did not add a second copy: "
                    + self.describe(twin)
                )
            if sum(x["state"] in ("pending", "running", "dispatching") for x in self.tasks) >= 100:
                raise ValueError("You have 100 active schedules. Cancel one first.")
            task = {
                **plan,
                "id": uuid.uuid4().hex[:8],
                "state": "pending",
                "created": self.clock(),
                "request_id": request_id,
                "signature": sig,
            }
            task.pop("command")
            self.tasks.append(task)
            try:
                self.save()
            except Exception:
                self.tasks.remove(task)
                raise
            return (
                "Scheduled: "
                + self.describe(task)
                + ". Nothing sent now. Say show schedules or cancel schedule "
                + task["id"]
                + "."
            )

    def finish(self, task, state, result):
        occurrence = self.claim_key(task)
        task.update(state=state, result=result)
        if task.get("daily") and state in ("completed", "missed"):
            date = dt.datetime.fromtimestamp(self.clock(), PKT)
            h, m = map(int, task["clock"].split(":"))
            nxt = date.replace(hour=h, minute=m, second=0, microsecond=0)
            if nxt.timestamp() <= self.clock():
                nxt += dt.timedelta(days=1)
            task.update(state="pending", due=nxt.timestamp(), last_result=result)
        self.save()
        if self.store and hasattr(self.store, "claim"):
            self.store.put(occurrence, {"state": "finished", "task": dict(task)})

    def claim_key(self, task):
        return "timed_occurrence_" + task["id"] + "_" + str(int(task["due"]))

    def tick(self):
        if not self.tick_lock.acquire(blocking=False):
            return
        try:
            for task in list(self.tasks):
                with self.lock:
                    if task["state"] == "running":
                        job = self.receipt(task["job_id"])
                        if not job:
                            self.finish(
                                task,
                                "uncertain",
                                "Receipt unavailable. Check WhatsApp. No automatic retry.",
                            )
                        elif job.get("done"):
                            results = job.get("results") or []
                            ok = (
                                len(results) == task.get("expected", len(results))
                                and bool(results)
                                and all(x.get("code") == "SUCCESS" for x in results)
                            )
                            self.finish(
                                task,
                                "completed" if ok else "failed",
                                job.get("message", "Delivery was not fully confirmed."),
                            )
                        continue
                    if task["state"] != "pending" or task["due"] > self.clock():
                        continue
                    if self.clock() - task["due"] > 900:
                        self.finish(
                            task,
                            "missed",
                            "Cloud was unavailable or sending was paused for over 15 minutes. No stale send was started.",
                        )
                        continue
                if not self.ready(task):
                    continue
                with self.lock:
                    if task["state"] != "pending":
                        continue
                    if self.store and hasattr(self.store, "claim"):
                        key = self.claim_key(task)
                        if not self.store.claim(
                            key, {"state": "dispatching", "claimed_at": self.clock()}
                        ):
                            claim = self.store.get(key, {})
                            if claim.get("state") == "finished" and isinstance(
                                claim.get("task"), dict
                            ):
                                task.update(claim["task"])
                                self.save()
                            elif claim.get("job_id"):
                                task.update(
                                    state="running",
                                    job_id=claim["job_id"],
                                    expected=claim["expected"],
                                )
                                self.save()
                            elif (
                                claim.get("state") == "dispatching"
                                and self.clock() - claim.get("claimed_at", 0) < 120
                            ):
                                continue
                            else:
                                self.finish(
                                    task,
                                    "cancelled"
                                    if claim.get("state") == "cancelled"
                                    else "uncertain",
                                    "This occurrence was already reserved. It will not be dispatched again.",
                                )
                            continue
                    task["state"] = "dispatching"
                    self.save()
                try:
                    result = self.dispatch(dict(task))
                    with self.lock:
                        if task["state"] == "cancelled":
                            if result.get("job_id"):
                                self.cancel_job(result["job_id"])
                            continue
                        if result.get("job_id"):
                            task.update(
                                state="running",
                                job_id=result["job_id"],
                                expected=result["expected"],
                            )
                            if self.store and hasattr(self.store, "claim"):
                                self.store.put(
                                    self.claim_key(task),
                                    {
                                        "state": "running",
                                        "job_id": result["job_id"],
                                        "expected": result["expected"],
                                    },
                                )
                            self.save()
                        else:
                            self.finish(task, "completed", str(result.get("message", "Confirmed.")))
                except Exception:
                    with self.lock:
                        if task["state"] != "cancelled":
                            self.finish(
                                task,
                                "uncertain",
                                "Dispatch was not confirmed. Check activity before rescheduling. No automatic retry.",
                            )
        finally:
            self.tick_lock.release()
