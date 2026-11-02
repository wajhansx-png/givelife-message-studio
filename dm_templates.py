"""Canonical GiveLife DM structure with editable wording variants.

Every variant keeps the same WhatsApp formatting and paragraph order:
opening, days/condition, risk, amount, two giving options, personal line,
payment details, reply instruction.
"""
import math, re

VERSION = 'dm-structure-2026-10-31-verified-facts'

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
        'opening': 'take one minute to read about Yousuf, a 2-year-old whose family urgently needs help.',
        'days': 'His family brought him to hospital and have been waiting there with him.',
        'condition': 'Doctors say fluid is gathering around his brain and it could paralyze him if it is not treated. Both of his kidneys are badly swollen, and he also has a hernia.',
        'risk': 'His family said he has been struggling to breathe. Please treat this as their report, pending verified medical confirmation.',
        'amount': 'Rs. {left} is the amount still standing between Yousuf and treatment.',
        'option2': '{p2} people giving Rs. 2,000 each would cover it',
        'option1': 'OR {p1} people giving Rs. 1,000 each 🤲',
        'hook': 'A two-year-old cannot ask for help himself.',
        'cta': 'Will you be one of the people who answers for him?',
    },
    {
        'opening': 'look at these numbers for Yousuf, 2 years old, before you scroll on.',
        'days': 'He has been in hospital with his parents at his side.',
        'condition': 'Fluid is building around his brain, and doctors warn it can paralyze him. Both kidneys are badly swollen, and a hernia adds to the strain on his small body.',
        'risk': 'His parents say his breathing has been shallow. Please rely on verified medical records, not this message, for exact details.',
        'amount': 'Only Rs. {left} stands between Yousuf and the treatment he needs.',
        'option2': 'That is just {p2} people at Rs. 2,000 each',
        'option1': 'OR {p1} people at Rs. 1,000 each 🤲',
        'hook': 'The number is small when it is split between many hands.',
        'cta': 'Be one of those hands today.',
    },
    {
        'opening': 'join the people already standing with Yousuf, 2 years old.',
        'days': 'He remains in hospital while his family tries to arrange his treatment.',
        'condition': 'Doctors have found fluid building around his brain, which risks paralysis if it is left untreated. Both his kidneys are badly swollen, and he also has a hernia.',
        'risk': 'His parents report he has had trouble breathing. Please treat this as their account, not a confirmed diagnosis.',
        'amount': 'Together we still need Rs. {left} for his treatment.',
        'option2': '{p2} more people giving Rs. 2,000 would close the gap',
        'option1': 'OR {p1} people giving Rs. 1,000 🤲',
        'hook': 'Every donor so far has been one more reason his family can still hope.',
        'cta': 'Add your name to that list.',
    },
    {
        'opening': 'read this about Yousuf before you put your phone down.',
        'days': 'He is still admitted in hospital, being cared for by the medical staff there.',
        'condition': 'Fluid continues to build around his brain, with a real risk of paralysis if the underlying cause is not treated. Both kidneys are badly swollen, and he has a hernia as well.',
        'risk': 'His parents describe his breathing as laboured. This is their account; please confirm with verified medical sources.',
        'amount': 'Rs. {left} is still needed before his treatment can proceed.',
        'option2': '{p2} people giving Rs. 2,000 each',
        'option1': 'OR {p1} people giving Rs. 1,000 each 🤲',
        'hook': 'He does not know this message exists, but his family is counting on it reaching the right people.',
        'cta': 'Let it reach you, then act.',
    },
    {
        'opening': 'take a moment for Yousuf, a 2-year-old whose family is asking for help.',
        'days': 'He has spent these days in hospital, with his parents by his bedside.',
        'condition': 'Doctors say fluid is collecting around his brain, with the risk of paralysis if it continues. Both kidneys are badly swollen, and a hernia adds further strain.',
        'risk': 'His parents report short, difficult breaths. Treat this as their report, pending verified confirmation.',
        'amount': 'Rs. {left} remains between Yousuf and the care he needs.',
        'option2': '{p2} people giving Rs. 2,000 each would be enough',
        'option1': 'OR {p1} people giving Rs. 1,000 each 🤲',
        'hook': 'Most people who see this message will simply scroll past.',
        'cta': "Be the one who doesn't.",
    },
    {
        'opening': "imagine being Yousuf's parent and reading this instead of writing it.",
        'days': 'They have stayed at the hospital with him since he was admitted.',
        'condition': 'Doctors have told them fluid is building around his brain and could paralyze him. Both his kidneys are badly swollen, and he also has a hernia.',
        'risk': 'They say his breathing has been difficult. This is what they have reported; please rely on verified medical information.',
        'amount': 'Rs. {left} is what still stands between him and treatment.',
        'option2': '{p2} people donating Rs. 2,000 each',
        'option1': 'OR {p1} people donating Rs. 1,000 each 🤲',
        'hook': 'No parent should have to ask strangers for this.',
        'cta': 'But they are asking, and you can answer.',
    },
    {
        'opening': 'here is what is happening with Yousuf, 2 years old.',
        'days': "He is in hospital right now, under his parents' care and the care of the medical staff.",
        'condition': 'Fluid is gathering around his brain and risks paralysing him if it is untreated. Both kidneys are badly swollen, and a hernia makes things harder still.',
        'risk': 'His parents say his breathing has been shallow. Please treat this as an unverified family report.',
        'amount': 'Rs. {left} is still needed for his treatment to go ahead.',
        'option2': '{p2} people at Rs. 2,000 each',
        'option1': 'OR {p1} people at Rs. 1,000 each 🤲',
        'hook': 'This is not a complicated ask.',
        'cta': 'It is a small amount from a lot of people, and you can be one of them.',
    },
    {
        'opening': "spend thirty seconds on Yousuf's message before you move on.",
        'days': 'He has been in hospital, where his family has stayed with him throughout.',
        'condition': 'Doctors report fluid building around his brain, which could paralyze him without treatment. Both kidneys are badly swollen, and he also carries a hernia.',
        'risk': 'His parents describe his breathing as strained. Please take this as their account, not a confirmed clinical record.',
        'amount': 'Rs. {left} is left to raise for his treatment.',
        'option2': '{p2} people giving Rs. 2,000 each would cover it',
        'option1': 'OR {p1} people giving Rs. 1,000 each 🤲',
        'hook': 'Thank you to everyone who has already given.',
        'cta': 'If you have not yet, this is your moment to join them.',
    },
    {
        'opening': 'Yousuf is 2. Please read what his family is dealing with.',
        'days': 'He remains admitted in hospital as his treatment is arranged.',
        'condition': 'Fluid is building around his brain, with real risk of paralysis if it is left untreated. Both his kidneys are badly swollen, and he also has a hernia.',
        'risk': 'His parents report he has been short of breath. Please rely on verified medical details, not this message alone.',
        'amount': 'Rs. {left} is still needed before treatment can begin.',
        'option2': '{p2} people donating Rs. 2,000 each',
        'option1': 'OR {p1} people donating Rs. 1,000 each 🤲',
        'hook': 'Two-year-olds cannot wait the way adults can.',
        'cta': 'Please help him not have to.',
    },
    {
        'opening': "here is a two-minute read about Yousuf that could change his family's week.",
        'days': 'He has stayed in hospital while doctors work out his care.',
        'condition': 'Fluid continues to collect around his brain, risking paralysis if it is not addressed. Both kidneys are badly swollen, and a hernia adds to his condition.',
        'risk': 'His parents say his breathing has been difficult. This is their report; please confirm with verified medical sources before relying on it.',
        'amount': 'Rs. {left} is still needed to move his treatment forward.',
        'option2': '{p2} people giving Rs. 2,000 each',
        'option1': 'OR {p1} people giving Rs. 1,000 each 🤲',
        'hook': "If you can't give today, sharing this with someone who can still helps.",
        'cta': "Either way, please don't let it end here.",
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
