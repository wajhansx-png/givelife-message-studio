"""Canonical GiveLife DM structure with editable wording variants.

Every variant keeps the same WhatsApp formatting and paragraph order:
opening, days/condition, risk, amount, two giving options, personal line,
payment details, reply instruction.
"""

import math, re

VERSION = "dm-structure-2026-10-31-verified-facts"

STRUCTURE = (
    "{greeting}, {opening}\n\n"
    "💔 {days}\n"
    "_{condition}_\n\n"
    "⚠️ *{risk}*\n\n"
    "💰 *_{amount}_*\n\n"
    "*_{option2}_*\n"
    "*_{option1}_*\n\n"
    "_{hook}_ {cta}\n\n"
    "📲 *03097458815*\n"
    "Easypaisa / JazzCash\n"
    "Wajdan Khan (GiveLife Foundation account)\n\n"
    "Reply *Done* after donating."
)

VARIANTS = [
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is 2. Fluid is filling his brain, which will paralyze his body. Both kidneys are badly swollen. He also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} still needed for treatment.",
        "option2": "Just {p2} people donating Rs. 2,000",
        "option1": "OR {p1} people contributing Rs. 1,000 🤲",
        "hook": "If you are reading this, it's you.",
        "cta": "Don't wait for someone else.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is only 2. Fluid is building in his brain and can paralyze his body. Both kidneys are badly swollen, and he also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} is still needed for his treatment.",
        "option2": "Only {p2} people giving Rs. 2,000",
        "option1": "OR {p1} people giving Rs. 1,000 🤲",
        "hook": "If this message reached you, it reached you for a reason.",
        "cta": "Please do not scroll past him.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is 2 years old. Fluid is collecting in his brain and may paralyse his body. His kidneys are both badly swollen. He also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} remains for his treatment.",
        "option2": "Just {p2} donors of Rs. 2,000",
        "option1": "OR {p1} donors of Rs. 1,000 🤲",
        "hook": "If you are still reading, this is your moment.",
        "cta": "Do not wait for someone else to save him.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is just 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} is still needed for his treatment.",
        "option2": "Only {p2} people at Rs. 2,000",
        "option1": "OR {p1} people at Rs. 1,000 🤲",
        "hook": "If you have read this far, it is you.",
        "cta": "Please do not turn away.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is 2. Fluid is filling his brain, which can paralyze his body. Both kidneys are badly swollen, and he has a hernia too.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} is still required for treatment.",
        "option2": "Just {p2} people contributing Rs. 2,000",
        "option1": "OR {p1} people contributing Rs. 1,000 🤲",
        "hook": "If you are reading this, it is not by accident.",
        "cta": "Do not wait for someone else.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is only 2. Fluid is building in his brain and can paralyse his body. Both of his kidneys are badly swollen. He also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} is still needed for his care.",
        "option2": "Only {p2} people donating Rs. 2,000",
        "option1": "OR {p1} people donating Rs. 1,000 🤲",
        "hook": "If you are reading this, it is you.",
        "cta": "Please do not wait for someone else.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is 2 years old. Fluid is filling his brain and may paralyze his body. Both kidneys are badly swollen, and he also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} still stands between him and treatment.",
        "option2": "Just {p2} people giving Rs. 2,000",
        "option1": "OR {p1} people giving Rs. 1,000 🤲",
        "hook": "If this is in front of you, it is your turn.",
        "cta": "Do not wait for someone else.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is just 2. Fluid is filling his brain, which can affect his body. Both kidneys are badly swollen. He also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} is still needed for his treatment.",
        "option2": "Only {p2} people contributing Rs. 2,000",
        "option1": "OR {p1} people contributing Rs. 1,000 🤲",
        "hook": "If you are reading this, it is you.",
        "cta": "Please do not wait for someone else.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is 2. Fluid is collecting in his brain and can paralyze his body. Both kidneys are badly swollen, and he has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} is still needed for treatment.",
        "option2": "Just {p2} people donating Rs. 2,000",
        "option1": "OR {p1} people contributing Rs. 1,000 🤲",
        "hook": "If you are reading this, it is you.",
        "cta": "Do not wait for someone else.",
    },
    {
        "opening": "please read about Yousuf and the support his family requested.",
        "days": "His parents reported that he was admitted to hospital for treatment.",
        "condition": "Yousuf is only 2. Fluid is filling his brain and threatening to paralyze his body. Both kidneys are badly swollen. He also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} is still needed for his treatment.",
        "option2": "Only {p2} people giving Rs. 2,000",
        "option1": "OR {p1} people giving Rs. 1,000 🤲",
        "hook": "If you are reading this, it is you.",
        "cta": "Please do not wait for someone else.",
    },
    {
        "opening": "take one minute to read about Yousuf and what his family has shared.",
        "days": "His parents told us he was admitted to hospital for treatment.",
        "condition": "He is only 2 years old. His parents say fluid is building up in his brain and can paralyze his body. Both of his kidneys are badly swollen, and he has a hernia as well.",
        "risk": "They also told us he was short of breath. Please check verified medical information for any further details.",
        "amount": "Rs. {left} is still needed for his treatment.",
        "option2": "{p2} people giving Rs. 2,000 each",
        "option1": "OR {p1} people giving Rs. 1,000 each 🤲",
        "hook": "A little boy cannot ask for help himself.",
        "cta": "Will you be one of the people who answers for him?",
    },
    {
        "opening": "look at these numbers for Yousuf before you scroll on.",
        "days": "According to his parents, he was admitted to hospital for treatment.",
        "condition": "Yousuf is 2. His family says fluid is filling his brain, which can paralyze his body. Both kidneys are badly swollen. A hernia adds to it.",
        "risk": "His parents also said he was short of breath. Verified medical records are the place for exact details.",
        "amount": "Rs. {left} is what remains for his treatment.",
        "option2": "That is only {p2} people at Rs. 2,000 each",
        "option1": "OR {p1} people at Rs. 1,000 each 🤲",
        "hook": "The number is small when it is split between many hands.",
        "cta": "Be one of those hands today.",
    },
    {
        "opening": "join the people already standing with Yousuf and his family.",
        "days": "His parents have shared that he was admitted to hospital for treatment.",
        "condition": "He is 2. They say fluid is collecting in his brain and may paralyse his body. His kidneys are both badly swollen, and he also has a hernia.",
        "risk": "His parents reported that he was short of breath. Please treat this as their report, not a medical diagnosis.",
        "amount": "Rs. {left} is what we still need, together, for his treatment.",
        "option2": "{p2} more people giving Rs. 2,000",
        "option1": "OR {p1} people giving Rs. 1,000 🤲",
        "hook": "Every person who has given so far has helped this family keep going.",
        "cta": "Please add your name to that list.",
    },
    {
        "opening": "please read this about Yousuf before you put your phone down.",
        "days": "His parents say he was admitted to hospital so he could be treated.",
        "condition": "Yousuf is just 2 years old. As his parents describe it, fluid is filling his brain and can paralyze his body. Both kidneys are badly swollen, and there is a hernia too.",
        "risk": "They reported that he was short of breath. For exact medical details, please rely on verified information.",
        "amount": "Rs. {left} is still required for his treatment.",
        "option2": "{p2} people giving Rs. 2,000 each",
        "option1": "OR {p1} people giving Rs. 1,000 each 🤲",
        "hook": "He does not know this message exists, but his family is hoping it reaches the right people.",
        "cta": "Let it reach you, then act.",
    },
    {
        "opening": "take a moment for Yousuf. His family is asking for help.",
        "days": "His parents let us know he was admitted to hospital for treatment.",
        "condition": "He is 2. His parents say there is fluid in his brain that can paralyze his body. Both of his kidneys are badly swollen. He also has a hernia.",
        "risk": "They added that he was short of breath. Verified medical information should be used for anything more.",
        "amount": "Rs. {left} is still needed for his care.",
        "option2": "{p2} people giving Rs. 2,000 each",
        "option1": "OR {p1} people giving Rs. 1,000 each 🤲",
        "hook": "Most people who see this will simply scroll past.",
        "cta": "Please be the one who doesn't.",
    },
    {
        "opening": "imagine being Yousuf's parent and having to write this message.",
        "days": "They say he was admitted to hospital for treatment.",
        "condition": "Their son is only 2. They report fluid building in his brain, which can paralyze his body. Both kidneys are badly swollen, and he has a hernia.",
        "risk": "They also said he was short of breath. Please rely on verified medical information for further details.",
        "amount": "Rs. {left} is still needed for his treatment.",
        "option2": "{p2} people donating Rs. 2,000 each",
        "option1": "OR {p1} people donating Rs. 1,000 each 🤲",
        "hook": "No parent wants to ask strangers for this.",
        "cta": "They are asking, and you can answer.",
    },
    {
        "opening": "here is what Yousuf's family has told us.",
        "days": "He was admitted to hospital for treatment, his parents reported.",
        "condition": "Yousuf is 2 years old. Fluid is filling his brain, they say, and it can paralyse his body. Both kidneys are badly swollen, and a hernia makes it harder.",
        "risk": "His parents said he was short of breath. This is their account, so please check verified medical details.",
        "amount": "Rs. {left} is still needed for his treatment.",
        "option2": "{p2} people at Rs. 2,000 each",
        "option1": "OR {p1} people at Rs. 1,000 each 🤲",
        "hook": "This is not a complicated ask.",
        "cta": "A small amount from many people is enough, and you can be one of them.",
    },
    {
        "opening": "spend thirty seconds on Yousuf's story before you move on.",
        "days": "His parents reported that he has been admitted to hospital for treatment.",
        "condition": "He is just 2. His family says fluid is building in his brain and can paralyze his body. His kidneys are both badly swollen, and he also carries a hernia.",
        "risk": "They told us he was short of breath. Please take this as their report, not a confirmed clinical record.",
        "amount": "Rs. {left} is left to raise for his treatment.",
        "option2": "{p2} people giving Rs. 2,000 each",
        "option1": "OR {p1} people giving Rs. 1,000 each 🤲",
        "hook": "Thank you to everyone who has already given.",
        "cta": "If you have not yet, please join them.",
    },
    {
        "opening": "Yousuf is a little boy, and his family needs support.",
        "days": "He was admitted to hospital for treatment, according to his parents.",
        "condition": "Yousuf is 2. His parents say fluid is collecting in his brain and may paralyze his body. Both his kidneys are badly swollen, and he also has a hernia.",
        "risk": "His parents reported he was short of breath. Please rely on verified medical details, not this message alone.",
        "amount": "Rs. {left} is still needed for treatment.",
        "option2": "{p2} people donating Rs. 2,000 each",
        "option1": "OR {p1} people donating Rs. 1,000 each 🤲",
        "hook": "You may never meet him, but you can still help him.",
        "cta": "Please do it today.",
    },
    {
        "opening": "here is a short read about Yousuf that matters to his family.",
        "days": "His parents shared that he was admitted to hospital for treatment.",
        "condition": "He is only 2 years old. According to his parents, fluid is filling his brain and can paralyse his body. Both kidneys are badly swollen, and a hernia adds to his condition.",
        "risk": "They reported that he was short of breath. Please confirm any details with verified medical sources.",
        "amount": "Rs. {left} is still needed for his treatment.",
        "option2": "{p2} people giving Rs. 2,000 each",
        "option1": "OR {p1} people giving Rs. 1,000 each 🤲",
        "hook": "If you can't give today, sharing this with someone who can still helps.",
        "cta": "Either way, please don't let it end here.",
    },
]

