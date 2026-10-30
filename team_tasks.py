"""Team tasks over WhatsApp. The owner writes today's tasks and a deadline; the app splits them into timed tasks (after a preview the
owner confirms) and then talks to the teammate on WhatsApp like the owner would: short, casual, no task numbers, no robot phrases.
It asks once, nudges once, checks before the deadline, notices lateness, reads his replies, and shows the owner one tiny screen.

Rules that keep it honest:
- All times are Pakistan time (UTC+5). Nothing goes out 11 pm to 7 am, while paused, or while sending is on hold.
- Nothing is sent until the owner confirms the plan.
- A message is reserved before it is sent, so a crash can never send the same message twice. A send that fails is retried
  (asks only), then the owner is told.
- "Done" from the teammate is only a report. "Not done", "almost done", "will be done by 5" are NOT reports.
- Network calls never run while the lock is held, so the owner's screen never waits on WhatsApp."""
import copy, datetime, hashlib, os, re, threading, time, uuid
from donor_book import normalize_phone

PKT = datetime.timezone(datetime.timedelta(hours=5))
OPEN = ('Waiting', 'Asked', 'Late', 'Reported')
LEFT = ('Waiting', 'Asked', 'Late')
DONE_CORE = r"(?:done|finished|completed?|posted|sent|submitted|uploaded|shared|ready|ho\s*gaya|ho\s*gya|hogaya|ho\s*gai|kar\s*diya|kar\s*di|kardiya|kr\s*diya)"
DONE_WORDS = re.compile(r"(?i)\b" + DONE_CORE + r"\b")
NOT_DONE = re.compile(r"(?i)(?:\b(?:not|isn'?t|wasn'?t|haven'?t|hasn'?t|didn'?t|never|nahi|nhi|nai|na)\s+(?:[\w']+\s+){0,2}" + DONE_CORE + r"\b"
                      r"|\b" + DONE_CORE + r"\s+(?:nahi|nhi|nai)\b|\bnot\s+yet\b|\b(?:almost|nearly|half|partly|partially|about to be)\s+" + DONE_CORE + r"\b"
                      r"|(?<![\d])(?:[1-9]?\d)\s*(?:%|percent|pct)\s*(?:[\w']+\s+)?" + DONE_CORE + r"\b"
                      r"|\b(?:will|shall|gonna|going to|i'?ll|it'?ll)\s+(?:be\s+)?(?:[\w']+\s+){0,2}" + DONE_CORE + r"\b"
                      r"|\b(?:once|when|after|before|until|till|if|as soon as)\s+(?:[\w']+\s+){0,3}" + DONE_CORE + r"\b"
                      r"|\b" + DONE_CORE + r"\s+(?:by|within|before|after|tomorrow|tonight|later|soon)\b|\b" + DONE_CORE + r"\s+(?:in|at)\s+\d|\b" + DONE_CORE + r"\s*\?)")
BLOCK_WORDS = re.compile(r"(?i)\b(?:stuck|problem|issue|cannot|can'?t|cant|unable|need help|help me|not possible|nahi ho|nahi hua|error|blocked|not working|doesn'?t work|login)\b")
URL = re.compile(r"(?i)https?://\S+|\bwww\.\S+")
ALL_WORDS = re.compile(r"(?i)\b(?:all|everything|both|sab|sub|saare|sare)\b")
STOP = {'done', 'fini', 'comp', 'with', 'that', 'this', 'have', 'been', 'will', 'from', 'task', 'what', 'your', 'they', 'them', 'then', 'just', 'also', 'here', 'there', 'okay', 'sure', 'thanks', 'thank', 'sent', 'shar', 'subm', 'uplo', 'read', 'when', 'about', 'abou', 'later', 'soon', 'bhai', 'sir', 'brot', 'much', 'many', 'some', 'more', 'only', 'it', 'was', 'were'}
MIN_SLOT = 60
CLOCK = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2})"
DEADLINE = re.compile(r"(?i)\b(?:(?:deadline|due|latest|all by|everything by|finish(?:ed)? by|complete(?:d)? by)\s*(?:is\s*)?(?:(tomorrow|tmrw|kal)\s+)?(?:at\s+)?(" + CLOCK + r"|\d{1,2}(?!\d|\s*(?:hours?|hrs?|h\b|minutes?|mins?|m\b)))(?![\d:])|(?:(?:deadline|due)\s*(?:is\s*)?(?:in\s+)?|in\s+|within\s+)(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\b)")


def fmt_time(ts, now=None):
    d = datetime.datetime.fromtimestamp(ts, PKT)
    out = d.strftime('%I:%M %p').lstrip('0')
    if now is not None and d.date() != datetime.datetime.fromtimestamp(now, PKT).date():
        out = d.strftime('%d %b ') + out
    return out


