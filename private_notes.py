"""Private, permanently stored foundation notes.

The default PIN is stored only as a salted PBKDF2 verifier. Browser devices keep
a revocable random token, never the PIN. Existing app authentication is also required.
"""
import datetime
import hashlib
import hmac
from html import escape
from html.parser import HTMLParser
import os
import re
import secrets
import threading
import time

SALT = bytes.fromhex('d1f0a6b8c294e037c735c41aff809d2a')
PIN_HASH = bytes.fromhex('7c12dd87ee15e4114f54a2b88a35d02b55f9fd070c028f6a16135dbb59d1278c')
MAX_HTML = 150_000
TAGS = frozenset(('p','div','h1','h2','h3','ul','ol','li','br','b','strong','em','i','u','s','span','blockquote'))
BANNED_CONTENT = frozenset(('script','style','iframe','object','svg','math','template','noscript','form','textarea','input','button'))
HEX = re.compile(r'^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$')
_LOCK = threading.RLock()
_FAILURES = {}

class CleanHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.opened = []
        self.skip = []

    def handle_starttag(self, tag, attrs):
        if tag in BANNED_CONTENT:
            self.skip.append(tag)
            return
        if self.skip or tag not in TAGS:
            return
        allowed = ''
        attrs = dict(attrs)
        if tag == 'span':
            m = re.search(r'(?:^|;)\\s*color\\s*:\\s*(#[0-9a-fA-F]{3,6})(?:\\s*;|\\s*$)', attrs.get('style', ''), re.I)
            if m and HEX.fullmatch(m.group(1)):
                allowed = ' style="color:' + m.group(1).lower() + '"'
        elif tag == 'ul' and attrs.get('data-checklist') == 'true':
            allowed = ' data-checklist="true"'
        elif tag == 'li' and attrs.get('data-checked') in ('true','false'):
            allowed = ' data-checked="' + attrs['data-checked'] + '"'
        if tag == 'br':
            self.parts.append('<br>')
        else:
            self.parts.append('<' + tag + allowed + '>')
            self.opened.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag in self.opened:
            while self.opened:
                current = self.opened.pop()
                self.parts.append('</' + current + '>')
                if current == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(escape(data))

    def close(self):
        super().close()
        while self.opened:
            self.parts.append('</' + self.opened.pop())

def clean_html(html):
    if not isinstance(html, str) or len(html) > MAX_HTML:
        raise ValueError('Notes are too long (maximum 150,000 characters).')
    parser = CleanHTML()
    parser.feed(html)
    parser.close()
    return ''.join(parser.parts)

def _digest(pin):
    return hashlib.pbkdf2_hmac('sha256', str(pin).encode(), SALT, 240_000)

class PrivateNotes:
    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock
        if store is None:
            raise RuntimeError('Private Notes require the persistent database.')

    def _check(self, token):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,160}', token):
            raise PermissionError('Unlock Notes on this device.')
        # All sessions are in persistent storage; a service restart keeps access.
        data = self.store.get('private_notes_sessions', {})
        return hmac.compare_digest(
            str((data if isinstance(data, dict) else {}).get(hashlib.sha256(token.encode()).hexdigest(), '')),
            'trusted'
        )

    def unlock(self, pin, ip='unknown'):
        ip = str(ip)[:80]
        with _LOCK:
            now = self.clock()
            failures = [t for t in _FAILURES.get(ip, []) if now-t < 600]
            if len(failures) >= 5:
                raise ValueError('Too many attempts. Try again in 10 minutes.')
            configured = os.environ.get('GIVELIFE_NOTES_PIN')
            correct = (hmac.compare_digest(str(pin), configured) if configured else
                       hmac.compare_digest(_digest(pin), PIN_HASH))
            if not correct:
                _FAILURES[ip] = failures + [now]
                raise ValueError('Incorrect Notes password.')
            _FAILURES.pop(ip, None)
            token = secrets.token_urlsafe(36)
            sessions = self.store.get('private_notes_sessions', {})
            sessions = sessions if isinstance(sessions, dict) else {}
            sessions[hashlib.sha256(token.encode()).hexdigest()] = 'trusted'
            # A small bounded number of registered browser profiles.
            self.store.put('private_notes_sessions', dict(list(sessions.items())[-40:]))
            return {'token': token, 'unlocked': True}

    def read(self, token):
        if not self._check(token):
            raise PermissionError('Unlock Notes on this device.')
        doc = self.store.get('private_foundation_notes', {})
        if not isinstance(doc, dict):
            doc = {}
        return {'html': clean_html(str(doc.get('html', ''))),
                'revision': int(doc.get('revision') or 0),
                'updated_at': doc.get('updated_at')}

    def save(self, token, html, revision):
        if not self._check(token):
            raise PermissionError('Unlock Notes on this device.')
        sanitized = clean_html(html)
        if type(revision) is not int or revision < 0:
            raise ValueError('Invalid note revision.')
        with _LOCK:
            doc = self.store.get('private_foundation_notes', {})
            doc = doc if isinstance(doc, dict) else {}
            old = int(doc.get('revision') or 0)
            if revision != old:
                raise ValueError('Notes changed on another device. Copy your edits before refreshing; nothing was overwritten.')
            updated = datetime.datetime.fromtimestamp(self.clock(), datetime.timezone.utc).isoformat()
            self.store.put('private_foundation_notes', {
                'html': sanitized, 'revision': old + 1, 'updated_at': updated
            })
            return {'revision': old + 1, 'updated_at': updated, 'html': sanitized}

    def lock_device(self, token):
        if not self._check(token):
            return {'locked': True}
        with _LOCK:
            sessions = self.store.get('private_notes_sessions', {})
            sessions = sessions if isinstance(sessions, dict) else {}
            sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
            self.store.put('private_notes_sessions', sessions)
        return {'locked': True}
