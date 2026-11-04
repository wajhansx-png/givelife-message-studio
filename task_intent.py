"""Deterministic one-prompt task framing. Context informs meaning, NEVER permission.

No model/API call, no side effects. The latest authenticated owner instruction is
the sole authority for writes and sends. Old replies and memories are evidence only.
"""

import re
from state_shapes import history as valid_history

STOP = set(
    "a an and are as at be by can could do for from have he her his how i if in into is it me my now of on or our please should so that the their then there these they this those to u us was were what when where who will with would you your".split()
)
SEND = re.compile(r"\b(?:send|resend|text|dm|message|post|share|bhejo|bhej)\b", re.I)
NEG_SEND = re.compile(
    r"(?i)\b(?:don't|dont|do not|never|without|no more|not now)\s+(?:\w+\s+){0,3}(?:send|sending|post|posting|dm|dming|message|share)\b"
)
COMMAND = re.compile(
    r"(?i)\b(?:send|post|share|change|edit|rewrite|correct|update|add|remove|delete|set|start|stop|pause|hold|resume|open|create|record|schedule|assign|cancel)\b"
)
REF = re.compile(
    r"(?i)\b(?:it|that|those|this|them|same|again|continue|previous|earlier|above|last|first|second|third|do it)\b|^\s*(?:[1-9]|yes|no|done|ok)\s*[.!]?\s*$"
)
DIVIDER = re.compile(
    r"(?i)\s*(?:;|\n|(?:\b(?:and then|and|then|also|plus)\s+(?=(?:please\s+)?(?:send|post|start|stop|pause|hold|change|edit|rewrite|update|set|add|delete|create|schedule|cancel)\b)))\s*"
)
CASE_WORDS = re.compile(
    r"(?i)\b(?:case|patient|child|medical|caption|appeal|amount|remaining|balance)\b"
)
STEP_PATTERNS = (
    ("hold", r"\b(?:hold|stop everything|pause everything|stop all|stop sending)\b"),
    ("case", r"\b(?:new case|create a case|start a case|switch case|change case|open case)\b"),
    ("balance", r"\b(?:amount left|remaining|balance|money came|received|donated|rs\.?\s*\d+)\b"),
    (
        "edit",
        r"\b(?:rewrite|reword|edit|caption|wording|shorten|shorter|longer|stronger|simpler|bolder|bold|italic|hook|fix|correct|replace|reformat|draft)\b",
    ),
    (
        "schedule",
        r"\b(?:every\s+\d+\s*(?:min|hour)|schedule|tomorrow|at\s+\d{1,2}(?:[:.]\d\d)?\s*(?:am|pm)|daily)\b",
    ),
    ("send", r"\b(?:send|resend|post|share|dm|text)\b"),
    ("team", r"\b(?:team|teammate|akhtar|assign tasks?)\b"),
    ("volunteer", r"\b(?:volunteers?|ambassadors?)\b"),
    ("status", r"\b(?:status|report|check|show|list|progress)\b"),
)


def words(value):
    return {w for w in re.findall(r"[\w]+", str(value).casefold()) if len(w) > 2 and w not in STOP}


def referential(text):
    return len(str(text).strip()) <= 180 and bool(REF.search(str(text)))


def retrieval_query(text, hist, task=None):
    """Give short follow-ups topic words for retrieval, never action permission."""
    value = str(text).strip()
    if not referential(value) and not re.fullmatch(
        r"(?i)(?:show|shorter|more short|only \d+ lines)[.!]*", value
    ):
        return value
    task = task if isinstance(task, dict) else {}
    hints = []
    if task.get("state") in ("editing", "ready") and isinstance(task.get("instruction"), str):
        hints.append(task["instruction"][:500])
    for turn in reversed(valid_history(hist)):
        if turn["who"] == "you" and turn["text"].strip() != value:
            hints.append(turn["text"][:500])
            break
    return value + "\nContext for retrieval only: " + " ".join(hints) if hints else value