def _clock(text, base, tomorrow=False):
    """A clock time like '6pm', '6:30 pm', '18:00' or bare '6' on the day of `base` (PKT). Bare numbers 1-11 mean the next such hour."""
    t = text.strip().lower().replace('.', '')
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if not m:
        raise ValueError(f'I could not read the time "{text}". Use a time like 6pm or 18:30.')
    hour, minute, mer = int(m[1]), int(m[2] or 0), m[3]
    if minute > 59 or hour > 23 or (mer and not 1 <= hour <= 12):
        raise ValueError(f'"{text}" is not a valid time.')
    if mer == 'pm' and hour != 12:
        hour += 12
    if mer == 'am' and hour == 12:
        hour = 0
    local = datetime.datetime.fromtimestamp(base, PKT)
    when = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if tomorrow:
        when += datetime.timedelta(days=1)
    elif not mer and not m[2] and hour <= 11 and when.timestamp() <= base:
        # "by 6" said at 4 pm means 6 pm
        when = when.replace(hour=hour + 12) if hour + 12 < 24 else when
    return when.timestamp()


def parse_deadline(text, now):
    """(deadline_epoch or None, text without the deadline phrase)."""
    m = DEADLINE.search(text)
    if not m:
        return None, text
    if m[3]:
        n = float(m[3]);unit = m[4].lower()
        secs = n * (3600 if unit.startswith('h') else 60)
        if secs <= 0:
            raise ValueError('The deadline must be in the future.')
        due = now + secs
    else:
        due = _clock(m[2], now, bool(m[1]))
    cleaned = (text[:m.start()] + ' ' + text[m.end():]).strip(' ,;:-\n')
    return due, cleaned


def split_items(text):
    """One task per line, per number (1) 2.), per bullet or per semicolon."""
    text = text.replace('\r', '\n')
    parts = re.split(r"\n+|;|(?:(?<=\s)|^)\(?\d{1,2}[.)]\s+|(?:(?<=\s)|^)[-•*▪]\s+|\s+(?:and also|also|then|after that|plus|aur phir|phir)\s+", text)
    out = []
    for p in parts:
        p = re.sub(r"^\s*(?:\d{1,2}[.)]\s*)", '', (p or '').strip(' ,-•*▪\t'))
        if p and p not in out:
            out.append(p)
    return out


def in_quiet(hour, quiet):
    """Quiet hours are only what the owner sets in Settings (for example 23 to 7). Off by default."""
    if not quiet:
        return False
    a, b = quiet
    return (hour >= a or hour < b) if a > b else (a <= hour < b)


def plan_tasks(text, now, quiet=None):   # quiet=None: no restriction on the hour
    """Turn the owner's text into timed tasks. Raises ValueError with a clear reason. Nothing is saved or sent."""
    text = str(text or '').strip()
    if not text:
        raise ValueError('Write today\'s tasks first, one per line, and a deadline like "deadline 6pm".')
    overall, body = parse_deadline(text, now)
    items = []
    for raw in split_items(body):
        own, clean = None, raw
        m = re.search(r"(?i)\s*(?:\(|\b)(?:by|at|before|till|until|tak)\s+(" + CLOCK + r")\)?[\s.!]*$", raw)
        if m:
            own = _clock(m[1], now);clean = raw[:m.start()].strip(' ,-')
        clean = clean.strip()
        if clean and clean.casefold().strip(' .') not in ('more', 'etc', 'others', 'other things', 'and more', 'some more', 'baqi', 'aur'):
            items.append({'text': clean[:300], 'own_due': own})
    if not items:
        raise ValueError('I found no tasks in that text.')
    if len(items) > 20:
        raise ValueError('Give at most 20 tasks at a time.')
    untimed = [i for i in items if i['own_due'] is None]
    if untimed and overall is None:
        raise ValueError('Give a deadline for the tasks, for example "deadline 6pm" or "in 3 hours".')
    if overall is not None and overall <= now + MIN_SLOT:
        raise ValueError('That deadline is too soon or already passed. Give a time at least 10 minutes from now.')
    for i in items:
        if i['own_due'] is not None and i['own_due'] <= now + MIN_SLOT:
            raise ValueError(f'"{i["text"][:40]}" has a time that is too soon or already passed.')
    out = []
    if untimed:
        slot = (overall - now) / len(untimed)
        if slot < MIN_SLOT:
            need = int(len(untimed) * MIN_SLOT / 60)
            raise ValueError(f'Not enough time: {len(untimed)} tasks need at least {need} minutes. Give a later deadline or fewer tasks.')
        k = 0
    for i in items:
        if i['own_due'] is not None:
            start = max(now, i['own_due'] - 3 * 3600);due = i['own_due']
        else:
            start = now + k * slot;due = start + slot;k += 1
        out.append({'text': i['text'], 'start_at': start, 'due_at': due})
    # nothing is sent at night: a task that would start in quiet hours starts when they end, and must still leave time to do it
    for t in (out if quiet else []):
        h = datetime.datetime.fromtimestamp(t['start_at'], PKT)
        if in_quiet(h.hour, quiet):
            morning = h.replace(hour=quiet[1], minute=5, second=0, microsecond=0)
            if morning <= h:
                morning += datetime.timedelta(days=1)
            t['start_at'] = morning.timestamp()
            if t['due_at'] < t['start_at'] + MIN_SLOT:
                raise ValueError(f'"{t["text"][:40]}" would start inside your quiet hours ({quiet[0]}:00 to {quiet[1]}:00, set in Settings), but its deadline comes before they end. Give it a later deadline or change the quiet hours.')
    return out


