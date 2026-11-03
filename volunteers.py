"""Volunteers: people who help share the case. A name and a private number, one message the owner writes, and the same
safe batch sending as donors (gaps, saved receipts, never twice) but with their own list, their own records and no appeal rules."""

import re, threading, time
from donor_book import DonorBook, normalize_phone, hide_numbers
from donor_delivery import DonorDelivery


class VolunteerBook(DonorBook):
    KEY = "volunteer_book"
    FILE = "volunteer-book.json"


class VolunteerDelivery(DonorDelivery):
    KEY = "volunteer_delivery"
    FILE = "volunteer-delivery.json"
    KIND = "volunteer_batch"
    CLAIM = "volunteer_batch_request_"


class Volunteers:
    MESSAGE_KEY = "volunteer_message"
    MAX = 4000

    def __init__(self, app, eligible):
        self.app = app
        self.book = VolunteerBook(app.DATA, app.STORE)
        self.lock = threading.RLock()
        self.jobs = VolunteerDelivery(
            app.DATA,
            app.STORE,
            self.book,
            app.send_custom,
            self.message,
            app.wa_ok,
            lambda: app.on_hold(),
            eligible,
            self.first_name,
        )
        self.path = app.DATA / "volunteer-message.txt"

    @staticmethod
    def first_name(label):
        first = re.sub(r"[^\w\s'-]", " ", str(label)).split()
        return (first[0].capitalize() if first else ""), "Brother"

    def message(self):
        text = self.app.STORE.get(self.MESSAGE_KEY) if self.app.STORE else None
        if text is None and self.path.exists():
            text = self.path.read_text(encoding="utf-8")
        return text if isinstance(text, str) else ""

    def set_message(self, text):
        if not isinstance(text, str) or len(text) > self.MAX:
            raise ValueError(f"Write the message in at most {self.MAX:,} characters.")
        text = text.replace("\r\n", "\n").strip()
        if self.app.STORE:
            self.app.STORE.put(self.MESSAGE_KEY, text)
        self.path.write_text(text, encoding="utf-8")
        return {"message": text}

    def view(self, query=""):
        out = self.book.list("all", query)
        out["message"] = self.message()
        out["delivery"] = self.jobs.status()
        return out

    def mutate(self, body):
        action = body.get("action")
        if action == "add":
            name = str(body.get("name", "")).strip()
            if not name:
                raise ValueError("Write the volunteer's name.")
            phone = body.get("phone", "")
            if not str(phone).strip():
                raise ValueError("Add their WhatsApp number so the message can reach them.")
            if normalize_phone(phone) == normalize_phone(self.app.OWNER_PHONE):
                raise ValueError("This is your connected account.")
            return self.book.add(name, phone, source="Volunteer")
        if action == "update":
            return self.book.update(
                body.get("id", ""),
                expected_updated_at=body.get("expected_updated_at"),
                **{k: v for k, v in body.items() if k == "name"},
            )
        if action == "delete":
            return self.book.delete(body.get("id", ""))
        if action == "restore":
            return self.book.restore(body.get("id", ""))
        if action == "message":
            return self.set_message(body.get("text"))
        if action == "stop":
            return self.jobs.cancel()
        if action in ("send_all", "send_one"):
            if not self.message().strip():
                raise ValueError(
                    "Write the message for volunteers first (the box under the list), then send."
                )
            if action == "send_one":
                return self.jobs.start(
                    "selected",
                    body.get("gap_seconds", 180),
                    ids=[self.book.resolve(body.get("id", ""))["id"]],
                    limit=1,
                    request_id=body.get("request_id"),
                    poster=bool(body.get("poster", True)),
                    skip_contacted=False,
                )
            return self.jobs.start(
                "all",
                body.get("gap_seconds", 180),
                limit=None,
                chunk=20,
                request_id=body.get("request_id"),
                poster=bool(body.get("poster", True)),
                skip_contacted=bool(body.get("skip_contacted", True)),
            )
        raise ValueError("Unknown volunteer action.")
