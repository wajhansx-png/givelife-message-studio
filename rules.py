"""Auto-mode rules: turn the owner's typed instructions into rules the engine follows, with no AI needed.

A rule is a plain dict:
  {'kind': 'gap',      'group': 'fiverr|main|free|all', 'minutes': 30}
  {'kind': 'quiet',    'group': 'all|<key>', 'start': 2, 'end': 7}
  {'kind': 'pause',    'group': '<key>|all', 'until': <epoch>}
  {'kind': 'cap',      'group': '<key>|all', 'per_day': 10}
  {'kind': 'schedule', 'target': '<group key>|<phone>', 'at': 'HH:MM', 'text': '' (empty = the current appeal),
                       'daily': True|False, 'next': <epoch>}
  {'kind': 'note',     'text': '...'}   # free-text standing instruction (read by the AI when it is connected)
"""
import re, time, datetime

PKT = datetime.timezone(datetime.timedelta(hours=5))
GROUPS = {
    'main': ['main', 'givelife', 'give life', 'foundation'],
    'community': ['upwork community', 'community'],
    'fiverr': ['fiverr course', 'fiverr'],
    'upwork': ['upwork course', 'upwork'],
    'uet': ['fiverr uet', 'uet'],
    'toprated': ['top rated', 'toprated'],
    'free': ['all freelance', 'freelance', 'all 5'],
    'all': ['all groups', 'every group', 'all'],
}
STANDING = re.compile(r"\b(always|never|from now|every day|daily|each day|only|don'?t|dont|do not|avoid|no more|at night|per day|a day)\b", re.I)


def find_group(text):
    low = text.lower()
    best = None
    for key, names in GROUPS.items():
        for n in names:
            m = re.search(r'\b' + re.escape(n) + r'\b', low)
            if m and (best is None or len(n) > best[1]):
                best = (key, len(n))
    return best[0] if best else None

def pace_rules(text):
    """Explicit speed instructions can set several groups without resetting the others."""
    low=text.casefold()
    if re.search(r'\b(?:dm|dms|donors?|now|immediately|asap)\b',low):return []
    if not re.search(r'\b(send|post|posting|sending|pace|speed)\b',low) or not re.search(r'\b(fast|faster|slow|slower)\b',low):return []
    out=[]
    for clause in re.split(r'\s+(?:and|but)\s+|[,;]',low):
        speed=re.search(r'\b(fast|faster|slow|slower)\b',clause)
        if not speed:continue
        group=find_group(clause)
        if not group:return []
        out.append({'kind':'gap','group':group,'minutes':15 if speed[1].startswith('fast') else 60})
    return out


def _hour(h, ampm):
    h = int(h)
    ampm = (ampm or '').lower()
    if ampm == 'pm' and h < 12:
        h += 12
    if ampm == 'am' and h == 12:
        h = 0
    return h % 24


def _time(text):
    """First clock time in the text -> 'HH:MM' (PKT)."""
    m = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text, re.I) or re.search(r'\b(?:at|@)\s*(\d{1,2})(?::(\d{2}))?\b(?!\s*(?:min|hour))', text, re.I)
    if not m:
        return None
    ampm = m.group(3) if m.lastindex and m.lastindex >= 3 else None
    return f'{_hour(m.group(1), ampm):02d}:{int(m.group(2) or 0):02d}'


def next_epoch(hhmm, now=None):
    now = now or time.time()
    d = datetime.datetime.fromtimestamp(now, PKT)
    h, mi = map(int, hhmm.split(':'))
    t = d.replace(hour=h, minute=mi, second=0, microsecond=0)
    if t.timestamp() <= now:
        t += datetime.timedelta(days=1)
    return t.timestamp()


