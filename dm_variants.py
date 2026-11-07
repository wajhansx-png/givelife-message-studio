"""Generate reworded versions of an owner-supplied WhatsApp DM.

The static canonical templates cover the built-in Yousuf DM. This module is
the general path: the owner pastes any complete message, the model rewrites
only the wording, and deterministic checks reject any version that changes the
line structure, emojis, bold/italic markers, numbers or payment details.
"""

import time
import difflib, json, re

import assistant
import dm_composer

VERSION = "dm-variants-2026-11-02-deep-rewrite"

# Meaning and formatting matter more than matching a character count.
# Allow sentence-level rewrites while keeping each message reasonably compact.
LENGTH_TOLERANCE = 0.28

SYSTEM = """You are the strongest direct-response fundraising copywriter in the world, writing
WhatsApp appeals for GiveLife Foundation. Your versions make a reader stop scrolling, feel the
need in their chest, and send money within a minute. You get that power from the TRUE facts in
the owner's message and from human psychology, never from invented facts.
Return only the JSON array the user asks for. Never add commentary, markdown fences, headings
or a delivery claim. English lines use very easy, punchy English; Urdu lines use simple,
moving Urdu in Urdu script. Rewrite the ENTIRE message, not just one hook.
Never invent medical details, deadlines, outcomes, names, numbers or promises."""


def clean_source(source):
    """Strip a leading/trailing owner instruction from a pasted message."""
    text = str(source or "").replace("\r\n", "\n").strip()
    lines = text.split("\n")
    instruction = re.compile(
        r"(?i)\b(?:generate|make|create|write|rewrite|give|show|prepare|produce)\b"
        r".{0,120}\b(?:versions?|variants?|wordings?|rewrites?)\b"
    )
    while lines and instruction.search(lines[0]) and len(lines[0]) < 300:
        lines.pop(0)
    while lines and instruction.search(lines[-1]) and len(lines[-1]) < 300:
        lines.pop()
    return "\n".join(lines).strip()


def length_range(source):
    n = len(str(source or "").strip())
    return int(n * (1 - LENGTH_TOLERANCE)), int(n * (1 + LENGTH_TOLERANCE)) + 1


def _shape(text):
    """The exact line/blank-line/emoji/marker skeleton of a message."""
    lines = str(text or "").replace("\r\n", "\n").strip("\n").split("\n")
    out = []
    for line in lines:
        if not line.strip():
            out.append(("", 0, 0, True))
            continue
        lead = re.match(r"^[^\w\s]*", line).group(0)
        out.append((lead, line.count("*"), line.count("_"), False))
    return out


