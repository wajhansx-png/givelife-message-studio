"""Canonical GiveLife DM structure with editable wording variants.

Every variant keeps the same WhatsApp formatting and paragraph order:
opening, days/condition, risk, amount, two giving options, personal line,
payment details, reply instruction.
"""
import math, re

VERSION = 'dm-structure-2026-10-29b'

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
        'opening': 'you can close this chat. Yousuf cannot close his pain.',
        'days': 'Days have passed. He is still at home.',
        'condition': 'Yousuf is 2. Fluid is filling his brain, which will paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': "The paralysing has started in his fingers. It is slowly moving to his whole body. It can damage his eyesight & also he's short of breath.",
        'amount': 'Rs. {left} still needed for treatment.',
        'option2': 'Just {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': "If you are reading this, it's you.",
        'cta': "Don't wait for someone else.",
    },
    {
        'opening': 'you can leave this chat. Yousuf cannot leave his pain.',
        'days': 'Another day has passed. He is still waiting at home.',
        'condition': 'Yousuf is only 2. Fluid is building in his brain and can paralyze his body. Both kidneys are badly swollen, and he also has a hernia.',
        'risk': 'The numbness has reached his fingers. It is spreading through his body. It can damage his eyesight, and he is already short of breath.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If this message reached you, it reached you for a reason.',
        'cta': 'Please do not scroll past him.',
    },
    {
        'opening': "you can end this conversation. Yousuf's pain will not end without help.",
        'days': 'The days are passing. He is still at home, waiting.',
        'condition': 'Yousuf is 2 years old. Fluid is collecting in his brain and may paralyse his body. His kidneys are both badly swollen. He also has a hernia.',
        'risk': 'The paralysis has begun in his fingers and is moving through his body. It can harm his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} remains for his treatment.',
        'option2': 'Just {p2} donors of Rs. 2,000',
        'option1': 'OR {p1} donors of Rs. 1,000 🤲',
        'hook': 'If you are still reading, this is your moment.',
        'cta': 'Do not wait for someone else to save him.',
    },
    {
        'opening': 'you can close this message. Yousuf cannot close his pain.',
        'days': 'Time is passing. He is still at home.',
        'condition': 'Yousuf is just 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'The paralysis is spreading from his fingers through his whole body. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people at Rs. 2,000',
        'option1': 'OR {p1} people at Rs. 1,000 🤲',
        'hook': 'If you have read this far, it is you.',
        'cta': 'Please do not turn away.',
    },
    {
        'opening': 'you can put this phone down. Yousuf cannot put his pain down.',
        'days': 'Days are passing. He is still at home.',
        'condition': 'Yousuf is 2. Fluid is filling his brain, which can paralyze his body. Both kidneys are badly swollen, and he has a hernia too.',
        'risk': 'The paralysing has started in his fingers. It is moving through his body. It can damage his eyesight, and he is already short of breath.',
        'amount': 'Rs. {left} is still required for treatment.',
        'option2': 'Just {p2} people contributing Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is not by accident.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'you can stop reading. Yousuf cannot stop needing treatment.',
        'days': 'The days keep passing. He is still at home.',
        'condition': 'Yousuf is only 2. Fluid is building in his brain and can paralyse his body. Both of his kidneys are badly swollen. He also has a hernia.',
        'risk': 'The paralysis has started in his fingers and is slowly spreading. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} is still needed for his care.',
        'option2': 'Only {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people donating Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': "you can close this chat. Yousuf's pain will still be here.",
        'days': 'More days have passed. He is still at home.',
        'condition': 'Yousuf is 2 years old. Fluid is filling his brain and may paralyze his body. Both kidneys are badly swollen, and he also has a hernia.',
        'risk': 'The paralysing has reached his fingers and is moving through his body. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} still stands between him and treatment.',
        'option2': 'Just {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If this is in front of you, it is your turn.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'you can end this chat. Yousuf cannot end his pain.',
        'days': 'The days are passing. He is still at home.',
        'condition': 'Yousuf is just 2. Fluid is filling his brain, which will paralyse his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'The paralysis has begun in his fingers and is spreading through his body. It can damage his eyesight, and he is already short of breath.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people contributing Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': 'you can shut this screen. Yousuf cannot shut out his pain.',
        'days': 'The days have passed. He is still at home, waiting.',
        'condition': 'Yousuf is 2. Fluid is collecting in his brain and can paralyze his body. Both kidneys are badly swollen, and he has a hernia.',
        'risk': 'The paralysing has started in his fingers and is slowly moving through his whole body. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} is still needed for treatment.',
        'option2': 'Just {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'you can walk away from this chat. Yousuf cannot walk away from his pain.',
        'days': 'Another day has passed. He is still at home.',
        'condition': 'Yousuf is only 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'The paralysing has started in his fingers and is moving through his body. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': 'you can look away from this message. Yousuf cannot look away from his pain.',
        'days': 'Days have passed. He is still at home.',
        'condition': 'Yousuf is 2. Fluid is filling his brain, which will paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': "The paralysing has started in his fingers. It is slowly moving to his whole body. It can damage his eyesight & also he's short of breath.",
        'amount': 'Rs. {left} still needed for treatment.',
        'option2': 'Just {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': "If you are reading this, it's you.",
        'cta': "Don't wait for someone else.",
    },
    {
        'opening': "you can end this chat. Yousuf's pain will not end by itself.",
        'days': 'Another day has passed. He is still waiting at home.',
        'condition': 'Yousuf is only 2. Fluid is building in his brain and can paralyze his body. Both kidneys are badly swollen, and he also has a hernia.',
        'risk': 'The numbness has reached his fingers. It is spreading through his body. It can damage his eyesight, and he is already short of breath.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If this message reached you, it reached you for a reason.',
        'cta': 'Please do not scroll past him.',
    },
    {
        'opening': 'you can put your phone down. Yousuf cannot put his pain down.',
        'days': 'The days are passing. He is still at home, waiting.',
        'condition': 'Yousuf is 2 years old. Fluid is collecting in his brain and may paralyse his body. His kidneys are both badly swollen. He also has a hernia.',
        'risk': 'The paralysis has begun in his fingers and is moving through his body. It can harm his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} remains for his treatment.',
        'option2': 'Just {p2} donors of Rs. 2,000',
        'option1': 'OR {p1} donors of Rs. 1,000 🤲',
        'hook': 'If you are still reading, this is your moment.',
        'cta': 'Do not wait for someone else to save him.',
    },
    {
        'opening': 'you can close this window. Yousuf cannot close his pain.',
        'days': 'Time is passing. He is still at home.',
        'condition': 'Yousuf is just 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'The paralysis is spreading from his fingers through his whole body. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people at Rs. 2,000',
        'option1': 'OR {p1} people at Rs. 1,000 🤲',
        'hook': 'If you have read this far, it is you.',
        'cta': 'Please do not turn away.',
    },
    {
        'opening': 'you can leave this conversation. Yousuf cannot leave his pain behind.',
        'days': 'Days are passing. He is still at home.',
        'condition': 'Yousuf is 2. Fluid is filling his brain, which can paralyze his body. Both kidneys are badly swollen, and he has a hernia too.',
        'risk': 'The paralysing has started in his fingers. It is moving through his body. It can damage his eyesight, and he is already short of breath.',
        'amount': 'Rs. {left} is still required for treatment.',
        'option2': 'Just {p2} people contributing Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is not by accident.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'you can stop reading now. Yousuf cannot stop needing help.',
        'days': 'The days keep passing. He is still at home.',
        'condition': 'Yousuf is only 2. Fluid is building in his brain and can paralyse his body. Both of his kidneys are badly swollen. He also has a hernia.',
        'risk': 'The paralysis has started in his fingers and is slowly spreading. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} is still needed for his care.',
        'option2': 'Only {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people donating Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': "you can close this message. Yousuf's pain will still be there.",
        'days': 'More days have passed. He is still at home.',
        'condition': 'Yousuf is 2 years old. Fluid is filling his brain and may paralyze his body. Both kidneys are badly swollen, and he also has a hernia.',
        'risk': 'The paralysing has reached his fingers and is moving through his body. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} still stands between him and treatment.',
        'option2': 'Just {p2} people giving Rs. 2,000',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'If this is in front of you, it is your turn.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'you can scroll past this. Yousuf cannot scroll past his pain.',
        'days': 'The days are passing. He is still at home.',
        'condition': 'Yousuf is just 2. Fluid is filling his brain, which will paralyse his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'The paralysis has begun in his fingers and is spreading through his body. It can damage his eyesight, and he is already short of breath.',
        'amount': 'Rs. {left} is still needed for his treatment.',
        'option2': 'Only {p2} people contributing Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Please do not wait for someone else.',
    },
    {
        'opening': 'you can turn away from this. Yousuf cannot turn away from his pain.',
        'days': 'The days have passed. He is still at home, waiting.',
        'condition': 'Yousuf is 2. Fluid is collecting in his brain and can paralyze his body. Both kidneys are badly swollen, and he has a hernia.',
        'risk': 'The paralysing has started in his fingers and is slowly moving through his whole body. It can damage his eyesight, and he is short of breath.',
        'amount': 'Rs. {left} is still needed for treatment.',
        'option2': 'Just {p2} people donating Rs. 2,000',
        'option1': 'OR {p1} people contributing Rs. 1,000 🤲',
        'hook': 'If you are reading this, it is you.',
        'cta': 'Do not wait for someone else.',
    },
    {
        'opening': 'you can put this conversation aside. Yousuf cannot put his pain aside.',
        'days': 'Another day has passed. He is still at home.',
        'condition': 'Yousuf is only 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.',
        'risk': 'The paralysing has started in his fingers and is moving through his body. It can damage his eyesight, and he is short of breath.',
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
