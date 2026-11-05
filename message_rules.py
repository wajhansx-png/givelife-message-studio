"""Checks a WhatsApp group message against the GiveLife PDF self-check lists.

`problems(text)` returns [] for a message that follows the prompt exactly, else short plain reasons.
Normal prompt: hook (bold), details (italic), line 3, line 4, footer.
Slow-donations prompt: Urdu hook (bold), English details (italic), one listed hadith, line 3, line 4, footer.
"""

import re, unicodedata
import team_rules as T

_BIDI = re.compile("[‎‏‪-‮⁦-⁩]")
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿]️?")
_URDU = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")
_LINE3 = re.compile(
    r"^• \*_Just (\d+) kind people donating Rs\. 2,000 or (\d+) people donating Rs\. 1,000 can complete this amount\._\*$"
)
_PRICE = re.compile(r"(?i)\brs\.?|\bpkr\b|rupee|روپے|\d{1,3},\d{3}|\d{4,}")


def _norm(text):
    """Same text, ignoring invisible direction marks, Arabic/Urdu letter variants and spacing."""
    text = unicodedata.normalize("NFC", _BIDI.sub("", str(text or "")))
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("ه", "ہ")
    return re.sub(r"\s+", " ", text).strip()


def _words(text):
    return [
        w
        for w in re.split(r"\s+", _EMOJI.sub(" ", re.sub(r"[*_]", " ", text)))
        if re.search(r"\w", w)
    ]


def blocks(text):
    text = _BIDI.sub("", str(text or "").replace("\r\n", "\n")).strip()
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def mode_of(text):
    first = (blocks(text) or [""])[0]
    return "slow" if len(_URDU.findall(first)) > len(_LATIN.findall(first)) else "normal"


def hook_patterns(facts):
    """The PDF's own hook patterns filled with verified facts. These are approved as written."""
    if not facts:
        return set()
    name, age, he = facts.get("name", ""), facts.get("age"), facts.get("gender") == "boy"
    his = "His" if he else "Her"
    out = {
        f"{name}'s parents are sitting with their child's body and have no money for the burial.",
        f"{name} کے ماں باپ اپنے بچے کی میت کے پاس بیٹھے ہیں اور کفن دفن کے پیسے نہیں۔",
    }
    if age is not None and facts.get("gender") in ("boy", "girl"):
        out.add(
            f"{age}-year-old {name} has passed away. {his} parents cannot pay for {his.lower()} Janazah."
        )
        out.add(
            f"{age} سال کا {name} دنیا سے چلا گیا، مگر اس کے والدین کے پاس تدفین کے پیسے بھی نہیں۔"
            if he
            else f"{age} سال کی {name} دنیا سے چلی گئی، مگر اس کے والدین کے پاس تدفین کے پیسے بھی نہیں۔"
        )
    return {_norm(p) for p in out}


def _check_hook(hook, mode, facts, out):
    core, end = hook.strip(), None
    for e in T.HOOK_ENDINGS:  # accepted: *text* 💔  or  *text 💔*
        if core.endswith(e):
            end, core = e, core[: -len(e)].rstrip()
            break
        if core.endswith(e + "*"):
            end, core = e, core[: -len(e) - 1].rstrip() + "*"
            break
    if not (core.startswith("*") and core.endswith("*") and len(core) > 2 and core.count("*") == 2):
        out.append("Line 1 must be bold: wrap it in *stars*.")
    if not end:
        out.append("Line 1 must end with 🔴 or 💔.")
    if "\n" in hook:
        out.append("Line 1 must be one line.")
    plain = _EMOJI.sub("", hook).replace("*", "").strip()
    if _PRICE.search(plain):
        out.append("Line 1 must not mention a price or amount.")
    if mode == "slow" and len(_URDU.findall(plain)) <= len(_LATIN.findall(plain)):
        out.append("Slow line 1 must be in Urdu script.")
    limit = T.HOOK_MAX_WORDS[mode]
    if len(_words(plain)) > limit and _norm(plain) not in hook_patterns(facts):
        out.append(f"Line 1 has {len(_words(plain))} words; the limit is {limit}.")


def _check_details(line, mode, out):
    if not (line.startswith("_") and line.endswith("_") and len(line) > 2) or line.startswith("_*"):
        out.append("Line 2 must be italic only: wrap it in _underscores_.")
    if "\n" in line:
        out.append("Line 2 must be one line.")
    count = len(_words(line))
    if count > T.DETAILS_MAX_WORDS:
        out.append(f"Line 2 has {count} words; the limit is {T.DETAILS_MAX_WORDS}.")
    if mode == "slow" and len(_URDU.findall(line)) > len(_LATIN.findall(line)):
        out.append("Slow line 2 must be in English.")


