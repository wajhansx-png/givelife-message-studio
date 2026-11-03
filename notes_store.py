"""Private, persistent GiveLife notes with a remembered desktop unlock.

This feature is separate from the donor records and AI assistant. No notes are
returned until both the studio authentication and notes device lock succeed.
"""

import hashlib
import hmac
import html
import os
import re
import secrets
import threading
import time
from html.parser import HTMLParser
from http.cookies import SimpleCookie

NOTE_KEY = "foundation_notes_v1"
SESSION_PREFIX = "foundation_notes_device_"
COOKIE = "GL_NOTES_DEVICE"
COOKIE_AGE = 400 * 24 * 3600  # Chrome caps persistent cookies; renew on each visit
MAX_SIZE = 250_000
# Salted verifier of the owner-selected PIN; the PIN itself is NOT checked into git.
# NOTES_PASSWORD env var overrides this verifier without rebuilding the application.
PIN_SALT = bytes.fromhex("1555704ab0df55e47acf12389a5d1128")
PIN_HASH = bytes.fromhex("7bdabe56198dbf1a97a3cdf562f3125aa5e18f98ef72810414f316c316d3462e")
PIN_ITERATIONS = 320_000
_lock = threading.RLock()
_attempts = {}


def verify_pin(value):
    if not isinstance(value, str) or len(value) > 128:
        return False
    configured = os.environ.get("NOTES_PASSWORD")
    if configured:
        return hmac.compare_digest(value.encode("utf-8"), configured.encode("utf-8"))
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), PIN_SALT, PIN_ITERATIONS)
    return hmac.compare_digest(digest, PIN_HASH)


def cookie_token(header):
    try:
        parsed = SimpleCookie()
        parsed.load(str(header or ""))
        value = parsed[COOKIE].value if COOKIE in parsed else ""
        return value if re.fullmatch(r"[a-f0-9]{64}", value) else ""
    except Exception:
        return ""


def device_key(token):
    return SESSION_PREFIX + hashlib.sha256(token.encode("ascii")).hexdigest()


def allowed(store, cookie_header):
    token = cookie_token(cookie_header)
    if not token or store is None:
        return False
    record = store.get(device_key(token))
    return isinstance(record, dict) and record.get("active") is True


def device_cookie(token, https=True):
    return (
        f"{COOKIE}={token}; Path=/notes; Max-Age={COOKIE_AGE}; HttpOnly; "
        + ("Secure; " if https else "")
        + "SameSite=Strict"
    )


def clear_cookie(https=True):
    return (
        f"{COOKIE}=; Path=/notes; Max-Age=0; HttpOnly; "
        + ("Secure; " if https else "")
        + "SameSite=Strict"
    )


def unlock(store, pin, ip="local"):
    if store is None:
        raise ValueError("Persistent storage is unavailable. Your notes were not unlocked.")
    now = time.monotonic()
    # Rate limit incorrect attempts (in addition to studio authentication).
    with _lock:
        recent = [t for t in _attempts.get(ip, []) if now - t < 600]
        if len(recent) >= 5:
            raise ValueError("Too many attempts. Try again in 10 minutes.")
    if not verify_pin(pin):
        with _lock:
            _attempts[ip] = recent + [now]
        raise ValueError("Incorrect notes password.")
    with _lock:
        _attempts.pop(ip, None)
    token = secrets.token_hex(32)
    store.put(device_key(token), {"active": True, "created_at": time.time()})
    return token


def lock_device(store, cookie_header):
    token = cookie_token(cookie_header)
    if token and store:
        store.put(device_key(token), {"active": False})


class SafeNoteHTML(HTMLParser):
    """Tight HTML allowlist: markup, headings, lists, checkboxes and text colors."""

    TAGS = {
        "p",
        "div",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "h1",
        "h2",
        "h3",
        "blockquote",
        "ul",
        "ol",
        "li",
        "span",
        "font",
        "input",
    }
    VOID = {"br", "input"}
    COLOR = re.compile(
        r"^(?:#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|rgb\(\s*(?:\d{1,3}\s*,\s*){2}\d{1,3}\s*\))$"
    )
    STYLE = re.compile(r"(?:^|;)\s*color\s*:\s*([^;]+)", re.I)

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style", "iframe", "object", "svg", "math"):
            self.hidden += 1
            return
        if self.hidden or tag not in self.TAGS:
            return
        props = dict(attrs)
        safe = ""
        if tag == "ul" and props.get("class") == "notes-checklist":
            safe = ' class="notes-checklist"'
        if tag == "li" and props.get("data-checked") == "true":
            safe = ' data-checked="true"'
        if tag in ("span", "font"):
            raw = props.get("color", "") if tag == "font" else ""
            if not raw:
                found = self.STYLE.search(props.get("style") or "")
                raw = found.group(1).strip() if found else ""
            if self.COLOR.fullmatch(raw):
                safe = ' style="color:' + raw + '"'
        if tag == "input":
            if props.get("type") != "checkbox":
                return
            safe = ' type="checkbox"' + (" checked" if "checked" in props else "")
        self.parts.append("<" + tag + safe + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style", "iframe", "object", "svg", "math"):
            if self.hidden:
                self.hidden -= 1
            return
        if self.hidden or tag not in self.TAGS or tag in self.VOID:
            return
        self.parts.append("</" + tag + ">")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(html.escape(data, quote=False))


def sanitize(source):
    if not isinstance(source, str):
        raise ValueError("Notes must be text.")
    if len(source.encode("utf-8")) > MAX_SIZE:
        raise ValueError("Notes are too long. Keep them under 250 KB.")
    parser = SafeNoteHTML()
    parser.feed(source)
    parser.close()
    return "".join(parser.parts)


def load(store):
    if store is None:
        raise ValueError("Persistent storage is unavailable.")
    record = store.get(NOTE_KEY)
    if not isinstance(record, dict):
        return {"html": "", "revision": 0, "updated_at": 0}
    return {
        "html": str(record.get("html", "")),
        "revision": int(record.get("revision", 0)),
        "updated_at": record.get("updated_at", 0),
    }


def save(store, source, revision):
    if type(revision) is not int or revision < 0:
        raise ValueError("Reload your notes before saving.")
    cleaned = sanitize(source)
    with _lock:
        current = load(store)
        if revision != current["revision"]:
            raise ValueError(
                "These notes changed in another window. Copy your current text before reloading."
            )
        row = {"html": cleaned, "revision": revision + 1, "updated_at": time.time()}
        store.put(NOTE_KEY, row)
        return row
