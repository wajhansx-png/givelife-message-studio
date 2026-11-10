"""Case-scoped completion updates; immutable sends and independent per-part receipts."""

import copy
import threading
import time
import uuid

import batch_media
from donor_book import hide_numbers
from message_library import library_for

DEFAULTS = {"gap_minutes": 5, "batch_size": 10, "rest_minutes": 20}


class DonorThanks:
    def __init__(self, app, hub):
        self.app, self.hub = app, hub
        self.lock = threading.RLock()
        self.worker = threading.Lock()
        self.boot = uuid.uuid4().hex

    def case_id(self):
        return self.hub.cases._load()["current"]

    def _load(self, cid=None):
        cid = cid or self.case_id()
        return (self.app.STORE.get("donor_thanks_" + cid) if self.app.STORE else None) or {
            "case_id": cid,
            "revision": 0,
            "attachment": None,
            "filename": "",
            "mime": "",
            "caption": "",
            "message": "",
            "settings": dict(DEFAULTS),
            "receipts": {},
            "on": False,
        }

    def _put(self, data):
        if not self.app.STORE:
            raise ValueError("Persistent storage is unavailable. Nothing was sent or saved.")
        self.app.STORE.put("donor_thanks_" + data["case_id"], data)

    @property
    def active(self):
        if not self.app.STORE:
            return False
        cid = self.app.STORE.get("donor_thanks_active")
        return bool(cid and self._load(cid).get("on"))

    def _rows(self):
        return self.hub.book.recipients("donated")

    def view(self):
        with self.lock:
            data = self._load()
            rows = self._rows()
            receipts = data["receipts"]
            done = sum(r.get("state") == "Sent" for r in receipts.values())
            public = {k: copy.deepcopy(v) for k, v in data.items() if k not in ("receipts", "ids")}
            registry = self.hub.cases._load()
            public["case_name"] = next(
                (c["name"] for c in registry.get("cases", []) if c["id"] == data["case_id"]),
                "Current case",
            )
            public.update(
                left=self.app.read_left(),
                recipients=[
                    {
                        "id": r["id"],
                        "name": hide_numbers(r["name"]),
                        "state": receipts.get(r["id"], {}).get("state", "Ready"),
                    }
                    for r in rows
                ],
                sent=done,
                total=len(rows),
                pending=sum(
                    r["id"] not in receipts or receipts[r["id"]].get("state") == "Pending"
                    for r in rows
                ),
            )
            return public

    def save(self, body):
        with self.hub.cases.lock, self.lock:
            data = self._load()
            if body.get("case_id") != data["case_id"] or body.get("revision") != data["revision"]:
                raise ValueError(
                    "This case update changed. Reopen Thank donors; your text is still in the editor."
                )
            if data["on"]:
                raise ValueError("Pause Thanks donors before changing its message or media.")
            for field in ("caption", "message"):
                if not isinstance(body.get(field), str) or len(body[field]) > 4000:
                    raise ValueError("Keep each text field within 4,000 characters.")
            attachment = body.get("attachment") or None
            mime = ""
            if attachment:
                _, mime = batch_media.load(self.app.STORE, attachment, self.app.ATT)
            elif body["caption"].strip():
                raise ValueError(
                    "A caption needs an attachment. Use Separate message for text alone."
                )
            if self.app.completed_case_appeal(body["caption"] + "\n" + body["message"]):
                raise ValueError(
                    "Use a completion or thank-you update, without a new fundraising appeal."
                )
            for field in ("caption", "message"):
                library_for(self.app).record(
                    "dm", body[field], source="completion_editor", quality="owner"
                )
            data.update(
                attachment=attachment,
                mime=mime,
                filename=hide_numbers(str(body.get("filename") or "Attachment"))[:150],
                caption=body["caption"],
                message=body["message"],
                revision=data["revision"] + 1,
            )
            self._put(data)
            return self.view()

    def configure(self, settings):
        if not isinstance(settings, dict):
            raise ValueError("Choose the sending pace to edit.")
        clean = {}
        for key, maximum in (("gap_minutes", 1440), ("batch_size", 100), ("rest_minutes", 1440)):
            value = settings.get(key, self._load()["settings"][key])
            if (
                type(value) not in (int, float)
                or not 1 <= value <= maximum
                or (key == "batch_size" and value != int(value))
            ):
                raise ValueError("Choose valid timing: 1–1,440 minutes, 1–100 donors per batch.")
            clean[key] = int(value) if key == "batch_size" else value
        with self.lock:
            data = self._load()
            data["settings"] = clean
            if data.get("on") and data.get("last_at"):
                data["next_at"] = data["last_at"] + 60 * clean["gap_minutes"]
                if data.get("waiting_batch") or data.get("batch_count", 0) >= clean["batch_size"]:
                    data["next_at"] = data["last_at"] + 60 * clean["rest_minutes"]
                    data.update(waiting_batch=True, batch_count=0)
            self._put(data)
        return self.view()

    def start(self):
        if not self.app.STORE:
            raise ValueError("Persistent storage is unavailable. Nothing was sent or saved.")
        with self.hub.cases.lock, self.hub.control_lock, self.lock:
            data = self._load()
            if data["on"]:
                return self.view()
            if self.app.read_left() > 0:
                raise ValueError("Finish this case before sending its thank-you update.")
            if (
                self.hub.jobs.active
                or self.hub.volunteers.jobs.active
                or self.app.CAMPAIGN.get("running")
                or getattr(self.app.ENGINE, "dm_running", False)
            ):
                raise ValueError("Pause the other DM queue before starting Thanks donors.")
            if not (data["attachment"] or data["message"].strip()):
                raise ValueError("Open Donated → Thank donors and save media or a message first.")
            if data["attachment"]:
                batch_media.load(self.app.STORE, data["attachment"], self.app.ATT)
            ids = [
                r["id"]
                for r in self._rows()
                if data["receipts"].get(r["id"], {}).get("state")
                not in ("Sent", "Uncertain", "Sending", "Skipped")
            ]
            if not ids:
                raise ValueError(
                    "No donors are waiting for this case update. Confirmed and unconfirmed updates are not repeated."
                )
            data.update(
                on=True,
                ids=ids,
                next_at=max(time.time(), data.get("next_at") or 0),
                error="",
                batch_count=data.get("batch_count", 0),
            )
            self._put(data)
            self.app.STORE.put("donor_thanks_active", data["case_id"])
        threading.Thread(target=self.tick, daemon=True).start()
        return self.view()

    def stop(self):
        with self.lock:
            data = self._load()
            data["on"] = False
            self._put(data)
        return self.view()

    def _busy(self):
        return bool(
            self.hub.jobs.active
            or self.hub.volunteers.jobs.active
            or self.app.CAMPAIGN.get("running")
            or getattr(self.app.ENGINE, "dm_running", False)
            or self.app.on_hold()
        )

    def tick(self, now=None):
        if not self.worker.acquire(blocking=False):
            return
        leased = False
        try:
            if not self.active or self._busy() or not self.app.wa_ok():
                return
            leased = self.app.STORE.lease_acquire("donor_thanks_worker", self.boot, 300)
            if not leased:
                return
            self._step(time.time() if now is None else now)
        finally:
            if leased:
                self.app.STORE.lease_release("donor_thanks_worker", self.boot)
            self.worker.release()

    def _step(self, now):
        with self.lock:
            cid = self.app.STORE.get("donor_thanks_active")
            data = self._load(cid)
            if not data["on"] or now < data.get("next_at", 0):
                return
            if cid != self.case_id() or self.app.read_left() > 0:
                data.update(
                    on=False,
                    error="The active case or its balance changed. Nothing further was sent.",
                )
                self._put(data)
                return
            ident = next(
                (
                    i
                    for i in data.get("ids", [])
                    if data["receipts"].get(i, {}).get("state")
                    not in ("Sent", "Skipped", "Uncertain", "Sending")
                ),
                None,
            )
            if ident is None:
                data.update(on=False, next_at=None)
                self._put(data)
                return
            row = next((r for r in self._rows() if r["id"] == ident), None)
            receipt = data["receipts"].setdefault(ident, {"state": "Pending", "parts": {}})
            if not row or not self.hub.eligible(row["phone"]):
                receipt.update(state="Skipped", note="No longer donated, or recipient excluded.")
                self._put(data)
                return
            parts = []
            if data["attachment"]:
                parts.append(("media", data["caption"], data["attachment"]))
            if data["message"].strip():
                parts.append(("message", data["message"], None))
            self._put(data)
        # Do not hold the editor lock while uploading: Stop must remain responsive.
        for part, text, attachment in parts:
            with self.lock:
                data = self._load(cid)
                if not data["on"]:
                    return
                receipt = data["receipts"][ident]
                if receipt["parts"].get(part) == "Sent":
                    continue
                key = "thanks_part_" + cid + "_" + ident + "_" + part
                if not self.app.STORE.claim(key, {"at": time.time()}):
                    receipt.update(
                        state="Uncertain",
                        note="An earlier send was started. Check WhatsApp; it will not repeat.",
                    )
                    data.update(on=False, error=receipt["note"])
                    self._put(data)
                    return
                receipt["parts"][part] = "Sending"
                self._put(data)
            name = (row["name"].split() or ["friend"])[0]
            try:
                result = self.app.send_custom(
                    {
                        "target": "phone",
                        "phone": row["phone"],
                        "message": text.replace("{name}", name),
                        "attachment": attachment,
                        "poster": False,
                        "kind": "donor_thanks",
                        "case_id": cid,
                        "donor_id": ident,
                        "first_in_batch": True,
                    }
                )
                confirmed = isinstance(result, dict) and result.get("code") == "SUCCESS"
                error = (
                    ""
                    if confirmed
                    else "Delivery is unconfirmed. Check WhatsApp before doing anything further."
                )
            except Exception as exc:
                confirmed, error = False, hide_numbers(str(exc))[:200]
            with self.lock:
                data = self._load(cid)
                receipt = data["receipts"][ident]
                receipt["parts"][part] = "Sent" if confirmed else "Uncertain"
                if not confirmed:
                    receipt.update(state="Uncertain", note=error)
                    data.update(on=False, error=error)
                    self._put(data)
                    return
                self._put(data)
        with self.lock:
            data = self._load(cid)
            data["receipts"][ident].update(state="Sent", at=time.time())
            count = data.get("batch_count", 0) + 1
            cfg = data["settings"]
            rest = count >= cfg["batch_size"]
            data.update(
                batch_count=0 if rest else count,
                waiting_batch=rest,
                last_at=time.time(),
                next_at=time.time() + 60 * cfg["rest_minutes" if rest else "gap_minutes"],
            )
            if all(
                data["receipts"].get(i, {}).get("state") in ("Sent", "Skipped", "Uncertain")
                for i in data["ids"]
            ):
                data.update(on=False, next_at=None)
            self._put(data)
