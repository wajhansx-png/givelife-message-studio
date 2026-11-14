"""The Giki list: the same Volunteers screen and rules, but with its own people, its own message and batch, and
its own WhatsApp (a second linked device). Nothing here touches the main volunteers or the main WhatsApp."""

import os, re, time, uuid
from pathlib import Path
from donor_book import PHONE, normalize_phone
from volunteers import Volunteers, VolunteerBook, VolunteerDelivery

MAX_IMPORT = 300
FOLLOW_MAX = 2000  # the share message follows the case as a second message
SEED = Path(__file__).with_name(
    "giki_numbers.md"
)  # the people the owner gave; GIKI_SEED_FILE="" switches it off
# Words saved on a contact that are not a first name ("Giki Donor 4", "Donor Giki Good", "Giki 500 Girl").
NOISE = {
    "giki", "gikian", "donor", "donir", "donkr", "volunteer", "volunt", "vol", "best",
    "good", "girl", "boy", "bhai", "brother", "the", "and", "from", "dm",
}  # fmt: skip


class GikiBook(VolunteerBook):
    KEY = "giki_book"
    FILE = "giki-book.json"


class GikiDelivery(VolunteerDelivery):
    KEY = "giki_delivery"
    FILE = "giki-delivery.json"
    KIND = "giki_batch"
    CLAIM = "giki_batch_request_"

    @staticmethod
    def follow_text(template, name, gender):
        """The share message after the case: {name} is the first name, or "friend". No "Bhai" is added."""
        return template.replace("{name}", name or "friend")


def first_name(label):
    """A real first name from a saved contact label, or "" (the message then says "friend")."""
    for word in re.sub(r"[^\w\s'-]", " ", str(label)).split():
        word = word.strip("-'_")
        if (
            len(word) > 1
            and word.lower() not in NOISE
            and not any(ch.isdigit() for ch in word)
            and word.lower() not in ("jr", "sr")
        ):
            return (word if word.isupper() and len(word) <= 3 else word.capitalize()), "Brother"
    return "", "Brother"


def clean_name(raw):
    """The saved label, without the leading dot or spaces some contacts carry to sort first."""
    return re.sub(r"\s+", " ", str(raw or "")).strip().lstrip(". ").strip()


def parse_numbers(text):
    """(name, number) rows from pasted text or an uploaded list. Understands a table (| # | name | number | ... |)
    and plain lines ("Name 0300 1234567"). Rows without exactly one clear number are returned as problems."""
    rows, problems = [], []
    lines = [x.strip() for x in str(text or "").splitlines()]
    table = any(
        x.startswith("|") for x in lines
    )  # a table file: its notes above and below are not people
    for line in lines:
        if not line or re.fullmatch(r"[|\s:-]+", line) or line.startswith("#"):
            continue
        if table and not line.startswith("|"):
            continue
        if "|" in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            at = next(
                (i for i, c in enumerate(cells) if re.fullmatch(r"\+?[\d\s().-]{8,}", c or "")),
                None,
            )
            if at is None:
                if any(PHONE.search(c) for c in cells):
                    problems.append(line[:60])
                continue  # a heading row ("# | Name | Number") or a note
            name = next(
                (c for c in reversed(cells[:at]) if c and not re.fullmatch(r"[\d\s.]+", c)),
                "",
            )
            number = cells[at]
        else:
            found = list(PHONE.finditer(line))
            if len(found) != 1:
                if found:
                    problems.append(line[:60])
                continue
            number = found[0][0]
            name = re.sub(
                r"(?im)^\s*\d{1,3}[.)]\s+",
                "",
                line[: found[0].start()] + " " + line[found[0].end() :],
            )
            name = name.strip(" ,;:|/-–—")
        try:
            phone = normalize_phone(number)
        except ValueError:
            problems.append(line[:60])
            continue
        rows.append((clean_name(name) or "Giki", phone))
    return rows, problems


