"""Message quality: the owner's hard rules (code) and one batched AI review for natural wording.

Code rules always run first. The AI review only scores versions that already passed them, five per
call, and its answer must be valid JSON; an invalid or missing answer never blocks a version.
"""

import re

BANNED = re.compile(
    r"(?i)\bdanger\b|please send now|please help if you can|please help us if you can|"
    r"help if you can|kindly help if possible"
)


def hard_reason(source, text):
    """'' when the owner's hard rules hold, else why not. Only phrases NOT already in the source count."""
    for m in BANNED.finditer(text):
        if m.group(0).lower() not in source.lower():
            return f'owner rule: never use "{m.group(0)}"'
    return ""


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
        'Answer ONLY JSON: {"scores":[{"i":0,"owner":5,"natural":5,"calm":5,"follows":5,"reason":"short"}]}\n'
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
        if 0 <= i < len(versions) and low:
            keep[i] = "review: " + (
                str(row.get("reason", "")).strip()[:120] or "low " + ", ".join(low)
            )
    return keep
