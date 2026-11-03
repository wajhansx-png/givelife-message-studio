"""Read-only daily planning. No send, model, payment, or staff mutation tools.

The only writes are a durable occurrence claim and its completed audit report.
Approval proposals are deliberately not executable jobs.
"""
import datetime as dt
import hashlib
import json
import math
import os
import secrets
import urllib.parse
from collections import Counter

PKT = dt.timezone(dt.timedelta(hours=5))


def money(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100_000_000:
        raise ValueError('Campaign amounts need review.')
    return value


def build_review(data):
    if not isinstance(data, dict) or not isinstance(data.get('case_id'), str) or not data['case_id']:
        raise ValueError('An active case is required.')
    remaining = money(data.get('remaining'))
    donated = money(data.get('recorded_donated'))
    donors = data.get('donors')
    if not isinstance(donors, list) or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in donors):
        raise ValueError('Donor records need review.')
    for flag in ('auto_on', 'hold', 'dm_paused', 'group_message_ready', 'dm_message_ready', 'reply_enabled'):
        if type(data.get(flag)) is not bool:
            raise ValueError('Automation status needs review.')
    jobs = data.get('jobs')
    if not isinstance(jobs, list) or any(not isinstance(j, dict) for j in jobs):
        raise ValueError('Delivery records need review.')
    queues = {'top': [], 'important': []}
    issues = []
    counts = {}
    ids = [r['id'] for r in donors]
    duplicates = {ident for ident, count in Counter(ids).items() if count > 1}
    if duplicates: issues.append('duplicate_donor_ids')
    excluded = set(data.get('excluded_ids', []))
    reserved = set(data.get('reserved_ids', []))
    decisions = []
    for row in donors:
        reason = None
        if row.get('deleted'): reason = 'deleted'
        elif row['id'] in duplicates: reason = 'duplicate_record'
        elif row['id'] in excluded: reason = 'not_eligible'
        elif row.get('dm_sent') or row.get('last_sent_at') or row.get('delivery') == 'Sent': reason = 'already_contacted'
        elif row.get('delivery') in ('Sending', 'Uncertain'): reason = 'unconfirmed_delivery'
        elif row['id'] in reserved: reason = 'existing_reservation'
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
            decisions.append({'donor_id': row['id'], 'decision': 'exclude', 'reason': reason})
            continue
        for scope, flag, field in [('top', 'top_donor', 'top_order'), ('important', 'important', 'important_order')]:
            if row.get(flag):
                if type(row.get(field)) is int and row[field] > 0:
                    queues[scope].append((row[field], row['id']))
                else:
                    counts['missing_rank'] = counts.get('missing_rank', 0) + 1
                    decisions.append({'donor_id': row['id'], 'decision': 'exclude_from_' + scope, 'reason': 'missing_rank'})
    for scope, rows in queues.items():
        ranks = [rank for rank, _ in rows]
        if len(ranks) != len(set(ranks)):
            issues.append('duplicate_' + scope + '_ranks'); queues[scope] = []
        else:
            queues[scope] = [ident for _, ident in sorted(rows)]
            decisions.extend({'donor_id': ident, 'decision': 'candidate_for_' + scope, 'reason': 'uncontacted_in_saved_order'} for ident in queues[scope])
    proposals = []
    def propose(kind, reason, evidence):
        proposals.append({'kind': kind, 'reason': reason, 'evidence': evidence, 'approval_required': True})
    if remaining == 0: issues.append('case_has_no_remaining_balance')
    if data['hold']: issues.append('all_sending_on_hold')
    if data['dm_paused']: issues.append('personal_dms_paused')
    for kind in ('group', 'dm'):
        if not data[kind + '_message_ready']: issues.append(kind + '_draft_missing')
    running = any(j.get('state') in ('Starting', 'Sending', 'Waiting') for j in jobs)
    if running: issues.append('existing_donor_batch')
    if not issues and any(queues.values()):
        propose('review_donor_batch', 'Review eligible donors in their saved order; no sends were started.',
                {'queues': queues, 'selection_required': True, 'gap_required': True})
    possible = data.get('possible_donations')
    if type(possible) is not int or possible < 0: raise ValueError('Receipt count needs review.')
    if possible:
        propose('verify_possible_receipts', 'A receipt or Done reply does not prove payment.', {'possible_receipts': possible})
    team = data.get('team')
    if not isinstance(team, dict) or not isinstance(team.get('tasks', []), list): raise ValueError('Staff records need review.')
    member = team.get('member') or {}
    if not isinstance(member, dict): raise ValueError('Staff connection needs review.')
    # Only known role names are disclosed; arbitrary donor/staff text is untrusted.
    name = str(member.get('name', '')).strip().casefold()
    connected = {'areeba': 'Areeba', 'akhtar': 'Akhtar'}.get(name, 'Other teammate' if name else None)
    missing = [n for n in ('Areeba', 'Akhtar') if n != connected]
    if missing: propose('review_staff_connections', 'The current app connects one teammate. No assignment was sent.', {'not_connected': missing})
    reported = sum(isinstance(t, dict) and t.get('status') == 'Reported' for t in team.get('tasks', []))
    if reported: propose('verify_staff_reports', 'Reported work still needs owner verification.', {'reported': reported})
    return {
        'mode': 'review_only', 'case_id': data['case_id'], 'remaining': remaining,
        'automation': {'auto_on': data['auto_on'], 'hold': data['hold'], 'dm_paused': data['dm_paused'],
                       'reply_enabled': data['reply_enabled'], 'running_donor_batch': running},
        'groups': data.get('groups', {}), 'donor_queues': queues, 'excluded_counts': counts, 'decisions': decisions,
        'donations': {'owner_recorded_amount': donated, 'possible_receipts': possible, 'payment_verification': 'not_connected'},
        'staff': {'connected': connected, 'not_connected': missing, 'reported_tasks': reported},
        'issues': issues, 'proposals': proposals, 'outbound_messages': 0, 'ai_calls': 0,
        'notice': 'This is a saved review, not a send schedule. All proposed actions need approval and a fresh eligibility check.',
    }


