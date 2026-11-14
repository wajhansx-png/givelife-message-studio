"""Extra WhatsApp lines: a second WhatsApp account (the Giki line) linked as its own device in the same gateway.

The main device is never touched here, and a line never falls back to the main device: if the line has no
device, nothing is sent. The device id is created once, saved, and reused after every restart."""

import base64, json, re, threading, urllib.error, urllib.parse, urllib.request, uuid

PREFIX = {"giki": "giki-"}


class LineError(ValueError):
    """A problem the owner can read. Never carries gateway internals."""


def is_line_device(device_id):
    """True for any extra line's device. The launcher uses this so the main device is never mistaken for one."""
    return any(str(device_id or "").startswith(p) for p in PREFIX.values())


def number_of(jid):
    """The phone digits of a WhatsApp id such as 923001234567:12@s.whatsapp.net."""
    return re.sub(r"\D", "", str(jid or "").split(":")[0].split("@")[0])


def main_candidates(devices, store):
    """The gateway devices that may be the main WhatsApp: never a line's device, and never a line's login that
    came back after a deploy under its number (an id with "@")."""
    taken = line_numbers(store)
    return [
        d
        for d in devices or []
        if isinstance(d, dict)
        and not is_line_device(d.get("id"))
        and ("@" not in str(d.get("id")) or number_of(d.get("jid") or d.get("id")) not in taken)
    ]


def line_numbers(store):
    """The numbers linked to the extra lines, so the launcher never takes one of them for the main WhatsApp."""
    found = set()
    for name in PREFIX:
        try:
            record = store.get("wa_line_" + name)
        except Exception:
            record = None
        if isinstance(record, dict) and record.get("number"):
            found.add(str(record["number"]))
    return found


def _digits(value):
    from donor_book import normalize_phone

    try:
        return normalize_phone(value)
    except ValueError:
        raise LineError(
            "Enter the WhatsApp number to connect, with its country code (for example 0300 1234567)."
        ) from None


def _friendly(message):
    """Plain words for the owner. The gateway's own text (addresses, internals) is never shown."""
    low = str(message or "").lower()
    if "not found" in low:
        return "This WhatsApp line was not found."  # status() reads this to start the link again
    if "not logged in" in low:
        return "This WhatsApp is not linked yet."
    if "already" in low and "logged" in low:
        return "This WhatsApp is already linked."
    return "WhatsApp could not be reached. Try again in a minute."


def _find_code(results):
    """The 8-character pairing code inside whatever shape the gateway answered with."""
    values = list(results.values()) if isinstance(results, dict) else [results]
    for v in values:
        text = str(v or "").strip()
        if re.fullmatch(r"[A-Za-z0-9]{4}-?[A-Za-z0-9]{4}", text):
            text = text.replace("-", "").upper()
            return text[:4] + "-" + text[4:]
    return ""


