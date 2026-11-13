"""Four message styles for the editor: Urdu + English, More Trigger, English, English Trigger.

The AI only writes the emotional parts (hook, short story, a few words). Everything that must be exact is
built here in code: the amount left, the donor count and amount, the Quran/Hadith text and reference
(chosen from a fixed list, never written by the AI), the saved payment account and the signature.
"""

import datetime, re, time
import dm_composer, quality, team_rules
from message_library import style_block

STYLES = ("ur_en", "ur_en_more", "en", "en_more")
BILINGUAL = ("ur_en", "ur_en_more")
TRIGGER = ("ur_en_more", "en_more")

ANGLES = (
    ("family", "family suffering: what this family is going through, using only the facts"),
    (
        "danger",
        "real danger: only if the facts really describe a danger; otherwise use the hardship itself",
    ),
    ("need", "immediate need: what has to be paid for and why it cannot wait, from the facts only"),
    ("islamic", "Islamic reminder: the reward of helping, tied gently to this case"),
    (
        "numbers",
        "donor numbers: how few people it takes to finish this, using the donor numbers given",
    ),
    ("gratitude", "gratitude: thank the donors and show their help is already making a difference"),
)

# Every verse and hadith the app may print. The AI picks an id; the text and reference come only from here.
# Hadith are the three the owner already approved (team_rules.HADITH, copied exactly).
_Q_UR = 'اللّٰہ تعالیٰ کا ارشاد ہے:\n"{t}"\n({r})'
_Q_EN = 'Allah says:\n"{t}"\n({r})'
VERSES = {
    "q34_39": dict(
        kind="quran",
        ur_ref="سورۃ سبا: 39",
        en_ref="Surah Saba 34:39",
        ur="تم جو کچھ بھی (اللہ کی راہ میں) خرچ کرو گے، وہ اس کا بدلہ دے گا۔",
        en="Whatever you spend (in Allah's way), He will replace it.",
        note="Allah gives back what is spent for Him",
    ),
    "q2_261": dict(
        kind="quran",
        ur_ref="سورۃ البقرہ: 261",
        en_ref="Surah Al-Baqarah 2:261",
        ur="جو لوگ اپنا مال اللہ کی راہ میں خرچ کرتے ہیں، ان کی مثال اس دانے کی سی ہے جس سے سات بالیاں اگیں اور ہر بالی میں سو دانے ہوں۔",
        en="Those who spend their wealth in Allah's way are like a seed that grows seven ears, with a hundred grains in every ear.",
        note="spending in Allah's way grows many times",
    ),
    "q2_245": dict(
        kind="quran",
        ur_ref="سورۃ البقرہ: 245",
        en_ref="Surah Al-Baqarah 2:245",
        ur="کون ہے جو اللہ کو قرضِ حسنہ دے، پھر اللہ اسے اس کے لیے کئی گنا بڑھا دے؟",
        en="Who will lend Allah a good loan, so that He multiplies it for him many times?",
        note="a good loan to Allah is multiplied",
    ),
    "q3_92": dict(
        kind="quran",
        ur_ref="سورۃ آل عمران: 92",
        en_ref="Surah Aal-Imran 3:92",
        ur="تم نیکی کو ہرگز نہیں پا سکتے جب تک اپنی پسندیدہ چیزوں میں سے (اللہ کی راہ میں) خرچ نہ کرو۔",
        en="You will never reach true goodness until you spend from what you love (in Allah's way).",
        note="true goodness means giving from what we love",
    ),
    "q5_2": dict(
        kind="quran",
        ur_ref="سورۃ المائدہ: 2",
        en_ref="Surah Al-Ma'idah 5:2",
        ur="نیکی اور تقویٰ میں ایک دوسرے کی مدد کرو۔",
        en="Help one another in goodness and taqwa.",
        note="helping each other in goodness",
    ),
    "h_muslim_2699": dict(
        kind="hadith",
        ur_full=team_rules.HADITH[0],
        en_full='The Prophet ﷺ said: "Whoever removes a worldly hardship from a Muslim, Allah will remove a hardship from him on the Day of Judgment." (Sahih Muslim 2699)',
        note="removing a believer's hardship",
    ),
    "h_bukhari_481": dict(
        kind="hadith",
        ur_full=team_rules.HADITH[1],
        en_full='The Prophet ﷺ said: "A believer is to a believer like a building, each part strengthening the other." (Sahih Bukhari 481)',
        note="believers support each other",
    ),
    "h_tirmidhi_2616": dict(
        kind="hadith",
        ur_full=team_rules.HADITH[2],
        en_full='The Prophet ﷺ said: "Charity wipes out sins just as water puts out fire." (Sunan Tirmidhi 2616)',
        note="charity wipes out sins",
    ),
}


