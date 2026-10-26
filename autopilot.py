"""Autopilot engine: runs the foundation's routine while the owner is away, inside hard safety limits.

It never changes the amount left (only the owner can), never invents facts, never sends to unknown groups,
and keeps WhatsApp's safety floors (15 minutes per group, 45 seconds between DMs).
Everything it needs from the outside world arrives through `h`, a dict of helpers supplied by server.py.
"""
import json, re, time, datetime, threading, random, hashlib, os, urllib.request
import rules, learning

PKT = datetime.timezone(datetime.timedelta(hours=5))
ACCOUNT = '03097458815'

# Minutes between posts by minutes since money last came: (from, name, main gap, freelance gap).
LADDER = [(360, 'L4', 30, 90), (90, 'L3', 15, 30), (40, 'L2', 15, 45), (0, 'L1', 20, 60)]
# L4 = six hours without money: more posts stop helping and tire the groups, so the pace eases while DMs and shares carry on.
VERY_SLOW = ('L3', 'L4')
TIER_CAPS = {'repeat': 10, 'donor': 15, 'member': 10, 'saved': 8}  # DMs per day for each kind of person
DM_QUIET = (23, 8)                                                    # no DMs at night
MILESTONES = (0.25, 0.5, 0.75, 0.9)

DONE = re.compile(r"\b(done|sent|send kar diya|bhej diya|kar diya|transferred|paid|donated)\b", re.I)
LATER = re.compile(r"\b(later|kal|tomorrow|baad mein|baad me|thori der|abhi nahi|not now|next week|salary|insha ?allah|will (?:try|do|send|donate))\b", re.I)
PAPERS = re.compile(r"\b(real|fake|papers?|proof|reports?|documents?|verify|genuine|scam)\b", re.I)
COMPLAINT = re.compile(r"\b(spam\w*|stop (posting|sending|messaging|this)|too many (messages|posts)|remove (me|this)|not allowed|report(ed)?|admin|irrelevant|don'?t post|mute)\b", re.I)
MONEY_HINT = re.compile(r"(?i)easypaisa|jazz ?cash|\brs\.?\s*\d|\d{3,}|donat|yousuf|givelife|03097458815")
OPT_OUT = re.compile(r"\b(stop|unsubscribe|don'?t (message|msg|dm) me|not interested|block)\b", re.I)
Q1 = 'Yes, medical papers are available. I will send them to you privately.'


def now():
    return time.time()


def pkt():
    return datetime.datetime.now(PKT)


def _stamp(m):
    try:
        return datetime.datetime.fromisoformat(str(m.get('timestamp', '')).replace('Z', '+00:00')).timestamp()
    except Exception:
        return now()


