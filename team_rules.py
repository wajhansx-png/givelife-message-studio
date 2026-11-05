"""Team rules from the GiveLife PDFs (Group message prompts + V2 Focus Guide), in one place.

Change a rule here, not in the code that uses it. Pakistan time (PKT, UTC+5) everywhere.
"""

import datetime

PKT = datetime.timezone(datetime.timedelta(hours=5))

# Focus Guide 01: working hours (strict). (start, end) in minutes after midnight; end is not included.
WORK_WINDOWS = ((12 * 60, 15 * 60 + 30), (18 * 60, 22 * 60 + 30))
WORK_HOURS_TEXT = "12:00 PM–3:30 PM and 6:00 PM–10:30 PM"

# Focus Guide 07: donations are slow -> GiveLife every 15 min, freelance every 30 min.
SLOW_AFTER_MINUTES = (
    90  # no money for this long = "donations are slow" (the app's existing L3 level)
)
SLOW_MAIN_GAP = 15
SLOW_FREE_GAP = 30

# Focus Guide 06: always 5 DMs per batch, 7 minutes between each message.
DM_BATCH = 5
DM_GAP_SECONDS = 7 * 60

# Group message prompts.
HOOK_MAX_WORDS = {"normal": 14, "slow": 16}
DETAILS_MAX_WORDS = 30
MAX_EMOJIS = 3
HOOK_ENDINGS = ("\U0001f534", "\U0001f494")  # 🔴 or 💔
BIG_GIFT, SMALL_GIFT = 2000, 1000
LINE3 = (
    "• *_Just {n} kind people donating Rs. 2,000 or {m} people donating Rs. 1,000 "
    "can complete this amount._*"
)
LINE4 = "Please don't think someone else will help."
FOOTER = (
    "03097458815",
    "EASYPAISA ONLY – Wajdan Khan (GiveLife Foundation account)",
    "— GiveLife Foundation",
)
# Slow-donations prompt: the ONLY hadith allowed, copied exactly (with source in brackets).
HADITH = (
    'نبی کریم ﷺ نے فرمایا: "جو شخص کسی مسلمان کی دنیاوی مشکل دور کرے گا، اللہ قیامت کے دن اس کی مشکل دور فرمائے گا۔" (صحیح مسلم 2699)',
    'نبی کریم ﷺ نے فرمایا: "مومن مومن کے لیے عمارت کی طرح ہے، جس کا ایک حصہ دوسرے حصے کو مضبوط کرتا ہے۔" (صحیح بخاری 481)',
    'نبی کریم ﷺ نے فرمایا: "صدقہ گناہوں کو اس طرح بجھا دیتا ہے جیسے پانی آگ کو بجھا دیتا ہے۔" (سنن ترمذی 2616)',
)
# Never offered (prompt NEVER list): any payment method other than Easypaisa.
OTHER_PAYMENT = r"(?i)jazz\s*cash|sada\s*pay|naya\s*pay|\biban\b|bank\s+(?:transfer|account)|\bupaisa\b|\bmeezan\b|\bhbl\b|\bubl\b"


def pkt_now():
    return datetime.datetime.now(PKT)


def in_work_hours(when=None):
    """True inside the strict team working hours (Pakistan time)."""
    when = (when or pkt_now()).astimezone(PKT)
    minute = when.hour * 60 + when.minute
    return any(start <= minute < end for start, end in WORK_WINDOWS)


def gift_counts(left, exact=True):
    """(N, M) for line 3. exact=True is the PDF rule (N×2,000 = X and M×1,000 = X), else None when it cannot split.
    exact=False rounds up, as the app already does for live balances that change after a part-donation."""
    if not isinstance(left, int) or isinstance(left, bool) or left <= 0:
        return None
    if left % BIG_GIFT:
        return None if exact else (-(-left // BIG_GIFT), -(-left // SMALL_GIFT))
    return left // BIG_GIFT, left // SMALL_GIFT
