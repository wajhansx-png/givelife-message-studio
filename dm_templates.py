"""Canonical GiveLife DM structure with editable wording variants.

Every variant keeps the same WhatsApp formatting and paragraph order:
opening, days/condition, risk, amount, two giving options, personal line,
payment details, reply instruction.
"""
import math, re

VERSION = 'dm-structure-2026-10-31-reported-facts'
# The old variants contain unsupported predictions that paralysis would start
# or spread. Preserve their layout but use a single, carefully attributed
# summary. New case details must never be inferred from old AI-generated text.
REPORTED_CONDITION = (
    'Yousuf is 2. His family reported fluid collecting in his brain, swollen '
    'kidneys and a hernia. Please check the latest medical documents for details.'
)

STRUCTURE = (
    '{greeting}, {opening}\n\n'
    '💔 {days}\n'
    '_{condition}_\n\n'
    '⚠️ *{risk}*\n\n'
    '💰 *_{amount}_*\n\n'
    '*_{option2}_*\n'
    '*_{option1}_*\n\n'
    '_{hook}_ {cta}\n\n'
    '📲 *03097458815*\n'
    'Easypaisa / JazzCash\n'
    'Wajdan Khan (GiveLife Foundation account)\n\n'
    'Reply *Done* after donating.'
)

VARIANTS = [
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2. Fluid is filling his brain, which will paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} still needed for treatment.',
        'option2': 'Just {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': "If you are reading this, it's you.",
        'cta': "Don't wait for someone else.",
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is only 2. Fluid is building in his brain and can paralyze his body. Both kidneys are badly swollen, and he also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If this message reached you, it reached you for a reason.',
        'cta': 'Please do not scroll past him.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2 years old. Fluid is collecting in his brain and may paralyse his body. His kidneys are both badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} remains for his treatment.',
        'option2': 'Just {p2} donors of Rs. 2,000',
        'option1': 'OR {p1} donors of Rs. 1,000 🤲',
        'hook': 'If you are still reading, this is your moment.',
        'cta': 'Do not wait for someone else to save him.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is just 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people at Rs. 2,000',
        'option1': 'OR {p1} people at Rs. 1,000 🤲',
        'hook': 'If you have read this far, it is you.',
        'cta': 'Please do not turn away.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2. Fluid is filling his brain, which can paralyze his body. Both kidneys are badly swollen, and he has a hernia too.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still required for treatment.',
        'option2': 'Just {p2} people contributing Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is not by accident.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is only 2. Fluid is building in his brain and can paralyse his body. Both of his kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his care.',
        'option2': 'Only {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people donating Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2 years old. Fluid is filling his brain and may paralyze his body. Both kidneys are badly swollen, and he also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} still stands between him and treatment.',
        'option2': 'Just {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If this is in front of you, it is your turn.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is just 2. Fluid is filling his brain, which can affect his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people contributing Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2. Fluid is collecting in his brain and can paralyze his body. Both kidneys are badly swollen, and he has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for treatment.',
        'option2': 'Just {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is only 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2. Fluid is filling his brain, which will paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} still needed for treatment.',
        'option2': 'Just {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': "If you are reading this, it's you.",
        'cta': "Don't wait for someone else.",
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is only 2. Fluid is building in his brain and can paralyze his body. Both kidneys are badly swollen, and he also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If this message reached you, it reached you for a reason.',
        'cta': 'Please do not scroll past him.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2 years old. Fluid is collecting in his brain and may paralyse his body. His kidneys are both badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} remains for his treatment.',
        'option2': 'Just {p2} donors of Rs. 2,000',
        'option1': 'OR {p1} donors of Rs. 1,000 🤲',
        'hook': 'If you are still reading, this is your moment.',
        'cta': 'Do not wait for someone else to save him.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is just 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people at Rs. 2,000',
        'option1': 'OR {p1} people at Rs. 1,000 🤲',
        'hook': 'If you have read this far, it is you.',
        'cta': 'Please do not turn away.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2. Fluid is filling his brain, which can paralyze his body. Both kidneys are badly swollen, and he has a hernia too.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still required for treatment.',
        'option2': 'Just {p2} people contributing Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is not by accident.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is only 2. Fluid is building in his brain and can paralyse his body. Both of his kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his care.',
        'option2': 'Only {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people donating Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2 years old. Fluid is filling his brain and may paralyze his body. Both kidneys are badly swollen, and he also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} still stands between him and treatment.',
        'option2': 'Just {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If this is in front of you, it is your turn.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is just 2. Fluid is filling his brain, which can affect his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people contributing Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is 2. Fluid is collecting in his brain and can paralyze his body. Both kidneys are badly swollen, and he has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for treatment.',
        'option2': 'Just {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'please read about Yousuf and the support his family requested.',
        'days': 'His parents reported that he was admitted to hospital for treatment.',
        'condition': 'Yousuf is only 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'His parents reported that he was short of breath. Please rely on verified medical information for further details.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
]

COUNT = len(VARIANTS)
PRIMARY_COUNT = 10


def build(index, left, greeting='Brother'):
    """Return one complete DM in the canonical structure."""
    left = int(left)
    p2 = math.ceil(left / 2000)
    p1 = math.ceil(left / 1000)
    item = {key: value.format(left=f'{left:,}', p2=p2, p1=p1) for key, value in VARIANTS[int(index) % COUNT].items()}
    item['condition'] = REPORTED_CONDITION  # never reuse the unsupported medical predictions above
    return STRUCTURE.format(
        greeting=greeting,
        left=f'{left:,}',
        p2=p2,
        p1=p1,
        **item,
    )


def _shape(text):
    """Line/marker skeleton, ignoring the words and the numbers."""
    lines = str(text or '').replace('\r\n', '\n').strip('\n').split('\n')
    out = []
    for line in lines:
        if not line.strip():
            out.append(('', 0, 0, True))
            continue
        lead = re.match(r'^[^\w\s]*', line).group(0)
        out.append((lead, line.count('*'), line.count('_'), False))
    return out


def matches(text):
    """True when a supplied message has the exact canonical line/format skeleton."""
    text = str(text or '')
    fixed = ('03097458815', 'Easypaisa / JazzCash', 'Wajdan Khan', 'Reply *Done* after donating.')
    if not all(token in text for token in fixed):
        return False
    try:
        return _shape(text) == _shape(build(0, 15000))
    except (TypeError, ValueError):
        return False