COUNT = len(VARIANTS)
PRIMARY_COUNT = 10


def build(index, left, greeting="Brother"):
    """Return one complete DM in the canonical structure."""
    left = int(left)
    p2 = math.ceil(left / 2000)
    p1 = math.ceil(left / 1000)
    item = {
        key: value.format(left=f"{left:,}", p2=p2, p1=p1)
        for key, value in VARIANTS[int(index) % COUNT].items()
    }
    return STRUCTURE.format(
        greeting=greeting,
        left=f"{left:,}",
        p2=p2,
        p1=p1,
        **item,
    )


def _shape(text):
    """Line/marker skeleton, ignoring the words and the numbers."""
    lines = str(text or "").replace("\r\n", "\n").strip("\n").split("\n")
    out = []
    for line in lines:
        if not line.strip():
            out.append(("", 0, 0, True))
            continue
        lead = re.match(r"^[^\w\s]*", line).group(0)
        out.append((lead, line.count("*"), line.count("_"), False))
    return out


def matches(text):
    """True when a supplied message has the exact canonical line/format skeleton."""
    text = str(text or "")
    fixed = ("03097458815", "Easypaisa / JazzCash", "Wajdan Khan", "Reply *Done* after donating.")
    if not all(token in text for token in fixed):
        return False
    try:
        return _shape(text) == _shape(build(0, 15000))
    except (TypeError, ValueError):
        return False
