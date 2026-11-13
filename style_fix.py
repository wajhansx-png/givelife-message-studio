"""Style fix: the SAME words, laid out in the owner's message structure. No new version, no AI.

The owner's template (see message_styles.assemble and message_rules.problems):
  line 1   the hook            bold         *...*
  line 2   the story           italic       _..._
  verse / hadith               plain
  amount   🔴 Rs. N LEFT        plain
  help     • *_Just N people donating Rs. E can help ..._* 🤲   (bold + italic)
  payment  03097458815 / EASYPAISA ONLY ... / — GiveLife Foundation
A PDF-style message has the exact line 3 ("kind people ... Rs. 2,000 or M ... Rs. 1,000"), line 4 and the footer instead
of the amount / help lines; it is fixed the same way.

fix() changes only markers (stars, underscores), spacing between parts and bullets. It never rewrites a word.
What is MISSING is added from the code-built pieces: the live amount, the donor sum, the saved payment account and
the signature. Nothing is saved or sent here.
"""

import re

import message_rules as MR
import message_styles as MS
import team_rules as T

_MARKS = re.compile(r"[*_~`]")
_NUM = re.compile(r"\d[\d,]*")
_LEFT = re.compile(r"(?i)\bleft\b|باقی")
_BULLET = re.compile(r"^\s*(?:[•·\-–]|\*(?=\s))\s*")
_JUST = re.compile(r"(?i)\bjust\s+\d+\b.*\bdonat")
_VERSE = re.compile(r"(?i)allah says|the prophet|sahih|sunan|surah|سورۃ|سورة|صحیح|سنن|ارشاد")
_PAYMENT = re.compile(r"\b0?\d{10,12}\b|(?i:easy\s?paisa)")
_TAIL_EMOJI = re.compile(r"[\s\U0001F000-\U0001FAFF☀-➿️]+$")
_HOOK_END = tuple(T.HOOK_ENDINGS)


def _plain(text):
    """The words only: no stars or underscores, one space between words."""
    return re.sub(r"[ \t]+", " ", _MARKS.sub("", str(text))).strip()


def _words(text):
    """Letters and digits only, for checking that the words did not change."""
    return re.findall(r"[^\W_]+", _plain(text).casefold())


def _role(block):
    lines = [ln for ln in block.split("\n") if ln.strip()]
    first = lines[0] if lines else ""
    flat = _plain(block)
    if _PAYMENT.search(flat.replace(" ", "")) or _PAYMENT.search(flat):
        return "payment"
    if "GiveLife" in flat and len(flat.split()) <= 6:  # the signature line ("— GiveLife Foundation")
        return "payment"
    if _BULLET.match(first) or _JUST.search(flat):
        return "bullet"
    if _LEFT.search(flat) and _NUM.search(flat) and len(flat.split()) <= 10:
        return "amount"
    if _VERSE.search(flat) or (len(lines) >= 2 and re.search(r"[\"“«]", flat)):
        return "verse"
    if flat == T.LINE4:
        return "line4"
    return "text"


def _bold_hook(block):
    out = []
    for line in [ln for ln in block.split("\n") if ln.strip()]:
        core = _plain(line)
        end = next((e for e in _HOOK_END if core.endswith(e)), "")
        core = core[: -len(end)].rstrip() if end else core
        out.append(f"*{core}*" + (f" {end}" if end else ""))
    return "\n".join(out)


def _italic(block):
    return "\n".join(f"_{_plain(line)}_" for line in block.split("\n") if line.strip())


def _amount(block):
    n = int(_NUM.search(_plain(block))[0].replace(",", "") or 0)
    return f"🔴 Rs. {n:,} LEFT"


def _bullet(block):
    flat = _plain(_BULLET.sub("", block.strip(), count=1)).replace("\n", " ")
    tail = _TAIL_EMOJI.search(flat)
    emoji = tail[0].strip() if tail else ""
    body = flat[: tail.start()].rstrip() if tail else flat
    return f"• *_{body}_*" + (f" {emoji}" if emoji else "")


def _verse(block):
    return "\n".join(_plain(line) for line in block.split("\n") if line.strip())


def _split(text):
    parts = MR.blocks(text)
    lines = [ln.strip() for ln in str(text).replace("\r\n", "\n").split("\n") if ln.strip()]
    if len(parts) < 3 and len(lines) >= 4:  # lines pasted without blank lines between them
        parts = lines
    return parts


def fix(text, left=None, saved=()):
    """Return {"text", "changed", "changes"}. `left` is the live amount still needed (None: add nothing that needs it);
    `saved` are the owner's saved messages, where the payment account and signature are copied from."""
    original = str(text or "").replace("\r\n", "\n").strip()
    if not original:
        raise ValueError("There is no message to fix. Write or open a message first.")
    blocks = _split(original)
    roles = [_role(b) for b in blocks]
    changes = []
    out = []
    for i, (block, role) in enumerate(zip(blocks, roles)):
        if i == 0 and role == "text":
            new, label = _bold_hook(block), "Line 1 is bold"
        elif i == 1 and role == "text":
            new, label = _italic(block), "Line 2 is italic"
        elif role == "amount":
            new, label = _amount(block), "The amount line is 🔴 Rs. … LEFT"
        elif role == "bullet":
            new, label = _bullet(block), "The help line is bold and italic"
        elif role == "verse":
            new, label = _verse(block), "The verse is plain"
        else:
            new, label = block.strip(), ""
        if label and new != block.strip():
            changes.append(label)
        out.append(new)
    kinds = ["hook" if r == "text" and i == 0 else "story" if r == "text" and i == 1 else r for i, r in enumerate(roles)]

    pdf = "line4" in kinds or any(MR._LINE3.match(b.strip()) for b in out)
    live = isinstance(left, int) and not isinstance(left, bool) and left > 0

    def at(role_list):
        return next((i for i, k in enumerate(kinds) if k in role_list), len(out))

    def put(index, block, role, why):
        index = max(index, min(len(out), 2))
        out.insert(index, block)
        kinds.insert(index, role)
        changes.append(why)

    if live and not pdf and "amount" not in kinds:
        put(at(("bullet", "payment")), f"🔴 Rs. {left:,} LEFT", "amount", f"Added the amount line (Rs. {left:,} left)")
    if live and "bullet" not in kinds:
        if pdf:
            counts = T.gift_counts(left, exact=False)
            if counts:
                put(at(("line4", "payment")), T.LINE3.format(n=counts[0], m=counts[1]), "bullet", "Added the help line")
        else:
            people, each = MS.donor_math(left)
            who = "person" if people == 1 else "people"
            line = f"• *_Just {people} {who} donating Rs. {each:,} can help this family._* 🤲"
            put(at(("payment",)) if "amount" not in kinds else kinds.index("amount") + 1, line, "bullet", "Added the help line")
    if pdf and "line4" not in kinds and "bullet" in kinds:
        put(kinds.index("bullet") + 1, T.LINE4, "line4", "Added the closing line")
    if "payment" not in kinds:
        block = "\n".join(T.FOOTER) if pdf else MS.payment_block(original, *saved)
        out.append(block)
        kinds.append("payment")
        changes.append("Added the payment account and signature")
    elif not any("GiveLife" in b for b in out):
        out.append("— GiveLife Foundation")
        kinds.append("payment")
        changes.append("Added the signature")

    result = "\n\n".join(out)
    return {"text": result, "changed": result != original, "changes": changes}
