"""Manager: the owner's single point of contact for every GiveLife agent.

Code routes each request to the right agent, calls that agent's REAL functions, checks the result and
records the task. AI is used only where judgment or writing is needed (Writer conversation, open
questions). Nothing is invented: an agent's reply is built from its real state or a real AI answer, and
an agent that cannot do something says so. Manager never sends WhatsApp messages and never bypasses
consent, limits, hold or approval: every send still goes through the existing guarded paths.
"""

import json, math, re, threading, time, uuid

NAMES = {
    "manager": "Manager",
    "writer": "Writer",
    "checker": "Checker",
    "replies": "Reply Reader",
    "dms": "DM Guard",
    "volunteers": "Volunteer Guide",
    "auto": "Group Poster",
    "plan": "Case Plan",
}
# Explicit names first; then words that clearly belong to one agent.
NAMED = [
    ("writer", r"\bwriter\b"),
    ("checker", r"\bchecker\b"),
    ("replies", r"\breply ?reader\b"),
    ("dms", r"\bdm ?(?:guard|sender)\b"),
    ("volunteers", r"\bvolunteer(?: guide)?s?\b"),
    ("auto", r"\bgroup ?poster\b"),
    ("plan", r"\bcase ?plan\b"),
]
ALL = re.compile(r"(?i)\b(all|every|each) (?:the )?agents?\b|\beveryone\b")
PROGRESS = re.compile(r"(?i)\b(progress|status|update|doing|how (?:is|are)|report)\b")
FOLLOW = re.compile(r"(?i)\b(it|this|that|again|more|better|shorter|longer|another)\b")
WRITE = re.compile(
    r"(?i)\b(write|rewrite|improve|draft|reword|make (?:it|this)|shorter|longer|softer|stronger)\b"
)
CHECK = re.compile(r"(?i)\b(check|verify|review)\b")
GENERATE = re.compile(r"(?i)\b(generate|make|write)\b.*\bversions?\b")
SAVE_DRAFT = re.compile(
    r"(?i)\b(save|use)\b.*\b(draft|this|it)\b.*\b(group|dm)\b|\b(group|dm)\b.*\b(save|use)\b.*\b(draft|this|it)\b"
)
TRANSIENT = re.compile(r"(?i)timed? ?out|timeout|429|50\d|temporar|connection|reset|unavailable")
KEEP = 200


def _now():
    return time.time()