def _numbers(text):
    return [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", str(text or ""))]


def _emojis(text):
    return re.findall(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", str(text or ""))


def _editable_lines(text):
    # Exclude exact payment/contact lines from variation scoring.
    return [
        line.strip()
        for line in str(text).split("\n")
        if line.strip()
        and not re.search(r"(?i)easypaisa|jazzcash|wajdan khan|reply \*done\*|03097458815", line)
    ]


def _similarity(a, b):
    def normalized(text):
        # Urdu (Arabic-script) words count too, so an Urdu hook is judged like an English one.
        return " ".join(
            re.findall(r"[a-z]+|[\u0600-\u06FF]+", "\n".join(_editable_lines(text)).lower())
        )

    return difflib.SequenceMatcher(None, normalized(a), normalized(b), autojunk=False).ratio()


def _meaningful_changes(source, candidate):
    a = _editable_lines(source)
    b = _editable_lines(candidate)
    if len(a) != len(b):
        return 0
    return sum(
        difflib.SequenceMatcher(None, x.lower(), y.lower(), autojunk=False).ratio() < 0.83
        for x, y in zip(a, b)
    )


_URDU = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN = re.compile(r"[A-Za-z]")


# Roman Urdu words that are not normal English words. Two or more in one line (and at least
# a quarter of its words) mean the line is Roman Urdu, even though it uses English letters.
_ROMAN = frozenset(
    """hai hain ka ki ke ko se ne nahi nahin nai aur yeh ye woh wo mein kar karo karna karein
    karen kare dein den diya diye hua hui huay gaya gayi gaye aaj abhi agar sirf log logon baqi
    raqam qarz wapas walidain waldain chahiye chahye taake takay jaise jaisay tarah paani pani aag
    sakti sakta sakte bhi kya hum aap unka uska unki uski unke uske liye apne apni apna bacha
    bachay bachy madad paise paisay paisy farmaya rasool dafan kafan tadfeen gunahon gunah bujha
    deta dete ab tak hoga hogi kyun kyunke lekin magar phir jab tab wala wali walay""".split()
)


def _lang(line):
    u, l = len(_URDU.findall(line)), len(_LATIN.findall(line))
    if u > l:
        return "urdu"
    if not l:
        return ""
    words = re.findall(r"[a-z]+", line.lower())
    hits = sum(w in _ROMAN for w in words)
    return "roman" if hits >= 2 and hits * 4 >= len(words) else "english"


def language_changed(source, text):
    """True when a version changes language: English must stay English (not Urdu script and
    not Roman Urdu), and Urdu or Roman Urdu lines must keep their language."""
    a, b = source.split("\n"), text.split("\n")
    la, lb = [_lang(x) for x in a], [_lang(y) for y in b]
    if "english" in la and not {"urdu", "roman"} & set(la) and {"urdu", "roman"} & set(lb):
        return True
    return len(a) == len(b) and any(x and y and x != y for x, y in zip(la, lb))


_SCRIPTURE = re.compile(r"ارشاد|فرمان|سور[ةۃہ]|حدیث|آیت|قرآن")
_PAYMENT = re.compile(r"(?i)easypaisa|jazzcash|account|03097458815|wajdan")


def is_fixed_line(line):
    """A line the app copies word for word and never lets the AI touch: a payment line, a Quran
    verse or hadith, its reference, or a quoted line written in Urdu script."""
    s = str(line or "").strip()
    if not s:
        return False
    if _PAYMENT.search(s):
        return True
    if _lang(s) != "urdu":
        return False
    first = s.lstrip("*_ ")[:1]
    return bool(_SCRIPTURE.search(s)) or (bool(first) and first in '"“«')


def repair(source, text):
    """Put back what the app is responsible for keeping, so one slip does not waste a whole version.
    When the line count matches, every fixed line (see is_fixed_line) and every line whose language
    flipped is replaced by the source's own line. The caller still runs every safety check after this,
    so a version that is not different enough, or has any other problem, is rejected as before."""
    a = str(source or "").replace("\r\n", "\n").strip().split("\n")
    b = str(text or "").replace("\r\n", "\n").strip().split("\n")
    if len(a) != len(b):
        return text
    out = []
    for x, y in zip(a, b):
        flipped = _lang(x) and _lang(y) and _lang(x) != _lang(y)
        out.append(x if x.strip() and (is_fixed_line(x) or flipped) else y)
    return "\n".join(out)


def validate(source, text, existing=()):
    """Return an error string, or '' when the version is safe to save."""
    if not isinstance(text, str):
        return "not text"
    text = text.replace("\r\n", "\n").strip()
    source = str(source or "").replace("\r\n", "\n").strip()
    if len(text) < 180:
        return "too short"
    if len(text) > 10000:
        return "too long"
    if text == source:
        return "same as the source"
    if language_changed(source, text):
        return "language changed; keep English lines English and Urdu lines Urdu"
    low, high = length_range(source)
    if not low <= len(text) <= high:
        return (
            f"length {len(text)} is outside {low}-{high} characters (the source has {len(source)})"
        )
    if text in existing:
        return "duplicate wording"
    if _shape(text) != _shape(source):
        return "line breaks, blank lines, emojis or bold/italic markers changed"
    if _emojis(text) != _emojis(source):
        return "an emoji changed or moved"
    if _numbers(source) != _numbers(text):
        return "a number, amount or phone number changed"
    source_lines = source.split("\n")
    text_lines = text.split("\n")
    for source_line, text_line in zip(source_lines, text_lines):
        if "Rs." in source_line and "Rs." not in text_line:
            return "the currency formatting changed"
    first_source = next((line for line in source_lines if line.strip()), "")
    first_text = next((line for line in text_lines if line.strip()), "")
    if first_source.startswith("Brother,") and not first_text.startswith("Brother,"):
        return "the greeting punctuation changed"
    for token in (
        "03097458815",
        "EASYPAISA ONLY",
        "Wajdan Khan",
        "Reply *Done* after donating.",
    ):
        if token in source and token not in text:
            return "payment details or the reply instruction changed"
    fixed_lines = [
        line.strip()
        for line in source.split("\n")
        if re.search(r"(?i)(?:Easypaisa|JazzCash|Wajdan Khan|03097458815|Reply \*Done\*)", line)
    ]
    if any(line not in text for line in fixed_lines):
        return "payment details or the reply instruction changed"
    if not dm_composer.complete(text):
        return "the message is not complete"
    # Reject superficial variations that merely swap the first sentence.
    # Requiring at least two rewritten editable lines makes the whole appeal change.
    editable = len(_editable_lines(source))
    minimum_lines = 2 if editable >= 3 else 1
    if _meaningful_changes(source, text) < minimum_lines or _similarity(source, text) > 0.81:
        return "not deeply rewritten; change the opening AND the body wording"
    if any(_similarity(text, other) > 0.87 for other in existing if isinstance(other, str)):
        return "too similar to an existing version; rewrite the story differently"
    return ""


def _json_list(raw):
    raw = str(raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw, strict=False)
    except (ValueError, TypeError):
        match = re.search(r"\[[\s\S]*\]", raw)
        if not match:
            raise ValueError("The model did not return a JSON list of messages.")
        data = json.loads(match.group(0), strict=False)
    if isinstance(data, dict):
        data = data.get("versions") or data.get("messages") or data.get("items")
    if isinstance(data, str):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("The model did not return a JSON list of messages.")
    out = []
    for item in data:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            out.append(item["text"])
    return out


# Set by the server: real past wordings that brought donations (learning.proven_texts).
PROVEN = lambda: []
# Set by the server: the owner's own recent saved messages (FocusBank.owner_style).
OWNER_STYLE = lambda: []
CORRECTIONS = lambda: []  # the owner's saved wording corrections; set by the server


def _prompt(source, count, avoid):
    lines = source.split("\n")
    blank = sum(1 for line in lines if not line.strip())
    avoid_text = ""
    if avoid:
        openings = []
        for item in avoid:
            first = next((line.strip() for line in item.split("\n") if line.strip()), "")
            if first and first not in openings:
                openings.append(first[:180])
        if openings:
            avoid_text = (
                "\nThese versions already exist. Do not reuse their openings or wording:\n"
                + "\n".join("- " + opening for opening in openings)
            )
    try:
        proven = [str(t) for t in (PROVEN() or [])][:2]
    except Exception:
        proven = []
    if proven:
        avoid_text += (
            "\n\nPROVEN STYLE (real past messages that were followed by donations). Learn their"
            " structure, opening style, urgency and tone only. Never copy their facts, names,"
            " amounts, times or deadlines; every fact must come from the SOURCE:\n"
            + "\n---\n".join(p[:900] for p in proven)
        )
    try:
        own = [str(t) for t in (OWNER_STYLE() or []) if str(t).strip() != source.strip()][:3]
    except Exception:
        own = []
    if own:
        avoid_text += (
            "\n\nOWNER'S OWN MESSAGES (written by the owner for earlier appeals). Learn their voice,"
            " intensity, hooks and rhythm only. Never copy their facts, names, amounts, times or"
            " deadlines; every fact must come from the SOURCE:\n"
            + "\n---\n".join(t[:900] for t in own)
        )
    try:
        import quality

        avoid_text += quality.corrections_block(CORRECTIONS() or [])
    except Exception:
        pass
    low, high = length_range(source)
    size = len(source)
    return f"""Rewrite the source message below into exactly {count} DISTINCT, fully reworded versions.

The source has {len(lines)} lines and {blank} blank lines. Keep that exact line
structure. Keep every blank line in the same place.

NON-NEGOTIABLE:
- Length: target {low} to {high} characters (source {size}); natural length is
  more important than matching the original number of letters.
- Rewrite the entire message: change the opening AND at least two other meaningful
  prose lines. Do NOT only change two words, replace synonyms, or reorder a sentence.
- Maintain the same core concept and verified urgency; use different clear, emotional
  approaches across versions. No invented time pressure, medical progression,
  consequences, deadlines, promises, or extra diagnoses.
- Rewrite each editable paragraph into genuinely different, very easy English.
- LANGUAGE: every version keeps the source's language line by line. An English line stays
  plain English: never Urdu script and never Roman Urdu (Urdu in English letters, like "Aaj hai
  qarz"). Never turn Urdu into English. Urdu only where the owner asked for it.
- URDU: a line written in Urdu stays in Urdu script and is reworded in simple, moving Urdu
  (never translated to English, never transliterated). A Quran verse, hadith or its
  reference, e.g. (سورة المائدہ: 2), is copied exactly, word for word.
  Retain the original paragraph order, blank lines, and WhatsApp formatting.
- Do not invent guilt, death threats, or unverified claims.
- Keep every emoji and every *, _ and *_ WhatsApp formatting marker in the same
  position. Do not flatten, add or remove formatting.
- Keep every number, amount, phone number, account name, payment method and the
  final reply instruction exactly as written in the source.
- Keep the same greeting form. Do not add a name or a new salutation.
- Do not invent symptoms, hospitals, dates, promises, donations or deadlines.
- Do not use long dashes.
- EVERY new version must differ substantively from the source and other versions
  in both the hook and body. Avoid repeating the same 5-8 word phrases.
- The exact payment/phone and account lines are immutable, copy them verbatim.
- VOICE: copy the owner's own voice from the source: same short punchy lines, same
  bold/italic rhythm, same direct "you" address, same simple words. Never sound formal.
- SAME PLACE, NEW WORDS: line N of every version says what line N of the source says.
  A fact in the first line (for example "22 hours until the Janazah") stays in the first
  line of every version, reworded. Keep each line within about 15% of its source line's
  length. Do not rearrange sections or move facts between lines.
- PSYCHOLOGY. Every line must earn its place; use a DIFFERENT mix in each version, built only
  from facts in the source:
  * Hook (line 1): a pattern interrupt the brain cannot ignore in under two seconds: the real
    time left, a stark contrast (a whole family's need vs one small gift), or a direct question.
  * Identifiable victim: name the person the source names and say their exact situation as
    written. One person moves people more than numbers. Do not assume age, gender or
    relationship beyond what the source says.
  * Vivid, concrete detail: turn the source's facts into a picture the reader can see.
  * Real urgency and loss aversion: what is lost if help does not arrive in the time the
    source gives. Only the source's own times; if it gives none, urgency is the amount still
    needed right now.
  * Make it small and doable: the smallest real ask from the source, and how few people it takes.
  * Responsibility: break the "someone else will help" bystander effect; "you" are the one.
  * Social proof and momentum: others are already helping, join them (only if the source
    implies it).
  * Reward: sadqa, dua and the reader's own akhirah, in warm words.
  * Close with an easy yes: one clear action now.
  Strong, never false: no invented guilt trips, threats, diagnoses, deadlines or outcomes.
- LEARN FROM THE OWNER: the SOURCE and any OWNER'S OWN MESSAGES below are the owner's voice.
  Match their intensity, line rhythm, emoji energy, hooks and directness; do not soften them.
  Never lower the urgency the owner wrote.
- Return ONLY a JSON array of {count} strings. No commentary, no markdown fences.

SOURCE:
<<<SOURCE
{source}
SOURCE>>>{avoid_text}
"""


def _call(key, prompt):
    message = assistant._chat_raw(
        key,
        SYSTEM,
        [],
        [{"role": "user", "content": prompt}],
        max_tokens=8192,
        thinking_mode=False,
        timeout=90,  # five full messages can take longer than the default 45 s
    )
    content = message.get("content") if isinstance(message, dict) else ""
    return _json_list(content)


AI_BACKOFF = (5, 15, 30)  # seconds to wait after a rate limit / server hiccup before retrying
_sleep = time.sleep


def ai_fatal(message):
    """A key or account problem: retrying cannot help."""
    return bool(
        re.search(
            r"(?i)\b(401|402|403)\b|not connected|api key|unauthori[sz]ed|insufficient",
            str(message),
        )
    )


def ai_transient(message):
    """Busy, rate limited, timed out or a server error: worth one more try after a short wait."""
    return bool(
        re.search(
            r"(?i)\b(429|500|502|503|504|529)\b|timed? ?out|timeout|temporar|overload|connection|reset|unavailable",
            str(message),
        )
    )


def top_reasons(tally, limit=3):
    top = sorted(tally.items(), key=lambda kv: -kv[1])[:limit]
    return "; ".join(f"{r} ({n}x)" if n > 1 else r for r, n in top)


def generate(source, count=10, avoid=None, *, progress=None, allow_partial=False):
    """Validate every rewrite, report accepted batches, and optionally retain partial results."""
    source = clean_source(source)
    if not dm_composer.complete(source):
        raise ValueError(
            "Paste the complete message with its paragraphs, amount and payment details."
        )
    count = max(1, min(20, int(count)))
    existing = [
        str(item).strip() for item in (avoid or []) if isinstance(item, str) and item.strip()
    ]
    out = []
    key = assistant.client()
    if key is None:
        raise ValueError(
            "The AI is not connected, so I cannot reword a custom message. The built-in structured DM still works."
        )
    last_error = ""
    reasons = {}
    waits = list(AI_BACKOFF)
    for attempt in range(5 + len(AI_BACKOFF)):
        if attempt - (len(AI_BACKOFF) - len(waits)) >= 5:
            break  # extra rounds only make up for rate-limit waits
        need = count - len(out)
        if need <= 0:
            break
        try:
            # Smaller batches avoid model truncation and improve diversity.
            prompt = _prompt(source, min(need, 5), existing + out)
            if last_error:
                prompt += (
                    "\nThe previous attempt was rejected because: "
                    + last_error[:240]
                    + ". Correct that while keeping the verified facts."
                )
            candidates = _call(key, prompt)
        except Exception as exc:
            last_error = str(exc)
            if ai_fatal(last_error):
                break
            if ai_transient(last_error) and waits:
                _sleep(waits.pop(0))  # busy or briefly down: wait, then try again
            continue
        before = len(out)
        tried = {}
        for candidate in candidates:
            if isinstance(candidate, str):
                candidate = repair(source, candidate.replace("\r\n", "\n").strip())
            reason = validate(source, candidate, existing + out)
            if reason:
                tried[reason] = tried.get(reason, 0) + 1
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            out.append(candidate.strip())
            if len(out) >= count:
                break
        if tried:
            last_error = top_reasons(tried)
        if progress is not None and len(out) > before:
            if progress(list(out)) is False:
                raise ValueError(
                    "Generation stopped because the source changed. Your newer edit is safe."
                )
    if allow_partial and out:
        return out[:count]
    if len(out) < count:
        summary = top_reasons(reasons) or last_error
        detail = (" Rejected because: " + summary + ".") if summary else ""
        raise ValueError(
            f"The AI returned only {len(out)} sufficiently different versions that kept the facts and formatting.{detail} "
            "The saved DM and the message bank were not changed."
        )
    return out[:count]
