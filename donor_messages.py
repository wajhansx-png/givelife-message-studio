"""Instant, editable wording bank from the saved DM or an owner-supplied message."""
import copy, hashlib, json, threading, time

import dm_composer
import dm_templates
import dm_variants
import draft_workflow


class MessageBank:
    def __init__(self, app):
        self.app = app
        self.path = app.DATA / 'donor-messages.json'
        self.lock = threading.RLock()
        self.gen_lock = threading.Lock()
        self.cache = None

    def _source(self):
        return self.app.get_message('dm')['text']

    def _fingerprint(self, source):
        return hashlib.sha256((dm_templates.VERSION + '\0' + str(source or '')).encode()).hexdigest()

    def _guard(self):
        """A long generation must not overwrite a newer owner instruction."""
        guard = getattr(self.app, 'OWNER_GUARD', None)
        revision = getattr(guard, 'revision', None)
        current = getattr(self.app, 'OWNER_REVISION', None)
        if revision is not None and current is not None and revision != current:
            raise ValueError('Superseded by your newer instruction. The message bank was not changed.')

    def _save(self, data):
        if self.app.STORE:
            self.app.STORE.put('donor_messages', data)
        self.cache = copy.deepcopy(data)
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def _entries(self, texts):
        return [{'id': f'wording-{i + 1:02d}', 'text': text, 'enabled': True} for i, text in enumerate(texts)]

    def _sync_amount(self, data):
        """Keep a custom bank aligned with the current campaign balance."""
        try:
            current = self.app.read_left()
        except (OSError, ValueError, TypeError):
            return
        old = data.get('left')
        if not isinstance(old, int) or old == current:
            data['left'] = current
            return
        changed = False
        for row in data.get('items', []):
            if isinstance(row, dict) and isinstance(row.get('text'), str):
                row['text'] = draft_workflow.update_amount(row['text'], old, current)
                changed = True
        data['left'] = current
        if changed:
            data['updated_at'] = time.time()
            self._save(data)

    def _build(self, source):
        left = self.app.read_left()
        case_name = self.app.active_case_name()
        # A new case must never inherit Yousuf's medical symptoms or name from
        # the legacy message bank; generic drafts are used until facts are entered.
        if case_name.casefold() in ('yousuf','current case'):
            messages=[dm_templates.build(i, left) for i in range(dm_templates.COUNT)]
        else:
            messages=[self.app.build_dm(i, left, case_name) for i in range(dm_templates.COUNT)]
        entries = self._entries(messages)
        return {
            'fingerprint': self._fingerprint(source),
            'items': entries,
            'updated_at': time.time(),
            'source': 'Structured saved DM; varied wording, not a delivery guarantee',
            'mode': 'structured',
            'origin': str(source or ''),
            'requested': dm_templates.PRIMARY_COUNT,
            'left': left,
        }

    def get(self):
        with self.lock:
            source = self._source()
            fingerprint = self._fingerprint(source)
            if self.cache is None:
                self.cache = self.app.STORE.get('donor_messages') if self.app.STORE else None
                if self.cache is None and self.path.exists():
                    self.cache = json.loads(self.path.read_text(encoding='utf-8'))
            # A custom bank is deliberately kept after the DM screen changes.
            # It is only replaced by an explicit regenerate or a new generate.
            if isinstance(self.cache, dict) and self.cache.get('mode') == 'custom':
                self._sync_amount(self.cache)
                return copy.deepcopy(self.cache)
            if not isinstance(self.cache, dict) or self.cache.get('fingerprint') != fingerprint:
                self._save(self._build(source))
            return copy.deepcopy(self.cache)

    def generate(self, source, count=10, total=20, master_first=False):
        """Build a bank from a pasted message. Returns the saved bank."""
        source = dm_variants.clean_source(source)
        if not dm_composer.complete(source):
            raise ValueError('Paste the complete message with its paragraphs, amount and payment details.')
        count = max(1, min(20, int(count or 10)))
        total = max(count, min(20, int(total or 20)))
        with self.gen_lock:
            warning = ''
            # Regenerate always uses the current saved Message 1, never the
            # initial template or an older hidden source. Keep it unmodified.
            canonical = dm_templates.matches(source) and not master_first
            left = self.app.read_left()
            if canonical:
                texts = [dm_templates.build(i, left) for i in range(total)]
                requested = count
            elif master_first:
                texts = [source]
                need = min(count - 1, total - 1)
                if need:
                    texts += dm_variants.generate(source, need, avoid=texts)
                requested = count
                if total > len(texts):
                    try:
                        texts += dm_variants.generate(source, total - len(texts), avoid=texts)
                    except ValueError as exc:
                        warning = str(exc)
            else:
                texts = dm_variants.generate(source, count)
                requested = len(texts)
                if total > len(texts):
                    try:
                        texts += dm_variants.generate(source, total - len(texts), avoid=texts)
                    except ValueError as exc:
                        warning = str(exc)
            texts = texts[:20]
            if master_first and (len(texts) != total or len(set(texts)) != total):
                raise ValueError(
                    f'Only {len(texts) - 1} of {total - 1} substantially rewritten versions passed verification. '
                    'Nothing was replaced; Message 1 and all previous messages are still saved. '
                    + (warning or 'Retry regeneration when the AI service is ready.')
                )
            data = {
                'fingerprint': self._fingerprint(source),
                'items': self._entries(texts),
                'updated_at': time.time(),
                'source': 'Generated from saved Message 1; same facts and formatting' if master_first else 'Generated from the message you supplied; same structure and facts',
                'mode': 'structured' if canonical else 'custom',
                'origin': source,
                'requested': min(requested, len(texts)),
                'warning': warning,
                'left': left,
            }
            self._guard()
            with self.lock:
                if master_first:
                    live = self.get()
                    primary = live.get('items',[{}])[0].get('text') if live.get('items') else None
                    if primary != source:
                        raise ValueError('Message 1 changed while regenerating. Your latest edit is safe. Click Regenerate again.')
                    # A donation can change the balance during an AI call.
                    self._sync_amount(data)
                self._save(data)
            return copy.deepcopy(data)

    def update(self, ident, text):
        if not isinstance(text, str) or len(text) > 10000 or not dm_composer.complete(text):
            raise ValueError('Keep the complete case message, paragraphs, remaining amount and payment details.')
        with self.lock:
            data = self.get()
            row = next((r for r in data['items'] if r['id'] == ident), None)
            if row is None:
                raise ValueError('Message not found.')
            row['text'] = text
            if ident == 'wording-01':
                # An owner-edited master becomes authoritative even when the
                # main DM draft is later changed in the other app screen.
                data['mode'] = 'custom'
                data['origin'] = text
                data['fingerprint'] = self._fingerprint(text)
            data['updated_at'] = time.time()
            self._save(data)
            return {'saved': True, 'item': row}

    def regenerate(self):
        with self.lock:
            data = self.get()
            # Message 1 is the single source of truth, including its edits,
            # emotional angle, bold/italic positions, spacing and CTA.
            items = data.get('items') or []
            if not items or not isinstance(items[0].get('text'), str):
                raise ValueError('Save Message 1 before regenerating.')
            source = items[0]['text']
            requested = max(2, min(20, int(data.get('requested') or dm_templates.PRIMARY_COUNT)))
        return self.generate(source, requested, total=20, master_first=True)

    def captions(self, count):
        items = [r['text'] for r in self.get()['items'] if r.get('enabled')]
        if len(set(items)) < count:
            raise ValueError('Prepare enough different messages in Messages before starting this batch.')
        return items[:count]

    ROTATION_KEY = 'donor_single_rotation'

    def _rotation_texts(self):
        """Validated, enabled Donors > Messages texts (the only source any DM route may use)."""
        bank = self.get()
        rows = bank.get('items') or []
        texts = [row['text'] for row in rows
                 if isinstance(row, dict) and row.get('enabled', True)
                 and isinstance(row.get('text'), str) and row['text'].strip()]
        if not texts or len(texts) != len(set(texts)):
            raise ValueError('Saved Donors Messages are missing or duplicated. Nothing was sent.')
        if any(not dm_composer.complete(text) for text in texts):
            raise ValueError('A saved donor message is incomplete. Edit it in Donors > Messages before sending.')
        return texts

    def _reserve(self, count):
        """Reserve the next `count` saved Donors > Messages versions from the ONE shared
        cursor used by every donor-DM route: single clicks (reserve_one) and batch/Auto
        rounds (reserve_round) advance the same persisted pointer, in persistent storage,
        so nobody gets repeated or near-repeated wording just because a different sending
        method was used. Uncertain sends stay consumed so a restart never replays them.
        """
        if not self.app.STORE:
            raise ValueError('Saved DM rotation is unavailable. Nothing was sent.')
        texts = self._rotation_texts()
        if count > len(texts):
            raise ValueError('Prepare enough different messages in Messages before starting this batch.')
        revision = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
        saved = self.app.STORE.get(self.ROTATION_KEY, {}) or {}
        index = int(saved.get('next_index', 0) or 0) % len(texts) if saved.get('revision') == revision else 0
        last = saved.get('last_text')
        if len(texts) > 1 and last == texts[index]:
            index = (index + 1) % len(texts)
        selected = []
        for _ in range(count):
            value = texts[index]
            selected.append(value)
            index = (index + 1) % len(texts)
        self.app.STORE.put(self.ROTATION_KEY, {
            'revision': revision,
            'next_index': index,
            'last_text': selected[-1]
        })
        return selected

    def reserve_one(self):
        """Reserve the next saved Donors > Messages version for an explicit single DM.

        All explicit one-person sends use exactly what the owner sees in
        Donors > Messages (not get_message('dm') or older templates).
        """
        with self.lock:
            return self._reserve(1)[0]

    def reserve_round(self, count):
        """Reserve `count` saved versions for one batch/Auto round, from the same shared
        cursor as reserve_one. Call this once per round at batch start, not per dispatch:
        the resulting assignment is fixed for the round and re-amount-synced later via
        captions()/the bank's own amount refresh, not by reserving again.
        """
        with self.lock:
            return self._reserve(count)
