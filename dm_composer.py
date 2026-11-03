"""Preserve the owner's full DM; recipient labels are not personal names."""

import re

LABEL = re.compile(
    r"(?i)\b(jr|junior|sr|senior|accounts?|accts?|admin|team|group|member|donors?|business|company|shop|store|services?|official|office|unknown|unnamed|name|contact|number|test|user|brother|bhai|sister|friend|wife|wifey|boss|customer|client|support|sales|marketing|web|developer|designer|agency|digital|seo|upwork|fiverr|foundation|givelife)\b"
)
GREETING = re.compile(
    r"^(?P<mark>\*?_?)(?:(?:[A-Za-z][A-Za-z .\'-]{0,45})\s+)?(?:Brother|Bhai|Sister)\b(?P<close>[_*]?)(?:[,.:!]?)[ \t\r\n]*",
    re.I,
)


def first_name(value):
    value = str(value or "").strip()
    if (
        not value
        or LABEL.search(value)
        or re.search(r"\d|@|https?://|[_/\\]|acc+ount", value, re.I)
    ):
        return ""
    value = re.sub(r"[^A-Za-z\s\'-]", "", value).strip()
    parts = value.split()
    if not parts or len(parts) > 4 or any(len(p) < 2 for p in parts):
        return ""
    first = parts[0]
    if not re.fullmatch(r"[A-Za-z][A-Za-z'-]{1,19}", first) or not re.search(
        "[aeiouy]", first, re.I
    ):
        return ""
    return first.title()


def greeting(name, gender="Brother"):
    name = first_name(name)
    return (name + " " if name else "") + ("Sister" if name and gender == "Sister" else "Bhai")


SALUTATION = re.compile(
    r"(?i)^[\W_]*(?:hi|hello|hey|dear|salam|assalam\S*|as-?salam\S*|aoa)\b[^\n]{0,30}"
)


def already_greets(text, name):
    """True when the owner's own opening already salutes this person by name ("Hi Ali, ...")."""
    first = first_name(name)
    if not first:
        return False
    match = SALUTATION.match(text)
    return bool(match and re.search(r"\b" + re.escape(first) + r"\b", match.group(0), re.I))


PAYMENT_OLD = re.compile(
    r"(?i)\beasy\s?paisa\s*(?:/|&|and|or|,)\s*jazz\s?cash(?:\s+only)?\b"
    r"|\bjazz\s?cash\s*(?:/|&|and|or|,)\s*easy\s?paisa\b|\bjazz\s?cash\b"
)


def payment_fix(text):
    """Every outgoing message names EASYPAISA ONLY: JazzCash is never offered."""
    return PAYMENT_OLD.sub("EASYPAISA ONLY", str(text))


def personalize(text, name="", gender="Brother"):
    text = payment_fix(str(text).replace("\r\n", "\n")).strip()
    if gender == "Sister" and first_name(name):
        # A message written for "Brother" reads "Sister" all the way through, not only in the greeting.
        text = re.sub(r"\bBrother\b", "Sister", text)
        text = re.sub(r"\bbrother\b", "sister", text)
    if already_greets(text, name):
        return text
    match = GREETING.match(text)
    prefix = greeting(name, gender) + ", "
    if match:
        # Keep formatting that wraps the opening paragraph, and all following text.
        prefix = match["mark"] + greeting(name, gender) + match["close"] + ", "
        return prefix + text[match.end() :]
    first_line = text.split(chr(10), 1)[0]
    if text[:1] in "*_" and len(first_line) > 2 and first_line.endswith(text[0]):
        # A bold/italic opening line keeps the name inside it: "*Hamza Bhai, Only 22 hours left*".
        return text[0] + greeting(name, gender) + ", " + text[1:]
    return prefix + text


UNVERIFIED_MEDICAL = re.compile(
    r"(?i)(?:paralys\w*|numbness|numb)\b[^\n.]{0,100}\b(?:fingers?|spread\w*|mov\w*)\b"
    r"|\b(?:fingers?|spread\w*|mov\w*)\b[^\n.]{0,100}\b(?:paralys\w*|numbness)\b"
)


def unverified_medical_claim(text):
    """Block disproven template claims; does not guess any clinical fact."""
    return bool(UNVERIFIED_MEDICAL.search(str(text or "")))


def complete(text):
    """A fundraising caption cannot consist of a salutation or a collapsed summary.

    The campaign is Yousuf-specific today, but the same guard is used for a
    message the owner pastes in. Check the shape and the payment/ask facts
    instead of hard-coding one name so a complete owner-supplied message can
    be reworded without being mistaken for a one-line reply.
    """
    text = str(text)
    body = text.strip()
    if unverified_medical_claim(body):
        return False
    if len(body) < 180 or len(re.split(r"\n\s*\n", body)) < 4:
        return False
    if not re.search(r"(?:\b\d{10,15}\b|Easypaisa|JazzCash|account)", text, re.I):
        return False
    return bool(
        re.search(
            r"\b(?:left|needed|need|remaining|remain|remains|required|stands|treatment|care|donat(?:e|ion|ions)?|help|goal|support)\b",
            text,
            re.I,
        )
    )
