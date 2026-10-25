"""Autopilot engine: runs the owner's routine without him, inside hard safety limits.

Never changes the amount left (only the owner can), never invents facts, never sends to unknown groups.
"""
import json, re, time, datetime, threading, random, hashlib, os, urllib.request

PKT = datetime.timezone(datetime.timedelta(hours=5))
# Escalation ladder from the owner's playbook: minutes between posts by minutes since money last came.
LADDER = [(90, 'L3', 15, 30), (40, 'L2', 15, 45), (0, 'L1', 20, 60)]
DONE = re.compile(r"\b(done|sent|send kar diya|bhej diya|kar diya|transferred|paid|donated|jazakallah)\b", re.I)
PAPERS = re.compile(r"\b(real|fake|papers?|proof|reports?|documents?|verify|genuine|scam)\b", re.I)
COMPLAINT = re.compile(r"\b(spam|stop posting|stop sending|remove (me|this)|not allowed|report(ed)?|admin|irrelevant|don'?t post)\b", re.I)
OPT_OUT = re.compile(r"\b(stop|unsubscribe|don'?t (message|msg|dm) me|not interested|block)\b", re.I)
Q1 = 'Yes, medical papers are available. I will send them to you privately.'


def now():
    return time.time()


def pkt():
    return datetime.datetime.now(PKT)


