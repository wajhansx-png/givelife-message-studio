"""Generate reworded versions of an owner-supplied WhatsApp DM.

The static canonical templates cover the built-in Yousuf DM. This module is
the general path: the owner pastes any complete message, the model rewrites
only the wording, and deterministic checks reject any version that changes the
line structure, emojis, bold/italic markers, numbers or payment details.
"""
import json, re

import assistant
import dm_composer

VERSION = 'dm-variants-2026-10-30'

# Each version stays about as long as the message the owner gave (a few characters either way).
LENGTH_TOLERANCE = 0.08

SYSTEM = """You are a careful fundraising copy editor for GiveLife Foundation.
You rewrite one WhatsApp direct message into new versions with the same concept,
facts and formatting. Return only the JSON array the user asks for. Never add
commentary, markdown fences, headings or a delivery claim."""


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
    if not set(_numbers(source)).issubset(set(_numbers(text))):
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
    return f"""Rewrite the source message below into exactly {count} new versions.

The source has {len(lines)} lines and {blank} blank lines. Keep that exact line
structure. Keep every blank line in the same place.

NON-NEGOTIABLE:
- Length: every version must be between {low} and {high} characters in total
  (the source has {size}). Count it. Do not make versions shorter or longer.
- Use factual urgency only. Rotate the documented need, current confirmed
  amount and clear ways to help, not invented symptoms or disease progression.
  Never imply a condition is spreading or worsening without verified source facts.
  Never write "will die" or an invented deadline,
  never the word DANGER, and never a begging closing line.
- Keep the same meaning, facts, paragraph order and length of the appeal.
- Change only the wording of the variable sentences. Do not change the concept.
- Keep every emoji and every *, _ and *_ WhatsApp formatting marker in the same
  position. Do not flatten, add or remove formatting.
- Keep every number, amount, phone number, account name, payment method and the
  final reply instruction exactly as written in the source.
- Keep the same greeting form. Do not add a name or a new salutation.
- Do not invent symptoms, hospitals, dates, promises, donations or deadlines.
- Do not use long dashes.
- Every version must be unique and clearly different from the others.
- Return ONLY a JSON array of {count} strings. No commentary, no markdown fences.

SOURCE:
<<<SOURCE
{source}
SOURCE>>>{avoid_text}
"""


def _call(key, prompt):
    message = assistant._chat_raw(key, SYSTEM, [], [{'role': 'user', 'content': prompt}], max_tokens=8192)
    content = message.get('content') if isinstance(message, dict) else ''
    return _json_list(content)


def generate(source, count=10, avoid=None):
    """Return `count` validated reworded versions, or raise ValueError."""
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
    for _ in range(4):
        need = count - len(out)
        if need <= 0:
            break
        try:
            candidates = _call(key, _prompt(source, need, existing + out))
        except Exception as exc:
            last_error = str(exc)
            if re.search(r'(?i)returned (?:401|403)|not connected|api key', last_error):
                break
            continue
        for candidate in candidates:
            reason = validate(source, candidate, existing + out)
            if reason:
                last_error = reason
                continue
            out.append(candidate.strip())
            if len(out) >= count:
                break
    if len(out) < count:
        detail = (' The last problem was: ' + last_error) if last_error else ''
        raise ValueError(
            f'The AI returned only {len(out)} versions that kept the exact structure and facts.{detail} '
            'The saved DM and the message bank were not changed.'
        )
    return out[:count]