class GikiVolunteers(Volunteers):
    MESSAGE_KEY = "giki_message"
    MESSAGE_FILE = "giki-message.txt"
    BOOK = GikiBook
    DELIVERY = GikiDelivery
    LINE = "giki"
    first_name = staticmethod(first_name)

    PACE = {"gap_minutes": 5, "batch_size": 10, "rest_minutes": 20}
    RANGE = {"gap_minutes": (1, 10), "batch_size": (1, 20), "rest_minutes": (1, 120)}
    LABEL = {
        "gap_minutes": "Minutes between DMs",
        "batch_size": "DMs per batch",
        "rest_minutes": "Rest between batches",
    }

    def pace_values(self):
        saved = self.app.STORE.get("giki_pace") if self.app.STORE else None
        out = dict(self.PACE)
        if isinstance(saved, dict):
            for key, (low, high) in self.RANGE.items():
                value = saved.get(key)
                if type(value) is int and low <= value <= high:
                    out[key] = value
        return out

    def set_pace(self, body):
        """Save the timer. Saving never sends anything; the next DM all uses it."""
        out = self.pace_values()
        for key, (low, high) in self.RANGE.items():
            if key not in body:
                continue
            value = body[key]
            if type(value) is float and value.is_integer():
                value = int(value)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{self.LABEL[key]}: choose a whole number from {low} to {high}.")
            out[key] = value
        if not self.app.STORE:
            raise ValueError("Persistent storage is unavailable. Nothing was saved.")
        self.app.STORE.put("giki_pace", out)
        return {"pace": out}

    def pace(self, body):
        v = self.pace_values()
        return {
            "gap_seconds": v["gap_minutes"] * 60,
            "chunk": v["batch_size"],
            "rests": [v["rest_minutes"] * 60],
        }

    def seed_path(self):
        env = os.environ.get("GIKI_SEED_FILE")
        return (Path(env) if env else None) if env is not None else SEED

    def seed_once(self):
        """The people the owner gave (giki_numbers.md) are added the first time the list opens, once. Someone
        removed later does not come back."""
        store, path = self.app.STORE, self.seed_path()
        if not store or not path or store.get("giki_seeded") or not path.is_file():
            return
        with self.lock:
            if store.get("giki_seeded"):
                return
            try:
                done = self.import_numbers(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return  # try again at the next open
            store.put("giki_seeded", {"added": done["added"], "time": time.time()})

    def waiting_ids(self, skip=True):
        """Who DM all would message now: everyone, minus those already messaged for this case."""
        out = []
        for r in self.book._load()["records"]:
            if r.get("deleted") or not r.get("phone"):
                continue
            if skip and (self.book.contacted(r) or r.get("delivery") in ("Uncertain", "Sending")):
                continue
            out.append(r["id"])
        return out

    def view(self, query=""):
        self.seed_once()
        out = super().view(query)
        out["pace"] = self.pace_values()
        out["waiting"] = len(self.waiting_ids())
        return out

    def _share(self, text=None, required=True):
        share = (text if isinstance(text, str) and text.strip() else self.message()).strip()
        if not share and required:
            raise ValueError("Write the share message first (tap Write, under the list).")
        if len(share) > FOLLOW_MAX:
            raise ValueError(
                f"The share message can be up to {FOLLOW_MAX:,} characters, because it follows the case."
            )
        return share

    def send_all(self, body):
        """DM all: each person gets the case first (poster and the Group msgs text, then the PDF / video that are on),
        then the share message the owner wrote. One person at a time with the saved timer. Never twice."""
        share = self._share()
        delay = body.get("delay_seconds", 0)
        if type(delay) is not int or delay not in self.START_DELAYS:
            raise ValueError("Choose Send now, 5, 10, 15, 30 minutes, 1 hour or 2 hours.")
        ids = self.waiting_ids(body.get("skip_contacted", True) is not False)
        if not ids:
            raise ValueError("Everyone in the list was already messaged for this case.")
        case = self.case_text()
        if not isinstance(case, str) or not case.strip():
            raise ValueError("The case message is empty. Write it in Group msgs first.")
        pace = self.pace(body)
        with self.lock:
            rid = body.get("request_id")
            old = next(
                (j for j in self.jobs.export_jobs()["jobs"] if rid and j.get("request_id") == rid),
                None,
            )
            if old:
                if (
                    old.get("start_delay_seconds", 0) != delay
                    or old.get("gap_seconds") != pace["gap_seconds"]
                ):
                    raise ValueError(
                        "This request was already used for another Giki batch. Check its delivery status."
                    )
                return {
                    "job": self.jobs._public(old),
                    "reply": "This Giki batch is already tracked. Its original send time is unchanged.",
                }
            result = self.jobs.start(
                "selected",
                pace["gap_seconds"],
                ids=ids,
                limit=None,
                chunk=pace["chunk"],
                rests=pace["rests"],
                request_id=rid,
                poster=True,
                skip_contacted=False,
                custom_template=case,
                follow_up=share,
                hold_until=time.time() + delay if delay else None,
                **self.case_extras(),
            )
            self.jobs._update(result["job"]["id"], start_delay_seconds=delay)
        result["reply"] = (
            f"Giki DMs scheduled to start in {delay // 60} minutes. The case goes first, then your share message."
            if delay
            else "Giki DMs started. Each person gets the case first, then your share message."
        )
        return result

    def test(self, body):
        """The DM as one person gets it (the case, then the share message), sent only to your own WhatsApp and
        marked TEST. If one part is missing, the other is still sent."""
        share = self._share(body.get("text"), required=False)
        case = self.case_text()
        case = case.strip() if isinstance(case, str) else ""
        if not case and not share:
            raise ValueError(
                "Nothing to test yet: write the share message (tap Write) or set the case in Group msgs."
            )
        return self.app.send_giki_test(case, share, **self.case_extras())

    def case_text(self):
        """DM Case sends exactly what the groups send: the message set in Group msgs, with today's amount. It is read
        again at every click, so a changed case changes the caption of the next person."""
        import caption_facts

        text = ""
        try:
            row = self.app.focus_bank().get("group")
            text = row.get("source", "") if isinstance(row, dict) else ""
        except Exception:
            text = ""
        if not isinstance(text, str) or not text.strip():
            text = self.app.get_message("group")["text"]
        return caption_facts.current(self.app, text)

    def case_extras(self):
        """The PDF and the video go with DM Case exactly when they are switched on for the group message: on = sent,
        off = not sent. Read at the click, from the same saved switches the group posts use."""
        import group_extras

        return group_extras.extras_for(self.app.STORE, "giki")  # the Giki page's own ticks

    def mutate(self, body):
        if body.get("action") == "import":
            return self.import_numbers(body.get("text"), dry_run=body.get("dry_run") is True)
        if body.get("action") == "pace":
            return self.set_pace(body)
        if body.get("action") == "send_all":
            return self.send_all(body)
        if body.get("action") == "test":
            return self.test(body)
        return super().mutate(body)

    def import_numbers(self, text, dry_run=False):
        """Add many people at once. A number already in the list (or already removed from it) is not added twice."""
        if not isinstance(text, str) or not text.strip() or len(text) > 200_000:
            raise ValueError("Choose the list of names and numbers first.")
        rows, problems = parse_numbers(text)
        if len(rows) > MAX_IMPORT:
            raise ValueError(f"Add at most {MAX_IMPORT} numbers at a time.")
        if not rows:
            raise ValueError("No names with numbers were found in this list.")
        own = normalize_phone(self.app.OWNER_PHONE)
        with self.book.lock:
            data = self.book._load()
            have = {r["phone"]: r for r in data["records"] if r.get("phone")}
            added, existing, own_number, repeats = [], 0, 0, 0
            seen = set()
            for name, phone in rows:
                if phone in seen:
                    repeats += 1
                    continue
                seen.add(phone)
                if phone == own:
                    own_number += 1
                    continue
                old = have.get(phone)
                if old and not old.get("deleted"):
                    existing += 1
                    continue
                added.append((name, phone, old))
            if not dry_run:
                now = time.time()
                for name, phone, old in added:
                    if old:  # was removed earlier: bring the same person back
                        old.update(deleted=False, updated_at=now)
                        continue
                    data["records"].append(
                        {
                            "id": uuid.uuid4().hex,
                            "name": name[:120],
                            "phone": phone,
                            "important": False,
                            "donated": False,
                            "amount": 0,
                            "normal_amount": 0,
                            "notes": "",
                            "source": "Giki list",
                            "created_at": now,
                            "updated_at": now,
                            "deleted": False,
                            "last_sent_at": None,
                            "delivery": "Not contacted",
                        }
                    )
                if added:
                    self.book._save(data)
        return {
            "dry_run": dry_run,
            "found": len(rows),
            "added": len(added),
            "existing": existing,
            "repeats": repeats,
            "own": own_number,
            "problems": len(problems),
            "reply": (
                f"{len(added)} new number{'s' if len(added) != 1 else ''} "
                + ("can be added" if dry_run else "added")
                + (f", {existing} already in the list" if existing else "")
                + "."
            ),
        }
