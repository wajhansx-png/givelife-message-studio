"""Message quality: the owner's hard rules (code) and one batched AI review for natural wording.

Code rules always run first. The AI review only scores versions that already passed them, five per
call, and its answer must be valid JSON; an invalid or missing answer never blocks a version.
"""

import re

BANNED = re.compile(
    r"(?i)\bdanger\b|please send now|please help if you can|please help us if you can|"
    r"help if you can|kindly help if possible"
)


# Owner rules, always on, even when the source says it: a donation is never called a "gift" (gift, gifts, gifted,
# gifting), and a family is never "begging" (beg, begs, begged, begging, beggar). The new wording must say
# donation, giving, helping, an amount, or state the need plainly instead.
NEVER = re.compile(r"(?i)\b(?:gift(?:s|ed|ing)?|beg(?:s|ged|ging)?|beggars?)\b")
NEVER_RULE = (
    'Never use the word "gift" (or gifts or gifting). Say donation, giving, helping or the amount instead. '
    'Never use the word "begging" (or beg, begs, begged, beggar). Say what the family needs, '
    'or that they are asking for help, instead.'
)

# The owner reads every message on a phone and so do the donors: plain words only.
EASY_RULE = (
    "EASY ENGLISH: write English the way you talk to a 10-year-old. Only common everyday words, short "
    "sentences (12 words or fewer), no idioms and no fancy or poetic phrases. Never use words like: plight, "
    "dire, endure, devastating, grave, unimaginable, harrowing, battling, shutting down, pulling toward, "
    "slipping away, teetering, relentless. Say it plainly, for example: \"He is very sick. His family has no "
    "money for the medicine.\""
)
FANCY = re.compile(
    r"\b(plight|dire|endur\w*|devastat\w*|grave|unimaginabl\w*|harrowing|battling|shutting down|pulling\b.{0,20}\btoward|"
    r"slipping away|teeter\w*|relentless\w*|agoniz\w*|anguish\w*|perilous|precarious|unbearabl\w*)\b",
    re.I,
)


def fancy_words(source, text):
    """Hard words a rewrite added that the owner's own message does not use (plain English only)."""
    have = {m.group(0).lower() for m in FANCY.finditer(str(source or ""))}
    return sorted({m.group(0).lower() for m in FANCY.finditer(str(text or ""))} - have)


def hard_reason(source, text):
    """'' when the owner's hard rules hold, else why not. Only phrases NOT already in the source count (except
    the word "gift", which is never allowed)."""
    m = NEVER.search(text)
    if m:
        return f'owner rule: never use "{m.group(0)}"'
    for m in BANNED.finditer(text):
        if m.group(0).lower() not in source.lower():
            return f'owner rule: never use "{m.group(0)}"'
    return ""


FACT_WORDS = re.compile(
    r"(?i)\b(mother|father|parents?|brother|sister|wife|husband|son|daughter|family|orphan|widow|"
    r"years?|months?|age|old|surgery|operation|cancer|tumou?r|kidney|heart|liver|brain|blood|"
    r"hospital|icu|ventilator|doctor|died|dead|death|passed|janazah|burial|accident|disease|ill|sick|"
    r"today|tonight|tomorrow|deadline|hours?|days?)\b"
)


def new_fact(source, phrase):
    """True when a quoted phrase holds something the source does not: a number, a capitalised name or
    place, or a case-fact word (family, age, illness, time). Plain rewording is not a new fact."""
    low = source.lower()
    if any(n not in source for n in re.findall(r"\d[\d,]*", phrase)):
        return True
    if any(w not in source for i, w in enumerate(re.findall(r"\b[A-Z][a-z]{2,}\b", phrase)) if i):
        return True
    return any(w.lower() not in low for w in FACT_WORDS.findall(phrase))


def corrections_block(corrections):
    items = [str(c).strip()[:200] for c in corrections or [] if str(c).strip()][:15]
    if not items:
        return ""
    return (
        "\n\nOWNER CORRECTIONS (the owner fixed these before; every version MUST follow them):\n"
        + "\n".join("- " + c for c in items)
    )


def review(chat, source, versions, examples=(), corrections=()):
    """Batched AI review. Returns a list of '' (keep) or a short reason (rewrite), one per version.
    Any invalid answer keeps all versions: code rules already passed and nothing is guessed."""
    import ai_call

    keep = [""] * len(versions)
    if not versions:
        return keep
    prompt = (
        "Review WhatsApp charity appeal versions against the OWNER'S approved style.\n"
        "Score each 1-5: owner = sounds like the owner's examples; natural = sounds like a real person,"
        " not a robot; calm = emotional but not over the top; follows = obeys every correction.\n"
        "Also copy, word for word, any phrase in a version that states a fact (a person, age, illness, place, date,"
        " amount or promise) that is NOT in the SOURCE; use an empty string when there is none.\n"
        'Answer ONLY JSON: {"scores":[{"i":0,"owner":5,"natural":5,"calm":5,"follows":5,"invented":"","reason":"short"}]}\n'
        + (
            "\nOWNER EXAMPLES:\n" + "\n---\n".join(e[:700] for e in list(examples)[:3])
            if examples
            else ""
        )
        + corrections_block(corrections)
        + "\n\nSOURCE:\n"
        + source[:1500]
        + "\n\nVERSIONS:\n"
        + "\n".join(f"[{i}]\n{v[:1500]}" for i, v in enumerate(versions))
    )
    try:
        data = ai_call.json_of(chat(prompt))
    except Exception:
        return keep
    for row in (data or {}).get("scores", []) if isinstance(data, dict) else []:
        try:
            i = int(row["i"])
            low = [k for k in ("owner", "natural", "calm", "follows") if int(row.get(k, 5)) < 4]
        except (KeyError, TypeError, ValueError):
            continue
        invented = str(row.get("invented") or "").strip()
        if (
            0 <= i < len(versions)
            and invented
            and invented.lower() in versions[i].lower()
            and invented.lower() not in source.lower()
            and new_fact(source, invented)
        ):
            keep[i] = 'review: new fact not in the source: "' + invented[:80] + '"'
            continue
        if 0 <= i < len(versions) and low:
            keep[i] = "review: " + (
                str(row.get("reason", "")).strip()[:120] or "low " + ", ".join(low)
            )
    return keep
