"""Reads one incoming reply and says what it means. Code first; AI only for what code cannot decide.

Labels: donated, shared, both, not_done, later, opt_out, question, ack, other.
"donated" is only a claim: a payment is never treated as verified and never changes the amount left.
"""

import datetime, json, re

SHARE = re.compile(
    r"(?i)\b(shared?|sharing|share kar (?:diya|di|dia)|forward(?:ed)?|posted|reposted|"
    r"(?:sent|send|bhej(?:a|i|\s*di(?:y|)a)?)\s+(?:it\s+)?(?:to|in|on|mein|me)\s+(?:my\s+|the\s+|\d+\s+|all\s+)?"
    r"(?:class|friends?|groups?|family|status|contacts?|people|batch|section|dept))"
)
DONATE = re.compile(
    r"(?i)\b(donated|donate kar|paid|transferred|transfer kar|sent (?:the )?(?:money|amount|payment|rs\.?|pkr)|"
    r"sent how much|how much i could|bhej diya|bhej di|send kar diya|kar diya|easypaisa|jazz ?cash|"
    r"rs\.?\s*\d|\d[\d,]{2,}\s*(?:rs|pkr|rupees)?)"
)
DONE = re.compile(r"(?i)^\W*(done|ho gaya|ho gya|kar diya|yes done|done brother|done bhai)\W*$")
NEGATE = re.compile(
    r"(?i)\b(not (?:yet )?(?:done|shared|sent|paid)|abhi nahi|nahi kiya|na(?:hi)? kar|haven'?t|didn'?t|couldn'?t|can'?t)\b"
)
LATER = re.compile(
    r"(?i)\b(later|kal|tomorrow|baad (?:mein|me)|thori der|not now|next week|salary|insha ?allah|"
    r"will (?:try|do|send|donate|share))\b"
)
OPT_OUT = re.compile(
    r"(?i)\b(stop|unsubscribe|don'?t (?:message|msg|dm|send)|not interested|block|spam|mat bhejo|band karo|remove me)\b"
)
ACK = re.compile(
    r"(?i)^\W*(ok+(?:ies|ay|y)?|k+|sure|theek|thik|ji|jee|g|alright|👍|🤲|❤️?|jazak ?allah\w*)\W*$"
)
# A payment CLAIM is a past-tense statement. Bare words like "easypaisa" or "Rs 500" are not claims.
CLAIM = re.compile(
    r"(?i)\b(donated|paid|transferred|transfer kar (?:diya|di)|sent (?:the )?(?:money|amount|payment|rs\.?|pkr)|"
    r"bhej diya|bhej di|bheje|bheji|send kar diya|kar diya|donate kar diya)\b"
)
FUTURE = re.compile(
    r"(?i)\b(will|i'?ll|shall|going to|dunga|dungi|karunga|karungi|bhejunga|bhejungi|"
    r"tomorrow|tmrw|baad (?:mein|me)|insha ?allah)\b"
)
ASK_INFO = re.compile(
    r"(?i)\b(send|share|give|bhejo|bhej do|batao|bata do|dedo|de do|what|which|kya|kaun|where)\b.*"
    r"\b(number|account|details|iban|link|address)\b|\b(number|account|details|iban|link)\b.*\b(bhejo|bhej do|batao|bata do|dedo|de do)\b"
)
NO = re.compile(r"(?i)^\W*(no|nope|nahi|nahin|na)\W*$")
SHARE_ASK = re.compile(r"(?i)\bshare\b|forward|class group|friends'? groups")
LABELS = ("donated", "shared", "both", "not_done", "later", "opt_out", "question", "ack", "other")


def classify(text, media_type="", last_outgoing=""):
    """(label, reason). Deterministic. Unclear text returns 'other' for the AI step or the owner."""
    t = str(text or "").strip()
    if media_type == "image" and not t:
        return "donated", "picture (not verified)"
    if OPT_OUT.search(t) and not DONATE.search(t):
        return "opt_out", "opt-out words"
    if NEGATE.search(t):
        return "not_done", "negation"
    if NO.match(t):
        return "not_done", "plain no"
    claim, future = bool(CLAIM.search(t)), bool(FUTURE.search(t))
    if (
        future
    ):  # "I will pay tomorrow" is a promise, not a payment; a promise AND a claim is unclear
        return ("other", "promise and claim together") if claim else ("later", "future words")
    asking = t.endswith("?") or re.match(
        r"(?i)^(is|are|what|which|where|how|who|when|kya|kab|kahan|kaun)\b", t
    )
    if (asking or ASK_INFO.search(t)) and not claim:
        return "question", "question or request for details"
    if asking and (claim or SHARE.search(t)):
        return "other", "claim inside a question"
    shared, donated = bool(SHARE.search(t)), bool(DONATE.search(t))
    if shared and donated:
        return "both", "share words and payment words"
    if shared:
        return "shared", "share words"
    if donated or media_type == "image":
        return "donated", "payment words" if donated else "picture (not verified)"
    if DONE.match(t):
        if SHARE_ASK.search(last_outgoing or ""):
            return "shared", '"done" after a share request'
        return "donated", '"done" after a donate request (not verified)'
    if t.endswith("?") or re.match(
        r"(?i)^(is|are|what|which|where|how|who|when|kya|kab|kahan|kaun)\b", t
    ):
        return "question", "question"
    if LATER.search(t):
        return "later", "later words"
    if ACK.match(t):
        return "ack", "acknowledgement"
    return "other", "unclear"


def ai_classify(chat, text, history):
    """AI step for unclear replies only. chat(prompt) returns raw model text.
    Returns (label, reason) or ('other', ...) when the answer is not valid or the evidence is not in the text."""
    prompt = (
        "Classify the LAST reply in a charity WhatsApp chat. Our side asks people to donate or to share a case.\n"
        f"Labels: {', '.join(LABELS)}. 'donated' = they say they paid. 'shared' = they say they shared/forwarded.\n"
        'Answer ONLY JSON: {"intent": label, "evidence": "exact words copied from the reply", "confident": true or false}\n'
        "Say confident=false when the reply could mean something else. A payment is only a claim: never say it is verified.\n\n"
        "Chat (oldest first):\n"
        + "\n".join(f"{who}: {msg[:300]}" for who, msg in history[-6:])
        + f"\n\nLAST reply: {text[:500]}"
    )
    try:
        raw = re.sub(r"^```(?:json)?|```$", "", str(chat(prompt)).strip()).strip()
        data = json.loads(raw)
        label, evidence = data.get("intent"), str(data.get("evidence", "")).strip()
        if data.get("confident") is False:
            return "other", "AI not confident"
    except Exception:
        return "other", "AI answer not valid"
    if label not in LABELS or not evidence or evidence.lower() not in str(text).lower():
        return "other", "AI evidence not found in the reply"
    return label, "AI: " + evidence[:80]


def stamp(m):
    try:
        return datetime.datetime.fromisoformat(
            str(m.get("timestamp", "")).replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return 0.0


def history_from(msgs, upto_id, limit=6):
    """The chat up to and including message `upto_id`, oldest first, as ('us'|'them', text) for the AI step."""
    rows = sorted((m for m in msgs or [] if isinstance(m, dict)), key=stamp)
    ids = [m.get("id") for m in rows]
    if upto_id in ids:
        rows = rows[: ids.index(upto_id) + 1]
    return [
        ("us" if m.get("is_from_me") else "them", str(m.get("content") or m.get("caption") or ""))
        for m in rows[-limit:]
    ]
