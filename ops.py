"""Response hardening and redacted runtime diagnostics; never logs request bodies or secrets."""

import json
import logging
import threading
import traceback
import uuid
from urllib.parse import urlsplit

LOG = logging.getLogger("givelife.ops")
_lock = threading.Lock()
_last = None


def security_headers(origins=(), https=False):
    trusted = []
    for origin in origins:
        p = urlsplit(origin)
        if (
            p.scheme == "https"
            and p.netloc
            and not p.username
            and p.path in ("", "/")
            and not p.query
            and not p.fragment
            and not any(c.isspace() for c in origin)
        ):
            trusted.append(p.scheme + "://" + p.netloc)
    headers = {
        "Content-Security-Policy": "frame-ancestors 'self'" + "".join(" " + o for o in trusted),
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    if not trusted:
        headers["X-Frame-Options"] = "SAMEORIGIN"
    if https:
        headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers


def record_error(handler, exc):
    global _last
    ident = uuid.uuid4().hex
    # Code locations and type identify the fault without serialising exception arguments,
    # headers, URL parameters, database URLs, donor records or a fundraising message.
    frames = [
        {"file": f.filename.rsplit("/", 1)[-1], "line": f.lineno, "function": f.name}
        for f in traceback.extract_tb(exc.__traceback__)[-8:]
    ]
    event = {
        "event": "request_failed",
        "id": ident,
        "method": getattr(handler, "command", "unknown"),
        "route": ("/" + getattr(handler, "path", "").split("?", 1)[0].strip("/").split("/")[0]),
        "error_type": type(exc).__name__,
        "frames": frames,
    }
    with _lock:
        _last = event
    LOG.error("%s", json.dumps(event))
    return ident


def diagnostics():
    with _lock:
        return {"last_error": dict(_last) if _last else None}