class OperationsReview:
    def __init__(self, store, collect):
        self.store, self.collect = store, collect

    @staticmethod
    def key(case_id, day):
        return 'operations_review:' + day + ':' + hashlib.sha256(case_id.encode()).hexdigest()[:24]

    def run(self, now=None):
        if self.store is None or not callable(getattr(self.store, 'claim', None)):
            raise ValueError('Daily reviews require durable database claims. Nothing was started.')
        now = now or dt.datetime.now(dt.timezone.utc)
        if now.tzinfo is None: raise ValueError('Review time must include a timezone.')
        day = now.astimezone(PKT).date().isoformat()
        # Validate before claiming; database/snapshot failures cannot leave a fake plan.
        report = build_review(self.collect())
        key = self.key(report['case_id'], day)
        pending = {'state': 'building', 'day': day, 'created_at': now.isoformat(), 'case_id': report['case_id']}
        if not self.store.claim(key, pending):
            prior = self.store.get(key)
            if not isinstance(prior, dict): raise ValueError('Saved review needs inspection.')
            return {**prior, 'duplicate': True}
        result = {**pending, 'state': 'ready_for_review', 'report': report}
        self.store.put(key, result)
        return {**result, 'duplicate': False}


def collect_app(app):
    """Read existing sources without invoking send loops or mutating public views."""
    # Cases applies new records before saving current. The same transition lock
    # is essential: checking current twice alone can still accept mixed facts.
    with app.LOCK:
        hub = app.donors()
    with hub.cases.lock:
        return _collect_app_locked(app)


