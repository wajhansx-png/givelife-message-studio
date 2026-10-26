"""Preserve the owner's full DM; recipient labels are not personal names."""
import re

LABEL = re.compile(r'(?i)\b(jr|junior|sr|senior|accounts?|accts?|admin|team|group|member|donors?|business|company|shop|store|services?|official|office|unknown|unnamed|name|contact|number|test|user|brother|sister|friend|wife|wifey|boss|customer|client|support|sales|marketing|web|developer|designer|agency|digital|seo|upwork|fiverr|foundation|givelife)\b')
GREETING = re.compile(r'^(?P<mark>\*?_?)(?:(?:[A-Za-z][A-Za-z .\'-]{0,45})\s+)?(?:Brother|Sister)\b(?P<close>[_*]?)(?:[,.:!]?)[ \t\r\n]*', re.I)

def first_name(value):
    value = str(value or '').strip()
    if not value or LABEL.search(value) or re.search(r'\d|@|https?://|[_/\\]|acc+ount', value, re.I):
        return ''
    value = re.sub(r'[^A-Za-z\s\'-]', '', value).strip()
    parts = value.split()
    if not parts or len(parts) > 4 or any(len(p) < 2 for p in parts):
        return ''
    first = parts[0]
    if not re.fullmatch(r"[A-Za-z][A-Za-z'-]{1,19}", first) or not re.search('[aeiouy]', first, re.I):
        return ''
    return first.title()

def greeting(name, gender='Brother'):
    name = first_name(name)
    return (name + ' ' if name else '') + ('Sister' if name and gender == 'Sister' else 'Brother')

def personalize(text, name='', gender='Brother'):
    text = str(text).replace('\r\n', '\n').strip()
    match = GREETING.match(text)
    prefix = greeting(name, gender) + ', '
    if match:
        # Keep formatting that wraps the opening paragraph, and all following text.
        prefix = match['mark'] + greeting(name, gender) + match['close'] + ', '
        return prefix + text[match.end():]
    return prefix + text

def complete(text):
    """A fundraising caption cannot consist of a salutation or a collapsed summary."""
    text = str(text)
    return (len(text.strip()) >= 180 and len(re.split(r'\n\s*\n', text.strip())) >= 4
            and bool(re.search(r'Yous[au]f', text, re.I))
            and '03097458815' in text and bool(re.search(r'\b(?:left|needed|remaining|remain)\b', text, re.I)))
