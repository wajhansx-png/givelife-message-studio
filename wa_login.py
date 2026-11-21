"""Linking the main WhatsApp: a pairing code to type in WhatsApp, and plain words for login problems.

The QR code needs a second screen. A pairing code does not: the owner types their WhatsApp number,
gets 8 characters, and types them in WhatsApp > Linked devices > Link a device > Link with phone number.
The gateway's own error text (addresses, internals) is never shown.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import wa_lines

COOLDOWN = 20  # seconds between code requests: hammering WhatsApp to link raises the risk of a restriction
_lock = threading.Lock()
_last = [0.0]


def problem(exc):
    """Plain words for a failed QR or code request."""
    text = str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        try:
            text += " " + exc.read().decode("utf-8", "replace")
        except Exception:
            pass
    low = text.lower()
    if "user id" in low or "session have been saved" in low or "already" in low:
        return "This number is already linked or is still connecting. Wait 5 seconds, then tap Check again."
    if isinstance(exc, urllib.error.URLError) and not isinstance(exc, urllib.error.HTTPError):
        return "Could not reach the WhatsApp service. Try again in a moment."
    return "WhatsApp could not make a link right now. Wait a minute and try again."


def _post(url, device):
    request = urllib.request.Request(url, data=b"", method="POST", headers={"X-Device-Id": device})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def request_code(gateway_url, device, phone, post=_post, now=time.time):
    """{"code": "ABCD-1234"} for the number to link. Raises wa_lines.LineError with words the owner can read."""
    number = wa_lines._digits(phone)
    with _lock:
        wait = COOLDOWN - (now() - _last[0])
        if wait > 0:
            raise wa_lines.LineError(
                f"Wait {int(wait) + 1} seconds before asking for another code."
            )
        _last[0] = now()
    url = f"{gateway_url}/devices/{device}/login/code?phone={urllib.parse.quote(number)}"
    try:
        data = post(url, device)
    except Exception as exc:
        raise wa_lines.LineError(problem(exc)) from None
    results = data.get("results") if isinstance(data, dict) else None
    code = wa_lines._find_code(results)
    if not code:
        raise wa_lines.LineError("WhatsApp did not give a code. Try again in a minute.")
    return {"code": code}