class Engine:
    def __init__(self, h):
        self.h = h
        self.f = h['DATA'] / 'autopilot-state.json'
        self.lock = threading.Lock()
        self.s = self._load()
        self.dm_running = False

    # ------------------------------------------------------------------ state
    def _load(self):
        base = {'last_money': None, 'left_seen': None, 'paused': {}, 'quiet': None, 'seen': [], 'notified': {},
                'day': None, 'posts_today': 0, 'dms_today': 0, 'done_today': 0, 'last_dm_batch': 0,
                'dm_daily': int(os.environ.get('AUTO_DM_DAILY', '30')), 'dm_enabled': True, 'dm_new': True,
                'last_scan': 0, 'last_dm_scan': 0, 'last_chat_scan': 0, 'last_report_day': None,
                'owner_seen': now(), 'started': now(), 'learn': learning.new(), 'milestones': [], 'dms_by_tier': {}}
        try:
            v = self.h['store_get']('autostate')
            if v:
                base.update(json.loads(v) if isinstance(v, str) else v)
            elif self.f.exists():
                base.update(json.loads(self.f.read_text(encoding='utf-8')))
        except Exception:
            pass
        return base

    def save(self):
        self.f.write_text(json.dumps(self.s), encoding='utf-8')
        self.h['persist']('autostate', self.f)

    def log(self, text, quiet=False):
        self.h['log'](text)

    def notify(self, key, text, every=3600):
        """A WhatsApp message to the owner's own number, at most once per `every` seconds for each key."""
        if now() - self.s['notified'].get(key, 0) < every:
            return
        self.s['notified'][key] = now()
        try:
            self.h['send_text'](self.h['owner_jid'](), 'GiveLife autopilot: ' + text)
        except Exception:
            pass
        self.log('Told owner: ' + text)

    @property
    def L(self):
        return self.s.setdefault('learn', learning.new())

    def activated(self):
        """Auto was just switched on: start the clock fresh so old quiet time does not trigger the slowest pace."""
        with self.lock:
            self.s['started'] = now()
            self.s['last_money'] = now()
            self.s['l4_told'] = False
            self.s['last_scan'] = self.s['last_dm_scan'] = 0  # read replies on the first minute
            self.s['notified'] = {k: v for k, v in self.s['notified'].items() if now() - v < 3600}
            self.save()

    def touch_owner(self):
        self.s['owner_seen'] = now()

    def away_hours(self):
        return (now() - self.s.get('owner_seen', now())) / 3600

    # ------------------------------------------------------------------ main loop
    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        if os.environ.get('RENDER_EXTERNAL_URL'):
            threading.Thread(target=self._keepalive, daemon=True).start()

    def _keepalive(self):
        url = os.environ['RENDER_EXTERNAL_URL'].rstrip('/') + '/health'
        while True:
            time.sleep(600)
            try:
                urllib.request.urlopen(url, timeout=20).read()
            except Exception:
                pass

    def _loop(self):
        while True:
            time.sleep(60)
            try:
                if self.h['enabled']():
                    with self.lock:
                        self.tick()
                        self.save()
            except Exception as e:
                self.log('Autopilot error: ' + str(e)[:150])

    def level(self):
        since = self.s['last_money'] or self.s['started']
        mins = (now() - since) / 60
        for limit, name, main_gap, free_gap in LADDER:
            if mins >= limit:
                po = self.s.get('pace_override')
                if po:
                    main_gap, free_gap = po
                return name, main_gap, free_gap, mins

    def tick(self):
        if self.h.get('on_hold', lambda: False)():
            return  # owner said hold: nothing is read, sent or alerted
        today = pkt().date().isoformat()
        if self.s['day'] != today:
            self.s.update(day=today, posts_today=0, dms_today=0, done_today=0, posts_by={}, dms_by_tier={})
        left = self.h['read_left']()
        prev = self.s['left_seen']
        if prev is not None and left < prev:
            self.s['last_money'] = now()
            learning.credit_money(self.L)
            came = prev - left
            due = self.s.get('update_due') or {}
            total = came + (due.get('came', 0) if due and now() - due.get('at', 0) < 5400 else 0)
            if total >= 1500 and left > 0:  # owner's rule: money came -> stress update, never a celebration
                self.s['update_due'] = {'came': total, 'at': now()}
            self.log(f'Money noticed: Rs. {prev - left:,}. Back to normal pace.')
        self.s['left_seen'] = left
        if self.level()[0] == 'L4' and not self.s.get('l4_told'):
            self.s['l4_told'] = True
            self.notify('fatigue', 'No money for 6 hours. More posts stop helping and tire the groups, so I eased the pace. I keep sending DMs to past donors and people who may help. A new photo or an update from the family would help most.', 12 * 3600)
        elif self.level()[0] != 'L4':
            self.s['l4_told'] = False
        if not self.h['wa_ok']():
            # try to fix it alone first; only bother the owner if it stays down
            if not self.s.get('wa_down_since'):
                self.s['wa_down_since'] = now()
            down = self.s['wa_down_since']
            if now() - self.s.get('wa_try', 0) >= 180 and 'wa_reconnect' in self.h:
                self.s['wa_try'] = now()
                try:
                    self.h['wa_reconnect']()
                except Exception:
                    pass
            if not self.h['wa_ok']():
                if now() - down >= 900:
                    self.notify('wa', 'WhatsApp has been disconnected for 15 minutes and I could not reconnect it. Open the studio and link WhatsApp again. Nothing is being sent.', 3 * 3600)
                return
            self.log('WhatsApp was disconnected and I reconnected it myself.')
        self.s['wa_down_since'] = 0
        if left <= 0:
            if not self.s.get('d1_done'):
                self.s['d1_done'] = True
                self.h['post_text_all'](self.h['done_text']())
                self.log('Goal complete: completion message posted to all groups. Posting stopped.')
            return self.notify('goal', 'The goal is complete (Rs. 0 left). I posted the completion message and stopped. Set up the next case when ready.', 86400)
        self.s['d1_done'] = False
        for key, every, scan in (('last_scan', 300, self.scan_group_replies), ('last_dm_scan', 600, self.scan_dm_replies),
                                 ('last_chat_scan', 1200, self.scan_saved_chats)):
            if now() - self.s[key] >= every:
                self.s[key] = now()
                scan()
        self.run_scheduled()
        self.run_followups()
        self.milestone_if_due(left)
        self.update_if_due(left)
        self.post_if_due()
        self.share_if_due()
        self.dm_if_due()
        self._owner_todo()
        self.daily_report(left)

    def _owner_todo(self):
        todo = [sg for sg in self.suggestions() if sg['action'] == 'owner']
        if todo and now() - self.s['started'] > 600:  # things only the owner can do: one combined note a day
            body = ' '.join(f'({i + 1}) {sg["text"]}' for i, sg in enumerate(todo[:4]))
            self.notify('owner-todo', f'{len(todo)} thing(s) need you: {body}', 24 * 3600)

    # ------------------------------------------------------------------ owner rules (typed in chat)
    def rules(self):
        return self.s.setdefault('rules', [])

    def add_rule(self, rule):
        rule = dict(rule)
        rule['id'] = int(now() * 1000) % 10_000_000
        if rule['kind'] in ('gap', 'quiet', 'cap'):  # a newer rule replaces an older one for the same group
            self.s['rules'] = [r for r in self.rules() if not (r['kind'] == rule['kind'] and r.get('group') == rule.get('group'))]
        if rule['kind'] == 'pause':
            self.s['paused'][rule['group']] = rule['until']
        self.rules().append(rule)
        self.save()
        return rule

    def delete_rule(self, rid):
        gone = [r for r in self.rules() if str(r.get('id')) == str(rid)]
        self.s['rules'] = [r for r in self.rules() if str(r.get('id')) != str(rid)]
        for r in gone:
            if r['kind'] == 'pause':
                self.s['paused'].pop(r['group'], None)
        self.save()
        return bool(gone)

    def rule_list(self):
        return [{'id': r['id'], 'text': rules.describe(r)} for r in self.rules() if r['kind'] != 'pause' or r['until'] > now()]

    @staticmethod
    def _matches(rule_group, key):
        return rule_group in ('all', key) or (rule_group == 'free' and key in ('community', 'fiverr', 'upwork', 'uet', 'toprated'))

    def gap_for(self, key, default):
        for r in reversed(self.rules()):
            if r['kind'] == 'gap' and self._matches(r['group'], key):
                return r['minutes']
        if self.s.get('pace_override'):
            return default
        mult = self.rhythm(key)[0]
        if self.level()[0] == 'L4' and mult < 1:
            mult = 1  # a long drought: never speed up, the groups are tired
        return max(15 if key == 'main' else 30, int(default * mult))

    def rhythm(self, key='main'):
        """(gap multiplier, reason) for the hour of the day in Pakistan: people sleep at night, read most in the evening."""
        hr = pkt().hour
        if 1 <= hr < 7:
            return (1.5 if key == 'main' else 2.0), 'Night: most people are asleep, so I post less often.'
        if hr in learning.hot_hours(self.L):
            return 0.8, 'Money usually comes around now, so I post a little more often.'
        if 19 <= hr <= 22 or 12 <= hr <= 13:
            return 0.85, 'Busy hour: many people are online, so I post a little more often.'
        return 1.0, ''

    def blocked(self, key):
        hr = pkt().hour
        if self.s['paused'].get(key, 0) > now():
            return True
        for r in self.rules():
            if r['kind'] == 'quiet' and self._matches(r['group'], key) and rules.in_quiet(r['start'], r['end'], hr):
                return True
            if r['kind'] == 'cap' and self._matches(r['group'], key) and self.s.setdefault('posts_by', {}).get(key, 0) >= r['per_day']:
                return True
        return False

    def quiet_now(self):
        q = self.s.get('quiet')
        return bool(q) and rules.in_quiet(q[0], q[1], pkt().hour)

    def run_scheduled(self):
        for r in self.rules():
            if r['kind'] != 'schedule' or r.get('done') or now() < r['next']:
                continue
            try:
                self.h['send_scheduled'](r['target'], r.get('text', ''))
                self.log(f'Scheduled task done: {rules.describe(r)}')
            except Exception as e:
                self.notify('sched-' + str(r['id']), f'A scheduled send did not go through ({str(e)[:80]}): {rules.describe(r)}', 3600)
            if r.get('daily'):
                r['next'] = rules.next_epoch(r['at'])
            else:
                r['done'] = True
        self.s['rules'] = [r for r in self.rules() if not r.get('done')]

    # ------------------------------------------------------------------ posting to the groups
    def check_post_results(self):
        """A group that keeps failing (not a member, removed) is paused instead of retried every minute."""
        if not self.s.get('pending_post') or self.h['busy']():
            return
        self.s['pending_post'] = 0
        fn = self.h.get('last_results')
        fails = self.s.setdefault('post_fails', {})
        for key, code, msg in (fn() if fn else []):
            if code in ('SUCCESS', 'COOLDOWN'):
                fails[key] = 0
                continue
            if 'disconnected' in str(msg).lower():
                continue
            fails[key] = fails.get(key, 0) + 1
            if fails[key] >= 3:
                fails[key] = 0
                self.s['paused'][key] = now() + 6 * 3600
                self.log(f'{key}: failed 3 times in a row ({str(msg)[:60]}). Paused for 6 hours.')
                self.notify('fail-' + key, f'The {key} group keeps failing ({str(msg)[:90]}). I paused it for 6 hours and keep posting to the others. Check that the linked WhatsApp number is in that group.', 6 * 3600)

    def post_if_due(self):
        if self.quiet_now() or self.h['busy']():
            return
        self.check_post_results()
        name, main_gap, free_gap, _ = self.level()
        last = self.h['last_sent']()
        keys = []
        for key in self.h['groups']():
            if self.blocked(key):
                continue
            gap = self.gap_for(key, main_gap if key == 'main' else free_gap)
            mins = (now() - last[key]) / 60 if last.get(key) else 9999
            if mins >= gap:
                keys.append(key)
        if not keys:
            return
        variant = self._pick_variant()
        if self.h['start_job'](keys, self.h['caption_variant'](variant[1])):
            learning.record_post(self.L, variant[0])
            self.s['pending_post'] = now()
            self.s['posts_today'] += len(keys)
            by = self.s.setdefault('posts_by', {})
            for k in keys:
                by[k] = by.get(k, 0) + 1
            self.log(f'{name}: posting to {len(keys)} group(s): {", ".join(keys)}.')

    def _pick_variant(self):
        """(learning id, index) of the next appeal wording: the one that brought most money, but varied."""
        base = 100 if self.h['variant_pool']() == 'a' else 0
        recent = [v - base for _, v in self.L['recent'][-2:] if base <= v < base + 100]
        idx = learning.pick_variant(self.L, self.h['variant_count'](), avoid=recent)
        return base + idx, idx

    def milestone_if_due(self, left):
        goal = self.h['goal']()
        if not goal or left >= goal or self.quiet_now() or self.h['busy']():
            return
        frac = (goal - left) / goal
        done = set(self.s.setdefault('milestones', []))
        reached = [f for f in MILESTONES if frac >= f]
        if not reached or max(reached) in done:
            return
        top = max(reached)
        if self.h['start_job'](['main'], self.h['milestone_text'](goal - left, left)):
            self.s['milestones'] = sorted(done | set(reached))
            self.log(f'Milestone: {int(top * 100)}% of the goal. Posted a progress update to the main group.')

    def update_if_due(self, left):
        """Post the U1-STRESS update in the main group once the 15-minute gap allows; drop it after 90 minutes."""
        due = self.s.get('update_due')
        if not due or 'update_text' not in self.h:
            return
        if now() - due['at'] > 5400:
            self.s['update_due'] = None
            return
        if self.quiet_now() or self.h['busy']() or self.blocked('main'):
            return
        last = self.h['last_sent']().get('main')
        if last and (now() - last) / 60 < 15:
            return
        if self.h['start_job'](['main'], self.h['update_text'](due['came'], left)):
            self.s['update_due'] = None
            self.log(f'Rs. {due["came"]:,} came: posted the update (not enough yet, Rs. {left:,} left) to the main group.')

    def share_if_due(self):
        if self.level()[0] not in VERY_SLOW or self.s.get('share_day') == self.s['day'] or self.quiet_now() or self.h['busy']():
            return
        last = self.h['last_sent']().get('main')
        if last and (now() - last) / 60 < 15:
            return
        if self.h['start_job'](['main'], self.h['share_text']()):
            self.s['share_day'] = self.s['day']
            self.log('Very slow: asked the main group to share the poster.')

    # ------------------------------------------------------------------ reading chats
    def scan_group_replies(self):
        seen = set(self.s['seen'])
        for key, jid in self.h['group_jids']().items():
            try:
                msgs = self.h['messages'](jid)
            except Exception:
                continue
            for m in msgs:
                mid = m.get('id')
                if not mid or mid in seen or m.get('is_from_me'):
                    continue
                seen.add(mid)
                if _stamp(m) < self.s['started']:
                    continue
                self._group_message(key, jid, m, str(m.get('content') or ''))
        self.s['seen'] = list(seen)[-1000:]

    def _group_message(self, key, jid, m, text):
        who = str(m.get('sender_jid') or m.get('sender') or '').split('@')[0]
        phone = self.h['sender_phone'](m)
        if COMPLAINT.search(text) and key != 'main':
            self.s['paused'][key] = now() + 7 * 86400
            self.notify('complaint-' + key, f'Someone complained in {key} ("{text[:80]}"). I stopped posting there for 7 days. Tell me "resume {key}" to restart.', 600)
        elif PAPERS.search(text) and '?' in text:
            sent = bool(phone) and self.h['send_papers'](phone)
            self._reply(jid, 'I have sent you the medical papers privately. 🤲' if sent else Q1)
            self.notify('papers-' + who, f'{who} asked "{text[:80]}" in {key}. ' + ('I sent the papers privately.' if sent else 'I said papers are available privately. Attach the papers in the studio ("these are the papers") so I can send them myself.'), 600)
        elif self._group_donation(key, text, m):
            self._donor_signal(phone, '', f'{who} posted "{text[:60] or "a picture"}" in {key}', m.get('id'))
        elif LATER.search(text) and phone:
            learning.add_followup(self.L, phone, '', learning.tomorrow_at(11))

    @staticmethod
    def _group_donation(key, text, m):
        """Freelance groups are busy with other talk and pictures: there a donation needs a clear money word."""
        if key == 'main':
            return bool(DONE.search(text)) or m.get('media_type') == 'image'
        return bool(DONE.search(text)) and bool(MONEY_HINT.search(text))

    def _donor_signal(self, phone, name, what, mid):
        """Someone says they donated: remember them, thank them privately, ask them to share, tell the owner."""
        self.s['done_today'] += 1
        if phone:
            learning.add_donor(self.L, phone, name)
            self.thank(phone)
        self.notify('done-' + str(mid), f'{what}. I thanked them privately and asked them to share. Check Easypaisa/JazzCash and tell me the new amount left (for example "34k left").', 0)

    def thank(self, phone):
        """Private thank-you plus a request to share, at most once a day per person."""
        day = self.s['day']
        if self.s.setdefault('thanked', {}).get(phone) == day:
            return
        self.s['thanked'][phone] = day
        self._reply(phone + '@s.whatsapp.net', self.h['thank_text']())

    def scan_dm_replies(self):
        for phone, sent_at in self.h['recent_dms']():
            self._read_dm_chat(phone, sent_at)

    def scan_saved_chats(self):
        """Read the owner's saved chats for appeals he (or an earlier tool) sent by hand and what people answered."""
        for phone, name in self.h['recent_chats']():
            try:
                msgs = self.h['messages'](phone + '@s.whatsapp.net')
            except Exception:
                continue
            ours = [m for m in msgs if m.get('is_from_me') and ACCOUNT in str(m.get('content') or m.get('caption') or '')]
            if ours:
                self._read_dm_chat(phone, min(_stamp(m) for m in ours), msgs, name)

    def _read_dm_chat(self, phone, sent_at, msgs=None, name=''):
        jid = phone + '@s.whatsapp.net'
        if msgs is None:
            try:
                msgs = self.h['messages'](jid)
            except Exception:
                return
        seen = set(self.s['seen'])
        for m in msgs:
            mid = m.get('id')
            if not mid or mid in seen or m.get('is_from_me') or _stamp(m) < sent_at:
                continue
            seen.add(mid)
            self._dm_message(phone, jid, m, str(m.get('content') or ''), name)
        self.s['seen'] = list(seen)[-1000:]

    def _dm_message(self, phone, jid, m, text, name):
        tail, mid = phone[-4:], m.get('id')
        first = name.split(' ')[0] if name else ''
        if OPT_OUT.search(text) and not DONE.search(text):
            self.h['optout'](phone)
            self._reply(jid, 'Sorry for the disturbance. We will not message you again. 🤲')
            self.log(f'…{tail} asked not to be messaged. Removed for good.')
        elif DONE.search(text) or m.get('media_type') == 'image':
            self._donor_signal(phone, first, f'…{tail} replied "{text[:60] or "a picture"}" to our DM', mid)
        elif PAPERS.search(text):
            sent = self.h['send_papers'](phone)
            if not sent:
                self._reply(jid, Q1)
            self.notify('dmpapers-' + tail, f'…{tail} asked about papers. ' + ('I sent them.' if sent else 'Attach the papers in the studio so I can send them.'), 3600)
        elif LATER.search(text):
            if learning.add_followup(self.L, phone, first, learning.tomorrow_at(11)):
                self._reply(jid, 'JazakAllah, take your time. 🤲')
                self.log(f'…{tail} said later. I will remind them gently tomorrow.')
        else:
            replied = self.s.setdefault('replied', {})
            if now() - replied.get(phone, 0) > 3600:
                replied[phone] = now()
                answer = self.h['donor_answer'](text)
                if answer:
                    self._reply(jid, answer)
                    self.log(f'Answered …{tail}: "{text[:50]}"')
                else:
                    self.notify('dmq-' + str(mid), f'…{tail} replied: "{text[:120]}". Please answer them.', 0)

    def _reply(self, jid, text):
        if not self.s.get('dm_enabled') or self.h.get('on_hold',lambda:False)():return
        try:
            self.h['send_text'](jid, text)
        except Exception:
            pass

    def run_followups(self):
        """Gentle reminders for people who said they would donate later."""
        if not self.s.get('dm_enabled') or self.quiet_now() or rules.in_quiet(DM_QUIET[0], DM_QUIET[1], pkt().hour):
            return
        for f in learning.followups_due(self.L)[:3]:
            digest = hashlib.sha256((f['phone'] + '@s.whatsapp.net').encode()).hexdigest()
            self._reply(f['phone'] + '@s.whatsapp.net', self.h['dm_text'](f['name'], 'reminder'))
            self.log(f'Gentle reminder sent to …{f["phone"][-4:]}.')

    # ------------------------------------------------------------------ DMs when donations are very slow
    def _dm_quiet(self):
        return self.quiet_now() or rules.in_quiet(DM_QUIET[0], DM_QUIET[1], pkt().hour)

    def dm_if_due(self):
        if not self.s.get('dm_enabled') or self.dm_running or self._dm_quiet() or self.level()[0] not in VERY_SLOW:
            return
        if self.h.get('dm_busy', lambda: False)():
            return  # the owner's own DM list is sending; never double the rate
        if self.s['dms_today'] >= self.s['dm_daily'] or now() - self.s['last_dm_batch'] < 45 * 60:
            return
        self.s['last_dm_batch'] = now()
        threading.Thread(target=self.dm_batch, daemon=True).start()

    def dm_batch(self):
        """Up to 5 people per batch: past donors first, then donor-labelled contacts, group members, saved chats."""
        self.dm_running = True
        try:
            by = self.s.setdefault('dms_by_tier', {})
            caps = {t: max(0, c - by.get(t, 0)) for t, c in TIER_CAPS.items()}
            if not self.s.get('dm_new'):
                caps['member'] = caps['saved'] = 0
            sent = 0
            for phone, name, tier in self.h['outreach'](caps):
                if sent >= 5 or self.s['dms_today'] >= self.s['dm_daily'] or not self.h['enabled']() or not self.s.get('dm_enabled') or self.h.get('on_hold',lambda:False)() or caps.get(tier, 0) <= 0:
                    continue
                digest = hashlib.sha256((phone + '@s.whatsapp.net').encode()).hexdigest()
                if tier != 'repeat' and self.h['already_dmed'](digest):
                    continue
                result = self.h['send_dm'](phone, self.h['dm_text'](name, tier), digest)
                if result.get('code') != 'SUCCESS':
                    self.notify('dmfail', 'A DM did not go through, so I stopped DMs for now: ' + str(result.get('message', ''))[:100], 3600)
                    break
                sent += 1
                caps[tier] -= 1
                by[tier] = by.get(tier, 0) + 1
                self.s['dms_today'] += 1
                self.h['note_dm'](phone)
                learning.mark_dm(self.L, phone)
                time.sleep(random.uniform(100, 150))
            if sent:
                self.log(f'Sent {sent} DM(s): ' + ', '.join(f'{n} {t}' for t, n in by.items() if n) + ' today.')
        finally:
            self.dm_running = False

    # ------------------------------------------------------------------ reports
    def daily_report(self, left):
        if pkt().hour != 23 or self.s['last_report_day'] == self.s['day']:
            return
        self.s['last_report_day'] = self.s['day']
        away = f' You have been away {round(self.away_hours())} hours; I kept running.' if self.away_hours() > 6 else ''
        notes = ' '.join(learning.insights(self.L, self.h.get('variant_names', lambda: {})()))
        self.notify('report-' + self.s['day'],
                    f'Today: Rs. {left:,} left · {self.s["posts_today"]} group posts · {self.s["dms_today"]} DMs · {self.s["done_today"]} possible donations seen · pace {self.level()[0]}.{away} {notes} Please confirm the amount left.', 0)

    # ------------------------------------------------------------------ settings (owner or AI)
    def pause(self, key, hours):
        self.s['paused'][key] = now() + float(hours) * 3600
        self.save()
        return f'Paused {key} for {hours} hours.'

    def resume(self, key):
        self.s['paused'].pop(key, None)
        self.save()
        return f'Resumed {key}.'

    def set_quiet(self, start, end):
        self.s['quiet'] = None if start == end else [int(start) % 24, int(end) % 24]
        self.save()
        return 'Quiet hours off.' if start == end else f'Quiet hours {int(start):02d}:00 to {int(end):02d}:00.'

    def set_pace(self, main_minutes, freelance_minutes):
        """Owner override of the posting pace. The floor protects the number from WhatsApp limits."""
        if not main_minutes and not freelance_minutes:
            self.s['pace_override'] = None
            self.save()
            return 'Back to the normal pace ladder.'
        m, f = max(15, int(main_minutes or 20)), max(15, int(freelance_minutes or 60))
        self.s['pace_override'] = [m, f]
        self.save()
        note = ' (automatic posting has a 15-minute minimum; manual Send overrides and resets it)' if min(int(main_minutes or 99), int(freelance_minutes or 99)) < 15 else ''
        return f'Pace set: main every {m} min, freelance every {f} min{note}.'

    def set_dms(self, enabled, daily, new_people=None):
        self.s['dm_enabled'] = bool(enabled)
        self.s['dm_daily'] = max(0, int(daily))
        if new_people is not None:
            self.s['dm_new'] = bool(new_people)
        self.save()
        return f'Auto DMs {"on" if enabled else "off"}, up to {int(daily)} a day' + ('' if self.s.get('dm_new') else ', past donors only') + '.'

    def amount_updated(self):
        self.s['last_amount'] = now()
        self.save()

    # ------------------------------------------------------------------ suggestions and live status
    def suggestions(self):
        """What the owner would do next. With Auto on, the engine does the sending ones itself."""
        name, main_gap, free_gap, mins = self.level()
        out = []
        ago = f'{round(mins)} min' if mins < 120 else f'{round(mins / 60)} h'
        last = self.h['last_sent']()
        due = [k for k in self.h['groups']() if not last.get(k) or (now() - last[k]) / 60 >= (main_gap if k == 'main' else free_gap)]
        if name != 'L1' and due:
            out.append({'id': f'post-{int(mins // 30)}', 'level': name, 'action': 'send_all', 'short': f'No money for {ago}: post now',
                        'text': f'No money for {ago}. Post a fresh message to the groups that are due ({len(due)}).'})
        if name in VERY_SLOW and self.s.get('dm_enabled') and self.s['dms_today'] < self.s['dm_daily'] and not self.dm_running:
            out.append({'id': f'dm-{int(mins // 45)}', 'level': name, 'action': 'dm_batch', 'short': 'DM 5 people who may help',
                        'text': f'Still slow ({ago}). DM 5 people (past donors first) with the poster, about 2 minutes apart.'})
        if name in VERY_SLOW and self.s['posts_today'] >= 3:
            out.append({'id': f'photo-{self.s["day"]}', 'level': name, 'action': 'owner', 'short': 'Ask the family for a new photo',
                        'text': 'Several posts and no money. A new photo or an update from the family usually helps. Ask them for one.'})
        if not self.h['has_papers']():
            out.append({'id': 'papers-missing', 'level': 'L1', 'action': 'owner', 'short': 'Attach the medical papers',
                        'text': 'Attach the medical papers once (📎 then "these are the papers"). I will send them privately to anyone who asks.'})
        if name != 'L1' and self.s.get('share_day') != self.s['day']:
            out.append({'id': f'share-{self.s["day"]}', 'level': name, 'action': 'share', 'short': 'Ask groups to share the poster',
                        'text': 'Ask the main group to share the poster on their WhatsApp status. Shares reach new donors for free.'})
        poster = self.h['poster_left']()
        if poster and poster != self.h['read_left']():
            out.append({'id': f'poster-{poster}', 'level': 'L2', 'action': 'owner', 'short': f'Poster shows Rs. {poster:,}',
                        'text': f'The poster still shows Rs. {poster:,}. A poster with the current amount looks more trustworthy.'})
        if 'last_amount' not in self.s:
            out.append({'id': 'amount-first', 'level': 'L2', 'action': 'owner', 'short': 'Tell me the real amount left',
                        'text': 'The amount left is still the starting value. Tell me the real amount (for example "34k left") so every message is right.'})
        elif now() - self.s['last_amount'] > 6 * 3600:
            out.append({'id': f'amount-{int(now() // 21600)}', 'level': 'L2', 'action': 'owner', 'short': 'Update the amount left',
                        'text': 'The amount left has not been updated for 6 hours. Check Easypaisa/JazzCash and tell me (for example "34k left").'})
        return out

    def run_suggestion(self, action):
        if action == 'share':
            if self.h['start_job'](['main'], self.h['share_text']()):
                self.s['share_day'] = self.s['day']
                self.save()
                return 'Asking the main group to share the poster now.'
            return 'Another send is running. Try again in a minute.'
        if action == 'dm_batch':
            if self.dm_running:
                return 'DMs are already being sent.'
            self.s['last_dm_batch'] = now()
            threading.Thread(target=self.dm_batch, daemon=True).start()
            return 'Sending up to 5 DMs now, about 2 minutes apart.'
        return None

    def status(self):
        """What the autopilot is doing right now and what comes next, for the live box on screen."""
        name, main_gap, free_gap, mins = self.level()
        if self.h.get('on_hold', lambda: False)():
            now_text = 'On hold: waiting for you to say resume'
        elif not self.h['wa_ok']():
            now_text = 'Paused: WhatsApp is not connected'
        elif self.h['read_left']() <= 0:
            now_text = 'Goal complete. Nothing more to send'
        elif self.h['busy']():
            now_text = self.h['job_message']() or 'Posting to the groups'
        elif self.dm_running:
            now_text = 'Sending DMs to people who may help'
        elif self.quiet_now():
            now_text = f'Quiet hours until {self.s["quiet"][1]:02d}:00'
        else:
            now_text = 'Watching replies and donations'
        last, nxt = self.h['last_sent'](), []
        for key in self.h['groups']():
            if self.blocked(key):
                continue
            gap = self.gap_for(key, main_gap if key == 'main' else free_gap)
            left_min = 0 if not last.get(key) else max(0, round(gap - (now() - last[key]) / 60))
            nxt.append({'group': key, 'in': left_min})
        nxt.sort(key=lambda x: x['in'])
        return {'now': now_text, 'pace': name, 'why': self.rhythm()[1], 'next': nxt[:3], 'away_hours': round(self.away_hours(), 1),
                'today': {'posts': self.s['posts_today'], 'dms': self.s['dms_today'], 'signals': self.s['done_today']},
                'learned': learning.insights(self.L, self.h.get('variant_names', lambda: {})())}

    def summary(self):
        name, main_gap, free_gap, mins = self.level()
        return {'pace': name, 'main_every': main_gap, 'freelance_every': free_gap, 'minutes_since_money': round(mins),
                'paused': {k: round((v - now()) / 3600, 1) for k, v in self.s['paused'].items() if v > now()},
                'quiet': self.s['quiet'], 'pace_override': self.s.get('pace_override'), 'posts_today': self.s['posts_today'],
                'dms_today': self.s['dms_today'], 'dm_daily': self.s['dm_daily'], 'dm_enabled': self.s['dm_enabled'],
                'dm_new': self.s.get('dm_new', True), 'possible_donations_today': self.s['done_today']}