def parse(text, now=None):
    """Returns (rule or None, human summary). Offline and deterministic."""
    now = now or time.time()
    t = text.strip()
    low = t.lower()
    group = find_group(low)

    # scheduled send: "send ... to X at 9pm", "post in main at 8am daily"
    when = _time(low)
    if when and re.search(r'\b(send|post|share|message|msg|bhejo|daalo)\b', low) and not re.search(r'\bevery\s+\d+\s*(min|hour|h)\b', low):
        phone = re.search(r'(?:\+?92|0092|0)?[\s-]?3\d{2}[\s-]?\d{7}', t)
        target = group or (re.sub(r'[\s()+-]', '', phone.group(0)) if phone else None)
        if target:
            body = ''
            q = re.search(r'["“\'](.+?)["”\']', t)
            if q:
                body = q.group(1)
            daily = bool(re.search(r'\b(daily|every day|each day|roz|everyday)\b', low))
            r = {'kind': 'schedule', 'target': target, 'at': when, 'text': body, 'daily': daily, 'next': next_epoch(when, now)}
            return r, f'{"Every day" if daily else "Once"} at {when}: send {"your text" if body else "the current appeal"} to {target}.'

    # every N minutes / hours
    m = re.search(r'\b(?:every|each|after)\s+(\d+(?:\.\d+)?)\s*(min(?:ute)?s?|mints?|mnts?|h(?:ours?)?)\b', low)
    if m and not group:return None, 'Name the group for this posting interval.'
    if m and group:
        mins = float(m.group(1)) * (60 if m.group(2).startswith('h') else 1)
        mins = max(15, int(mins))
        g = group
        return {'kind': 'gap', 'group': g, 'minutes': mins}, f'Post in {g} every {mins} minutes (15 is the automatic-posting minimum; manual sends override it).'

    # quiet hours: "no posting 2am to 7am", "quiet 2 to 7", "don't post at night"
    m = re.search(r'\b(?:between\s+)?(\d{1,2})\s*(am|pm)?\s*(?:to|-|till|until|se)\s*(\d{1,2})\s*(am|pm)?\b', low)
    if m and re.search(r'\b(no|not|dont|don\'t|do not|stop|quiet|silent|avoid|nahi)\b', low) and re.search(r'\b(post|posting|send|sending|dm|dms|message|quiet)\b', low):
        a, b = _hour(m.group(1), m.group(2)), _hour(m.group(3), m.group(4))
        return {'kind': 'quiet', 'group': group or 'all', 'start': a, 'end': b}, f'No sending in {group or "any group"} from {a:02d}:00 to {b:02d}:00.'
    if re.search(r'\b(night|raat)\b', low) and re.search(r'\b(no|not|dont|don\'t|do not|stop|avoid|nahi)\b', low) and re.search(r'\b(post|posting|send|sending|dm|dms|message)\b', low):
        return {'kind': 'quiet', 'group': group or 'all', 'start': 0, 'end': 7}, f'No sending in {group or "any group"} at night (00:00 to 07:00).'

    # pause: "pause fiverr for 2 hours", "stop uet today", "stop posting in fiverr"
    if re.search(r'\b(pause|stop|hold|skip|band)\b', low) and group and not re.search(r'\bdms?\b', low):
        m = re.search(r'\bfor\s+(\d+(?:\.\d+)?)\s*(h(?:ours?)?|d(?:ays?)?|min(?:ute)?s?)\b', low)
        if m:
            v = float(m.group(1))
            secs = v * (86400 if m.group(2).startswith('d') else 3600 if m.group(2).startswith('h') else 60)
            label = f'{m.group(1)} {m.group(2)}'
        elif re.search(r'\b(week)\b', low):
            secs, label = 7 * 86400, 'a week'
        elif re.search(r'\b(today|aaj)\b', low):
            d = datetime.datetime.fromtimestamp(now, PKT)
            secs, label = (d.replace(hour=23, minute=59, second=59) - d).total_seconds(), 'today'
        else:
            secs, label = 24 * 3600, '24 hours'
        return {'kind': 'pause', 'group': group, 'until': now + secs}, f'Paused {group} for {label}.'

    # daily cap: "max 10 posts a day in main"
    m = re.search(r'\b(?:max(?:imum)?|only|at most|up to|limit)\s+(\d+)\s*(?:posts?|messages?)?\s*(?:per day|a day|daily|each day)\b', low)
    if m:
        return {'kind': 'cap', 'group': group or 'all', 'per_day': int(m.group(1))}, f'At most {m.group(1)} posts a day in {group or "each group"}.'

    # anything else that sounds like a standing instruction is kept as a note
    if re.search(r'\b(always|never|remember|from now|in future|every day|daily|per day|each day)\b',low) and len(t) >= 8 and '?' not in t:
        return {'kind': 'note', 'text': t[:300]}, f'Saved as a standing rule: "{t[:120]}".'
    return None, ''


def describe(r):
    k = r.get('kind')
    if k == 'gap':
        return f'Post in {r["group"]} every {r["minutes"]} min'
    if k == 'quiet':
        return f'Quiet {r["group"]} {r["start"]:02d}:00 to {r["end"]:02d}:00'
    if k == 'pause':
        left = max(0, (r['until'] - time.time()) / 3600)
        return f'Paused {r["group"]} ({left:.1f} h left)'
    if k == 'cap':
        return f'Max {r["per_day"]} posts a day in {r["group"]}'
    if k == 'schedule':
        return f'{"Daily" if r.get("daily") else "Once"} at {r["at"]}: {"text" if r.get("text") else "appeal"} to {r["target"]}'
    return r.get('text', '')[:80]


def in_quiet(start, end, hour):
    return start <= hour < end if start < end else (hour >= start or hour < end)