class Engine:
    def __init__(self, h):
        """h: dict of helpers from server.py."""
        self.h = h
        self.f = h['DATA'] / 'autopilot-state.json'
        self.lock = threading.Lock()
        self.s = self.load()
        self.dm_running = False

    # ---------- state ----------
    def load(self):
        base = {'last_money': None, 'left_seen': None, 'paused': {}, 'quiet': None, 'seen': [], 'notified': {},
                'day': None, 'posts_today': 0, 'dms_today': 0, 'done_today': 0, 'last_dm_batch': 0,
                'dm_daily': int(os.environ.get('AUTO_DM_DAILY', '30')), 'dm_enabled': True,
                'last_scan': 0, 'last_report_day': None, 'last_advisor': 0, 'started': now()}
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

    def log(self, text):
        self.h['log'](text)

    def notify(self, key, text, every=3600):
        """WhatsApp message to the owner's own number, at most once per `every` seconds per key."""
        if now() - self.s['notified'].get(key, 0) < every:
            return
        self.s['notified'][key] = now()
        try:
            self.h['send_text'](self.h['owner_jid'](), 'GiveLife autopilot: ' + text)
        except Exception:
            pass
        self.log('Told owner: ' + text)

    # ---------- main loop ----------
    def start(self):
        threading.Thread(target=self.loop, daemon=True).start()
        if os.environ.get('RENDER_EXTERNAL_URL'):
            threading.Thread(target=self.keepalive, daemon=True).start()

    def keepalive(self):
        url = os.environ['RENDER_EXTERNAL_URL'].rstrip('/') + '/health'
        while True:
            time.sleep(600)
            try:
                urllib.request.urlopen(url, timeout=20).read()
            except Exception:
                pass

    def loop(self):
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
        today = pkt().date().isoformat()
        if self.s['day'] != today:
            self.s.update(day=today, posts_today=0, dms_today=0, done_today=0)
        left = self.h['read_left']()
        if self.s['left_seen'] is not None and left < self.s['left_seen']:
            self.s['last_money'] = now()
            self.log(f'Money noticed: Rs. {self.s["left_seen"] - left:,}. Back to normal pace.')
        self.s['left_seen'] = left
        if not self.h['wa_ok']():
            return self.notify('wa', 'WhatsApp is disconnected. Open the studio and link WhatsApp again. Nothing is being sent.', 3 * 3600)
        if left <= 0:
            if not self.s.get('d1_done'):
                self.s['d1_done'] = True
                self.h['post_text_all'](self.h['done_text']())
                self.log('Goal complete: completion message posted to all groups. Posting stopped.')
            return self.notify('goal', 'The goal is complete (Rs. 0 left). I posted the completion message and stopped. Set up the next case when ready.', 86400)
        self.s['d1_done'] = False
        if now() - self.s['last_scan'] >= 300:
            self.s['last_scan'] = now()
            self.scan_replies()
        if now() - self.s.get('last_dm_scan', 0) >= 600:
            self.s['last_dm_scan'] = now()
            self.scan_dms()
        self.post_if_due()
        self.share_if_due()
        self.dm_if_due()
        for sg in self.suggestions():  # things only the owner can do: tell him once
            if sg['action'] == 'owner':
                self.notify('sg-' + sg['id'], sg['text'], 6 * 3600)
        self.daily_report(left)

    # ---------- posting ----------
    def quiet_now(self):
        q = self.s.get('quiet')
        if not q:
            return False
        hr = pkt().hour
        a, b = q
        return a <= hr < b if a < b else (hr >= a or hr < b)

    def post_if_due(self):
        if self.quiet_now() or self.h['busy']():
            return
        name, main_gap, free_gap, _ = self.level()
        last = self.h['last_sent']()
        keys = []
        for key in self.h['groups']():
            until = self.s['paused'].get(key, 0)
            if until and now() < until:
                continue
            gap = main_gap if key == 'main' else free_gap
            mins = (now() - last[key]) / 60 if last.get(key) else 9999
            if mins >= gap:
                keys.append(key)
        if not keys:
            return
        caption = self.h['caption']()
        if self.h['start_job'](keys, caption):
            self.s['posts_today'] += len(keys)
            self.log(f'{name}: posting to {len(keys)} group(s): {", ".join(keys)}.')

    # ---------- replies in groups ----------
    def scan_replies(self):
        seen = set(self.s['seen'])
        since = self.s['started']
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
                try:
                    ts = datetime.datetime.fromisoformat(str(m.get('timestamp', '')).replace('Z', '+00:00')).timestamp()
                except Exception:
                    ts = now()
                if ts < since:
                    continue
                text = str(m.get('content') or '')
                who = str(m.get('sender_jid') or m.get('sender') or '').split('@')[0]
                phone = self.h['sender_phone'](m)
                if COMPLAINT.search(text) and key != 'main':
                    self.s['paused'][key] = now() + 7 * 86400
                    self.notify('complaint-' + key, f'Someone complained in {key} ("{text[:80]}"). I stopped posting there for 7 days. Tell me "resume {key}" to restart.', 600)
                elif PAPERS.search(text) and '?' in text:
                    sent = bool(phone) and self.h['send_papers'](phone)
                    try:
                        self.h['send_text'](jid, 'I have sent you the medical papers privately. 🤲' if sent else Q1)
                    except Exception:
                        pass
                    self.notify('papers-' + who, f'{who} asked "{text[:80]}" in {key}. ' + ('I sent the papers privately.' if sent else 'I said papers are available privately. Attach the papers in the studio ("these are the papers") so I can send them myself.'), 600)
                elif DONE.search(text) or m.get('media_type') == 'image':
                    self.s['done_today'] += 1
                    if phone:
                        self.thank(phone)
                    self.notify('done-' + str(mid), f'{who} posted "{text[:60] or "a picture"}" in {key}. I thanked them privately and asked them to share. Check Easypaisa/JazzCash and tell me the new amount left (for example "34k left").', 0)
        self.s['seen'] = list(seen)[-800:]

    def thank(self, phone):
        """Private thank-you plus a request to share, at most once a day per person."""
        day = self.s['day']
        if self.s.setdefault('thanked', {}).get(phone) == day:
            return
        self.s['thanked'][phone] = day
        try:
            self.h['send_text'](phone + '@s.whatsapp.net', self.h['thank_text']())
        except Exception:
            pass

    # ---------- replies to our DMs ----------
    def scan_dms(self):
        seen = set(self.s['seen'])
        replied = self.s.setdefault('replied', {})
        for phone, sent_at in self.h['recent_dms']():
            jid = phone + '@s.whatsapp.net'
            try:
                msgs = self.h['messages'](jid)
            except Exception:
                continue
            for m in msgs:
                mid = m.get('id')
                if not mid or mid in seen or m.get('is_from_me'):
                    continue
                seen.add(mid)
                try:
                    ts = datetime.datetime.fromisoformat(str(m.get('timestamp', '')).replace('Z', '+00:00')).timestamp()
                except Exception:
                    ts = now()
                if ts < sent_at:
                    continue
                text = str(m.get('content') or '')
                tail = phone[-4:]
                if OPT_OUT.search(text) and not DONE.search(text):
                    self.h['optout'](phone)
                    self._reply(jid, 'Sorry for the disturbance. We will not message you again. 🤲')
                    self.log(f'…{tail} asked not to be messaged. Removed for good.')
                elif DONE.search(text) or m.get('media_type') == 'image':
                    self.s['done_today'] += 1
                    self.thank(phone)
                    self.notify('dmdone-' + str(mid), f'…{tail} replied "{text[:60] or "a picture"}" to our DM. I thanked them and asked them to share. Check Easypaisa/JazzCash and tell me the new amount left.', 0)
                elif PAPERS.search(text):
                    sent = self.h['send_papers'](phone)
                    if not sent:
                        self._reply(jid, Q1)
                    self.notify('dmpapers-' + tail, f'…{tail} asked about papers. ' + ('I sent them.' if sent else 'Attach the papers in the studio so I can send them.'), 3600)
                elif now() - replied.get(phone, 0) > 3600:
                    replied[phone] = now()
                    answer = self.h['donor_answer'](text)
                    if answer:
                        self._reply(jid, answer)
                        self.log(f'Answered …{tail}: "{text[:50]}"')
                    else:
                        self.notify('dmq-' + str(mid), f'…{tail} replied: "{text[:120]}". Please answer them.', 0)
        self.s['seen'] = list(seen)[-800:]

    def _reply(self, jid, text):
        try:
            self.h['send_text'](jid, text)
        except Exception:
            pass

    # ---------- share request when donations are very slow ----------
    def share_if_due(self):
        name = self.level()[0]
        if name != 'L3' or self.s.get('share_day') == self.s['day'] or self.quiet_now() or self.h['busy']():
            return
        last = self.h['last_sent']().get('main')
        if last and (now() - last) / 60 < 15:
            return
        if self.h['start_job'](['main'], self.h['share_text']()):
            self.s['share_day'] = self.s['day']
            self.log('Very slow: asked the main group to share the poster.')

    # ---------- DMs to donor contacts ----------
    def dm_if_due(self):
        if not self.s.get('dm_enabled') or self.dm_running or self.quiet_now():
            return
        name, _, _, _ = self.level()
        if name != 'L3' or self.s['dms_today'] >= self.s['dm_daily'] or now() - self.s['last_dm_batch'] < 45 * 60:
            return
        self.s['last_dm_batch'] = now()
        threading.Thread(target=self.dm_batch, daemon=True).start()

    def dm_batch(self):
        self.dm_running = True
        try:
            people = self.h['donor_contacts']()
            sent = 0
            for phone, name in people:
                if sent >= 5 or self.s['dms_today'] >= self.s['dm_daily'] or not self.h['enabled']():
                    break
                digest = hashlib.sha256((phone + '@s.whatsapp.net').encode()).hexdigest()
                if self.h['already_dmed'](digest):
                    continue
                text = self.h['dm_text'](name)
                result = self.h['send_dm'](phone, text, digest)
                if result.get('code') != 'SUCCESS':
                    self.notify('dmfail', 'A DM did not go through, so I stopped DMs for now: ' + str(result.get('message', ''))[:100], 3600)
                    break
                sent += 1
                self.s['dms_today'] += 1
                self.h['note_dm'](phone)
                time.sleep(random.uniform(100, 150))
            if sent:
                self.log(f'Sent {sent} DM(s) to donor contacts.')
        finally:
            self.dm_running = False

    # ---------- daily report ----------
    def daily_report(self, left):
        if pkt().hour != 23 or self.s['last_report_day'] == self.s['day']:
            return
        self.s['last_report_day'] = self.s['day']
        name = self.level()[0]
        self.notify('report-' + self.s['day'], f'Today: Rs. {left:,} left · {self.s["posts_today"]} group posts · {self.s["dms_today"]} DMs · {self.s["done_today"]} possible donations seen · pace {name}. Please confirm the amount left.', 0)

    # ---------- settings the owner (or the AI, from his rules) can change ----------
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
        """Owner override of the posting pace. Floors protect the number from WhatsApp limits."""
        if not main_minutes and not freelance_minutes:
            self.s['pace_override'] = None
            self.save()
            return 'Back to the normal pace ladder.'
        m, f = max(15, int(main_minutes or 20)), max(15, int(freelance_minutes or 60))
        self.s['pace_override'] = [m, f]
        self.save()
        note = ' (15 minutes is the fastest WhatsApp safely allows per group)' if min(int(main_minutes or 99), int(freelance_minutes or 99)) < 15 else ''
        return f'Pace set: main every {m} min, freelance every {f} min{note}.'

    def set_dms(self, enabled, daily):
        self.s['dm_enabled'] = bool(enabled)
        self.s['dm_daily'] = max(0, int(daily))
        self.save()
        return f'Auto DMs {"on" if enabled else "off"}, up to {int(daily)} a day.'

    def amount_updated(self):
        self.s['last_amount'] = now()
        self.save()

    def suggestions(self):
        """What the owner would do next. In autopilot the engine already does the sending ones itself."""
        name, main_gap, free_gap, mins = self.level()
        out = []
        last = self.h['last_sent']()
        due = [k for k in self.h['groups']() if not last.get(k) or (now() - last[k]) / 60 >= (main_gap if k == 'main' else free_gap)]
        if name != 'L1' and due:
            out.append({'id': f'post-{int(mins // 30)}', 'level': name, 'action': 'send_all',
                        'text': f'No money for {round(mins)} min. Post a fresh message to the groups that are due ({len(due)}).'})
        if name == 'L3' and self.s.get('dm_enabled') and self.s['dms_today'] < self.s['dm_daily'] and not self.dm_running:
            out.append({'id': f'dm-{int(mins // 45)}', 'level': name, 'action': 'dm_batch',
                        'text': f'Still slow ({round(mins)} min). DM 5 donor contacts with the poster, about 2 minutes apart.'})
        if name == 'L3' and self.s['posts_today'] >= 3:
            out.append({'id': f'photo-{self.s["day"]}', 'level': name, 'action': 'owner',
                        'text': 'Several posts and no money. A new photo or an update from the family usually helps. Ask them for one.'})
        if not self.h['has_papers']():
            out.append({'id': 'papers-missing', 'level': 'L1', 'action': 'owner',
                        'text': 'Attach the medical papers once (📎 then "these are the papers"). I will send them privately to anyone who asks.'})
        if name != 'L1' and self.s.get('share_day') != self.s['day']:
            out.append({'id': f'share-{self.s["day"]}', 'level': name, 'action': 'share',
                        'text': 'Ask the main group to share the poster on their WhatsApp status. Shares reach new donors for free.'})
        poster = self.h['poster_left']()
        if poster and poster != self.h['read_left']():
            out.append({'id': f'poster-{poster}', 'level': 'L2', 'action': 'owner',
                        'text': f'The poster still shows Rs. {poster:,}. A poster with the current amount looks more trustworthy.'})
        if now() - self.s.get('last_amount', self.s['started']) > 6 * 3600:
            out.append({'id': f'amount-{int(now() // 21600)}', 'level': 'L2', 'action': 'owner',
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
            return 'Sending up to 5 donor DMs now, about 2 minutes apart.'
        return None

    def summary(self):
        name, main_gap, free_gap, mins = self.level()
        return {'pace': name, 'main_every': main_gap, 'freelance_every': free_gap, 'minutes_since_money': round(mins),
                'paused': {k: round((v - now()) / 3600, 1) for k, v in self.s['paused'].items() if v > now()},
                'quiet': self.s['quiet'], 'pace_override': self.s.get('pace_override'), 'posts_today': self.s['posts_today'], 'dms_today': self.s['dms_today'],
                'dm_daily': self.s['dm_daily'], 'dm_enabled': self.s['dm_enabled'], 'possible_donations_today': self.s['done_today']}