def _check_facts(hook, details, facts, out):
    if not facts:
        return
    text = hook + " " + details
    name = str(facts.get("name", "")).strip()
    if name and name.casefold() not in text.casefold():
        out.append(f"Lines 1–2 must name {name}.")
    allowed = {str(facts["age"])} if facts.get("age") is not None else set()
    allowed |= set(re.findall(r"\d+", str(facts.get("deadline") or "")))
    allowed |= set(re.findall(r"\d+", str(facts.get("what_happened") or "")))
    allowed |= set(re.findall(r"\d+", str(facts.get("money_for") or "")))
    for number in re.findall(r"\d+", _BIDI.sub("", text)):
        if number not in allowed:
            out.append(f"Lines 1–2 contain {number}, which is not in the case facts.")
            break


def problems(text, left=None, facts=None, exact=True):
    """[] when the message follows the PDF exactly. `left` = live amount still needed.

    exact=False accepts the app's round-up for a live balance that is not a multiple of Rs. 2,000."""
    if not isinstance(text, str) or not text.strip():
        return ["The message is empty."]
    out = []
    parts = blocks(text)
    mode = mode_of(text)
    expected = 6 if mode == "slow" else 5
    if len(parts) < expected:
        return [f"The message needs {expected} parts separated by blank lines; found {len(parts)}."]
    hook, details = parts[0], parts[1]
    rest = parts[2:]
    if mode == "slow":
        hadith = rest.pop(0)
        if _norm(hadith) not in {_norm(h) for h in T.HADITH}:
            out.append("The hadith must be copied exactly from the approved list of three.")
    line3, line4, footer = rest[0], rest[1], "\n".join(rest[2:])
    _check_hook(hook, mode, facts, out)
    _check_details(details, mode, out)
    match = _LINE3.match(line3.strip())
    if not match:
        out.append(
            "Line 3 must be copied exactly: • *_Just N kind people donating Rs. 2,000 or M …_*"
        )
    else:
        n, m = int(match[1]), int(match[2])
        want = T.gift_counts(left, exact) if left is not None else None
        if left is not None and not want:
            out.append(
                f"Rs. {left:,} cannot be split exactly into Rs. 2,000 gifts (PDF rule). The owner must decide."
                if left > 0
                else "Nothing is left to collect."
            )
        elif want and (n, m) != want:
            out.append(
                f"Line 3 says {n} and {m} people but Rs. {left:,} is still needed ({want[0]} and {want[1]})."
            )
        elif left is None and n * T.BIG_GIFT != m * T.SMALL_GIFT:
            out.append(f"Line 3 math is wrong: {n} × 2,000 is not {m} × 1,000.")
    if line4.strip() != T.LINE4:
        out.append("Line 4 must be exactly: " + T.LINE4)
    if [_norm(x) for x in footer.split("\n") if x.strip()] != [_norm(x) for x in T.FOOTER]:
        out.append(
            "The footer must be copied exactly (03097458815 / EASYPAISA ONLY – Wajdan Khan …)."
        )
    if re.search(T.OTHER_PAYMENT, text):
        out.append("Only Easypaisa may be mentioned. Remove other payment methods.")
    if re.search(r"(?<![\w&])#\w", text):
        out.append("No hashtags.")
    if len(_EMOJI.findall(text)) > T.MAX_EMOJIS:
        out.append(f"Use at most {T.MAX_EMOJIS} emojis.")
    _check_facts(hook, details, facts, out)
    return out


def refresh_amount(text, left):
    """Line 3 rewritten for the live amount still needed (rounded up when it cannot split exactly)."""
    if not isinstance(text, str) or not isinstance(left, int) or left <= 0:
        return text

    def fix(m):
        n, k = -(-left // T.BIG_GIFT), -(-left // T.SMALL_GIFT)
        return T.LINE3.format(n=n, m=k)

    return re.sub(_LINE3.pattern.strip("^$"), fix, text)


def is_pdf_message(text):
    """A message written with the PDF prompt (it has the exact line 3 and the Easypaisa footer)."""
    clean = _BIDI.sub("", str(text or ""))
    return any(_LINE3.match(b) for b in blocks(clean)) and T.FOOTER[1] in clean


def version_rules(source):
    """Extra instructions for AI rewrites of a PDF message ('' for other messages)."""
    if not is_pdf_message(source):
        return ""
    slow = mode_of(source) == "slow"
    return (
        "\nGiveLife PDF rules: copy line 3, line 4"
        + (", the hadith" if slow else "")
        + " and the footer exactly, character for character. Rewrite only line 1 (bold *…*, at most "
        + str(T.HOOK_MAX_WORDS["slow" if slow else "normal"])
        + (" words in Urdu script" if slow else " words")
        + ", same ending emoji, no prices) and line 2 (italic _…_, English, at most 30 words). "
        "Use only the facts already in the message."
    )
