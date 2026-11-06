"""GiveLife agents: one Manager over seven specialist agents.

Each agent does one job and has the same two abilities:
  status() -> its real state, read from the app (no mock data)
  ask(text) -> (ok, reply), using its real functions only
The engines underneath (sending, WhatsApp, rotation, replies, volunteers, case plan) are the tested
ones in the app; agents never send WhatsApp messages themselves and never bypass consent, limits,
hold or approval. Code decides rules, limits and checks; AI only writes and judges wording.
"""

import difflib, json, math, re, threading, time, uuid

TRANSIENT = re.compile(r"(?i)timed? ?out|timeout|429|50\d|temporar|connection|reset|unavailable")
KEEP = 200


def _now():
    return time.time()


def _ago(t):
    if not t:
        return "never"
    m = int((_now() - t) // 60)
    return "just now" if m < 1 else f"{m} min ago"


def _quoted(text):
    m = re.search(r'["“]([\s\S]{3,}?)["”]', text) or re.search(r":\s*\n?([\s\S]{8,})$", text)
    return m.group(1).strip() if m else ""


# Owner language: Roman Urdu phrases and typos are mapped to intent words. Only routing reads this;
# the AI always receives the owner's original words.
ROMAN = (
    (r"\b(yaad rakh(?:o|na)|yad rakho)\b", "remember"),
    (r"\bhamesha\b", "always"),
    (r"\bkabhi (?:bhi )?nahi?\b", "never"),
    (r"\b(sab|saray|saare|sare) agents?\b", "all agents"),
    (r"\b(behtar|acha|achha) (?:karo|kar do|bana do)\b", "improve"),
    (r"\b(chhota|chota) (?:karo|kar do)\b", "shorter"),
    (r"\b(likho|likh do)\b", "write"),
    (r"\b(save karo|save kar do|rakh lo)\b", "save"),
    (r"\b(check karo|check kar do)\b", "check"),
    (r"\b(galat|ghalat|bekar|bakwas|pasand nahi)\b", "wrong"),
    (r"\b(kya haal|kahan tak|progress batao)\b", "progress"),
    (r"\b(phir|uske baad|us ke baad)\b", "then"),
    (r"\bagar\b", "if"),
)
VOCAB = "writer checker poster guard reader volunteer volunteers plan manager agents improve rewrite generate versions progress status remember always never check save shorter longer write draft".split()
ACTION = re.compile(
    r"\?\s*$|\b(how many|kitne|dms?|case|posts?|replies|writer|checker|poster|guard|reader|volunteers?|plan|agents|improve|rewrite|generate|versions|progress|status|remember|always|never|check|save|write|draft|post|tell|ask)\b"
)
REJECT = re.compile(r"^\W*(no|nope|wrong|not good|weak|bad|don'?t like|dont like)\b")


def intent_text(text):
    low = " ".join(str(text).lower().split())
    for pat, word in ROMAN:
        low = re.sub(pat, word, low)
    return re.sub(
        r"[a-z]{4,}", lambda m: (difflib.get_close_matches(m[0], VOCAB, 1, 0.82) or [m[0]])[0], low
    )


def split_instructions(text):
    """'Ask Writer to improve it; then check it' -> two steps, in order. Message text is never split."""
    if re.search(r'["“]', text):
        return [text]
    parts = [
        p.strip()
        for p in re.split(
            r"\n\s*(?:\d+[.)]|[-•])\s+|\s*;\s*|\s+(?:and then|then|phir|uske baad)\s+",
            "\n" + text.strip(),
        )
        if p and p.strip()
    ]
    if len(parts) > 1 and all(ACTION.search(intent_text(p)) for p in parts):
        return parts
    return [text]


def math_problem(text):
    """'N people giving Rs. 2,000' must cover the amount still needed in the same message."""
    amounts = [int(a.replace(",", "")) for a in re.findall(r"(?i)rs\.?\s*(\d[\d,]{3,})", text)]
    big = [a for a in amounts if a not in (1000, 2000)]
    if not big:
        return ""
    total = max(big)
    for n, unit in re.findall(
        r"(?i)\b(\d{1,4})\s+(?:\w+\s+){0,2}(?:people|donors|log)\b[^\n]{0,40}?rs\.?\s*([12],?000)\b",
        text,
    ):
        n, unit = int(n), int(unit.replace(",", ""))
        need = math.ceil(total / unit)
        if n * unit < total or n > need + 3:
            return f"math: {n} people × Rs. {unit:,} does not match Rs. {total:,} (needs {need})"
    return ""


class Agent:
    id = name = role = ""
    words = r"$^"  # owner words that clearly mean this agent
    topics = r"$^"  # what the owner talks about when he does not name the agent
    log_words = r"$^"  # activity-log lines that belong to this agent

    def __init__(self, system):
        self.sys, self.app = system, system.app

    def status(self):
        raise NotImplementedError

    STATUS = re.compile(r"\b(status|progress|report|how many|kitne|kya haal)\b")
    talks = False  # agents that use AI can hold a conversation (Writer has its own; Checker is code only)

    def ask(self, text):
        if self.talks and not self.STATUS.search(intent_text(text)):
            return self.sys.agent_chat(self, text)
        return self.report()

    def report(self):
        s = self.status()
        return True, "; ".join([s["now"]] + list(s.get("facts") or [])) + "."

    def card(self):
        s = {"facts": [], "errors": [], "progress": {}}
        s.update(self.status())
        return {"id": self.id, "name": self.name, "role": self.role, **s}


# ---------------------------------------------------------------------------- Writer
class Writer(Agent):
    id, name = "writer", "Writer"
    role = (
        "Writes and improves your messages in your style, and makes 5 checked versions per click."
    )
    words = r"\bwriter\b"
    log_words = r"(?i)\bversions?\b|saved group message|wording"
    WRITE = re.compile(
        r"(?i)\b(write|rewrite|improve|draft|reword|make (?:it|this)|shorter|longer|softer|stronger|hook)\b"
    )
    GENERATE = re.compile(r"(?i)\b(generate|make|write)\b.*\bversions?\b")
    SAVE = re.compile(
        r"(?i)\b(save|use)\b.*\b(draft|this|it)\b.*\b(group|dm)\b|\b(group|dm)\b.*\b(save|use)\b.*\b(draft|this|it)\b"
    )
    APPROVE = re.compile(
        r"(?i)^(?:i\s+)?approve(?:d)?(?:\s+(?:it|this|this message))?"
        r"(?:\s*[,;:]?\s*(?:and\s+)?(?:save|put)\s+(?:it|this)"
        r"\s+(?:to|in|as)\s+(?:the\s+)?group(?:\s+messages?)?)?[.!\s]*$"
    )

    def status(self):
        bank = self.app.focus_bank()
        g, d = bank.get("group"), bank.get("dm")
        n = len(g.get("items") or [])
        state = g.get("state", "Not generated")
        errors = (
            [
                {
                    "text": g["error"][:200],
                    "fix": "Write the next 5 again. Saved versions are kept.",
                    "action": "retry_writer",
                }
            ]
            if g.get("error") and state in ("Needs retry", "Partial")
            else []
        )
        return {
            "state": "Working"
            if "Generating" in (state, d.get("state"))
            else "Error"
            if errors
            else "Active"
            if n
            else "Idle",
            "now": f"Group {n} versions ({state}); DM {len(d.get('items') or [])} versions ({d.get('state', 'Not generated')})",
            "progress": {"label": "Group versions ready", "value": n},
            "errors": errors,
        }

    def ask(self, text):
        bank = self.app.focus_bank()
        low = intent_text(text)
        kind = "dm" if re.search(r"\bdms?\b", low) else "group"
        if self.APPROVE.fullmatch(low):
            preview = self.sys.state.get("writer_preview") or {}
            return self.approve(preview.get("id"))
        if self.SAVE.search(low):
            preview = self.sys.state.get("writer_preview") or {}
            if kind == "group":
                if preview.get("status") == "pending":
                    return self.approve(preview.get("id"))
                return (
                    False,
                    "No checked Group draft is awaiting approval. Ask Writer to draft one first.",
                )
            draft = self.sys.ctx.get("draft")
            if not draft:
                return False, "There is no draft from me yet. Ask me to write one first."
            bad = self.sys.agents["checker"].problems(draft, kind)
            if bad:
                return False, "I will not save it: " + "; ".join(bad)
            ok = bank.save(kind, draft).get("source") == draft
            if ok:
                self.sys.note_draft("approved", draft)
            return ok, f"Saved as the {kind.upper()} base message." if ok else "Saving failed."
        if self.GENERATE.search(low):
            before = len(bank.get(kind).get("items") or [])
            row = bank.generate(kind)
            ok = row.get("state") == "Generating" or len(row.get("items") or []) > before
            return ok, (
                f"Writing 5 new {kind.upper()} versions ({before} saved). Each is checked before it is saved."
                if ok
                else f"Could not start: {row.get('error') or row.get('state')}"
            )
        if re.search(r"\b(progress|status)\b", low) and not self.WRITE.search(low):
            return True, self.status()["now"] + "."
        return self.chat(text, kind)

    def approve(self, preview_id):
        """Explicit owner approval: save the selected, checked Group draft; never send."""
        preview = self.sys.state.get("writer_preview") or {}
        if not preview_id or preview.get("id") != preview_id or preview.get("status") != "pending":
            return (
                False,
                "That Group preview is no longer awaiting approval. Review the newest draft.",
            )
        text = str(preview.get("text") or "")
        if preview.get("kind") != "group" or not text:
            return False, "Only a pending Group draft can be approved here."
        issues = self.sys.agents["checker"].problems(text, "group")
        if issues:
            return False, "Not saved. Checker found: " + "; ".join(issues)
        try:
            bank = self.app.focus_bank()
            row = bank.save("group", text, revision=preview.get("base_revision"))
            ok = row.get("source") == text and self.app.get_message("group")["text"] == text
        except ValueError as exc:
            return False, "Not saved: " + str(exc)
        if not ok:
            return False, "Saving could not be verified. No message was approved."
        self.sys.note_draft("approved", text)
        self.sys.state["writer_preview"] = None
        self.sys.ctx.pop("draft", None)
        return True, "Approved and saved to Group Messages. Nothing was sent to WhatsApp."

    def chat(self, text, kind="group"):
        """Conversation like ChatGPT, grounded in verified facts; Checker reviews every draft once more."""
        import assistant

        key = assistant.client()
        if not key:
            return False, "I cannot write right now: the AI is not connected (DEEPSEEK_API_KEY)."
        style, corrections = [], []
        try:
            style = self.app.focus_bank().owner_style(limit=2)
        except Exception:
            pass
        try:
            corrections = [str(c)[:200] for c in (__import__("dm_variants").CORRECTIONS() or [])][
                -12:
            ]
        except Exception:
            pass
        system = (
            "You are Writer, the fundraising message writer of GiveLife Foundation, talking with the owner.\n"
            "Use ONLY the verified facts below. Never invent medical details, ages, names, amounts, deadlines or"
            " urgency. Keep the payment number and the 'EASYPAISA ONLY' line exactly. Keep WhatsApp formatting"
            " valid (*bold* and _italic_ in pairs). Follow every owner preference. Write in the owner's style."
            " Answer questions and discuss ideas plainly.\n"
            'Reply with ONE JSON object: {"reply": "your answer to the owner", "draft": "the full WhatsApp'
            ' message if you wrote or rewrote one, else empty"}\n\nVERIFIED FACTS:\n'
            + self.sys.facts()
            + (
                "\n\nOWNER STYLE EXAMPLES:\n" + "\n---\n".join(s[:900] for s in style)
                if style
                else ""
            )
            + (
                "\n\nOWNER PREFERENCES (newest wins):\n" + "\n".join("- " + c for c in corrections)
                if corrections
                else ""
            )
            + self.sys.draft_lessons()
            + self.sys.context_for("writer")
        )
        history = [
            {"role": "user" if m["who"] == "you" else "assistant", "content": m["text"][:1500]}
            for m in self.sys.state["chat"][-10:-1]
            if m.get("agent") == "writer" and m["who"] in ("you", "writer")
        ]
        messages = history + [{"role": "user", "content": text}]
        data = self.sys.ai_json(key, system, messages)
        if not data:
            return (
                False,
                "The AI answer was not valid, so I show nothing rather than guess. Try again.",
            )
        draft, note = str(data.get("draft") or "").strip(), ""
        if draft:
            checker = self.sys.agents["checker"]
            prev = self.sys.ctx.get("draft") or ""
            same = (
                ["almost the same as the last draft; write it genuinely differently"]
                if prev and difflib.SequenceMatcher(None, prev, draft).ratio() > 0.92
                else []
            )
            bad = checker.problems(draft, kind) + same
            m = self.sys.state["metrics"]
            m["drafts"] = m.get("drafts", 0) + 1
            m["first_pass"] = m.get("first_pass", 0) + (not bad)
            if bad:  # Manager's quality gate: one revision with Checker's exact reasons
                fixed = self.sys.ai_json(
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
                still = checker.problems(draft, kind)
                note = (
                    "\n\n(Checker found "
                    + "; ".join(bad)
                    + ". Writer revised it"
                    + (
                        " and it now passes.)"
                        if not still
                        else ", but problems remain: " + "; ".join(still) + ".)"
                    )
                )
            final_issues = checker.problems(draft, kind)
            if prev and difflib.SequenceMatcher(None, prev, draft).ratio() > 0.92:
                final_issues.append("too similar to the previous draft")
            if final_issues:
                return False, (
                    "No new preview: Checker rejected the draft: "
                    + "; ".join(final_issues)
                    + ". The previous draft is still available."
                )
            self.sys.ctx["draft"] = draft
            if kind == "group":
                base = self.app.focus_bank().get("group")
                self.sys.state["writer_preview"] = {
                    "id": uuid.uuid4().hex[:14],
                    "kind": "group",
                    "text": draft,
                    "status": "pending",
                    "base_revision": base.get("revision", ""),
                    "created": _now(),
                }
        out = (
            str(data.get("reply") or "").strip() + ("\n\n" + draft if draft else "") + note
        ).strip()
        if draft:
            out += (
                "\n\nReview the WhatsApp-style preview, then choose Next or Approve."
                if kind == "group"
                else '\n\nSay "save this as the DM message" to use it.'
            )
        return True, out or "No answer."


# ---------------------------------------------------------------------------- Checker
class Checker(Agent):
    id, name = "checker", "Checker"
    role = "Checks every draft and version in code: facts, amounts, payment line, formatting, language, duplicates."
    words = r"\bchecker\b|\b(check|verify|review)\b"

    def status(self):
        return {"state": "Active", "now": "Checks every draft before it is shown or saved"}

    def known_numbers(self):
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

    def problems(self, text, kind="group"):
        import quality, dm_variants, message_rules
        from focus_bank import format_problem, wording_key

        out = []
        try:
            source = self.app.get_message(kind)["text"]
        except Exception:
            source = ""
        known = self.known_numbers()
        new = sorted({n for n in re.findall(r"\d[\d,]*", text) if n.replace(",", "") not in known})
        if new:
            out.append("numbers not in the verified facts: " + ", ".join(new[:5]))
        if "03097458815" in source and "03097458815" not in text:
            out.append("the payment number 03097458815 is missing")
        for check in (
            lambda: quality.hard_reason(source, text),
            lambda: format_problem(source, text, bullets=False) if source else "",
            lambda: (
                "the language changed"
                if source and dm_variants.language_changed(source, text)
                else ""
            ),
        ):
            reason = check()
            if reason:
                out.append(reason)
        if math_problem(text):
            out.append(math_problem(text))
        if source and message_rules.is_pdf_message(source):
            out += ["PDF rule: " + p for p in message_rules.problems(text)[:2]]
        try:
            row = self.app.focus_bank().get(kind)
            keys = {
                wording_key(v): i
                for i, v in enumerate([row.get("source", "")] + (row.get("items") or []))
            }
            i = keys.get(wording_key(text))
            if i is not None:
                out.append(
                    "same as the saved base message" if i == 0 else f"same as saved version {i}"
                )
        except Exception:
            pass
        return out

    def ask(self, text):
        body = _quoted(text) or self.sys.ctx.get("draft")
        if not body:
            return (
                False,
                "Give me the message to check, in quotes, or ask Writer for a draft first.",
            )
        bad = self.problems(body, "dm" if re.search(r"(?i)\bdms?\b", text) else "group")
        return True, ("Problems: " + "; ".join(bad)) if bad else "Passed every check."


# ---------------------------------------------------------------------------- Group Poster
class GroupPoster(Agent):
    id, name = "auto", "Group Poster"
    role = "Posts saved versions to the groups on the timers, never repeating a wording in a round."
    words = r"\bgroup ?poster\b"
    topics = r"\bnext (?:group )?post|\bposting\b|\bgroup posts?\b|\bschedule\b|\bpace\b"
    talks = True

    def status(self):
        app = self.app
        snap = app.live_snapshot()
        st, sm = snap["status"], snap["summary"]
        wa = st.get("state") != "offline"
        errors = (
            [
                {
                    "text": "WhatsApp is not connected.",
                    "fix": "Open the main page and link WhatsApp.",
                    "action": "open_home",
                }
            ]
            * (not wa)
            + [
                {"text": e.get("text", ""), "fix": "It retries by itself.", "action": ""}
                for e in st.get("errors") or []
            ]
            + (
                [
                    {
                        "text": "Everything is on hold.",
                        "fix": "Resume when ready.",
                        "action": "resume",
                    }
                ]
                if snap["hold"]
                else []
            )
        )
        facts = [
            f"Pace {sm.get('pace', '')}: GiveLife every {sm.get('main_every', '?')} min, freelance every {sm.get('freelance_every', '?')} min"
        ] + [f"Next: {n['group']} in {n['in']} min" for n in st.get("next", [])]
        return {
            "state": "Error"
            if errors
            else "Working"
            if st.get("state") in ("sending", "reading")
            else "Active"
            if snap["on"]
            else "Idle",
            "now": st.get("now", "") or ("Auto on" if snap["on"] else "Automatic actions off"),
            "progress": {"label": "Posts today", "value": sm.get("posts_today", 0)},
            "facts": facts,
            "errors": errors,
            "rules": app.ENGINE.rule_list(),
        }

    def rule(self, text):
        """A clear standing rule ("post in main every 20 min") saved to the real rule list. None = not a rule."""
        import rules

        rule, description = rules.parse(re.sub(r"(?i)\bfree\b", "freelance", text))
        if not rule or rule["kind"] in ("schedule", "note"):
            return None
        if any(
            r["text"].casefold() == rules.describe(rule).casefold()
            for r in self.app.ENGINE.rule_list()
        ):
            return True, "Already saved: " + rules.describe(rule)
        self.app.ENGINE.add_rule(rule)
        ok = any(r["text"] == rules.describe(rule) for r in self.app.ENGINE.rule_list())
        return ok, ("Saved rule: " if ok else "Could not save the rule: ") + description


# ---------------------------------------------------------------------------- DM Guard
class DMGuard(Agent):
    id, name = "dms", "DM Guard"
    role = "Sends donor DMs only within the limits: 40 a day, 3+ minutes apart, consent and opt-outs first."
    words = r"\bdm ?(?:guard|sender)\b"
    topics = r"\bdms?\b|direct messages?|opt.?outs?"
    talks = True
    log_words = r"(?i)\bdms?\b|donor dm"

    def status(self):
        app = self.app
        sm = app.ENGINE.summary()
        ledger = (app.STORE.get("dm_daily", {}) if app.STORE else {}) or {}
        on = sm.get("dm_enabled") and app.auto_on()
        return {
            "state": "Active" if on else "Idle",
            "now": "DMs on"
            if on
            else "DMs set, waiting for Auto"
            if sm.get("dm_enabled")
            else "DMs off",
            "progress": {
                "label": "DMs today",
                "value": ledger.get("count", 0),
                "max": app.DM_DAILY_CAP,
            },
            "facts": [
                f"Automatic DMs today {sm.get('dms_today', 0)}/{sm.get('dm_daily', 0)}",
                f"Opt-outs today {ledger.get('optouts', 0)} (2 pause DMs for the day)",
                f"At least {app.DM_MIN_GAP // 60} min between DMs; new contacts {'allowed' if sm.get('dm_new') else 'off (consent first)'}",
            ],
        }


# ---------------------------------------------------------------------------- Reply Reader
class ReplyReader(Agent):
    id, name = "replies", "Reply Reader"
    role = "Reads replies: donation claims, shares, questions, promises, opt-outs. A payment is never treated as verified."
    words = r"\breply ?reader\b"
    topics = r"\brepl(?:y|ied|ies)\b|\bdonated\b|\bthank"
    talks = True
    log_words = r"(?i)repl|answered|asked not to|said later|reminder|money noticed|thank"

    def status(self):
        app = self.app
        rs = app.reply_setup.get(app.STORE) if app.STORE else {}
        on = app.auto_on() and rs.get("enabled")
        return {
            "state": "Active" if on else "Idle",
            "now": "Auto replies on" if rs.get("enabled") else "Auto replies off",
            "progress": {
                "label": "Donation claims today",
                "value": app.ENGINE.summary().get("possible_donations_today", 0),
            },
            "facts": [f"Last reply check: {_ago(app.ENGINE.s.get('last_reply_read'))}"],
        }

    def ask(self, text):
        import reply_intent

        q = _quoted(text)
        if q:
            label, why = reply_intent.classify(q)
            return (
                True,
                f'"{q[:80]}" reads as: {label} ({why}). A payment is never treated as verified.',
            )
        return super().ask(text)


# ---------------------------------------------------------------------------- Volunteer Guide
class VolunteerGuide(Agent):
    id, name = "volunteers", "Volunteer Guide"
    role = "Asks volunteers to share, one message at a time: ask, poster, 'Share this brother.', check, thanks."
    words = r"\bvolunteer(?: guide)?s?\b"
    talks = True
    log_words = r"(?i)volunteer"

    def status(self):
        flow = self.app.ENGINE.s.get("vol_flow", {}) or {}
        steps = {}
        for st in flow.values():
            steps[st.get("step", "?")] = steps.get(st.get("step", "?"), 0) + 1
        waiting = [f"…{p[-4:]}" for p, st in flow.items() if st.get("step") == "waiting_owner"]
        try:
            total = len(self.app.donors().volunteers.view().get("items") or [])
        except Exception:
            total = 0
        active = sum(n for k, n in steps.items() if k in ("asked", "poster"))
        return {
            "state": "Working" if active else "Idle",
            "now": f"{total} volunteers; this case: "
            + (", ".join(f"{n} {k}" for k, n in sorted(steps.items())) or "nobody asked yet"),
            "progress": {"label": "Asked this case", "value": len(flow)},
            "facts": ["Waiting for YOUR answer: " + ", ".join(waiting[:10])] if waiting else [],
        }


# ---------------------------------------------------------------------------- Case Plan
class CasePlan(Agent):
    id, name = "plan", "Case Plan"
    role = (
        "Switches between the Normal and Slow messages from the case facts and donation progress."
    )
    words = r"\bcase ?plan\b"
    topics = r"\bcase\b|\bpaise\b|reh gaye|amount left|\bhow much\b.*\bleft\b|\bslow message"
    talks = True
    log_words = r"(?i)case plan"

    def status(self):
        app = self.app
        plan, left = app.plan_get(), app.read_left()
        mins = round(app.ENGINE.level()[3])
        active = bool(plan) and plan.get("state") in __import__("case_plan").ACTIVE
        return {
            "state": "Active" if active else "Idle",
            "now": (plan or {}).get("state", "No case plan"),
            "progress": {"label": "Amount left (Rs.)", "value": left},
            "facts": [
                f"{mins} min since money came in"
                + (
                    "; the Slow message starts after 90 min"
                    if (plan or {}).get("state") == "normal"
                    else ""
                )
            ],
        }

    def report(self):
        s = self.status()
        return True, f"{s['now']}; Rs. {s['progress']['value']:,} left; " + s["facts"][0] + "."


# ---------------------------------------------------------------------------- Manager
class Manager:
    """The owner talks to Manager. It routes each request to the right agent, shows that agent's real
    reply, checks quality, tracks every task, watches for problems and retries only safe work."""

    ORDER = (Writer, Checker, GroupPoster, DMGuard, ReplyReader, VolunteerGuide, CasePlan)
    ALL = re.compile(r"(?i)\b(all|every|each) (?:the )?agents?\b|\beveryone\b")
    FOLLOW = re.compile(r"(?i)\b(it|this|that|again|more|better|shorter|longer|another)\b")
    REMEMBER = re.compile(r"(?i)\s*(remember|always|never|from now|in future)\b")

    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.file = app.DATA / "agents.json"
        self.agents = {cls.id: cls(self) for cls in self.ORDER}
        self.state = self._load()
        self.thread = None
        self._icache, self._irunning = (0.0, []), False

    @property
    def ctx(self):
        return self.state["ctx"]

    # -------------------------------------------------------------- memory: database first, file copy
    def _load(self):
        base = {
            "chat": [],
            "tasks": [],
            "decisions": [],
            "ctx": {},
            "retries": {},
            "drafts": [],
            "writer_preview": None,
            "metrics": {},
            "regressions": [],
            "summaries": {},
        }
        try:
            saved = self.app.STORE.get("agents_state") if self.app.STORE else None
            if not saved and self.file.exists():
                saved = json.loads(self.file.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                base.update({k: saved[k] for k in base if k in saved})
        except Exception:
            pass
        for t in base["tasks"]:
            if t.get("status") == "running":  # a restart stopped it: never shown as done
                t.update(
                    status="interrupted",
                    result="Stopped by a restart before it finished. Ask again.",
                    verified=False,
                )
        return base

    def save(self):
        for k in ("chat", "tasks", "decisions", "drafts", "regressions"):
            self.state[k] = self.state[k][-KEEP:]
        raw = json.dumps(self.state, ensure_ascii=False)
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text(raw, encoding="utf-8")
        except Exception:
            pass
        if self.app.STORE:
            try:
                self.app.STORE.put("agents_state", json.loads(raw))
            except Exception:
                pass  # the file copy keeps working; memory_status() reports the database problem

    def _say(self, who, text, agent, task=None):
        item = {
            "id": uuid.uuid4().hex,
            "at": _now(),
            "who": who,
            "agent": agent,
            "text": str(text)[:4000],
        }
        if task:
            item["task"] = task
        self.state["chat"].append(item)

    def _run(self, agent_id, text, fn):
        t = {
            "id": uuid.uuid4().hex[:12],
            "at": _now(),
            "agent": agent_id,
            "instruction": text[:300],
            "status": "running",
        }
        self.state["tasks"].append(t)
        try:
            ok, reply = fn()
        except Exception as e:  # one broken agent never stops the others
            ok, reply = False, f"I could not do that: {str(e)[:200]}"
        t.update(
            status="done" if ok else "failed",
            result=str(reply)[:300],
            verified=bool(ok),
            done=_now(),
        )
        self._say(agent_id, reply, agent_id, t["id"])

    # -------------------------------------------------------------- conversation
    def handle(self, text, agent=None):
        """One owner message, optionally addressed to one agent. Returns the new chat items."""
        text = str(text or "").strip()[:2000]
        if not text:
            raise ValueError("Type a message.")
        forced = agent if agent in self.agents else None
        with self.lock:
            last = next((m for m in reversed(self.state["chat"]) if m["who"] == "you"), None)
            if last and last["text"] == text and _now() - last["at"] < 15:
                return []  # a double tap: the first one is already being handled, never twice
            start = len(self.state["chat"])
            self._say("you", text, forced or "manager")
            steps = split_instructions(text)
            if len(steps) > 1:
                self._say("manager", f"{len(steps)} steps, done in order.", forced or "manager")
            for step in steps:
                try:
                    self._route(step, forced)
                except Exception as e:
                    self._say("manager", "That did not work: " + str(e)[:200], forced or "manager")
            try:
                self.summarize(forced or self.ctx.get("agent") or "manager")
            except Exception:
                pass
            self.save()
            return self.state["chat"][start:]

    def note_draft(self, status, draft, reason=""):
        self.state["drafts"].append(
            {"at": _now(), "status": status, "draft": draft[:3000], "reason": reason[:300]}
        )
        m = self.state["metrics"]
        m[status] = m.get(status, 0) + 1

    def draft_lessons(self):
        """Approved drafts teach the style; rejected ones, with the owner's reason, what to avoid."""
        ok = [d for d in self.state["drafts"] if d["status"] == "approved"][-2:]
        no = [d for d in self.state["drafts"] if d["status"] == "rejected"][-3:]
        out = ""
        if ok:
            out += "\n\nDRAFTS THE OWNER APPROVED:\n" + "\n---\n".join(d["draft"][:900] for d in ok)
        if no:
            out += "\n\nDRAFTS THE OWNER REJECTED (avoid what the reason says):\n" + "\n---\n".join(
                f"REASON: {d['reason']}\n{d['draft'][:600]}" for d in no
            )
        return out

    def _learn_rejection(self, reason):
        """The owner rejected the last draft: keep the lesson, save the correction, and turn any mistake
        the Checker can see into a regression case that is re-checked on every watch."""
        draft = self.ctx.get("draft") or ""
        self.note_draft("rejected", draft, reason)
        bad = self.agents["checker"].problems(draft)
        if bad:
            self.state["regressions"].append({"draft": draft[:3000], "problems": bad})
        try:
            self.app.mem_add("Writer feedback on a draft: " + reason[:300])
        except Exception:
            pass

    def regression_failures(self):
        checker = self.agents["checker"]
        return [r for r in self.state["regressions"] if not checker.problems(r["draft"])]

    def _route(self, text, forced):
        low = intent_text(text)
        if self.ctx.get("draft") and REJECT.match(low) and forced in (None, "writer"):
            self._learn_rejection(text)
            forced = "writer"  # Writer revises with the reason; Checker reviews again
        if not forced and self.ALL.search(low):
            self._say("manager", "Asking every agent for its progress.", "manager")
            for a in self.agents.values():
                self._run(a.id, text, a.report)
            return
        writer = self.agents["writer"]
        # A plain "Approved" in Manager or Writer chat is an explicit save request,
        # but ONLY when a checked Group preview is actually pending.
        preview = self.state.get("writer_preview") or {}
        if (
            preview.get("status") == "pending"
            and writer.APPROVE.fullmatch(low)
            and forced in (None, "writer")
        ):
            return self._run("writer", text, lambda: writer.approve(preview["id"]))
        # Order matters: a named agent, then what you ask for, then the topic, then "it/this" follow-up.
        target = forced or next(
            (a.id for a in self.agents.values() if a.id != "checker" and re.search(a.words, low)),
            None,
        )
        pref = not forced and (self.REMEMBER.match(low) or low.startswith("if "))
        if pref:
            target = None  # a preference or condition is saved first, never mistaken for a task
        elif not target and re.search(r"\bchecker\b|^\W*(check|verify|review)\b", low):
            target = "checker"
        if (
            not target
            and not pref
            and (writer.WRITE.search(low) or writer.GENERATE.search(low) or writer.SAVE.search(low))
        ):
            target = "writer"
        if not target and not pref:
            target = next((a.id for a in self.agents.values() if re.search(a.topics, low)), None)
        if not target and not pref and self.FOLLOW.search(low) and self.ctx.get("agent"):
            target = self.ctx["agent"]  # "tell it to make it shorter"
        poster = self.agents["auto"]
        if target in (None, "auto"):
            done = poster.rule(text)
            if done:
                return self._run("auto", text, lambda: done)
        if re.search(
            r"\b(send|post|dm|bhejo|bhej do)\b.*\b(now|abhi|right now|today)\b", low
        ) and not re.search(r"\b(versions?|draft|write|improve|check)\b", low):
            return self._run(
                target or "manager",
                text,
                lambda: (
                    True,
                    "I did not send anything. Sending happens on the Groups or Donors screen, or in the main Chat,"
                    " where the WhatsApp safety checks run. Agents here prepare, check and track.",
                ),
            )
        if not target and (self.REMEMBER.match(low) or low.startswith("if ")):
            return self._run("writer", text, lambda: self._remember(text, low.startswith("if ")))
        if not target:
            return self._answer(text)
        self.ctx["agent"] = target
        mine = next(m for m in reversed(self.state["chat"]) if m["who"] == "you")
        mine["agent"] = target  # the agent's own thread keeps the whole conversation
        if not forced:
            self._say("manager", f"Passing this to {self.agents[target].name}.", "manager")
        agent = self.agents[target]
        self._run(target, text, lambda: agent.ask(text))

    def agent_chat(self, agent, text):
        """Free conversation with one agent, grounded ONLY in its real status and role. It can explain and
        advise; it never claims an action happened (actions go through the agent's real functions)."""
        import assistant

        ok, facts = agent.report()
        key = assistant.client()
        if not key:
            return True, "The AI is not connected, so here are the real facts: " + facts
        history = [
            {"role": "user" if m["who"] == "you" else "assistant", "content": m["text"][:800]}
            for m in self.state["chat"][-8:-1]
            if m.get("agent") == agent.id and m["who"] in ("you", agent.id)
        ]
        system = (
            f"You are {agent.name} in the GiveLife charity app: {agent.role}\n"
            "Talk with the owner in short, plain English (he may write Roman Urdu; answer in the same language)."
            " Use ONLY the live facts below. If something is not in them, say you do not know. You cannot send"
            " WhatsApp messages or change settings from this chat: if asked to, say which screen or agent does it."
            " Never say a task is done unless the facts show it. Owner preferences:\n"
            + "\n".join("- " + str(c)[:200] for c in self._preferences())
            + self.context_for(agent.id)
            + "\n\nLIVE FACTS:\n"
            + facts
        )
        try:
            msg = assistant._chat_raw(
                key,
                system,
                [],
                history + [{"role": "user", "content": text}],
                max_tokens=700,
                thinking_mode=False,
            )
            answer = str(msg.get("content", "")).strip() if isinstance(msg, dict) else ""
        except Exception:
            answer = ""
        return (True, answer) if answer else (True, "The AI did not answer. Real facts: " + facts)

    def context_for(self, agent_id):
        """What an agent sees besides its own last messages (Agents SDK handoff + Letta-style summary):
        a summary of its older messages and the latest turns of the whole conversation."""
        summary = self.state.get("summaries", {}).get(agent_id, {}).get("text", "")
        recent = [
            f"{m['who']}: {m['text'][:200]}"
            for m in self.state["chat"][-7:-1]
            if m.get("agent") != agent_id
            and m["who"] != "manager"
            and not (m["who"] == "you" and self.REMEMBER.match(intent_text(m["text"])))
        ]
        out = ""
        if summary:
            out += (
                "\n\nEARLIER CONVERSATION (summary, decisions still apply unless changed later):\n"
                + summary
            )
        if recent:
            out += "\n\nRECENT CONVERSATION WITH OTHER AGENTS:\n" + "\n".join(recent)
        return out

    def summarize(self, agent_id, keep=8, every=12):
        """When an agent's chat grows, older messages become a short summary instead of being forgotten."""
        import assistant, ai_call

        mine = [m for m in self.state["chat"] if m.get("agent") == agent_id]
        sums = self.state.setdefault("summaries", {})
        done = sums.get(agent_id, {}).get("upto", 0)
        old = [m for m in mine[:-keep] if m["at"] > done]
        if len(old) < every or not assistant.client():
            return
        try:
            raw = ai_call.chat(
                "Summarise this part of a charity app conversation for later. Keep every owner decision,"
                " preference, correction, fact and open task. Newer decisions replace older ones. Do not add"
                ' anything that is not written. Answer ONLY JSON: {"summary": "short bullet points"}\n\n'
                + (
                    "PREVIOUS SUMMARY:\n" + sums.get(agent_id, {}).get("text", "") + "\n\n"
                    if done
                    else ""
                )
                + "\n".join(f"{m['who']}: {m['text'][:400]}" for m in old)
            )
        except Exception:
            return
        data = ai_call.json_of(raw)
        text = str((data or {}).get("summary") or "").strip()
        if text:
            sums[agent_id] = {"text": text[:2000], "upto": old[-1]["at"]}

    def _preferences(self):
        try:
            return [str(c) for c in (__import__("dm_variants").CORRECTIONS() or [])][-8:]
        except Exception:
            return []

    def _reconcile(self, text):
        """Mem0 pattern: compare the new preference with the active ones (numbered, so the AI cannot invent
        ids) and decide ADD / UPDATE / DELETE / NONE. Returns (add_new, entries_to_retire).
        Without AI, the shared memory's same-topic rule still retires an older preference."""
        import assistant, ai_call

        entries = [
            e
            for e in getattr(getattr(self.app, "KNOWLEDGE", None), "data", {}).get("entries", [])
            if e.get("active")
        ][-40:]
        if not entries or not assistant.client():
            return True, []
        listing = "\n".join(f"{i}: {e.get('text', '')[:200]}" for i, e in enumerate(entries))
        try:
            raw = ai_call.chat(
                "You manage the owner's saved preferences for a charity messaging app.\n"
                "Compare the NEW preference with the EXISTING ones. For each existing one it replaces or contradicts,"
                ' return {"id": number, "event": "UPDATE"} (same topic, new wording or opposite decision) or'
                ' {"id": number, "event": "DELETE"} (no longer true). If the new one is already saved, return'
                ' {"event": "NONE"}. Otherwise {"event": "ADD"}. Never change unrelated preferences.\n'
                'Answer ONLY JSON: {"memory": [ ... ]}\n\nEXISTING:\n'
                + listing
                + "\n\nNEW: "
                + text[:400]
            )
        except Exception:
            return True, []  # AI trouble never blocks saving; the same-topic rule still applies
        data = ai_call.json_of(raw) or {}
        events = (
            [m for m in data.get("memory", []) if isinstance(m, dict)]
            if isinstance(data.get("memory"), list)
            else []
        )
        if not events:
            return True, []
        retire = [
            entries[int(m["id"])]
            for m in events
            if m.get("event") in ("UPDATE", "DELETE")
            and str(m.get("id", "")).isdigit()
            and int(m["id"]) < len(entries)
        ]
        add = not any(m.get("event") == "NONE" for m in events) or bool(retire)
        return add, retire

    def _remember(self, text, condition=False):
        add, retire = self._reconcile(text)
        if not add:
            return True, "That preference is already saved. Nothing changed."
        saved = self.app.mem_add(text)
        knowledge = getattr(self.app, "KNOWLEDGE", None)
        if retire and knowledge:
            with knowledge.lock:
                for e in retire:
                    if e.get("text") != text.strip():
                        e["active"] = False
                        e["superseded_by"] = "owner: " + text[:80]
                knowledge.save()
        entries = getattr(getattr(self.app, "KNOWLEDGE", None), "data", {}).get("entries", [])
        ok = bool(saved) and (
            not entries or any(e.get("active") and e.get("text") == text.strip() for e in entries)
        )
        note = (
            " I apply it when writing; I do not run automatic actions on conditions."
            if condition
            else " I use it in every new message; it replaces any older preference on the same topic."
        )
        return ok, (
            str(saved) + note
        ) if ok else "I could not confirm it was saved. Please say it again."

    def _answer(self, text):
        import assistant

        overview = self.overview()
        key = assistant.client()
        answer = ""
        if key:
            try:
                msg = assistant._chat_raw(
                    key,
                    "You are Manager of the GiveLife charity app. Answer the owner in short, plain English using ONLY"
                    " the live status below. If the answer is not in it, say you do not know. Never claim an agent"
                    " did something the status does not show. Suggest asking a named agent when that helps.\n\n"
                    "LIVE STATUS:\n" + overview,
                    [],
                    [{"role": "user", "content": text}],
                    max_tokens=900,
                    thinking_mode=False,
                )
                answer = str(msg.get("content", "")).strip() if isinstance(msg, dict) else ""
            except Exception:
                answer = ""
        self._say("manager", answer or "Here are the real facts:\n" + overview, "manager")

    def ai_json(self, key, system, messages):
        import assistant, ai_call

        try:
            msg = assistant._chat_raw(
                key, system, [], messages, max_tokens=1800, thinking_mode=False
            )
        except Exception:
            return None
        return ai_call.json_of(msg.get("content", "") if isinstance(msg, dict) else "")

    def facts(self):
        app, parts = self.app, []
        for k in ("group", "dm"):
            try:
                parts.append(f"Saved {k.upper()} message:\n" + app.get_message(k)["text"][:2500])
            except Exception:
                pass
        for fn in (
            lambda: f"Amount still needed now: Rs. {app.read_left():,}",
            lambda: "Case: " + app.active_case_name(),
        ):
            try:
                parts.append(fn())
            except Exception:
                pass
        return "\n\n".join(parts)

    def overview(self):
        lines = []
        for a in self.agents.values():
            try:
                lines.append(f"{a.name}: {a.status()['now']}")
            except Exception as e:
                lines.append(f"{a.name}: could not read ({str(e)[:60]})")
        return "\n".join(lines + ["Issue: " + i["text"] for i in self.issues()])

    # -------------------------------------------------------------- watching and safe recovery
    def memory_status(self):
        store = self.app.STORE
        if not store:
            return {
                "ok": False,
                "text": "No database is connected. Learning and versions are lost on every restart.",
            }
        try:
            probe = uuid.uuid4().hex
            store.put("agents_probe", probe)
            if store.get("agents_probe") != probe:
                raise ValueError("read back a different value")
        except Exception as e:
            return {"ok": False, "text": f"The database is not saving right now ({str(e)[:80]})."}
        pending = int(getattr(store, "pending_writes", 0) or 0)
        if pending:
            return {
                "ok": False,
                "text": f"{pending} saves are waiting to reach the database; they retry by themselves.",
            }
        return {"ok": True, "text": "Memory is saved in the database."}

    def issues_cached(self):
        """What the page shows. The real checks (WhatsApp, database, groups) are slow, so they run in the
        background and the page never waits for them."""
        if _now() - self._icache[0] > 90 and not self._irunning:
            self._irunning = True

            def refresh():
                try:
                    self.issues()
                finally:
                    self._irunning = False

            threading.Thread(target=refresh, daemon=True, name="agents-issues").start()
        return self._icache[1]

    def issues(self):
        app, out = self.app, []

        def add(key, level, text):
            out.append({"key": key, "level": level, "text": text})

        def memory():
            m = self.memory_status()
            if not m["ok"]:
                add("memory", "error", m["text"])

        def ai():
            if not __import__("assistant").client():
                add(
                    "ai",
                    "error",
                    "The AI is not connected (DEEPSEEK_API_KEY). Writing and unclear replies need it.",
                )

        def whatsapp():
            if not app.wa_ok():
                return add(
                    "wa",
                    "error",
                    "WhatsApp is disconnected. Nothing can be sent until it is linked.",
                )
            missing = list(app.check_groups().get("missing") or [])
            if missing:
                add(
                    "groups",
                    "error",
                    "The linked WhatsApp number is not in: "
                    + ", ".join(missing)
                    + ". Sends there fail while the Test group works.",
                )

        def writer():
            for k in ("group", "dm"):
                row = app.focus_bank().get(k)
                if row.get("error") and (
                    row.get("auto_failed") or row.get("state") in ("Needs retry", "Partial")
                ):
                    add("writer-" + k, "warn", f"Writer ({k.upper()}): {row['error'][:160]}")

        def groups():
            for k, h in app.ENGINE.summary().get("paused", {}).items():
                add("paused-" + k, "warn", f"Group Poster: {k} is paused for {h} more hours.")

        def volunteers():
            n = sum(
                1
                for st in (app.ENGINE.s.get("vol_flow") or {}).values()
                if st.get("step") == "waiting_owner"
            )
            if n:
                add("volunteers", "ask", f"{n} volunteer(s) replied and wait for your answer.")

        def fundraising():
            if app.read_left() > 0 and app.ENGINE.level()[0] in ("L3", "L4"):
                tip = (
                    ""
                    if app.focus_bank().get("group").get("items")
                    else " Generate 5 Versions gives Auto fresh wording."
                )
                add(
                    "slow",
                    "ask",
                    f"Donations are slow: {round(app.ENGINE.level()[3])} min without money.{tip} A new photo or a family update helps most.",
                )

        for fn in (memory, ai, whatsapp, writer, groups, volunteers, fundraising):
            try:
                fn()
            except Exception as e:
                add("check-" + fn.__name__, "warn", f"Could not check {fn.__name__}: {str(e)[:80]}")
        self._icache = (_now(), out)
        return out

    def quality_facts(self):
        m = self.state["metrics"]
        out = []
        if m.get("drafts"):
            out.append(
                f"Writer: {m.get('first_pass', 0)}/{m['drafts']} drafts passed Checker first time; {m.get('approved', 0)} approved, {m.get('rejected', 0)} rejected"
            )
        broken = self.regression_failures()
        if broken:
            out.append(f"Checker no longer catches {len(broken)} past mistake(s)")
        return out

    def watch(self):
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
            self.save()

    def _recover(self):
        """A Writer batch that failed for a temporary reason is retried at most 3 times a day, 30 min apart."""
        bank, day = self.app.focus_bank(), time.strftime("%Y-%m-%d")
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

        self.thread = threading.Thread(target=loop, daemon=True, name="agents-watch")
        self.thread.start()

    # -------------------------------------------------------------- page data and actions
    def view(self):
        app = self.app
        log = [e for e in getattr(app, "AUTOLOG", [])[-60:]]
        cards = []
        for a in self.agents.values():
            try:
                c = a.card()
            except Exception as e:
                c = {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role,
                    "state": "Error",
                    "now": f"Could not read: {str(e)[:100]}",
                    "facts": [],
                    "errors": [],
                    "progress": {},
                }
            c["feed"] = [
                {"time": e.get("time"), "text": e.get("text", "")}
                for e in log
                if re.search(a.log_words, e.get("text", "") or "")
                or (
                    a.id == "auto"
                    and not any(
                        re.search(b.log_words, e.get("text", "") or "")
                        for b in self.agents.values()
                        if b.id != "auto"
                    )
                )
            ][-15:]
            cards.append(c)
        with self.lock:
            issues = self.issues_cached()
            running = any(t.get("status") == "running" for t in self.state["tasks"][-20:])
            boss = {
                "id": "manager",
                "name": "Manager",
                "role": "Talk to me. I pass your request to the right agent, check its work and show you its real reply.",
                "state": "Error"
                if any(i["level"] == "error" for i in issues)
                else "Working"
                if running
                else "Active",
                "now": f"{len(issues)} thing(s) need attention" if issues else "All agents checked",
                "facts": [i["text"] for i in issues] + self.quality_facts(),
                "errors": [],
                "progress": {
                    "label": "Tasks done today",
                    "value": sum(
                        1
                        for t in self.state["tasks"]
                        if t.get("status") == "done" and _now() - t.get("at", 0) < 86400
                    ),
                },
                "feed": [
                    {"time": d["at"], "text": d["text"]} for d in self.state["decisions"][-15:]
                ],
            }
            chat = self.state["chat"][-120:]
        preview = self.state.get("writer_preview")
        return {
            "agents": [boss] + cards,
            "chat": chat,
            "writer_preview": preview
            if isinstance(preview, dict) and preview.get("status") == "pending"
            else None,
            "auto": bool(app.auto_on()),
            "updated": _now(),
        }

    def act(self, body):
        """Every Agents-page action. Returns the fresh view plus the new chat lines."""
        action, app = body.get("action"), self.app
        if action == "say":
            items = self.handle(body.get("text"), body.get("agent"))
            return {"messages": items, **self.view()}
        if action in ("writer_next", "writer_approve"):
            with self.lock:
                preview = self.state.get("writer_preview") or {}
                if preview.get("status") != "pending" or body.get("preview_id") != preview.get(
                    "id"
                ):
                    raise ValueError("This preview has changed. Review the current draft.")
                if action == "writer_approve":
                    ok, reply = self.agents["writer"].approve(preview["id"])
                    if not ok:
                        raise ValueError(reply)
                    self._say("writer", reply, "writer")
                    self.save()
                    return {"reply": reply, **self.view()}
                before = preview["id"]
                instruction = (
                    "Write the NEXT alternative GROUP message to the draft below. "
                    "Change BOTH the opening and body substantially, use a different truthful hook, "
                    "but preserve every verified fact, current amount, payment line, language and "
                    "the owner's formatting preferences. Return a complete new draft, no sending or saving.\n\n"
                    "PREVIOUS DRAFT:\n" + preview["text"][:3000]
                )
                start = len(self.state["chat"])
                self._say("you", "Next version", "writer")
                self._run(
                    "writer",
                    instruction,
                    lambda: self.agents["writer"].chat(instruction, kind="group"),
                )
                self.save()
                new_preview = self.state.get("writer_preview") or {}
                if new_preview.get("id") == before:
                    raise ValueError(
                        "Writer could not create a different checked draft. Your previous draft is kept."
                    )
                return {"messages": self.state["chat"][start:], **self.view()}
        if action == "auto":
            reply = app.set_auto(bool(body.get("on")))
        elif action == "rule_delete":
            app.ENGINE.delete_rule(body.get("id"))
            reply = "Rule removed."
        elif action == "fix":
            fix = body.get("fix")
            if fix == "retry_writer":
                app.focus_bank().retry("group")
                reply = "Writer is writing the next 5 again."
            elif fix == "resume":
                reply = app.set_hold(False)
            else:
                raise ValueError("Unknown fix.")
        else:
            raise ValueError("Unknown action.")
        return {"reply": reply, **self.view()}
