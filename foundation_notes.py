"""Private, persistent foundation notes. Separate device trust from studio login."""
import hashlib
import hmac
import html
import re
import secrets
import threading
import time
from html.parser import HTMLParser
from http.cookies import SimpleCookie

# Salted PBKDF2 verifier of the owner-supplied Notes PIN; the PIN is never stored.
PIN_SALT = bytes.fromhex('0b9cb927cd92d3be8fc15f6a973fcc7a')
PIN_DIGEST = bytes.fromhex('eecb851d675129056b9f574737ac7abf37fafd7d396b40d6eb4cbb92d6d5a324')
COOKIE = 'gl_notes_trust'
MAX_AGE = 34560000  # Sliding 400 days, refreshed during use (browser may cap lifetime).
COLORS = {'#e76f51', '#2c8f74', '#3b82f6', '#a855f7', '#d97706',
          '#e85d75', '#64748b', '#111827', '#f1f5f9'}
TAGS = {'p','div','br','h1','h2','h3','strong','b','em','i','u','s',
        'blockquote','ol','ul','li','span'}
VOID = {'br'}

class UnlockError(ValueError):
    pass

class ConflictError(ValueError):
    pass

class Cleaner(HTMLParser):
    """Keep only text-editing markup, checked states and the fixed color palette."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ('script','style','svg','math','iframe','object','template'):
            self.skip += 1
            return
        if self.skip or tag not in TAGS:
            return
        allowed = ''
        at = dict(attrs)
        if tag == 'ul' and at.get('data-list') == 'check':
            allowed = ' data-list="check"'
        if tag == 'li' and at.get('data-checked') in ('true','false'):
            allowed = ' data-checked="' + at['data-checked'] + '"'
        if tag == 'span':
            raw_style = at.get('style') or ''
            color = re.fullmatch(r'\s*color\s*:\s*(#[0-9a-fA-F]{6}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\))\s*;?\s*', raw_style, re.I)
            if color:
                value = color[1].lower()
                if value.startswith('rgb'):
                    values = [int(n) for n in re.findall(r'\d+', value)]
                    if len(values) == 3 and all(n <= 255 for n in values):
                        value = '#' + ''.join(format(n, '02x') for n in values)
                if value in COLORS:
                    allowed = ' style="color:' + value + '"'
        self.parts.append('<' + tag + allowed + '>')
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in VOID:
            self.handle_starttag(tag, attrs)
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in ('script','style','svg','math','iframe','object','template'):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.stack:
            return
        while self.stack:
            closing = self.stack.pop()
            self.parts.append('</' + closing + '>')
            if closing == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(html.escape(data, quote=False))

    def finish(self):
        self.close()
        while self.stack:
            self.parts.append('</' + self.stack.pop() + '>')
        return ''.join(self.parts)

def clean_html(source):
    if not isinstance(source, str) or len(source) > 150000:
        raise ValueError('Notes must be text under 150,000 characters.')
    parser = Cleaner()
    parser.feed(source)
    return parser.finish()

def check_pin(password):
    if not isinstance(password, str) or len(password) > 100:
        return False
    attempt = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), PIN_SALT, 350000)
    return hmac.compare_digest(attempt, PIN_DIGEST)

def cookie_token(cookie_header):
    try:
        cookies = SimpleCookie()
        cookies.load(cookie_header or '')
        token = cookies.get(COOKIE)
        value = token.value if token else ''
        return value if re.fullmatch('[0-9a-f]{64}', value) else ''
    except Exception:
        return ''

def cookie_header(token, clear=False):
    return (COOKIE + '=' + ('' if clear else token)
            + '; Max-Age=' + ('0' if clear else str(MAX_AGE))
            + '; Path=/foundation-notes; HttpOnly; Secure; SameSite=Strict')

class NotesVault:
    DOCUMENT = 'foundation_notes_v1'
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.attempts = {}

    def require_store(self):
        if not self.store:
            raise ValueError('Permanent storage is unavailable. Nothing was saved.')

    def trusted(self, cookie):
        token = cookie_token(cookie)
        if not token or not self.store:
            return False
        key = 'foundation_notes_device_' + hashlib.sha256(token.encode()).hexdigest()
        return self.store.get(key) is not None

    def unlock(self, password, peer=''):
        self.require_store()
        ip = str(peer or 'unknown')[:80]
        with self.lock:
            times = [x for x in self.attempts.get(ip, []) if x > time.time()-900]
            if len(times) >= 8:
                raise UnlockError('Too many attempts. Try again in 15 minutes.')
            if not check_pin(password):
                times.append(time.time())
                self.attempts[ip] = times
                raise UnlockError('Incorrect Notes password.')
            self.attempts.pop(ip, None)
        token = secrets.token_hex(32)
        key = 'foundation_notes_device_' + hashlib.sha256(token.encode()).hexdigest()
        self.store.put(key, {'created_at': time.time()})
        return token

    def forget(self, cookie):
        self.require_store()
        token = cookie_token(cookie)
        if token:
            # A revoked token remains a tombstone because generic CloudStore has no delete API.
            key = 'foundation_notes_device_' + hashlib.sha256(token.encode()).hexdigest()
            self.store.put(key, {'revoked': True})

    def can_access(self, cookie):
        token = cookie_token(cookie)
        if not token or not self.store:
            return False
        key = 'foundation_notes_device_' + hashlib.sha256(token.encode()).hexdigest()
        row = self.store.get(key)
        return isinstance(row, dict) and not row.get('revoked')

    def read(self):
        self.require_store()
        value = self.store.get(self.DOCUMENT) or {}
        return {'html': value.get('html', ''),
                'version': value.get('version', 0),
                'updated_at': value.get('updated_at')}

    def save(self, source, version):
        self.require_store()
        if type(version) is not int or version < 0:
            raise ValueError('Invalid document version.')
        result = clean_html(source)
        with self.lock:
            old = self.read()
            if version != old['version']:
                raise ConflictError('Notes changed in another tab. Copy your edits before reloading.')
            new = {'html': result, 'version': version+1, 'updated_at': time.time()}
            self.store.put(self.DOCUMENT, new)
            return new