class Manager:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.file = app.DATA / "manager.json"
        self.state = self._load()
        self.thread = None

    # ------------------------------------------------------------------ memory (database first, file copy)
    def _load(self):
        base = {"chat": [], "tasks": [], "decisions": [], "ctx": {}, "retries": {}}
        try:
            saved = self.app.STORE.get("manager_state") if self.app.STORE else None
            if not saved and self.file.exists():
                saved = json.loads(self.file.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                base.update({k: saved[k] for k in base if k in saved})
        except Exception:
            pass
        return base

    def _save(self):
        for k in ("chat", "tasks", "decisions"):
            self.state[k] = self.state[k][-KEEP:]
        raw = json.dumps(self.state, ensure_ascii=False)
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text(raw, encoding="utf-8")
        except Exception:
            pass
        if self.app.STORE:
            try:
                self.app.STORE.put("manager_state", json.loads(raw))
            except Exception:
                pass  # the file copy keeps working; memory_status() reports the database problem

    def _say(self, who, text, task=None):
        item = {"id": uuid.uuid4().hex, "at": _now(), "who": who, "text": str(text)[:4000]}
        if task:
            item["task"] = task
        self.state["chat"].append(item)
        return item

    def _task(self, agent, instruction):
        t = {
            "id": uuid.uuid4().hex[:12],
            "at": _now(),
            "agent": agent,
            "instruction": str(instruction)[:300],
            "status": "running",
        }
        self.state["tasks"].append(t)
        return t

    def _finish(self, t, ok, result, verified=None):
        t.update(
            status="done" if ok else "failed",
            result=str(result)[:300],
            verified=bool(ok if verified is None else verified),
            done=_now(),
        )

    # ------------------------------------------------------------------ the owner talks to Manager
    def handle(self, text, agent=None):
        """One owner message. Returns the new chat items (owner line first, then each real reply)."""
        text = str(text or "").strip()[:2000]
        if not text:
            raise ValueError("Type a message for Manager.")
        with self.lock:
            start = len(self.state["chat"])
            self._say("you", text)
            try:
                self._route(text, agent if agent in NAMES else None)
            except Exception as e:  # one broken agent never breaks the conversation
                self._say("manager", "That did not work: " + str(e)[:200])
            self._save()
            return self.state["chat"][start:]

    def _route(self, text, forced):
        low = text.lower()
        if forced in (None, "manager") and ALL.search(text):
            self._say("manager", "Asking every agent for its progress.")
            for a in ("writer", "checker", "replies", "dms", "volunteers", "auto", "plan"):
                self._ask(a, "progress", text)
            return
        target = forced if forced not in (None, "manager") else None
        if not target:
            target = next((a for a, p in NAMED if re.search(p, low)), None)
        if not target and FOLLOW.search(text) and self.state["ctx"].get("agent"):
            target = self.state["ctx"]["agent"]  # "tell it to improve this"
        if not target and (WRITE.search(text) or GENERATE.search(text) or SAVE_DRAFT.search(text)):
            target = "writer"
        if not target and CHECK.search(text):
            target = "checker"
        rule = self._rule(text) if target in (None, "auto") else None
        if (
            not rule
            and not target
            and re.match(r"(?i)\s*(remember|always|never|from now|in future)\b", text)
        ):
            t = self._task("manager", text)
            saved = self.app.mem_add(text)
            self._finish(t, bool(saved), saved)
            self._say("manager", f"{saved} Writer uses it in every new message.")
            return
        if rule:
            return
        if not target:
            return self._manager_answer(text)
        self.state["ctx"]["agent"] = target
        if target != forced:
            self._say("manager", f"Passing this to {NAMES[target]}.")
        self._ask(
            target, "progress" if PROGRESS.search(text) and not WRITE.search(text) else "task", text
        )

    def _rule(self, text):
        """A clear standing rule ("post in main every 20 min") goes to Group Poster's real rule list."""
        import rules

        rule, description = rules.parse(re.sub(r"(?i)\bfree\b", "freelance", text))
        if not rule or rule["kind"] in ("schedule", "note"):
            return False
        t = self._task("auto", text)
        self.app.ENGINE.add_rule(rule)
        saved = any(r["text"] == rules.describe(rule) for r in self.app.ENGINE.rule_list())
        self._finish(t, saved, description)
        self._say(
            "auto",
            ("Saved rule: " if saved else "Could not save the rule: ") + description,
            t["id"],
        )
        return True

    def _ask(self, agent, kind, text):
        t = self._task(agent, text)
        try:
            ok, reply = getattr(self, "_" + agent)(kind, text)
        except Exception as e:
            ok, reply = False, f"I could not do that: {str(e)[:200]}"
        self._finish(t, ok, reply)
        self._say(agent, reply, t["id"])

    # ------------------------------------------------------------------ agents: real capabilities only
    def _writer(self, kind, text):
        bank = self.app.focus_bank()
        which = "dm" if re.search(r"(?i)\bdms?\b", text) else "group"
        if kind == "progress":
            parts = []
            for k in ("group", "dm"):
                row = bank.get(k)
                n = len(row.get("items") or [])
                parts.append(
                    f"{k.upper()}: {n} versions, {row.get('state', 'Not generated')}"
                    + (f" ({row['error'][:120]})" if row.get("error") else "")
                )
            return True, "; ".join(parts) + "."
        if SAVE_DRAFT.search(text):
            draft = self.state["ctx"].get("draft")
            if not draft:
                return False, "There is no draft from me yet. Ask me to write one first."
            bad = self._problems(draft)
            if bad:
                return False, "I will not save it: " + "; ".join(bad)
            row = bank.save(which, draft)
            ok = row.get("source") == draft
            return ok, f"Saved as the {which.upper()} base message." if ok else "Saving failed."
        if GENERATE.search(text):
            before = len(bank.get(which).get("items") or [])
            row = bank.generate(which)
            ok = row.get("state") == "Generating" or len(row.get("items") or []) > before
            return ok, (
                f"Writing 5 new {which.upper()} versions now ({before} saved). Each one is checked before it is saved."
                if ok
                else f"Could not start: {row.get('error') or row.get('state')}"
            )
        return self._writer_chat(text)

    def _writer_chat(self, text):
        import assistant

        key = assistant.client()
        if not key:
            return False, "I cannot write right now: the AI is not connected (DEEPSEEK_API_KEY)."
        facts = self._facts()
        style = []
        try:
            style = self.app.focus_bank().owner_style(limit=2)
        except Exception:
            pass
        try:
            corrections = [str(c)[:200] for c in (__import__("dm_variants").CORRECTIONS() or [])][
                -12:
            ]
        except Exception:
            corrections = []
        system = (
            "You are Writer, the fundraising message writer of GiveLife Foundation, talking with the owner.\n"
            "Use ONLY the verified facts below. Never invent medical details, ages, names, amounts, deadlines or"
            " urgency. Keep the payment number and the 'EASYPAISA ONLY' line exactly. Follow every owner"
            " correction. Write in the owner's style. Answer questions and discuss ideas plainly.\n"
            'Reply with ONE JSON object: {"reply": "your answer to the owner", "draft": "the full WhatsApp'
            ' message if you wrote or rewrote one, else empty"}\n\nVERIFIED FACTS:\n'
            + facts
            + (
                "\n\nOWNER STYLE EXAMPLES:\n" + "\n---\n".join(s[:900] for s in style)
                if style
                else ""
            )
            + (
                "\n\nOWNER CORRECTIONS:\n" + "\n".join("- " + c for c in corrections)
                if corrections
                else ""
            )
        )
        history = [
            {"role": "user" if m["who"] == "you" else "assistant", "content": m["text"][:1500]}
            for m in self.state["chat"][-10:-1]
            if m["who"] in ("you", "writer")
        ]
        messages = history + [{"role": "user", "content": text}]
        data = self._ai_json(key, system, messages)
        if not data:
            return (
                False,
                "The AI answer was not valid, so I show nothing rather than guess. Try again.",
            )
        draft = str(data.get("draft") or "").strip()
        note = ""
        if draft:
            # Manager quality gate: Checker reviews the draft; one revision if it fails.
            bad = self._problems(draft)
            if bad:
                fixed = self._ai_json(
                    key,
                    system,
                    messages
                    + [
                        {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
                        {
                            "role": "user",
                            "content": "Checker rejected the draft: "
                            + "; ".join(bad)
                            + ". Fix only that and answer with the same JSON.",
                        },
                    ],
                )
                if fixed and str(fixed.get("draft") or "").strip():
                    data, draft = fixed, str(fixed["draft"]).strip()
                still = self._problems(draft)
                note = (
                    "\n\n(Manager: Checker found "
                    + "; ".join(bad)
                    + ". Writer revised it"
                    + (
                        " and it now passes.)"
                        if not still
                        else ", but problems remain: " + "; ".join(still) + ".)"
                    )
                )
            self.state["ctx"]["draft"] = draft
        reply = str(data.get("reply") or "").strip()
        out = (reply + ("\n\n" + draft if draft else "") + note).strip()
        if draft:
            out += '\n\nSay "save this as the Group message" (or DM) to use it.'
        return True, out or "No answer."

    def _ai_json(self, key, system, messages):
        import assistant, ai_call

        try:
            msg = assistant._chat_raw(
                key, system, [], messages, max_tokens=1800, thinking_mode=False
            )
        except Exception:
            return None
        return ai_call.json_of(msg.get("content", "") if isinstance(msg, dict) else "")

    def _facts(self):
        app = self.app
        parts = []
        for k in ("group", "dm"):
            try:
                parts.append(f"Saved {k.upper()} message:\n" + app.get_message(k)["text"][:2500])
            except Exception:
                pass
        try:
            left = app.read_left()
            parts.append(f"Amount still needed now: Rs. {left:,}")
        except Exception:
            pass
        try:
            parts.append("Case: " + app.active_case_name())
        except Exception:
            pass
        return "\n\n".join(parts)

    def _known_numbers(self):
        nums = set()
        for k in ("group", "dm"):
            try:
                nums |= set(re.findall(r"\d[\d,]*", self.app.get_message(k)["text"]))
            except Exception:
                pass
        try:
            left = int(self.app.read_left())
            for n in (left, math.ceil(left / 2000), math.ceil(left / 1000)):
                nums |= {str(n), f"{n:,}"}
        except Exception:
            pass
        return {n.replace(",", "") for n in nums}

    def _problems(self, text, kind="group"):
        """Checker (code only): facts, amounts, payment line, banned phrases, language, duplicates."""
        import quality, dm_variants, message_rules
        from focus_bank import wording_key

        out = []
        try:
            source = self.app.get_message(kind)["text"]
        except Exception:
            source = ""
        new = sorted(
            {
                n
                for n in re.findall(r"\d[\d,]*", text)
                if n.replace(",", "") not in self._known_numbers()
            }
        )
        if new:
            out.append("numbers not in the verified facts: " + ", ".join(new[:5]))
        if "03097458815" in source and "03097458815" not in text:
            out.append("the payment number 03097458815 is missing")
        hard = quality.hard_reason(source, text)
        if hard:
            out.append(hard)
        if source and dm_variants.language_changed(source, text):
            out.append("the language changed")
        if source and message_rules.is_pdf_message(source):
            out += ["PDF rule: " + p for p in message_rules.problems(text)[:2]]
        try:
            row = self.app.focus_bank().get(kind)
            keys = {
                wording_key(v): i
                for i, v in enumerate([row.get("source", "")] + (row.get("items") or []))
            }
            if wording_key(text) in keys:
                i = keys[wording_key(text)]
                out.append(
                    "same as the saved base message" if i == 0 else f"same as saved version {i}"
                )
        except Exception:
            pass
        return out

    def _checker(self, kind, text):
        if kind == "progress":
            return (
                True,
                "I check drafts and versions in code: facts, amounts, payment line, banned phrases, language and duplicates.",
            )
        body = self._quoted(text) or self.state["ctx"].get("draft")
        if not body:
            return (
                False,
                "Give me the message to check, in quotes, or ask Writer for a draft first.",
            )
        bad = self._problems(body, "dm" if re.search(r"(?i)\bdms?\b", text) else "group")
        return True, ("Problems: " + "; ".join(bad)) if bad else "Passed every check."

    def _replies(self, kind, text):
        import reply_intent

        q = self._quoted(text)
        if q and kind != "progress":
            label, why = reply_intent.classify(q)
            return (
                True,
                f'"{q[:80]}" reads as: {label} ({why}). A payment is never treated as verified.',
            )
        s = self.app.ENGINE.summary()
        rs = self.app.reply_setup.get(self.app.STORE) if self.app.STORE else {}
        return True, (
            f"Auto replies {'on' if rs.get('enabled') else 'off'}; donation signals today: "
            f"{s.get('possible_donations_today', 0)}; last reply check: "
            + self.app._ago(self.app.ENGINE.s.get("last_reply_read"))
            + "."
        )

    def _dms(self, kind, text):
        s = self.app.ENGINE.summary()
        ledger = (self.app.STORE.get("dm_daily", {}) if self.app.STORE else {}) or {}
        return True, (
            f"DMs {'on' if s.get('dm_enabled') else 'off'}{' (waiting for Auto)' if s.get('dm_enabled') and not self.app.auto_on() else ''}; "
            f"Auto DMs today {s.get('dms_today', 0)}/{s.get('dm_daily', 0)}; all DMs today {ledger.get('count', 0)}/"
            f"{self.app.DM_DAILY_CAP}; opt-outs today {ledger.get('optouts', 0)}; at least "
            f"{self.app.DM_MIN_GAP // 60} min between DMs; new contacts {'allowed' if s.get('dm_new') else 'off (consent first)'}."
        )

    def _volunteers(self, kind, text):
        flow = self.app.ENGINE.s.get("vol_flow", {}) or {}
        steps = {}
        for st in flow.values():
            steps[st.get("step", "?")] = steps.get(st.get("step", "?"), 0) + 1
        waiting = [f"…{p[-4:]}" for p, st in flow.items() if st.get("step") == "waiting_owner"]
        try:
            total = len(self.app.donors().volunteers.view().get("items") or [])
        except Exception:
            total = 0
        msg = f"{total} volunteers saved. This case: " + (
            ", ".join(f"{n} {k}" for k, n in sorted(steps.items())) or "nobody asked yet"
        )
        if waiting:
            msg += ". Waiting for YOUR answer: " + ", ".join(waiting[:10])
        return True, msg + "."

    def _auto(self, kind, text):
        s = self.app.ENGINE.summary()
        on = self.app.auto_on()
        nxt = self.app.ENGINE.status().get("next", []) if on else []
        bank = self.app.focus_bank().get("group")
        msg = (
            f"Auto {'on' if on else 'off'}; pace {s.get('pace')}: GiveLife every {s.get('main_every')} min, "
            f"freelance every {s.get('freelance_every')} min; posts today {s.get('posts_today', 0)}; "
            f"{len(bank.get('items') or [])} Group versions ({bank.get('state', 'Not generated')})"
        )
        if s.get("paused"):
            msg += "; paused: " + ", ".join(f"{k} {h} h" for k, h in s["paused"].items())
        if nxt:
            msg += "; next: " + ", ".join(f"{n['group']} in {n['in']} min" for n in nxt[:3])
        return True, msg + "."

    def _plan(self, kind, text):
        plan = self.app.plan_get()
        left = self.app.read_left()
        mins = round(self.app.ENGINE.level()[3])
        if not plan:
            return True, f"No case plan. Rs. {left:,} left; {mins} min since money came in."
        f = plan.get("facts", {})
        return True, (
            f"Plan {plan.get('state')}"
            + (f" ({plan['reason']})" if plan.get("reason") else "")
            + f" for {f.get('name', '?')}; Rs. {left:,} left; {mins} min since money came in"
            + (
                "; Slow message after 90 min without money."
                if plan.get("state") == "normal"
                else "."
            )
        )

    @staticmethod
    def _quoted(text):
        m = re.search(r'["“]([\s\S]{3,}?)["”]', text) or re.search(r":\s*\n?([\s\S]{8,})$", text)
        return m.group(1).strip() if m else ""

    # ------------------------------------------------------------------ Manager's own answers
    def _manager_answer(self, text):
        import assistant

        overview = self.overview()
        key = assistant.client()
        if not key:
            self._say(
                "manager", "The AI is not connected, so here are the real facts:\n" + overview
            )
            return
        try:
            msg = assistant._chat_raw(
                key,
                "You are Manager of the GiveLife charity app. Answer the owner in short, plain English using ONLY"
                " the live status below. If the answer is not in it, say you do not know. Never claim an agent did"
                " something that the status does not show. Suggest the owner ask a named agent when that helps.\n\n"
                "LIVE STATUS:\n" + overview,
                [],
                [{"role": "user", "content": text}],
                max_tokens=900,
                thinking_mode=False,
            )
            answer = str(msg.get("content", "")).strip() if isinstance(msg, dict) else ""
        except Exception as e:
            answer = ""
            self._say("manager", f"The AI did not answer ({str(e)[:80]}). Real facts:\n" + overview)
            return
        self._say("manager", answer or "No answer. Real facts:\n" + overview)

    def overview(self):
        lines = []
        for a in ("writer", "replies", "dms", "volunteers", "auto", "plan"):
            try:
                lines.append(f"{NAMES[a]}: " + getattr(self, "_" + a)("progress", "")[1])
            except Exception as e:
                lines.append(f"{NAMES[a]}: could not read ({str(e)[:60]})")
        lines += ["Issue: " + i["text"] for i in self.issues()]
        return "\n".join(lines)

    # ------------------------------------------------------------------ watching, recovery, memory
    def memory_status(self):
        store = self.app.STORE
        if not store:
            return {
                "ok": False,
                "text": "No database is connected (DB_URI). Learning and versions are lost on every restart.",
            }
        try:
            probe = uuid.uuid4().hex
            store.put("manager_probe", probe)
            if store.get("manager_probe") != probe:
                raise ValueError("read back a different value")
        except Exception as e:
            return {
                "ok": False,
                "text": f"The database is not saving right now ({str(e)[:80]}). Recent changes may be lost.",
            }
        pending = int(getattr(store, "pending_writes", 0) or 0)
        if pending:
            return {
                "ok": False,
                "text": f"{pending} saves are waiting to reach the database; they retry by themselves.",
            }
        return {"ok": True, "text": "Memory is saved in the database."}

    def issues(self):
        """Real problems right now, each checked independently so one failure never hides the others."""
        app, out = self.app, []

        def check(fn):
            try:
                fn()
            except Exception as e:
                out.append(
                    {
                        "key": "check-" + fn.__name__,
                        "level": "warn",
                        "text": f"Could not check {fn.__name__}: {str(e)[:80]}",
                    }
                )

        def memory():
            m = self.memory_status()
            if not m["ok"]:
                out.append({"key": "memory", "level": "error", "text": m["text"]})

        def ai():
            if not __import__("assistant").client():
                out.append(
                    {
                        "key": "ai",
                        "level": "error",
                        "text": "The AI is not connected (DEEPSEEK_API_KEY). Writing and unclear replies need it.",
                    }
                )

        def whatsapp():
            if not app.wa_ok():
                out.append(
                    {
                        "key": "wa",
                        "level": "error",
                        "text": "WhatsApp is disconnected. Nothing can be sent until it is linked.",
                    }
                )
            else:
                missing = list(app.check_groups().get("missing") or [])
                if missing:
                    out.append(
                        {
                            "key": "groups",
                            "level": "error",
                            "text": "The linked WhatsApp number is not in: "
                            + ", ".join(missing)
                            + ". Sends to those groups fail while the Test group still works. "
                            "Add the number to the group, or link the right number.",
                        }
                    )

        def writer():
            bank = app.focus_bank()
            for k in ("group", "dm"):
                row = bank.get(k)
                if row.get("auto_failed") or row.get("state") in ("Needs retry", "Partial"):
                    if row.get("error"):
                        out.append(
                            {
                                "key": "writer-" + k,
                                "level": "warn",
                                "text": f"Writer ({k.upper()}): {row['error'][:160]}",
                            }
                        )

        def groups():
            for k, h in app.ENGINE.summary().get("paused", {}).items():
                out.append(
                    {
                        "key": "paused-" + k,
                        "level": "warn",
                        "text": f"Group Poster: {k} is paused for {h} more hours.",
                    }
                )

        def volunteers():
            n = sum(
                1
                for st in (app.ENGINE.s.get("vol_flow") or {}).values()
                if st.get("step") == "waiting_owner"
            )
            if n:
                out.append(
                    {
                        "key": "volunteers",
                        "level": "ask",
                        "text": f"{n} volunteer(s) replied and wait for your answer.",
                    }
                )

        def fundraising():
            if app.read_left() > 0 and app.ENGINE.level()[0] in ("L3", "L4"):
                mins = round(app.ENGINE.level()[3])
                tip = (
                    ""
                    if app.focus_bank().get("group").get("items")
                    else " Generate 5 Versions would give Auto fresh wording."
                )
                out.append(
                    {
                        "key": "slow",
                        "level": "ask",
                        "text": f"Donations are slow: {mins} min without money.{tip} A new photo or family update helps most.",
                    }
                )

        for fn in (memory, ai, whatsapp, writer, groups, volunteers, fundraising):
            check(fn)
        return out

    def watch(self):
        """Background check: record new problems once, and retry only safe, recoverable work."""
        with self.lock:
            seen = {
                d.get("key")
                for d in self.state["decisions"][-50:]
                if _now() - d.get("at", 0) < 6 * 3600
            }
            for i in self.issues():
                if i["key"] not in seen:
                    self.state["decisions"].append(
                        {"at": _now(), "key": i["key"], "text": "Noticed: " + i["text"]}
                    )
            self._recover()
            self._save()

    def _recover(self):
        """A Writer top-up that failed for a temporary reason is retried at most 3 times a day, 30 min apart."""
        bank = self.app.focus_bank()
        day = time.strftime("%Y-%m-%d")
        for k in ("group", "dm"):
            row = bank.get(k)
            if not row.get("auto_failed") or not TRANSIENT.search(str(row.get("error", ""))):
                continue
            r = self.state["retries"].get(k, {})
            if r.get("day") != day:
                r = {"day": day, "n": 0, "at": 0}
            if r["n"] >= 3 or _now() - r["at"] < 1800:
                continue
            r.update(n=r["n"] + 1, at=_now())
            self.state["retries"][k] = r
            try:
                bank.retry(k)
                text = f"Retried Writer's {k.upper()} batch after a temporary error ({r['n']}/3 today)."
            except Exception as e:
                text = f"Could not retry Writer's {k.upper()} batch: {str(e)[:80]}"
            self.state["decisions"].append({"at": _now(), "key": "retry-" + k, "text": text})

    def start(self, every=60):
        if self.thread:
            return

        def loop():
            while True:
                time.sleep(every)
                try:
                    self.watch()
                except Exception:
                    pass  # the watcher never stops the app

        self.thread = threading.Thread(target=loop, daemon=True, name="manager-watch")
        self.thread.start()

    def view(self):
        with self.lock:
            issues = self.issues()
            running = [t for t in self.state["tasks"][-20:] if t.get("status") == "running"]
            return {
                "id": "manager",
                "name": "Manager",
                "role": "Talk to me. I pass your request to the right agent, check its work and show you its real reply.",
                "status": "Error"
                if any(i["level"] == "error" for i in issues)
                else "Working"
                if running
                else "Active",
                "now": f"{len(issues)} thing(s) need attention" if issues else "All agents checked",
                "progress": {
                    "label": "Tasks done today",
                    "value": sum(
                        1
                        for t in self.state["tasks"]
                        if t.get("status") == "done" and _now() - t.get("at", 0) < 86400
                    ),
                },
                "facts": [i["text"] for i in issues],
                "errors": [],
                "feed": [
                    {"id": str(d["at"]), "time": d["at"], "text": d["text"]}
                    for d in self.state["decisions"][-15:]
                ],
                "chat": self.state["chat"][-60:],
                "names": NAMES,
            }
