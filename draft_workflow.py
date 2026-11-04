"""Persistent draft task and server-issued next actions; never model-issued sends."""

import hashlib, json, re, threading, time, uuid, math
from state_shapes import mapping
import manual_commands


def digest(text):
    return hashlib.sha256(str(text).encode()).hexdigest()


def repeat_target(task, text):
    """The send-now route is deterministic; a test receipt cannot select its target."""
    if task.get("kind") != "group":
        return None
    if task.get("state") != "ready" or task.get("hash") != digest(text):
        raise ValueError("The latest draft edit is not ready. Check it before sending.")
    if not task.get("target"):
        raise ValueError(
            "Choose the group for this draft. The previous recipient will not be reused."
        )
    return task["target"]


# Update only numbers labelled as the balance. Never change a donation unit
# (for example Rs. 2,000 per donor) when the balance itself is Rs. 2,000.
_BALANCE_VALUE = r"(?:Rs\.?\s*)?(?P<sum>\d[\d,]*(?:\.\d+)?)(?:\s*(?P<scale>k|thousand|hazar|hazaar|lakh|lac))?"
_BALANCE_AFTER = re.compile(
    r"(?i)(?<![A-Za-z0-9])" + _BALANCE_VALUE
    + r"(?P<tail>\s+(?:(?:still|urgently|only|more)\s+){0,3}(?:left|needed|required|remaining|to\s+raise|to\s+go))(?=$|[^A-Za-z0-9])"
)
_BALANCE_BEFORE = re.compile(
    r"(?i)(?P<head>\b(?:amount\s+left|remaining\s+amount|remaining|balance|still\s+need|need\s+to\s+raise)"
    r"\s*(?:is|of|:|=)?\s*(?:Rs\.?\s*)?)"
    + r"(?P<sum>\d[\d,]*(?:\.\d+)?)(?:\s*(?P<scale>k|thousand|hazar|hazaar|lakh|lac))?(?![A-Za-z0-9])"
)
_BALANCE_ONLY = re.compile(
    r"(?i)(?P<head>\bonly\s+Rs\.?\s*)(?P<sum>\d[\d,]*(?:\.\d+)?)(?:\s*(?P<scale>k|thousand|hazar|hazaar|lakh|lac))?(?![A-Za-z0-9])"
)


def remaining_amount(text):
    """Read an explicitly labelled remaining balance, never a giving option."""
    for pattern in (_BALANCE_AFTER, _BALANCE_BEFORE, _BALANCE_ONLY):
        match = pattern.search(str(text or ""))
        if not match:
            continue
        amount = float(match["sum"].replace(",", ""))
        unit = (match["scale"] or "").lower()
        multiplier = 1000 if unit in ("k", "thousand", "hazar", "hazaar") else 100000 if unit in ("lakh", "lac") else 1
        value = amount * multiplier
        if value.is_integer() and 0 <= value <= 10000000:
            return int(value)
    return None


def update_amount(text, old, left):
    """Keep saved balances and donor math current without changing historical expenses."""
    left = max(0, int(left))
    text = str(text or "")
    # A message can be older than the last balance change; use its own labelled
    # balance rather than assuming its previous amount equals 'old'.
    def change_balance(match):
        number = float(match["sum"].replace(",", ""))
        scale = (match["scale"] or "").lower()
        if scale in ("k", "thousand", "hazar", "hazaar"):
            number *= 1000
        elif scale in ("lakh", "lac"):
            number *= 100000
        if number < 1000 and not scale and not re.search(r"(?i)rs\.?", match[0]):
            return match[0]  # "3 left" is a count, not a donation balance
        start = match.start("sum") - match.start()
        end = match.end("scale") - match.start() if match["scale"] else match.end("sum") - match.start()
        return match[0][:start] + f"{left:,}" + match[0][end:]

    for pattern in (_BALANCE_AFTER, _BALANCE_BEFORE, _BALANCE_ONLY):
        text = pattern.sub(change_balance, text)
    # Also support a standalone WhatsApp-styled balance: "*_Rs. 25,000_*".
    text = re.sub(
        r"(?im)^(?P<head>[ \t]*[*_]*[ \t]*Rs\.?[ \t]*)(?P<number>\d[\d,]*)(?P<tail>[ \t]*[*_]*[ \t]*)$",
        lambda m: m["head"] + f"{left:,}" + m["tail"],
        text,
    )

    def option(m):
        return (
            str(math.ceil(left / int(m["unit"].replace(",", "").replace(" ", ""))))
            + m["body"]
            + m["unit"]
        )

    text = re.sub(
        r"(?i)(?<!\d)\d+(?P<body>\s+(?:kind\s+)?people\s+(?:(?:donating|giving|contributing|contributing at|at|of|or)\s+)?(?:Rs\.?\s*)?)(?P<unit>2[ ,]?000|1[ ,]?000)",
        option,
        text,
    )
    text = re.sub(
        r"(?i)(?<!\d)\d+(?P<body>\s*[×x]\s*(?:Rs\.?\s*)?)(?P<unit>2[ ,]?000|1[ ,]?000)",
        option,
        text,
    )

    def reverse(m):
        return m[1] + str(math.ceil(left / int(m[2].replace(",", "").replace(" ", "")))) + m[3]

    return re.sub(r"(?i)((?:Rs\.?\s*)?(2[ ,]?000|1[ ,]?000)\s+by\s+)\d+(\s+people)", reverse, text)