def steps(text):
    """Small, explainable plan for the current request. NOT an execution grant."""
    cleaned = str(text).strip()
    if not cleaned:
        return []
    clauses = [x.strip() for x in DIVIDER.split(cleaned) if x.strip()]
    out = []
    for clause in clauses[:12]:
        # A question or negative is not a command to send, even if it mentions a send.
        question = bool(
            re.match(
                r"(?i)^\s*(?:what|why|how|when|where|did|have|has|can i|could i|should i|tell me|show me|suggest)\b",
                clause,
            )
        )
        negative = bool(NEG_SEND.search(clause))
        kinds = [name for name, pattern in STEP_PATTERNS if re.search(pattern, clause, re.I)]
        if "send" in kinds and (negative or question):
            kinds.remove("send")
        if not kinds and not COMMAND.search(clause):
            continue
        # Scope clauses can contain more than one operation, e.g. "post every 15 min".
        explicit = [x for x in kinds if x not in ("team", "volunteer", "status")]
        if not explicit:
            explicit = kinds[:1]
        # "caption" is incidental to "send the caption", not a requested draft edit.
        if (
            "send" in explicit
            and "edit" in explicit
            and not re.search(
                r"(?i)\b(?:edit|rewrite|correct|shorten|shorter|longer|stronger|simpler|bold|fix|update|change|replace)\b", clause
            )
        ):
            explicit.remove("edit")
        for kind in explicit:
            item = {"kind": kind, "instruction": clause[:240]}
            if item not in out:
                out.append(item)
    return out[:12]


def reference_history(text, hist, active_case=""):
    """Pick current relevant OWNER instructions, not arbitrary assistant guesses."""
    if not referential(text):
        return []
    turns = valid_history(hist)
    owner = [
        (i, h)
        for i, h in enumerate(turns)
        if h["who"] == "you"
        and len(h["text"].strip()) >= 12
        and h["text"].strip().casefold() != str(text).strip().casefold()
    ]
    if not owner:
        return []
    query = words(text)
    case = words(active_case) if active_case and active_case.casefold() != "current case" else set()
    scored = []
    for i, h in owner:
        previous = words(h["text"])
        overlap = len(query & previous)
        recency = 1 / (1 + (len(turns) - 1 - i) / 8)
        case_match = len(case & previous)
        # Avoid an old, unrelated patient's facts when a different active case exists.
        other_case = bool(
            CASE_WORDS.search(h["text"])
            and re.search(r"(?i)\b(?:yousuf|affan)\b", h["text"])
            and case
            and not case_match
        )
        score = 2.5 * overlap + recency + 2 * case_match - (7 if other_case else 0)
        scored.append((score, i, h))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    if not scored:
        return []
    # Avoid smuggling an unrelated older case into "fix that"; only include
    # context whose topic is close to the most relevant owner instruction.
    threshold = max(0, scored[0][0] - 1.25)
    selected = sorted([x for x in scored if x[0] >= threshold][:2], key=lambda t: t[1])
    return [{"who": "you", "text": h["text"][:1400]} for _, _, h in selected]


def compound(text):
    """True for two independent imperative clauses, not a single post/pace rule."""
    value = str(text or "").strip()
    if not value or value[0] in ('"', "'", ">"):
        return False
    clauses = [c.strip() for c in DIVIDER.split(value) if c.strip()]
    if len(clauses) < 2:
        return False
    return (
        sum(
            bool(
                re.search(
                    r"(?i)^\s*(?:please\s+)?(?:send|post|set|update|edit|rewrite|change|start|stop|pause|hold|schedule|create|add|remove|delete|record|assign|open|cancel)\b",
                    c,
                )
            )
            for c in clauses
        )
        >= 2
    )


def send_clauses(text):
    """Independent explicit sends, used to prevent a one-prompt job stopping early."""
    parts = [c.strip() for c in DIVIDER.split(str(text or "")) if c.strip()]
    return [
        part
        for part in parts
        if re.match(r"(?i)^(?:please\s+)?(?:send|resend|text|post|share|dm)\b", part)
    ]


def quoted_sends(text):
    """Extract exact per-recipient texts; do not confuse one person's quote with another."""
    result = []
    for part in send_clauses(text):
        match = re.match(
            r'(?is)^(?:please\s+)?(?:send|resend|text|message)\s+["“]([^"”]+)["”]\s+(?:to|ko)\s+(.+)$',
            part,
        )
        if match:
            result.append({"text": match[1].strip(), "to": match[2].strip()})
    return result