def verse_block(verse_id, english):
    v = VERSES[verse_id]
    if v["kind"] == "hadith":
        return v["en_full"] if english else v["ur_full"]
    if english:
        return _Q_EN.format(t=v["en"], r=v["en_ref"])
    return _Q_UR.format(t=v["ur"], r=v["ur_ref"])


def donor_math(left):
    """(people, rupees each) so that people x rupees covers what is left. 1,000 or 2,000 each like the app
    always does, 5,000/10,000 only when the count would otherwise be large. Rounds up, never down."""
    left = int(left)
    if left <= 0:
        raise ValueError("The case is complete (Rs. 0 left). Nothing was written.")
    if left <= 1000:
        return 1, left
    for each in (1000, 2000, 5000, 10000):
        people = -(-left // each)
        if people <= 10 or each == 10000:
            return people, each


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def numbers_in(text):
    """Every whole number written in the text (commas allowed; Urdu digits counted)."""
    return {
        int(n.replace(",", ""))
        for n in re.findall(r"\d[\d,]*", str(text).translate(_DIGITS))
        if n.replace(",", "")
    }


def payment_block(*texts):
    """The saved payment account and signature, taken from the owner's own saved message."""
    for text in texts:
        lines = str(text or "").strip().splitlines()
        for i in range(len(lines) - 1, -1, -1):
            if re.search(r"\b0?\d{10,12}\b", lines[i].replace("*", "").replace(" ", "")):
                start = i - 1 if i and re.search(r"(?i)easypaisa|account", lines[i - 1]) else i
                tail = lines[start:]
                end = next((n for n, line in enumerate(tail) if "GiveLife" in line), None)
                block = "\n".join(
                    tail[: end + 1] if end is not None else tail
                ).strip()  # ends at the signature
                if "GiveLife" not in block:
                    block += "\n— GiveLife Foundation"
                return dm_composer.payment_fix(block)
    return dm_composer.payment_fix("\n".join(team_rules.FOOTER))


def _words(text):
    return set(re.findall(r"[^\W\d_]{3,}", str(text).casefold()))


def similarity(a, b):
    a, b = _words(a), _words(b)
    return len(a & b) / max(1, len(a | b))


def opening_key(hook):
    return " ".join(re.findall(r"[^\W\d_]+", str(hook).casefold())[:7])


def _clean_line(value, limit):
    value = re.sub(r"[*_~`]+", "", re.sub(r"\s+", " ", str(value or ""))).strip()
    if not value or len(value) > limit:
        raise ValueError("a line was missing or too long")
    return value


def assemble(style, parts, ctx):
    """The finished message. Nothing the AI wrote can change the structure, amounts, verse text or account."""
    english = style not in BILINGUAL
    people, each = ctx["people"], ctx["each"]
    hook = _clean_line(parts.get("hook"), 150)
    story = _clean_line(parts.get("story"), 330).rstrip(" 💔.") + ". 💔"
    story = story.replace("..", ".")
    help_for = re.sub(r"[^A-Za-z' -]", "", str(parts.get("help") or "")).strip()
    help_for = help_for if 0 < len(help_for.split()) <= 8 else "this family"
    verse = verse_block(parts["verse"], english)
    who = "person" if people == 1 else "people"
    return "\n\n".join(
        [
            f"*{hook}*",
            f"_{story}_",
            verse,
            f"🔴 Rs. {ctx['left']:,} LEFT",
            f"• *_Just {people} {who} donating Rs. {each:,} can help {help_for}._* 🤲",
            ctx["payment"],
        ]
    )


def allowed_numbers(ctx):
    base = {ctx["left"], ctx["people"], ctx["each"], 1}
    return base | {n for n in numbers_in(ctx.get("facts", "")) if n < 100}


def problems(style, text, parts, ctx, previous=""):
    """Why a finished message must not be used ('' list when it is fine)."""
    out = []
    english = style not in BILINGUAL
    hook_urdu = bool(re.search(r"[؀-ۿ]", str(parts.get("hook", ""))))
    if english and (hook_urdu or re.search(r"[؀-ۿ]", text)):
        out.append("an English message contains Urdu")
    if not english and not hook_urdu:
        out.append("the first line is not in Urdu")
    extra = numbers_in(
        parts.get("hook", "") + " " + parts.get("story", "") + " " + parts.get("help", "")
    ) - allowed_numbers(ctx)
    if extra:
        out.append(
            "it used numbers that are not in the case: "
            + ", ".join(f"{n:,}" for n in sorted(extra))
        )
    if re.search(team_rules.OTHER_PAYMENT, text):
        out.append("it names a payment method other than Easypaisa")
    if dm_composer.unverified_medical_claim(text):
        out.append("it makes a medical claim that is not confirmed")
    never = quality.NEVER.search(text)
    if never:
        out.append(f'it uses the word "{never.group(0)}" (never say gift: say donation, giving or helping)')
    if parts.get("verse") not in VERSES:
        out.append("the verse is not on the approved list")
    if style in TRIGGER and previous:
        if similarity(previous, parts.get("hook", "") + " " + parts.get("story", "")) > 0.45:
            out.append("it is too close to the message it should replace")
        if parts.get("verse") and parts["verse"] == ctx.get("last_verse"):
            out.append("it uses the same verse as before")
    if not dm_composer.complete(text):
        out.append("the message is not complete")
    return out


def pick_angle(state, style):
    last = state.get("angle")
    names = [a[0] for a in ANGLES]
    i = (
        (names.index(last) + (2 if style in TRIGGER else 1)) % len(ANGLES)
        if last in names
        else (state.get("n", 0) % len(ANGLES))
    )
    return ANGLES[i]


def build_prompt(style, ctx, angle, avoid, previous, notes):
    english = style not in BILINGUAL
    verses = "\n".join(
        f"- {k}: {v['note']}"
        for k, v in VERSES.items()
        if k != ctx.get("last_verse") or style not in TRIGGER
    )
    lines = [
        "Write the emotional parts of ONE WhatsApp fundraising message for GiveLife Foundation.",
        "",
        "CASE FACTS (the owner's own saved messages. These are the ONLY facts you may use):",
        ctx["facts"][:12000],
        "",
        f"MONEY: Rs. {ctx['left']:,} is still needed. Just {ctx['people']} people giving Rs. {ctx['each']:,} each can finish it.",
        f"ANGLE for this message: {angle[1]}.",
        "RULES:",
        "- Use extremely simple English (short sentences, everyday words).",
        "- Never invent a danger, deadline, medical claim, donation, name, age or number. If a fact is not above, do not write it.",
        "- The only numbers you may write are "
        + f"{ctx['people']} and {ctx['each']:,}"
        + " (and numbers already in the facts).",
        "- No quotes from the Quran or Hadith in your text. Only choose a verse id from the list.",
        (
            "- hook: ONE strong emotional line in English, under 15 words."
            if english
            else "- hook: ONE strong emotional line in URDU (Urdu script), under 15 words."
        ),
        "- story: 1 or 2 short simple ENGLISH sentences that explain the case. Do not end it with an emoji.",
        "- help: 2 to 5 words finishing 'can help ...' for example 'this helpless father'.",
        "- Do not use * or _ characters.",
        "- " + quality.NEVER_RULE,
        "",
        "VERSES (choose the one id that fits this case and angle best):",
        verses,
    ]
    if style in TRIGGER:
        lines += [
            "",
            "THIS IS A SECOND, STRONGER VERSION. Change the whole concept: a new story angle, a new first line, new wording.",
            "Do not just swap words. Make the real need feel more urgent, using only the true facts above.",
        ]
    if previous:
        lines += [
            "",
            "THE MESSAGE BEING REPLACED (do not reuse its ideas or wording):",
            previous[:900],
        ]
    if avoid:
        lines += [
            "",
            "OPENINGS ALREADY USED TODAY (the new first line must be clearly different): "
            + " | ".join(avoid[:8]),
        ]
    for note in notes:
        lines += ["", "FIX THIS FROM THE LAST TRY: " + note]
    lines += [
        "",
        'Reply with one JSON object only: {"hook": "...", "story": "...", "help": "...", "verse": "<id>", "concept": "<5 words>"}',
    ]
    return "\n".join(lines) + style_block(ctx.get("style_examples", []))


SYSTEM = "You are a careful, honest charity copywriter. You never invent facts. Reply with one JSON object only."


def generate(style, ctx, state, chat, json_of, today=None, deadline=75.0, archive=None):
    """-> (result dict, new state). `chat(system, prompt)` returns text. Raises ValueError with a plain reason."""
    if style not in STYLES:
        raise ValueError("Unknown message style.")
    if ctx["left"] <= 0:
        raise ValueError("The case is complete (Rs. 0 left). Nothing was written.")
    ctx = dict(ctx)
    ctx["people"], ctx["each"] = donor_math(ctx["left"])
    ctx["payment"] = payment_block(ctx.get("group_text"), ctx.get("dm_text"))
    ctx["last_verse"] = (state.get("last") or {}).get("verse")
    day = today or datetime.date.today().isoformat()
    used = list((state.get("openings") or {}).get(day, []))
    previous = ctx.get("current_text", "") if style in TRIGGER else ""
    angle = pick_angle(state, style)
    started, notes, failures = time.monotonic(), [], []
    for attempt in range(3):
        if attempt and time.monotonic() - started > deadline:
            break
        raw = chat(SYSTEM, build_prompt(style, ctx, angle, used, previous, notes))
        parts = json_of(raw)
        if not parts:
            notes.append("Reply with valid JSON only.")
            failures.append("the AI did not answer in the required form")
            continue
        try:
            text = assemble(style, parts, ctx)
        except (ValueError, KeyError):
            notes.append("Every field is required, within its length, with no * or _.")
            failures.append("the AI left out a required part")
            continue
        bad = problems(style, text, parts, ctx, previous)
        if archive:
            archive(text, "candidate")
        key = opening_key(parts.get("hook"))
        if key in used:
            bad.append("the first line was already used today")
        if bad:
            notes.append("; ".join(bad))
            failures.append(bad[0])
            continue
        used.append(key)
        new_state = dict(state)
        new_state["angle"] = angle[0]
        new_state["n"] = int(state.get("n", 0)) + 1
        new_state["openings"] = {day: used[-40:]}
        new_state["last"] = {
            "style": style,
            "verse": parts["verse"],
            "hook": parts.get("hook"),
            "at": time.time(),
        }
        if archive:
            archive(text, "validated")
        return {
            "text": text,
            "angle": angle[0],
            "concept": str(parts.get("concept", ""))[:60],
        }, new_state
    raise ValueError(
        "I could not write a message that passed every check ("
        + (failures[-1] if failures else "no answer")
        + "). Nothing was changed. Press the button again."
    )
