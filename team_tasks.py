"""Team tasks: the owner writes today's tasks and a deadline, the app splits them into timed tasks (after a preview the owner
confirms), asks the teammate on WhatsApp, reads his replies, reminds once, marks late tasks, and shows updates in one simple screen.

Rules that keep it honest:
- All times are Pakistan time (UTC+5).
- Nothing is sent until the owner confirms the plan.
- Every WhatsApp message is reserved before it is sent, so a crash or restart can never send the same message twice.
- "Done" from the teammate is only a report. The owner verifies it (or sends it back).
- Quiet hours (23:00-07:00) and the global hold are respected. One message per minute at most."""
import copy, datetime, re, threading, time, uuid
from donor_book import normalize_phone

PKT = datetime.timezone(datetime.timedelta(hours=5))
OPEN = ('Waiting', 'Asked', 'Late', 'Reported')
DONE_WORDS = re.compile(r"(?i)\b(?:done|finished|completed?|ho\s*gaya|ho\s*gya|hogaya|kar\s*diya|kardiya|ready)\b")
BLOCK_WORDS = re.compile(r"(?i)\b(?:stuck|problem|issue|cannot|can't|cant|unable|need help|help me|delay(?:ed)?|late|not possible|nahi ho|nahi hua|error)\b")
URL = re.compile(r"(?i)https?://\S+|\bwww\.\S+")
MIN_SLOT = 10 * 60
CLOCK = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2})"
DEADLINE = re.compile(r"(?i)\b(?:(?:deadline|due|latest|all by|everything by|finish(?:ed)? by|complete(?:d)? by|till|until|tak)\s*(?:is\s*)?(?:(tomorrow|tmrw|kal)\s+)?(?:at\s+)?(" + CLOCK + r"|\d{1,2})\b|(?:in|within)\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\b)")


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
    parts = re.split(r"\n+|;|(?:(?<=\s)|^)\(?\d{1,2}[.)]\s+|(?:(?<=\s)|^)[-•*▪]\s+", text)
    out = []
    for p in parts:
        p = re.sub(r"^\s*(?:\d{1,2}[.)]\s*)", '', (p or '').strip(' ,-•*▪\t'))
        if p and p not in out:
            out.append(p)
    return out


def plan_tasks(text, now):
    """Turn the owner's text into timed tasks. Raises ValueError with a clear reason. Nothing is saved or sent."""
    text = str(text or '').strip()
    if not text:
        raise ValueError('Write today\'s tasks first, one per line, and a deadline like "deadline 6pm".')
    overall, body = parse_deadline(text, now)
    items = []
    for raw in split_items(body):
        own, clean = None, raw
        m = re.search(r"(?i)\s*(?:\(|\b)(?:by|at|before)\s+(" + CLOCK + r")\)?\s*$", raw)
        if m:
            own = _clock(m[1], now);clean = raw[:m.start()].strip(' ,-')
        clean = clean.strip()
        if clean:
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
    return out


