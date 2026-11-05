"""One case, one plan: verified facts -> Normal and Slow messages (PDF prompts) -> one state.

States: draft (facts saved, waiting for approval) -> ready -> normal <-> slow -> done.
Any state -> stopped (owner or a failed check). Nothing here sends anything.
"""

import re, time
import team_rules as T
import message_rules

STATES = ("draft", "ready", "normal", "slow", "done", "stopped")
ACTIVE = ("ready", "normal", "slow")
_DEATH = re.compile(
    r"(?i)passed away|\bdied\b|\bdeath\b|is no more|janaz[ae]h|intiqal|wafat|انتقال|وفات"
)


def _clean(value, limit):
    value = re.sub(r"\s+", " ", str(value or "")).strip().rstrip(".")
    if len(value) > limit or any(c in value for c in "*_#\n"):
        raise ValueError(f"Keep each fact short and plain (max {limit} characters, no * _ #).")
    return value


def clean_facts(raw):
    """Verified case facts typed by the owner. Raises ValueError with a plain reason."""
    raw = raw if isinstance(raw, dict) else {}
    name = _clean(raw.get("name"), 40)
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]{0,39}", name):
        raise ValueError("Enter the patient's name in English letters.")
    try:
        age = int(str(raw.get("age", "")).strip())
    except ValueError:
        raise ValueError("Enter the age as a number.") from None
    if not 0 <= age <= 120:
        raise ValueError("Enter a real age (0–120).")
    gender = str(raw.get("gender", "")).strip().lower()
    if gender not in ("boy", "girl"):
        raise ValueError("Choose boy or girl.")
    facts = {
        "name": name,
        "age": age,
        "gender": gender,
        "what_happened": _clean(raw.get("what_happened"), 80),
        "money_for": _clean(raw.get("money_for"), 80),
        "deadline": _clean(raw.get("deadline"), 60) or None,
        "hadith": int(raw.get("hadith") or 1),
    }
    if not facts["what_happened"] or not facts["money_for"]:
        raise ValueError("Enter what happened and what the money is for.")
    if facts["hadith"] not in (1, 2, 3):
        raise ValueError("Choose hadith 1, 2 or 3 from the approved list.")
    return facts


def _details(f):
    pronoun = "His" if f["gender"] == "boy" else "Her"
    text = f"{f['name']}, {f['age']} years old, {f['what_happened']}. {pronoun} family needs help with {f['money_for']}."
    if f.get("deadline"):
        text += " " + f["deadline"][0].upper() + f["deadline"][1:] + "."
    return "_" + text + "_"


def build(facts, left, exact=True):
    """{'normal': text, 'slow': text} from the PDF patterns. Raises ValueError when the PDF cannot be followed."""
    if not _DEATH.search(facts["what_happened"] + " " + facts["money_for"]):
        raise ValueError(
            "The PDF hooks are for a child who passed away (Janazah). Write this case's message by hand."
        )
    if facts["age"] >= 18:
        raise ValueError(
            "The PDF hooks are written for a child. Write this case's message by hand."
        )
    counts = T.gift_counts(left, exact)
    if not counts:
        raise ValueError(
            f"Rs. {left:,} cannot be split exactly into Rs. 2,000 gifts (PDF rule). Set an amount that can."
        )
    n, m = counts
    boy = facts["gender"] == "boy"
    name, age = facts["name"], facts["age"]
    hook = f"{age}-year-old {name} has passed away. {'His' if boy else 'Her'} parents cannot pay for {'his' if boy else 'her'} Janazah."
    urdu = (
        f"{age} سال کا {name} دنیا سے چلا گیا، مگر اس کے والدین کے پاس تدفین کے پیسے بھی نہیں۔"
        if boy
        else f"{age} سال کی {name} دنیا سے چلی گئی، مگر اس کے والدین کے پاس تدفین کے پیسے بھی نہیں۔"
    )
    tail = [T.LINE3.format(n=n, m=m), T.LINE4, "\n".join(T.FOOTER)]
    drafts = {
        "normal": "\n\n".join([f"*{hook}* 💔", _details(facts), *tail]),
        "slow": "\n\n".join(
            [f"*{urdu}* 💔", _details(facts), T.HADITH[facts["hadith"] - 1], *tail]
        ),
    }
    for kind, text in drafts.items():
        bad = message_rules.problems(text, left=left, facts=facts, exact=exact)
        if bad:
            raise ValueError(f"The {kind} message failed its check: " + " ".join(bad))
    return drafts


def new_case(raw, left, case_name):
    facts = clean_facts(raw)
    return {
        "facts": facts,
        "drafts": build(facts, left, exact=False),
        "state": "draft",
        "case": case_name,
        "built_left": left,
        "created": time.time(),
        "approved": None,
        "reason": "",
    }


def approve(case, left):
    if not case or case.get("state") != "draft":
        raise ValueError("There is no new case message waiting for approval.")
    case["drafts"] = build(case["facts"], left, exact=False)  # re-checked with the live amount
    case.update(state="ready", approved=time.time(), built_left=left, reason="")
    return case


def stop(case, reason):
    if case:
        case.update(state="stopped", reason=str(reason)[:200])
    return case


def resume(case):
    if not case or case.get("state") != "stopped":
        raise ValueError("The case plan is not stopped.")
    case.update(state="ready" if case.get("approved") else "draft", reason="")
    return case


def advance(case, left, minutes_since_money, case_name):
    """The state the case should be in now. Pure: no saving, no sending."""
    state = (case or {}).get("state")
    if state not in ACTIVE:
        return state
    if case.get("case") != case_name:
        return "stopped"
    if left <= 0:
        return "done"
    return "slow" if minutes_since_money >= T.SLOW_AFTER_MINUTES else "normal"


def message_for(case, mode, left):
    """The approved message for `mode`, with line 3 for the live amount."""
    return message_rules.refresh_amount(case["drafts"][mode], left)
