"""Factual caption updates shared by drafts, version banks and dispatch."""

import re, uuid
import draft_workflow

TIME = re.compile(
    r"(?i)\bjanaz[ae]h\s+(?:time\s+)?(?:(?:is|at|will be|now is|is now)\s+)?(?:(today|tomorrow)\s+)?(\d{1,2})(?::([0-5]\d))?\s*(a\.?m\.?|p\.?m\.?)?\s*(today|tomorrow)?\b"
)
# Bound by "not a letter/digit" rather than \b: WhatsApp italics put "_" (a regex
# word character) on both sides, so \b missed "*_Rs. 25,000 LEFT_*" entirely.
TOTAL = re.compile(
    r"(?i)(?<![A-Za-z0-9])Rs\.?\s*([\d,]+)\s*(?:urgently\s+)?(?:left|needed|required|remaining)(?![A-Za-z0-9])"
)
JANAZAH = re.compile(
    r"(?i)\b(?:(?:his|the)\s+)?janaz[ae]h(?:\s+time)?\s+(?:is|has|will|at)[^\n.!?*_]*(?:[.!?]|(?=[*_\n]|$))"
)


def parse_time(text):
    if "?" in text or re.search(r"(?i)\b(?:if|suppose|example|don'?t)\b", text):
        return None
    if not re.search(r"(?i)\bjanaz[ae]h\b", text) or re.search(
        r"(?i)\b(?:what|when|show|check|is it|not|dont|do not|cancel)\b", text
    ):
        return None
    m = TIME.search(text)
    if not m:
        return None
    day1, hour, minute, period, day2 = m.groups()
    hour = int(hour)
    if (day1 and day2 and day1.lower() != day2.lower()) or hour > 23:
        raise ValueError("Please give one clear Janazah time and day.")
    if period and not 1 <= hour <= 12:
        raise ValueError("Use a time from 1 to 12 with AM or PM.")
    if not period and hour <= 12:
        raise ValueError("Is the Janazah time AM or PM?")
    return (
        f"{hour}:{minute or '00'}"
        + (" " + period.replace(".", "").upper() if period else "")
        + (" " + (day1 or day2).lower() if day1 or day2 else "")
    )


def update_time(text, value):
    sentence = "The Janazah is at " + value + "."
    if JANAZAH.search(text):
        return JANAZAH.sub(lambda m: sentence, text)
    return text + "\n\n" + sentence if len(text) > 120 else text


def scope(app):
    return app.active_case_name().casefold()


def facts(app):
    return (app.STORE.get("case_caption_facts", {}) if app.STORE else {}).get(scope(app), {})


def current(app, text):
    if not isinstance(text, str):
        return text
    old_balance = draft_workflow.remaining_amount(text)
    match = TOTAL.search(text)
    if old_balance is None and match:
        old_balance = int(match[1].replace(",", ""))
    if old_balance is not None and old_balance != app.read_left():
        text = draft_workflow.update_amount(text, old_balance, app.read_left())
    value = facts(app).get("janazah_time")
    if value and ("janaz" in text.lower() or old_balance is not None):
        text = update_time(text, value)
    return text


def transform_banks(app, fn):
    if not app.STORE:
        return
    # Updating the revision invalidates any generation based on superseded facts.
    data = app.STORE.get("focus_wording", {})
    for row in data.values():
        if not isinstance(row, dict) or "source" not in row:
            continue
        row["source"] = fn(row["source"])
        for key in ("items", "manual", "avoid"):
            row[key] = list(dict.fromkeys(fn(t) for t in row.get(key, []) if isinstance(t, str)))
        row.update(
            revision=uuid.uuid4().hex,
            state="Ready"
            if len(row["items"]) >= 10
            else "Partial"
            if row["items"]
            else "Needs retry",
            error="",
            generator=4,
        )
    app.STORE.put("focus_wording", data)
    # MessageBank has a separate cache. Its next read loads this updated record.
    bank = app.STORE.get("donor_messages")
    if isinstance(bank, dict):
        # Previous approved versions may still be used while regeneration runs.
        # Update both current and fallback captions before the next donor send.
        for field in ("items", "previous_items"):
            for entry in bank.get(field, []):
                if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                    entry["text"] = fn(entry["text"])
        if isinstance(bank.get("origin"), str):
            bank["origin"] = fn(bank["origin"])
        generation = bank.get("generation")
        if isinstance(generation, dict) and generation.get("state") == "Generating":
            generation.update(state="Superseded", error="The balance changed. Regenerate with the new amount.")
        bank["left"] = app.read_left()
        app.STORE.put("donor_messages", bank)
        if getattr(app, "DONORS", None):
            app.DONORS.messages.cache = None


def set_time(app, value):
    with app.LOCK:
        if hasattr(app, "OWNER_REVISION"):
            app.OWNER_REVISION += 1
            app.OWNER_GUARD.revision = app.OWNER_REVISION
        data = app.STORE.get("case_caption_facts", {}) if app.STORE else {}
        data.setdefault(scope(app), {})["janazah_time"] = value
        if app.STORE:
            app.STORE.put("case_caption_facts", data)
        for kind in ("group", "dm"):
            app.save_draft(kind, update_time(app.get_message(kind)["text"], value))
        transform_banks(app, lambda text: update_time(text, value))
    return "Janazah time set to " + value + ". Group, DM and saved versions updated. Nothing sent."
