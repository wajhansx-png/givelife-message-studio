"""Volunteers: people who help share the case. A name and a private number, one message the owner writes, and the same
safe batch sending as donors (gaps, saved receipts, never twice) but with their own list, their own records and no appeal rules."""

from persist import atomic_write
import re, threading, time
from donor_book import DonorBook, normalize_phone
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
    START_DELAYS = (0, 300, 600, 900, 1800, 3600, 7200)

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
        atomic_write(self.path, text)
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
            delay = body.get("delay_seconds", 0)
            if type(delay) is not int or delay not in self.START_DELAYS:
                raise ValueError("Choose Send now, 5, 10, 15, 30 minutes, 1 hour or 2 hours.")
            with self.lock:
                rid = body.get("request_id")
                old = next(
                    (
                        j
                        for j in self.jobs.export_jobs()["jobs"]
                        if rid and j.get("request_id") == rid
                    ),
                    None,
                )
                if old:
                    if (
                        old.get("start_delay_seconds", 0) != delay
                        or old.get("poster") != bool(body.get("poster", True))
                        or old.get("gap_seconds") != body.get("gap_seconds", 180)
                    ):
                        raise ValueError(
                            "This request was already used for another volunteer batch. Check its delivery status."
                        )
                    return {
                        "job": self.jobs._public(old),
                        "reply": "This volunteer batch is already tracked. Its original send time is unchanged.",
                    }
                result = self.jobs.start(
                    "all",
                    body.get("gap_seconds", 180),
                    limit=None,
                    chunk=20,
                    request_id=rid,
                    poster=bool(body.get("poster", True)),
                    skip_contacted=bool(body.get("skip_contacted", True)),
                    hold_until=time.time() + delay if delay else None,
                )
                self.jobs._update(result["job"]["id"], start_delay_seconds=delay)
            if delay:
                result["reply"] = (
                    f"Volunteer DMs scheduled to start in {delay // 60} minutes. The saved message and poster choice are queued; you can close the app."
                )
            return result
        raise ValueError("Unknown volunteer action.")