class TeamTasks:
    KEY = 'team'
    QUIET = (23, 7)

    def __init__(self, app, clock=time.time):
        self.app = app;self.now = clock;self.lock = threading.RLock();self._cache = None

    # ---- storage
    def _load(self):
        if self._cache is None:
            raw = self.app.STORE.get(self.KEY) if self.app.STORE else None
            if raw is None and (self.app.DATA / 'team.json').exists():
                import json
                raw = json.loads((self.app.DATA / 'team.json').read_text(encoding='utf-8'))
            if not isinstance(raw, dict):
                raw = {}
            raw.setdefault('member', None);raw.setdefault('tasks', []);raw.setdefault('feed', []);raw.setdefault('plan', None)
            raw.setdefault('seen', []);raw.setdefault('counter', 0);raw.setdefault('paused', False);raw.setdefault('unread', 0)
            raw.setdefault('last_sent', 0);raw.setdefault('pending_notes', []);raw.setdefault('last_note', 0)
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
                    'feed': [{**e, 'label': fmt_time(e['at'], now)} for e in d['feed'][-80:]][::-1], 'unread': d['unread'], 'plan': plan, 'paused': d['paused'], 'now_label': fmt_time(now),
                    'counts': {s: sum(1 for t in d['tasks'] if t['status'] == s) for s in ('Waiting', 'Asked', 'Reported', 'Late', 'Done')}}

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
            items = plan_tasks(text, self.now())
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
                t = {'id': uuid.uuid4().hex, 'no': d['counter'], 'text': i['text'], 'start_at': i['start_at'], 'due_at': i['due_at'], 'status': 'Waiting', 'created_at': now,
                     'attempts': 0, 'next_try': 0, 'asked_at': None, 'reminded': False, 'checked': False, 'final_sent': False, 'acked': False, 'proof': False,
                     'proof_asked': False, 'report_text': '', 'reported_at': None, 'verified_at': None}
                d['tasks'].append(t);made.append(t)
            d['plan'] = None
            self._event('plan', f'{len(made)} task{"s" if len(made) != 1 else ""} started for {d["member"]["name"]}.')
            self._save()
            return {**self.view(), 'reply': f'{len(made)} task{"s" if len(made) != 1 else ""} started. The first message goes out at {fmt_time(min(t["start_at"] for t in made), now)}.'}

    def _find(self, ident):
        d = self._load()
        for t in reversed(d['tasks']):
            if t['id'] == ident or (str(t['no']) == str(ident) and t['status'] in OPEN):
                return t
        raise ValueError('That task was not found, or it is already finished.')

    def verify(self, ident):
        with self.lock:
            t = self._find(ident)
            if t['status'] not in ('Reported', 'Late', 'Asked', 'Waiting'):
                raise ValueError('This task is not waiting for you.')
            t['status'] = 'Done';t['verified_at'] = self.now();self._event('verified', f'You verified task #{t["no"]}: {t["text"]}', t);self._save();return self.view()

    def reject(self, ident, note=''):
        with self.lock:
            t = self._find(ident);now = self.now()
            if t['status'] != 'Reported':
                raise ValueError('Only a reported task can be sent back.')
            t.update(status='Asked', reminded=False, checked=False, final_sent=False, acked=False, report_text='', reported_at=None, proof_asked=False)
            if t['due_at'] < now + 1800:
                t['due_at'] = now + 1800
            self._queue(f'Task #{t["no"]} needs another look' + (f': {str(note).strip()[:200]}' if str(note).strip() else '.') + f' New deadline {fmt_time(t["due_at"], now)}. Reply "{t["no"]} done" when ready.', t, 'rejected')
            self._event('rejected', f'You sent task #{t["no"]} back.', t);self._save();return self.view()

    def cancel(self, ident):
        with self.lock:
            t = self._find(ident);t['status'] = 'Cancelled';self._event('cancel', f'Task #{t["no"]} cancelled.', t);self._save();return self.view()

    def pause(self, on):
        with self.lock:
            self._load()['paused'] = bool(on);self._save();return self.view()

    def mark_read(self):
        with self.lock:
            self._load()['unread'] = 0;self._save();return self.view()

    # ---- sending (reserve first, then send: at most once)
    def _quiet(self, now):
        h = datetime.datetime.fromtimestamp(now, PKT).hour
        a, b = self.QUIET
        return h >= a or h < b

    def _queue(self, text, task, kind):
        d = self._load();d.setdefault('outbox', []).append({'text': text, 'task': task['no'] if task else None, 'kind': kind, 'at': self.now()})

    def _send(self, text):
        d = self._load()
        r = self.app.send_custom({'kind': 'team_msg', 'target': 'phone', 'phone': d['member']['phone'], 'message': text, 'poster': False})
        if not isinstance(r, dict) or r.get('code') != 'SUCCESS':
            raise ValueError('not delivered')

    def _can_send(self, now):
        d = self._load()
        return bool(d['member']) and not d['paused'] and not self._quiet(now) and now - d['last_sent'] >= 60 and not self.app.on_hold() and self.app.wa_ok()

    def _transmit(self, text, now):
        """Reserve the time slot first; a failure is reported, never retried blindly."""
        d = self._load();d['last_sent'] = now;self._save()
        self._send(text)

    # ---- the clock: called every ~20 seconds
    def tick(self):
        with self.lock:
            d = self._load();now = self.now()
            if not d['member']:
                return
            self._poll(now)
            self._deadlines(now)
            self._outbound(now)
            self._notify_owner(now)
            self._save()

    def _deadlines(self, now):
        d = self._load();name = d['member']['name']
        for t in d['tasks']:
            if t['status'] in ('Waiting', 'Asked') and now > t['due_at']:
                was = t['status'];t['status'] = 'Late';t['late_at'] = now
                self._event('late', f'Task #{t["no"]} is late: {t["text"]}' + ('' if was == 'Asked' else ' (it was never sent)'), t, notify=True)

    def _outbound(self, now):
        d = self._load()
        if not self._can_send(now):
            return
        name = d['member']['name'].split()[0]
        if d.get('outbox'):
            m = d['outbox'].pop(0)
            try:
                self._transmit(m['text'], now);self._event('sent', m['text'], None, to_task=m['task'])
            except Exception:
                self._event('send_failed', 'A message to ' + name + ' could not be sent.', None, notify=True)
            return
        for t in sorted(d['tasks'], key=lambda x: x['start_at']):
            text = kind = None
            if t['status'] == 'Waiting' and now >= t['start_at'] and now >= t['next_try']:
                text = f'Assalam o alaikum {name}. Task #{t["no"]}: {t["text"]}\nDeadline: {fmt_time(t["due_at"], now)}.\nReply "{t["no"]} done" when finished (send a photo or link as proof), or tell me if you are stuck.'
                kind = 'ask'
            elif t['status'] == 'Asked' and not t['acked'] and not t['reminded'] and now >= (t['asked_at'] or now) + 30 * 60 and now < t['due_at'] - 15 * 60:
                text = f'Reminder: task #{t["no"]} - {t["text"]}. Deadline {fmt_time(t["due_at"], now)}. Any update?';kind = 'remind'
            elif t['status'] == 'Asked' and not t['checked'] and t['due_at'] - 15 * 60 <= now < t['due_at'] and (t['asked_at'] or 0) < t['due_at'] - 15 * 60:
                text = f'Quick check: is task #{t["no"]} done? Deadline {fmt_time(t["due_at"], now)}. Reply "{t["no"]} done" or tell me what is left.';kind = 'check'
            elif t['status'] == 'Late' and t.get('asked_at') and not t['final_sent']:
                text = f'The deadline for task #{t["no"]} has passed. Please send an update now.';kind = 'final'
            elif t['status'] == 'Reported' and not t['proof'] and not t['proof_asked']:
                text = f'Thanks. For task #{t["no"]}, please send a screenshot, photo or link as proof.';kind = 'proof'
            if not text:
                continue
            # reserve before sending: a crash can never produce a second copy
            if kind == 'ask':
                t['status'] = 'Asked';t['asked_at'] = now;t['attempts'] += 1
            elif kind == 'remind':
                t['reminded'] = True
            elif kind == 'check':
                t['checked'] = True
            elif kind == 'final':
                t['final_sent'] = True
            elif kind == 'proof':
                t['proof_asked'] = True
            try:
                self._transmit(text, now);self._event('sent', text, t)
            except Exception:
                if kind == 'ask':
                    t['status'] = 'Waiting';t['asked_at'] = None
                    t['next_try'] = now + 300
                    if t['attempts'] >= 3:
                        t['next_try'] = now + 3600
                        self._event('send_failed', f'Task #{t["no"]} could not be sent to {d["member"]["name"]} ({t["attempts"]} tries). Check WhatsApp.', t, notify=True)
                else:
                    self._event('send_failed', f'A {kind} message for task #{t["no"]} could not be sent.', t)
            return  # one message per tick

    # ---- reading his replies
    def _poll(self, now):
        d = self._load();m = d['member']
        try:
            msgs = self.app.group_messages(m['phone'] + '@s.whatsapp.net')
        except Exception:
            return
        self.handle_messages(msgs)

    @staticmethod
    def _stamp(m):
        try:
            return datetime.datetime.fromisoformat(str(m.get('timestamp', '')).replace('Z', '+00:00')).timestamp()
        except Exception:
            return 0.0

    def handle_messages(self, msgs):
        d = self._load();seen = set(d['seen']);changed = False
        for m in sorted(msgs or [], key=self._stamp):
            mid = m.get('id')
            if not mid or mid in seen or m.get('is_from_me'):
                continue
            if self._stamp(m) and self._stamp(m) < d['member']['since']:
                continue
            seen.add(mid);changed = True
            self.handle_reply(str(m.get('content') or m.get('caption') or ''), bool(m.get('media_type') or m.get('filename') or m.get('image') or m.get('url') or str(m.get('type', '')).lower() in ('image', 'video', 'document')))
        if changed:
            d['seen'] = list(seen)[-500:];self._save()

    def handle_reply(self, text, media=False):
        """One message from the teammate. Matches it to tasks by number; never guesses between several."""
        d = self._load();now = self.now();text = text.strip()
        proof = media or bool(URL.search(text))
        asked = [t for t in d['tasks'] if t['status'] in ('Asked', 'Late')]
        nums = [int(n) for n in re.findall(r"(?<![\d:/.])#?(\d{1,2})(?![\d:/.]|\s*(?:am|pm|min|hour|hr))", text)]
        by_no = {t['no']: t for t in asked}
        said_done = bool(DONE_WORDS.search(text))
        shown = text or '(sent a photo or file)'
        if said_done:
            if re.search(r"(?i)\ball\b", text):
                targets = asked
            elif nums:
                targets = [by_no[n] for n in dict.fromkeys(nums) if n in by_no]
                if not targets:
                    self._event('update', f'{d["member"]["name"]}: {shown}', notify=True)
                    self._queue('I could not match that to an open task. Open tasks: ' + (', '.join('#' + str(t['no']) for t in asked) or 'none') + '. Reply like "2 done".', None, 'clarify')
                    return
            elif len(asked) == 1:
                targets = asked
            else:
                self._event('update', f'{d["member"]["name"]}: {shown}  (which task?)', notify=True)
                if asked:
                    self._queue('Which task is done? Open: ' + ', '.join('#' + str(t['no']) for t in asked) + '. Reply like "2 done".', None, 'clarify')
                return
            for t in targets:
                t['status'] = 'Reported';t['report_text'] = shown[:400];t['reported_at'] = now;t['acked'] = True
                t['proof'] = t['proof'] or proof
                self._event('report', f'{d["member"]["name"]} says task #{t["no"]} is done: {shown}', t, notify=True, proof=t['proof'])
            self._queue('Thanks. Noted as done: ' + ', '.join('#' + str(t['no']) for t in targets) + '. I will confirm after checking.', None, 'ack')
            return
        target = by_no.get(nums[0]) if nums and nums[0] in by_no else (asked[-1] if len(asked) == 1 else None)
        if target:
            target['acked'] = True
            if proof:
                target['proof'] = True
        kind = 'blocked' if BLOCK_WORDS.search(text) else ('proof' if proof and not text else 'update')
        self._event(kind, f'{d["member"]["name"]}: {shown}', target, notify=True)

    def _notify_owner(self, now):
        d = self._load()
        if not d['pending_notes'] or now - d['last_note'] < 120:
            return
        notes = d['pending_notes'][:5];rest = len(d['pending_notes']) - len(notes);d['pending_notes'] = []
        text = 'GiveLife team: ' + ' | '.join(n['text'] for n in notes) + (f' (+{rest} more)' if rest > 0 else '')
        d['last_note'] = now
        try:
            self.app.send_text(self.app.OWNER_PHONE + '@s.whatsapp.net', text[:900])
        except Exception:
            pass

    # ---- chat
    def summary(self):
        with self.lock:
            v = self.view()
            if not v['member']:
                return 'No teammate set yet. Say: set teammate Bilal 0300 1234567'
            if not v['tasks']:
                return f'No tasks for {v["member"]["name"]} right now.'
            lines = [f'#{t["no"]} {t["text"][:60]} - {t["status"]} (due {t["due_label"]})' for t in v['tasks']]
            return f'{v["member"]["name"]}: ' + '; '.join(lines)

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
        m = re.fullmatch(r"(?i)(?:please\s+)?(?:verify|approve|confirm)\s+task\s+#?(\d{1,2})", low)
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
        if low in ('resume team', 'resume tasks'):
            self.pause(False);return {'reply': 'Team follow-up resumed.', 'team_changed': True}
        return None
