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


def update_amount(text, old, left):
    text = re.sub(
        r"(?<!\d)(?:" + re.escape(f"{old:,}") + "|" + str(old) + r")(?!\d)", f"{left:,}", text
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