def requirements(prompt):
    t = str(prompt)
    out = {}
    groups = manual_commands.groups(t)
    # Common writing words are not recipient choices: "main point", "all words",
    # and "free of errors" must never switch the task to a group/broadcast.
    n = manual_commands.norm(t)
    if groups == ["main"] and not re.search(
        r"\bgivelife\b|\bgive life\b|\bmain group\b|\b(?:for|to|in|on)\s+(?:the\s+)?main\b", n
    ):
        groups = []
    if groups == ["all"] and not re.search(r"\ball\s+(?:(?:six|6)\s+)?groups\b", n):
        groups = []
    if groups == ["free"] and not re.search(r"\bfreelance\b", n):
        groups = []
    if len(groups) == 1 and groups[0] != "test":
        out["target"] = groups[0]
    if re.search(
        r"(?i)\b(?:without|no|not)\s+(?:the\s+)?(?:poster|picture|image)\b|\b(?:text only|only text)\b",
        t,
    ):
        out["poster"] = False
    elif re.search(
        r"(?i)\b(?:with|attach|include|add)\s+(?:the\s+)?(?:poster|picture|image)\b|\bposter\s*\+",
        t,
    ):
        out["poster"] = True
    # Only a total length instruction, not "rewrite the first 2 lines".
    if re.search(r"(?i)\b(?:only|total|entire|whole|short|shorter)\b", t) and not re.search(
        r"(?i)\bfirst\s+\d+\s+lines?", t
    ):
        m = re.search(r"(?i)\b(\d+|one|two|three|four|five)\s+lines?\b", t)
        if m:
            n = (
                int(m[1])
                if m[1].isdigit()
                else ["one", "two", "three", "four", "five"].index(m[1].lower()) + 1
            )
            if not 1 <= n <= 30:
                raise ValueError("Choose a total line limit from 1 to 30.")
            out["max_lines"] = n
    return out


class DraftWorkflow:
    def __init__(self, path, store):
        self.path = path
        self.store = store
        self.lock = threading.RLock()
        self.data = (
            mapping(store.get("draft_workflow", {}))
            if store
            else mapping(path.read_text(encoding="utf-8"))
            if path.exists()
            else {}
        )

    def persist(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        if self.store:
            self.store.put("draft_workflow", self.data)

    def begin(self, prompt, kind, current):
        with self.lock:
            old = self.data
            keep = old.get("kind") == kind and (
                old.get("hash") == digest(current) or old.get("state") == "editing"
            )
            self.data = {
                **(old if keep else {"id": uuid.uuid4().hex, "poster": True}),
                **requirements(prompt),
                "kind": kind,
                "state": "editing",
                "instruction": str(prompt)[:1200],
                "actions": [],
                "updated": time.time(),
            }
            self.persist()

    def validate(self, text):
        n = self.data.get("max_lines")
        if n and len(str(text).strip().splitlines()) > n:
            raise ValueError(
                f"The owner requested at most {n} total lines, including blank lines. Save a shorter complete message."
            )

    def commit(self, kind, text):
        with self.lock:
            self.validate(text)
            self.data.update(
                kind=kind, hash=digest(text), state="ready", actions=[], updated=time.time()
            )
            self.persist()

    def revise(self, text):
        """A direct editor change is a new owner revision, not an AI-generated edit."""
        with self.lock:
            if (
                self.data.get("max_lines")
                and len(text.strip().splitlines()) > self.data["max_lines"]
            ):
                self.data.pop("max_lines")
            self.data.update(hash=digest(text), state="ready", actions=[], updated=time.time())
            self.persist()

    def current(self, kind, text):
        with self.lock:
            return (
                self.data.get("kind") == kind
                and self.data.get("state") == "ready"
                and self.data.get("hash") == digest(text)
            )

    def options(self, kind, text):
        return dict(self.data) if self.current(kind, text) else None

    def select(self, target, text):
        with self.lock:
            if self.current("group", text) and target != "test":
                self.data.update(target=target, actions=[])
                self.persist()

    def apply_options(self, prompt, text):
        with self.lock:
            if self.current("group", text):
                change = requirements(prompt)
                if change:
                    self.data.update(change, actions=[])
                    self.persist()

    def suggest(self, text):
        with self.lock:
            if not self.current("group", text):
                return []
            if not self.data.get("actions"):
                mode = "Poster + caption" if self.data.get("poster", True) else "Text only"
                target = self.data.get("target")
                choices = [("preview", "View message", None), ("send", "Send test", "test")]
                if target:
                    choices.append(
                        (
                            "send",
                            "Send to "
                            + (
                                {
                                    "main": "GiveLife main",
                                    "free": "5 freelance groups",
                                    "all": "all 6 groups",
                                }.get(target, target)
                            ),
                            target,
                        )
                    )
                else:
                    choices.append(("choose", "Choose group", None))
                self.data["actions"] = [
                    {
                        "id": uuid.uuid4().hex,
                        "type": typ,
                        "label": label,
                        "target": dest,
                        "detail": mode,
                        "hash": self.data["hash"],
                        "poster": self.data.get("poster", True),
                    }
                    for typ, label, dest in choices
                ]
                self.persist()
            return [dict(a) for a in self.data["actions"]]

    def action(self, ident, text):
        with self.lock:
            a = next((a for a in self.data.get("actions", []) if a["id"] == ident), None)
            if not a or not self.current("group", text) or a["hash"] != digest(text):
                raise ValueError(
                    "The draft changed. Use the latest chat actions; nothing was sent."
                )
            return dict(a)

    def started(self, ident, job):
        with self.lock:
            for a in self.data.get("actions", []):
                if a["id"] == ident:
                    a.update(job_id=job, disabled=True)
            self.persist()
