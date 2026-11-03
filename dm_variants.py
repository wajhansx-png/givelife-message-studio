"""Generate reworded versions of an owner-supplied WhatsApp DM.

The static canonical templates cover the built-in Yousuf DM. This module is
the general path: the owner pastes any complete message, the model rewrites
only the wording, and deterministic checks reject any version that changes the
line structure, emojis, bold/italic markers, numbers or payment details.
"""
import difflib, json, re

import assistant
import dm_composer

VERSION = 'dm-variants-2026-11-02-deep-rewrite'

# Meaning and formatting matter more than matching a character count.
# Allow sentence-level rewrites while keeping each message reasonably compact.
LENGTH_TOLERANCE = 0.28

SYSTEM = """You are a careful fundraising copy editor for GiveLife Foundation.
You rewrite one WhatsApp direct message into new versions with the same concept,
facts and formatting. Return only the JSON array the user asks for. Never add
commentary, markdown fences, headings or a delivery claim.
Write in very easy English. Vary the ENTIRE editable story, not just one hook.
Do not invent medical details, fundraising deadlines or verified outcomes."""


def clean_source(source):
    """Strip a leading/trailing owner instruction from a pasted message."""
    text = str(source or '').replace('\r\n', '\n').strip()
    lines = text.split('\n')
    instruction = re.compile(
        r'(?i)\b(?:generate|make|create|write|rewrite|give|show|prepare|produce)\b'
        r'.{0,120}\b(?:versions?|variants?|wordings?|rewrites?)\b'
    )
    while lines and instruction.search(lines[0]) and len(lines[0]) < 300:
        lines.pop(0)
    while lines and instruction.search(lines[-1]) and len(lines[-1]) < 300:
        lines.pop()
    return '\n'.join(lines).strip()


def length_range(source):
    n = len(str(source or '').strip())
    return int(n * (1 - LENGTH_TOLERANCE)), int(n * (1 + LENGTH_TOLERANCE)) + 1


def _shape(text):
    """The exact line/blank-line/emoji/marker skeleton of a message."""
    lines = str(text or '').replace('\r\n', '\n').strip('\n').split('\n')
    out = []
    for line in lines:
        if not line.strip():
            out.append(('', 0, 0, True))
            continue
        lead = re.match(r'^[^\w\s]*', line).group(0)
        out.append((lead, line.count('*'), line.count('_'), False))
    return out


def _numbers(text):
    return [int(value.replace(',', '')) for value in re.findall(r'\d[\d,]*', str(text or ''))]


def _emojis(text):
    return re.findall(r'[\U0001F000-\U0001FAFF\u2600-\u27BF]', str(text or ''))


def _editable_lines(text):
    # Exclude exact payment/contact lines from variation scoring.
    return [line.strip() for line in str(text).split('\n')
            if line.strip() and not re.search(
                r'(?i)easypaisa|jazzcash|wajdan khan|reply \*done\*|03097458815', line)]


def _similarity(a, b):
    def normalized(text):
        return ' '.join(re.findall(r"[a-z]+", '\n'.join(_editable_lines(text)).lower()))
    return difflib.SequenceMatcher(None, normalized(a), normalized(b), autojunk=False).ratio()


def _meaningful_changes(source, candidate):
    a = _editable_lines(source)
    b = _editable_lines(candidate)
    if len(a) != len(b):
        return 0
    return sum(difflib.SequenceMatcher(None, x.lower(), y.lower(), autojunk=False).ratio() < 0.83
               for x, y in zip(a, b))


def validate(source, text, existing=()):
    """Return an error string, or '' when the version is safe to save."""
    if not isinstance(text, str):
        return 'not text'
    text = text.replace('\r\n', '\n').strip()
    source = str(source or '').replace('\r\n', '\n').strip()
    if len(text) < 180:
        return 'too short'
    if len(text) > 10000:
        return 'too long'
    if text == source:
        return 'same as the source'
    low, high = length_range(source)
    if not low <= len(text) <= high:
        return f'length {len(text)} is outside {low}-{high} characters (the source has {len(source)})'
    if text in existing:
        return 'duplicate wording'
    if _shape(text) != _shape(source):
        return 'line breaks, blank lines, emojis or bold/italic markers changed'
    if _emojis(text) != _emojis(source):
        return 'an emoji changed or moved'
    if _numbers(source) != _numbers(text):
        return 'a number, amount or phone number changed'
    source_lines = source.split('\n')
    text_lines = text.split('\n')
    for source_line, text_line in zip(source_lines, text_lines):
        if 'Rs.' in source_line and 'Rs.' not in text_line:
            return 'the currency formatting changed'
    first_source = next((line for line in source_lines if line.strip()), '')
    first_text = next((line for line in text_lines if line.strip()), '')
    if first_source.startswith('Brother,') and not first_text.startswith('Brother,'):
        return 'the greeting punctuation changed'
    for token in ('03097458815', 'Easypaisa / JazzCash', 'Wajdan Khan', 'Reply *Done* after donating.'):
        if token in source and token not in text:
            return 'payment details or the reply instruction changed'
    fixed_lines = [
        line.strip() for line in source.split('\n')
        if re.search(r'(?i)(?:Easypaisa|JazzCash|Wajdan Khan|03097458815|Reply \*Done\*)', line)
    ]
    if any(line not in text for line in fixed_lines):
        return 'payment details or the reply instruction changed'
    if not dm_composer.complete(text):
        return 'the message is not complete'
    # Reject superficial variations that merely swap the first sentence.
    # Requiring at least two rewritten editable lines makes the whole appeal change.
    editable = len(_editable_lines(source))
    minimum_lines = 2 if editable >= 3 else 1
    if _meaningful_changes(source, text) < minimum_lines or _similarity(source, text) > 0.81:
        return 'not deeply rewritten; change the opening AND the body wording'
    if any(_similarity(text, other) > 0.87 for other in existing if isinstance(other, str)):
        return 'too similar to an existing version; rewrite the story differently'
    return ''