def _collect_app_locked(app):
    from donor_book import normalize_phone
    store = app.STORE
    keys = ['cases', 'donor_book', 'donor_delivery', 'team', 'donor_dm_pause', 'reply_setup']
    raw = store.get_many(keys) if hasattr(store, 'get_many') else {k: store.get(k) for k in keys}
    def obj(key):
        value = raw.get(key) or {}
        if isinstance(value, str): value = json.loads(value)
        if not isinstance(value, dict): raise ValueError('Stored ' + key + ' needs inspection.')
        return value
    cases, book, delivery, team = (obj(k) for k in keys[:4])
    rows = book.get('records', [])
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows): raise ValueError('Donor records need inspection.')
    excluded, reserved = [], set()
    jobs = delivery.get('jobs', [])
    if not isinstance(jobs, list) or any(not isinstance(j, dict) for j in jobs): raise ValueError('Delivery records need inspection.')
    for job in jobs:
        if job.get('state') in ('Starting', 'Sending', 'Waiting', 'Stopped', 'Interrupted'):
            reserved.update(job.get('ids', []))
        for receipt in job.get('receipts', []):
            if receipt.get('state') in ('Sent', 'Uncertain'): reserved.add(receipt.get('id'))
    lookups = {}
    valid_phones = {}
    for row in rows:
        try: phone = normalize_phone(row.get('phone'))
        except ValueError:
            excluded.append(row.get('id')); continue
        digests = [hashlib.sha256(j.encode()).hexdigest() for j in (phone, phone + '@s.whatsapp.net')]
        if phone == normalize_phone(app.OWNER_PHONE) or any(d in app.BLOCKED - app.CAMPAIGN_CONTACTED for d in digests):
            excluded.append(row.get('id')); continue
        valid_phones[row.get('id')] = (phone, digests)
        lookups.update({prefix + d: None for d in digests for prefix in ('optout_', 'dm_recipient_')})
    values = store.get_many(lookups) if hasattr(store, 'get_many') else {key: store.get(key) for key in lookups}
    phone_counts = Counter(phone for phone, _ in valid_phones.values())
    for ident, (phone, digests) in valid_phones.items():
        if phone_counts[phone] > 1: excluded.append(ident)
        if any(values.get('optout_' + d) for d in digests): excluded.append(ident)
        if any(values.get('dm_recipient_' + d) for d in digests): reserved.add(ident)
    with app.LOCK:
        # Read live values used by existing senders. Do not re-capture archived cases.
        remaining = app.read_left()
        drafts = json.loads(app.DRAFT.read_text(encoding='utf-8-sig'))
        auto_on, hold = app.auto_on(), app.on_hold()
        last_sent = app.dashboard_send_times()
    with app.ENGINE.lock:
        state = dict(app.ENGINE.s)
    groups = {key: {'paused': state.get('paused', {}).get(key, 0) > dt.datetime.now().timestamp(),
                     'last_confirmed_at': last_sent.get(key, 0)} for key in app.GROUPS}
    if not isinstance(drafts, dict): raise ValueError('Saved drafts need inspection.')
    if any(not isinstance(drafts.get(kind, ''), str) for kind in ('group', 'dm')):
        raise ValueError('Saved messages must be text.')
    if (store.get('cases') or {}).get('current') != cases.get('current'):
        raise ValueError('The active case changed during review. Try again.')
    donated = sum(money(r.get('amount') or 0) for r in rows if r.get('donated') and not r.get('deleted'))
    return {'case_id': cases.get('current'), 'remaining': remaining,
            'auto_on': auto_on, 'hold': hold, 'dm_paused': bool(raw.get('donor_dm_pause')),
            'group_message_ready': bool(str(drafts.get('group') or '').strip()),
            'dm_message_ready': bool(str(drafts.get('dm') or '').strip()),
            'reply_enabled': bool(obj('reply_setup').get('enabled')),
            'donors': rows, 'excluded_ids': excluded, 'reserved_ids': list(reserved), 'jobs': jobs,
            'team': team, 'recorded_donated': donated, 'groups': groups,
            'possible_donations': state.get('done_today', 0) if state.get('day') == dt.datetime.now(PKT).date().isoformat() else 0}


def handle_http(handler, app):
    """A narrow machine credential never grants access to other studio endpoints."""
    key = os.environ.get('OPERATIONS_REVIEW_KEY', '')
    machine = bool(len(key) >= 32) and secrets.compare_digest(handler.headers.get('Authorization', ''), 'Bearer ' + key)
    if not machine and not handler.authorized():
        return handler.reply({'error': 'Review access required.'}, status=401)
    origin = handler.headers.get('Origin')
    if origin and urllib.parse.urlparse(origin).netloc != handler.headers.get('Host') and origin not in handler.remote_config().get('origins', []):
        return handler.reply({'error': 'Origin not allowed.'}, status=403)
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 1024: raise ValueError()
        body = json.loads(handler.rfile.read(length))
        if body != {}: raise ValueError()
    except (ValueError, TypeError):
        return handler.reply({'error': 'Send an empty JSON object. This endpoint only reviews existing records.'}, status=400)
    try:
        result = OperationsReview(app.STORE, lambda: collect_app(app)).run()
    except Exception:
        return handler.reply({'error': 'Daily review could not be saved reliably. Check the database and campaign records. Nothing was sent.'}, status=503)
    return handler.reply(result, status=200 if result['state'] == 'ready_for_review' else 409)