def words(text):
    """Four-letter word stems, so 'posted' and 'post' or 'groups' and 'group' match when he names a task in his own words."""
    return {w[:4] for w in re.findall(r"[a-z]{4,}", str(text).lower())} - STOP


def short(text, limit=48):
    text = re.sub(r"\s+", ' ', str(text)).strip(' .,:;-')
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0]
    return (cut or text[:limit]).strip(' .,:;-')


def said_done(text):
    """True only for a real "it is finished". 'not done', 'almost done', 'will be done by 5', 'done?' are not."""
    return bool(DONE_WORDS.search(text)) and not NOT_DONE.search(text)


def pick(options, seed):
    return options[int(hashlib.md5(str(seed).encode()).hexdigest(), 16) % len(options)]


class TeamTasks:
    KEY = 'team'
    RETRY_AFTER = 300
    JITTER = (5, 45)   # seconds after the start time before the first message goes out, so it does not arrive on the dot

    def __init__(self, app, clock=time.time):
        self.app = app;self.now = clock;self.lock = threading.RLock();self.tick_lock = threading.Lock();self._cache = None

    # ---- storage
    def _load(self):
        if self._cache is None:
            raw = self.app.STORE.get(self.KEY) if self.app.STORE else None
            if raw is None and (self.app.DATA / 'team.json').exists():
                import json
                raw = json.loads((self.app.DATA / 'team.json').read_text(encoding='utf-8'))
            if not isinstance(raw, dict):
                raw = {}
            for k, v in (('member', None), ('tasks', []), ('feed', []), ('plan', None), ('seen', []), ('counter', 0), ('paused', False), ('unread', 0),
                         ('last_sent', 0), ('pending_notes', []), ('last_note', 0), ('outbox', []), ('greeted', ''), ('last_clarify', 0), ('quiet', None)):
                raw.setdefault(k, v)
            self._cache = raw
        return self._cache

    def _save(self):
        import json
        d = self._cache
        d['feed'] = d['feed'][-300:];d['seen'] = d['seen'][-500:]
        if self.app.STORE:
            self.app.STORE.put(self.KEY, d)
        try:
            (self.app.DATA / 'team.json').write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        except OSError:
            pass

    def _event(self, kind, text, task=None, notify=False, **extra):
        d = self._load()
        ev = {'id': uuid.uuid4().hex[:10], 'at': self.now(), 'kind': kind, 'text': text[:600], 'task': task['no'] if task else None, **extra}
        d['feed'].append(ev)
        if kind in ('update', 'report', 'blocked', 'proof', 'late'):
            d['unread'] += 1
        if notify:
            d['pending_notes'].append({'text': text[:300], 'at': ev['at']})
        return ev

    def _first(self):
        return self._load()['member']['name'].split()[0]

    # ---- views
    def _public_task(self, t, now):
        return {k: t.get(k) for k in ('id', 'no', 'text', 'start_at', 'due_at', 'status', 'report_text', 'proof', 'reported_at', 'verified_at', 'asked_at')} | {'due_label': fmt_time(t['due_at'], now), 'start_label': fmt_time(t['start_at'], now)}

    def view(self):
        with self.lock:
            d = self._load();now = self.now()
            plan = None
            if d['plan'] and d['plan']['created'] > now - 900:
                plan = {'items': [{**i, 'due_label': fmt_time(i['due_at'], now), 'start_label': fmt_time(i['start_at'], now)} for i in d['plan']['items']]}
            return {'member': {'name': d['member']['name']} if d['member'] else None, 'tasks': [self._public_task(t, now) for t in d['tasks'] if t['status'] != 'Cancelled'],
                    'unread': d['unread'], 'plan': plan, 'paused': d['paused'], 'quiet': d['quiet'], 'now_label': fmt_time(now),
                    'counts': {s: sum(1 for t in d['tasks'] if t['status'] == s) for s in ('Waiting', 'Asked', 'Reported', 'Late', 'Done')},
                    'latest': [{'label': fmt_time(e['at'], now), 'text': e['text']} for e in d['feed'] if e['kind'] in ('update', 'report', 'blocked', 'proof')][-3:][::-1]}

    # ---- owner actions
    def set_member(self, name, phone):
        name = str(name or '').strip()
        if not 1 <= len(name) <= 60:
            raise ValueError('Write the teammate\'s name.')
        phone = normalize_phone(phone)
        if phone == normalize_phone(self.app.OWNER_PHONE):
            raise ValueError('That is your own number.')
        with self.lock:
            d = self._load();d['member'] = {'name': name, 'phone': phone, 'since': self.now()};self._save()
            return self.view()

    def plan(self, text):
        with self.lock:
            d = self._load()
            if not d['member']:
                raise ValueError('Add your teammate first (name and WhatsApp number).')
            items = plan_tasks(text, self.now(), d['quiet'])
            d['plan'] = {'created': self.now(), 'items': items};self._save()
            return self.view()

    def discard_plan(self):
        with self.lock:
            self._load()['plan'] = None;self._save();return self.view()

    def confirm_plan(self):
        with self.lock:
            d = self._load();now = self.now()
            if not d['plan'] or d['plan']['created'] < now - 900:
                d['plan'] = None;self._save()
                raise ValueError('There is no task plan waiting. Write the tasks again.')
            if not d['member']:
                raise ValueError('Add your teammate first.')
            if not any(t['status'] in OPEN for t in d['tasks']):
                d['counter'] = 0
            made = []
            for i in d['plan']['items']:
                if i['due_at'] <= now:
                    raise ValueError('The deadline passed while the plan was waiting. Plan it again.')
                d['counter'] += 1
                tid = uuid.uuid4().hex
                made.append({'id': tid, 'no': d['counter'], 'text': i['text'], 'start_at': i['start_at'], 'due_at': i['due_at'], 'status': 'Waiting', 'created_at': now, 'attempts': 0,
                             'next_try': 0, 'asked_at': None, 'reminded': False, 'checked': False, 'final_sent': False, 'acked': False, 'proof': False, 'proof_asked': False,
                             'blocked_replied': False, 'report_text': '', 'reported_at': None, 'verified_at': None, 'jit': self.JITTER[0] + int(tid[:6], 16) % (self.JITTER[1] - self.JITTER[0] + 1)})
            d['tasks'].extend(made);d['plan'] = None
            self._event('plan', f'{len(made)} task{"s" if len(made) != 1 else ""} started for {d["member"]["name"]}.')
            self._save()
            return {**self.view(), 'reply': f'{len(made)} task{"s" if len(made) != 1 else ""} started. The first message goes out at {fmt_time(min(t["start_at"] for t in made), now)}.'}

    def _find(self, ident):
        d = self._load()
        for t in reversed(d['tasks']):
            if t['id'] == ident or (str(t['no']) == str(ident) and t['status'] in OPEN):
                return t
        raise ValueError('That task was not found, or it is already finished.')

    def match_task(self, ref):
        """A task the owner names by number or by a word from it. Only open tasks; never guesses between several."""
        with self.lock:
            open_ = [t for t in self._load()['tasks'] if t['status'] in OPEN]
            ref = str(ref or '').strip()
            if re.fullmatch(r'#?\d{1,2}', ref):
                hit = [t for t in open_ if str(t['no']) == ref.lstrip('#')]
            else:
                w = words(ref);scored = [(len(w & words(t['text'])), t) for t in open_];best = max((s for s, _ in scored), default=0)
                hit = [t for s, t in scored if s == best and best > 0]
            if len(hit) != 1:
                raise ValueError('Name the task more clearly (its number or a word from it).' if hit else 'No open task matches that.')
            return hit[0]['id']

    def verify(self, ident):
        with self.lock:
            t = self._find(ident);now = self.now();name = self._first()
            if t['status'] not in ('Reported', 'Late', 'Asked', 'Waiting'):
                raise ValueError('This task is not waiting for you.')
            was = t['status'];t['status'] = 'Done';t['verified_at'] = now
            if was == 'Reported':
                self._queue(pick((f'Looks good, thanks {name}. ({short(t["text"])})', f'Perfect, thanks {name}. ({short(t["text"])})', f'Great, that is fine. Thanks. ({short(t["text"])})'), t['id']), t, 'verified')
            self._event('verified', f'You verified: {t["text"]}', t);self._save();return self.view()

    def reject(self, ident, note=''):
        with self.lock:
            t = self._find(ident);now = self.now();name = self._first()
            if t['status'] != 'Reported':
                raise ValueError('Only a reported task can be sent back.')
            t.update(status='Asked', reminded=False, checked=False, final_sent=False, acked=False, report_text='', reported_at=None, proof_asked=False, proof=False, asked_at=now)
            moved = t['due_at'] < now + 1800
            if moved:
                t['due_at'] = now + 1800
            note = str(note).strip()[:200]
            body = pick((f'{name}, can you look at this again? {short(t["text"])}.', f'{name}, this still is not right: {short(t["text"])}.'), t['id'])
            self._queue(body + (' ' + note if note else '') + (f' Can you finish by {fmt_time(t["due_at"], now)}?' if moved else ''), t, 'rejected')
            self._event('rejected', f'You sent back: {t["text"]}', t);self._save();return self.view()

    def cancel(self, ident):
        with self.lock:
            t = self._find(ident);name = self._first()
            if t['status'] in ('Asked', 'Late'):
                self._queue(pick((f'{name}, leave this for now, no need anymore: {short(t["text"])}.', f'Forget this one, I do not need it anymore: {short(t["text"])}.'), t['id']), t, 'cancel')
            t['status'] = 'Cancelled';self._event('cancel', f'Cancelled: {t["text"]}', t);self._save();return self.view()

    def pause(self, on):
        with self.lock:
            self._load()['paused'] = bool(on);self._save();return self.view()

    def set_quiet(self, start=None, end=None):
        """Optional. start/end are hours 0-23 in Pakistan time; None switches quiet hours off."""
        with self.lock:
            if start is None or end is None or start == '' or end == '':
                self._load()['quiet'] = None
            else:
                a, b = int(start), int(end)
                if not (0 <= a <= 23 and 0 <= b <= 23) or a == b:
                    raise ValueError('Use two different hours from 0 to 23, for example 23 and 7.')
                self._load()['quiet'] = [a, b]
            self._save();return self.view()

    def mark_read(self):
        with self.lock:
            self._load()['unread'] = 0;self._save();return self.view()

    # ---- how the owner sounds on WhatsApp (short, casual, no task numbers)
    def _queue(self, text, task, kind):
        self._load()['outbox'].append({'text': text, 'task': task['id'] if task else None, 'kind': kind, 'at': self.now()})

    def _prefix(self, now):
        d = self._load();day = datetime.datetime.fromtimestamp(now, PKT).date().isoformat();name = self._first()
        if d['greeted'] != day:
            d['greeted'] = day;return f'Assalam o alaikum {name}, '
        return f'{name}, '

    def _ask_text(self, tasks, now):
        due = lambda t: fmt_time(t['due_at'], now)
        p = self._prefix(now)
        if len(tasks) == 1:
            t = tasks[0]
            return p + pick((f"here's one for you: {t['text']}. Need it by {due(t)}.", f"can you do this one: {t['text']}? Deadline is {due(t)}.",
                             f"next thing: {t['text']}. Please get it done by {due(t)} and let me know.", f"I need this by {due(t)}: {t['text']}. Tell me once it's done."), t['id'])
        lead = pick(('a few things for you:', "here's what I need from you:"), tasks[0]['id'])
        return p + lead + '\n' + '\n'.join(f'- {t["text"]} (by {due(t)})' for t in tasks) + '\nLet me know as each one is done.'

    def _text_for(self, kind, t, now):
        """The task text is an instruction ("update the sheet"), so it is quoted after a colon instead of being forced into a sentence."""
        name = self._first();s = short(t['text']);due = fmt_time(t['due_at'], now)
        options = {
            'remind': (f'{name}, any update on this? {s}', f"How's this coming along? {s}", f'Checking in on this one, {name}: {s}. How far along are you?'),
            'check': (f'{s} - will that be ready by {due}?', f'Quick one, {name}: {s}. Are you on track for {due}?', f'Still waiting on this: {s}. It is due at {due}, are you close?'),
            'final': (f'{name}, this was due at {due}: {s}. Where are we on it?', f"It's past {due} and I haven't heard back on this: {s}. What's the status?", f'I was expecting this by {due}: {s}. Can you update me?'),
            'proof': (f'Can you send a screenshot or a photo so I can check it? ({s})', f'{name}, send me a quick screenshot of it so I can verify? ({s})'),
        }[kind]
        return pick(options, t['id'] + kind)

    # ---- sending: reserve under the lock, talk to WhatsApp outside it, then record the result
    def _quiet(self, now):
        return in_quiet(datetime.datetime.fromtimestamp(now, PKT).hour, self._load()['quiet'])

    def _can_send(self, now):
        d = self._load()
        return bool(d['member']) and not d['paused'] and not self._quiet(now) and now - d['last_sent'] >= 60 and not self.app.on_hold() and self.app.wa_ok()

    def _next_job(self, now):
        d = self._load()
        if not self._can_send(now):
            return None
        if d['outbox']:
            m = d['outbox'].pop(0);d['last_sent'] = now
            return {'kind': 'say', 'text': m['text'], 'tasks': [], 'sub': m['kind']}
        ready = sorted((t for t in d['tasks'] if t['status'] == 'Waiting' and now >= t['start_at'] + t['jit'] and now >= t['next_try']), key=lambda x: x['start_at'])[:4]
        if ready:
            for t in ready:
                t['status'] = 'Asked';t['asked_at'] = now;t['attempts'] += 1
            d['last_sent'] = now
            return {'kind': 'ask', 'text': self._ask_text(ready, now), 'tasks': [t['id'] for t in ready]}
        for t in sorted(d['tasks'], key=lambda x: x['start_at']):
            kind = None
            if t['status'] == 'Asked' and not t['acked'] and not t['reminded'] and now >= (t['asked_at'] or now) + 30 * 60 + t['jit'] * 10 and now < t['due_at'] - 15 * 60:
                kind = 'remind';t['reminded'] = True
            elif t['status'] == 'Asked' and not t['checked'] and t['due_at'] - 15 * 60 <= now < t['due_at'] and (t['asked_at'] or 0) < t['due_at'] - 15 * 60:
                kind = 'check';t['checked'] = True
            elif t['status'] == 'Late' and t.get('asked_at') and not t['final_sent']:
                kind = 'final';t['final_sent'] = True
            elif t['status'] == 'Reported' and not t['proof'] and not t['proof_asked'] and now >= (t['reported_at'] or now) + 90:
                kind = 'proof';t['proof_asked'] = True
            if kind:
                d['last_sent'] = now
                return {'kind': kind, 'text': self._text_for(kind, t, now), 'tasks': [t['id']]}
        return None

    def _deliver(self, text, phone):
        """Outside every lock. True only when WhatsApp confirms."""
        try:
            r = self.app.send_custom({'kind': 'team_msg', 'target': 'phone', 'phone': phone, 'message': text, 'poster': False})
            return isinstance(r, dict) and r.get('code') == 'SUCCESS'
        except Exception:
            return False

    def _finish(self, job, ok, now):
        d = self._load();tasks = [t for t in d['tasks'] if t['id'] in job['tasks']]
        if ok:
            self._event('sent', job['text'], tasks[0] if tasks else None)
            return
        if job['kind'] == 'ask':
            for t in tasks:
                t['status'] = 'Waiting';t['asked_at'] = None;t['next_try'] = now + (3600 if t['attempts'] >= 3 else self.RETRY_AFTER)
                if t['attempts'] == 3:
                    self._event('send_failed', f'Could not reach {d["member"]["name"]} on WhatsApp about: {t["text"][:60]}. Check WhatsApp.', t, notify=True)
        else:
            self._event('send_failed', f'A message to {d["member"]["name"]} did not go through ({job["kind"]}).', tasks[0] if tasks else None)

    # ---- the clock: called every ~20 seconds
    def tick(self):
        if not self.tick_lock.acquire(blocking=False):
            return
        try:
            d = self._load()
            if not d['member']:
                return
            phone = d['member']['phone']
            try:
                msgs = self.app.group_messages(phone + '@s.whatsapp.net')
            except Exception:
                msgs = None
            with self.lock:
                now = self.now()
                if msgs:
                    self.handle_messages(msgs)
                self._deadlines(now)
                job = self._next_job(now);self._save()
            ok = self._deliver(job['text'], phone) if job else None
            with self.lock:
                now = self.now()
                if job:
                    self._finish(job, ok, now)
                note = self._take_note(now);self._save()
            if note:
                try:
                    self.app.send_text(self.app.OWNER_PHONE + '@s.whatsapp.net', note)
                except Exception:
                    pass
        finally:
            self.tick_lock.release()

    def _deadlines(self, now):
        for t in self._load()['tasks']:
            if t['status'] in ('Waiting', 'Asked') and now > t['due_at']:
                was = t['status'];t['status'] = 'Late';t['late_at'] = now
                self._event('late', f'Late: {t["text"]}' + ('' if was == 'Asked' else ' (it was never sent to him)'), t, notify=True)

    def _take_note(self, now):
        d = self._load()
        if not d['pending_notes'] or now - d['last_note'] < 120:
            return None
        notes = d['pending_notes'][:5];rest = len(d['pending_notes']) - len(notes);d['pending_notes'] = [];d['last_note'] = now
        return ('Team: ' + ' | '.join(n['text'] for n in notes) + (f' (+{rest} more)' if rest > 0 else ''))[:900]

    # ---- reading his replies
    @staticmethod
    def _stamp(m):
        try:
            return datetime.datetime.fromisoformat(str(m.get('timestamp', '')).replace('Z', '+00:00')).timestamp()
        except Exception:
            return 0.0

    @staticmethod
    def _media(m):
        kind = ' '.join(str(m.get(k) or '') for k in ('media_type', 'type', 'message_type', 'mimetype')).lower()
        if any(w in kind for w in ('audio', 'ptt', 'voice')):
            return 'audio'
        if any(w in kind for w in ('image', 'photo', 'video', 'sticker', 'document', 'pdf')) or m.get('image') or m.get('url') or m.get('filename'):
            return 'image'
        return None

    def handle_messages(self, msgs):
        d = self._load();seen = set(d['seen']);changed = False
        for m in sorted(msgs or [], key=self._stamp):
            mid = m.get('id')
            if not mid or mid in seen or m.get('is_from_me'):
                continue
            if self._stamp(m) and self._stamp(m) < d['member']['since']:
                continue
            seen.add(mid);changed = True
            self.handle_reply(str(m.get('content') or m.get('caption') or ''), self._media(m))
        if changed:
            d['seen'] = list(seen)[-500:]

    def _targets(self, text, pool):
        """Which of the open tasks does this message mean? Never guesses between several."""
        if not pool:
            return []
        if ALL_WORDS.search(text):
            return list(pool)
        nums = [int(n) for n in re.findall(r"(?<![\d:/.])#?(\d{1,2})(?![\d:/.]|\s*(?:am|pm|min|hour|hr|baje))", text)]
        byno = [t for t in pool if t['no'] in nums]
        if nums and byno:
            return byno
        w = words(text)
        scored = [(len(w & words(t['text'])), t) for t in pool]
        best = max((s for s, _ in scored), default=0)
        if best > 0:
            top = [t for s, t in scored if s == best]
            return top if len(top) == 1 else []
        return list(pool) if len(pool) == 1 else []

    def _clarify(self, pool, now):
        d = self._load()
        if len(pool) < 2 or now - d['last_clarify'] < 600:
            return
        d['last_clarify'] = now
        names = [short(t['text'], 28) for t in pool[:4]]
        self._queue('Which one do you mean, ' + ', '.join(names[:-1]) + ' or ' + names[-1] + '?', None, 'clarify')

    def handle_reply(self, text, media=None):
        d = self._load();now = self.now();text = str(text or '').strip();first = self._first()
        proof = media == 'image' or bool(URL.search(text))
        shown = text or ('(voice note)' if media == 'audio' else '(sent a photo or file)')
        pool = [t for t in d['tasks'] if t['status'] in ('Asked', 'Late')] or [t for t in d['tasks'] if t['status'] == 'Waiting']
        if said_done(text):
            targets = self._targets(text, pool)
            if not targets:
                self._event('update', f'{first}: {shown}' + ('  (which task?)' if len(pool) > 1 else ''), notify=True);self._clarify(pool, now)
                return
            for t in targets:
                t.update(status='Reported', report_text=shown[:400], reported_at=now, acked=True)
                t['proof'] = t['proof'] or proof
                self._event('report', f'{first} says it is done: {short(t["text"], 70)}' + (f' ("{shown[:80]}")' if text else ''), t, notify=True)
            if all(t['proof'] for t in targets):
                self._queue(pick((f'Nice, thanks {first}.', 'Great, thank you.', f'Perfect, thanks {first}.'), targets[0]['id']), None, 'ack')
            else:
                for t in targets:
                    t['proof_asked'] = True
                self._queue(pick((f'Thanks {first}. Can you send a screenshot or photo so I can check it?', 'Okay good. Send me a quick screenshot or photo so I can check?'), targets[0]['id']), None, 'ack')
            return
        waiting_proof = [t for t in d['tasks'] if t['status'] == 'Reported' and not t['proof']]
        candidates = self._targets(text, pool + waiting_proof) if (text or proof) else []
        target = candidates[0] if len(candidates) == 1 else None
        if target is None and proof and not text and len(waiting_proof) == 1:
            target = waiting_proof[0]
        if target:
            target['acked'] = True
            target['proof'] = target['proof'] or proof
        kind = 'blocked' if BLOCK_WORDS.search(text) else ('proof' if proof and not text else 'update')
        self._event(kind, f'{first}: {shown}', target, notify=True)
        if kind == 'blocked' and target and not target['blocked_replied']:
            target['blocked_replied'] = True
            self._queue(pick((f'Okay {first}, what exactly is stopping you?', "Alright, what's the problem? Tell me what's blocking you."), target['id']), target, 'blocked')

    # ---- chat
    def summary(self):
        with self.lock:
            v = self.view()
            if not v['member']:
                return 'No teammate set yet. Say: set teammate Bilal 0300 1234567'
            if not v['tasks']:
                return f'No tasks for {v["member"]["name"]} right now.'
            done = sum(1 for t in v['tasks'] if t['status'] == 'Done')
            left = [f'{t["text"][:50]} ({t["status"].lower()}, due {t["due_label"]})' for t in v['tasks'] if t['status'] != 'Done']
            return f'{done} of {len(v["tasks"])} done. ' + ('Left: ' + '; '.join(left) if left else 'All done.')

    def command(self, raw, t):
        """Chat shortcuts. Returns a result dict, or None when the text is about something else."""
        low = t.casefold().strip()
        m = re.match(r"(?i)^(?:please\s+)?set\s+(?:my\s+)?(?:team\s*mate|teammate|team member)\s*[:=-]?\s*(.+)$", raw.strip())
        if m:
            from donor_book import PHONE, parse_contact
            if not PHONE.search(m[1]):
                raise ValueError('Say it like: set teammate Bilal 0300 1234567')
            label, phone = parse_contact(m[1], '')
            if label == 'Donor':
                raise ValueError('Write the teammate\'s name with the number.')
            self.set_member(label, phone);return {'reply': f'{label} is your teammate now. Number saved and hidden.', 'team_changed': True}
        m = re.match(r"(?is)^(?:please\s+)?(?:give\s+|set\s+|assign\s+|add\s+)?(?:(?:today'?s|todays|these|new)\s+)?(?:tasks?|todo)(?:\s+(?:for|to)\s+[\w ]{1,30}?)?\s*[:\-]\s*(.+)$", raw.strip())
        if m:
            v = self.plan(m[1])
            lines = [f'{i + 1}. {x["text"]}  (ask {x["start_label"]}, due {x["due_label"]})' for i, x in enumerate(v['plan']['items'])]
            return {'reply': 'Here is the plan:\n' + '\n'.join(lines) + '\nSay "confirm tasks" to start, or "cancel tasks".', 'team_changed': True}
        if low in ('confirm tasks', 'confirm task', 'start tasks', 'yes tasks', 'send tasks'):
            r = self.confirm_plan();return {'reply': r['reply'], 'team_changed': True}
        if low in ('cancel tasks', 'discard tasks', 'cancel plan'):
            self.discard_plan();return {'reply': 'Plan discarded. Nothing was sent.', 'team_changed': True}
        if low in ('team status', 'task status', 'tasks status', 'show tasks', 'show team', 'team update', 'team updates', 'what are the tasks'):
            return {'reply': self.summary()}
        m = re.fullmatch(r"(?i)(?:please\s+)?(?:verify|approve|confirm|mark)\s+task\s+#?(\d{1,2})(?:\s+(?:as\s+)?(?:done|verified))?", low)
        if m:
            self.verify(m[1]);return {'reply': f'Task #{m[1]} verified.', 'team_changed': True}
        m = re.fullmatch(r"(?is)task\s+#?(\d{1,2})\s+(?:not done|redo|send back|rejected?)\s*[:\-]?\s*(.*)", raw.strip())
        if m:
            self.reject(m[1], m[2]);return {'reply': f'Task #{m[1]} sent back to him.', 'team_changed': True}
        m = re.fullmatch(r"(?i)(?:please\s+)?cancel\s+task\s+#?(\d{1,2})", low)
        if m:
            self.cancel(m[1]);return {'reply': f'Task #{m[1]} cancelled.', 'team_changed': True}
        if low in ('pause team', 'pause tasks', 'pause team follow-up'):
            self.pause(True);return {'reply': 'Team follow-up paused. No messages will go to him until you resume.', 'team_changed': True}
        m = re.fullmatch(r"(?i)(?:team\s+)?quiet hours\s+(?:from\s+)?(\d{1,2})\s*(?:to|-|till|until)\s*(\d{1,2})", low)
        if m:
            self.set_quiet(m[1], m[2]);return {'reply': f'Quiet hours set: no team messages from {int(m[1])}:00 to {int(m[2])}:00.', 'team_changed': True}
        if low in ('team quiet hours off', 'quiet hours off', 'no quiet hours'):
            self.set_quiet();return {'reply': 'Team quiet hours are off. Messages can go out at any hour.', 'team_changed': True}
        if low in ('resume team', 'resume tasks'):
            self.pause(False);return {'reply': 'Team follow-up resumed.', 'team_changed': True}
        return None