def _json_list(raw):
    raw = str(raw or '').strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.I)
    raw = re.sub(r'\s*```$', '', raw)
    try:
        data = json.loads(raw, strict=False)
    except (ValueError, TypeError):
        match = re.search(r'\[[\s\S]*\]', raw)
        if not match:
            raise ValueError('The model did not return a JSON list of messages.')
        data = json.loads(match.group(0), strict=False)
    if isinstance(data, dict):
        data = data.get('versions') or data.get('messages') or data.get('items')
    if isinstance(data, str):
        data = [data]
    if not isinstance(data, list):
        raise ValueError('The model did not return a JSON list of messages.')
    out = []
    for item in data:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get('text'), str):
            out.append(item['text'])
    return out


def _prompt(source, count, avoid):
    lines = source.split('\n')
    blank = sum(1 for line in lines if not line.strip())
    avoid_text = ''
    if avoid:
        openings = []
        for item in avoid:
            first = next((line.strip() for line in item.split('\n') if line.strip()), '')
            if first and first not in openings:
                openings.append(first[:180])
        if openings:
            avoid_text = (
                '\nThese versions already exist. Do not reuse their openings or wording:\n'
                + '\n'.join('- ' + opening for opening in openings)
            )
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
- Make every version emotionally gripping and urgent using ONLY the true facts in the
  source (the patient's situation exactly as written, the amount still needed, how few
  people it takes). Start with a scroll-stopping hook: a direct question to the reader, a
  stark small-amount-versus-the-need contrast, or a vivid detail from the source. Use a
  different emotional angle in each version (the family's pain, the small amount, "it
  could be someone you love", gratitude, sharing helps). Do not assume the patient's age,
  gender or relationship: say only what the source says. Urgency means "needed now because
  of the amount left", never an invented deadline.
- Return ONLY a JSON array of {count} strings. No commentary, no markdown fences.

SOURCE:
<<<SOURCE
{source}
SOURCE>>>{avoid_text}
"""


def _call(key, prompt):
    message = assistant._chat_raw(key, SYSTEM, [], [{'role': 'user', 'content': prompt}], max_tokens=8192, thinking_mode=False)
    content = message.get('content') if isinstance(message, dict) else ''
    return _json_list(content)


def generate(source, count=10, avoid=None, *, progress=None, allow_partial=False):
    """Validate every rewrite, report accepted batches, and optionally retain partial results."""
    source = clean_source(source)
    if not dm_composer.complete(source):
        raise ValueError('Paste the complete message with its paragraphs, amount and payment details.')
    count = max(1, min(20, int(count)))
    existing = [str(item).strip() for item in (avoid or []) if isinstance(item, str) and item.strip()]
    out = []
    key = assistant.client()
    if key is None:
        raise ValueError('The AI is not connected, so I cannot reword a custom message. The built-in structured DM still works.')
    last_error = ''
    for _ in range(5):
        need = count - len(out)
        if need <= 0:
            break
        try:
            # Smaller batches avoid model truncation and improve diversity.
            prompt = _prompt(source, min(need, 5), existing + out)
            if last_error:
                prompt += "\nThe previous attempt was rejected because: " + last_error[:240] + ". Correct that while keeping the verified facts."
            candidates = _call(key, prompt)
        except Exception as exc:
            last_error = str(exc)
            if re.search(r'(?i)returned (?:401|402|403|429)|not connected|api key', last_error):
                break
            continue
        before = len(out)
        for candidate in candidates:
            reason = validate(source, candidate, existing + out)
            if reason:
                last_error = reason
                continue
            out.append(candidate.strip())
            if len(out) >= count:
                break
        if progress is not None and len(out) > before:
            if progress(list(out)) is False:
                raise ValueError("Generation stopped because the source changed. Your newer edit is safe.")
    if allow_partial and out:
        return out[:count]
    if len(out) < count:
        detail = (' The last problem was: ' + last_error) if last_error else ''
        raise ValueError(
            f'The AI returned only {len(out)} sufficiently different versions that kept the facts and formatting.{detail} '
            'The saved DM and the message bank were not changed.'
        )
    return out[:count]