class Line:
    def __init__(self, name, store, gateway_url, call=None):
        if name not in PREFIX:
            raise ValueError("Unknown WhatsApp line.")
        self.name = name
        self.key = "wa_line_" + name
        self.store = store
        self.url = str(gateway_url).rstrip("/")
        self._call = call or self._http
        self.lock = threading.RLock()
        self._device = None

    # -- the gateway -------------------------------------------------------------------------------
    def _http(self, method, path, device="", body=None, timeout=15, raw=False):
        headers = {"X-Device-Id": device} if device else {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = r.read()
        except urllib.error.HTTPError as e:
            try:
                message = str(json.loads(e.read() or b"{}").get("message") or "")
            except Exception:
                message = ""
            raise LineError(_friendly(message)) from None
        return payload if raw else json.loads(payload or b"{}")

    # -- the saved device id ------------------------------------------------------------------------
    def device(self):
        """The line's device id, or "" when the line was never set up."""
        if self._device is None:
            record = self.store.get(self.key) if self.store else None
            self._device = str(record.get("device") or "") if isinstance(record, dict) else ""
        return self._device

    def _record(self):
        record = self.store.get(self.key) if self.store else None
        return dict(record) if isinstance(record, dict) else {}

    def _save(self, device):
        if self.store:
            self.store.put(self.key, {**self._record(), "device": device})
        self._device = device

    def _remember_number(self, digits):
        """Keep the linked number, so after a restart the launcher knows this login is not the main WhatsApp."""
        if not digits or digits == getattr(self, "_number", None) or not self.store:
            return
        record = self._record()
        if record.get("number") != digits:
            self.store.put(self.key, {**record, "number": digits})
        self._number = digits

    def ensure(self):
        """The device id, creating the device in the gateway the first time. One device only."""
        with self.lock:
            device = self.device()
            if device and self._known(device):
                return device
            device = device or PREFIX[self.name] + uuid.uuid4().hex[:12]
            try:
                self._call("POST", "/devices", body={"device_id": device})
            except LineError:
                if not self._known(device):
                    raise
            self._save(device)
            return device

    def _known(self, device):
        try:
            results = self._call("GET", "/devices").get("results")
        except Exception:
            raise LineError("WhatsApp is restarting. Try again in a minute.") from None
        return any(isinstance(d, dict) and d.get("id") == device for d in (results or []))

    # -- what the page shows -------------------------------------------------------------------------
    def status(self):
        """{state: none|ready|dropped|unlinked|unknown, connected, logged_in, tail}. Never raises."""
        device = self.device()
        out = {"state": "none", "connected": False, "logged_in": False, "tail": ""}
        if not device:
            return out
        try:
            s = self._call("GET", f"/devices/{device}/status", device=device).get("results") or {}
        except LineError as e:
            # A device the gateway does not know any more must be linked again; any other problem is a busy gateway.
            out["state"] = "none" if "was not found" in str(e) else "unknown"
            return out
        except Exception:
            out["state"] = "unknown"
            return out
        connected, logged = bool(s.get("is_connected")), bool(s.get("is_logged_in"))
        out.update(
            connected=connected,
            logged_in=logged,
            state="ready" if connected and logged else "dropped" if logged else "unlinked",
        )
        if logged:
            try:
                info = self._call("GET", f"/devices/{device}", device=device).get("results") or {}
                digits = number_of(info.get("jid"))
                out["tail"] = digits[-4:]
                out["number"] = digits  # for the server only; never sent to the page
                self._remember_number(digits)
            except Exception:
                pass
        return out

    def ready(self):
        return self.status()["state"] == "ready"

    # -- linking ---------------------------------------------------------------------------------------
    def qr(self):
        device = self.ensure()
        data = self._call("GET", f"/devices/{device}/login", device=device, timeout=25)
        results = data.get("results") if isinstance(data.get("results"), dict) else {}
        path = urllib.parse.urlparse(str(results.get("qr_link") or "")).path
        if not path.startswith("/statics/qrcode/"):
            raise LineError("The QR code is not ready. Try again in a few seconds.")
        png = self._call("GET", path, raw=True, timeout=10)
        return {
            "qr": "data:image/png;base64," + base64.b64encode(png).decode(),
            "duration": int(results.get("qr_duration") or 30),
        }

    def pair_code(self, phone):
        """A code to type in WhatsApp (Linked devices -> Link with phone number). Works on the same phone."""
        number = _digits(phone)
        device = self.ensure()
        path = f"/devices/{device}/login/code?phone={urllib.parse.quote(number)}"
        data = self._call("POST", path, device=device, timeout=30)
        code = _find_code(data.get("results"))
        if not code:
            raise LineError("WhatsApp did not give a code. Try again in a minute.")
        return {"code": code}

    def reconnect(self):
        device = self.device()
        if not device:
            raise LineError("Connect WhatsApp first.")
        self._call("POST", f"/devices/{device}/reconnect", device=device, timeout=30)
        return self.status()

    def logout(self):
        device = self.device()
        if not device:
            return self.status()
        try:
            self._call("POST", f"/devices/{device}/logout", device=device, timeout=30)
        except LineError:
            pass  # already logged out
        return self.status()
