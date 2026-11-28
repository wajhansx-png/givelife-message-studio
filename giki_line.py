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


# Two test people at the top of the list (the owner's checks). Everything sent to them goes to the GiveLife test group,
# through the very same Giki steps as a real person (case, 2nd, 3rd, share), so the owner sees each DM before the real
# people get it. Their numbers are placeholders that are not WhatsApp numbers: a send to them never reaches a person.
TEST_PEOPLE = (("Ahmad test", "999000000001"), ("Zain test", "999000000002"))
TEST_PHONES = {phone for _, phone in TEST_PEOPLE}


def is_test_phone(phone):
    try:
        return normalize_phone(phone) in TEST_PHONES
    except ValueError:
        return False


class GikiBook(VolunteerBook):
    KEY = "giki_book"
    FILE = "giki-book.json"

    @staticmethod
    def queue_key(r):
        """The test people first (shown first, and DM all sends to them first), then everyone as before."""
        return (0 if is_test_phone(r.get("phone")) else 1,) + VolunteerBook.queue_key(r)


class GikiDelivery(VolunteerDelivery):
    KEY = "giki_delivery"
    FILE = "giki-delivery.json"
    KIND = "giki_batch"
    CLAIM = "giki_batch_request_"
    REST_FROM_CASE = (
        True  # preserve the Timer's break between batches, measured from the last opening message
    )
    WAIT_STEPS = (2, 2, 3, 3, 5, 5, 10, 15)  # a WhatsApp blip costs seconds, not 15 s per message

    @staticmethod
    def follow_text(template, name, gender):
        """The share message after the case: {name} is the greeting ("Asad Bhai", "Areeba Sister"), or nothing."""
        return fill_name(template, name)

    def _gap(self, j):
        """Exactly the Timer's "Minutes between DMs" (the owner wants it exact, not 5 to 7 minutes)."""
        return float(j["gap_seconds"])


# What {name} becomes for the people the owner gave, checked one by one: first name + Bhai / Sister. A contact with
# no real name ("Giki Donor", "ZB Giki Donor", a nickname) gets nothing, so the message just reads without a name.
GREETING = {
    "giki donor 4": "",
    "ali donor giki": "Ali Bhai",
    "anas giki 140": "Anas Bhai",
    "areeba malik giki": "Areeba Sister",
    "ahmad test": "Ahmad Bhai",  # test person: to the test group
    "zain test": "Zain Bhai",  # test person: to the test group
    "asad giki donor": "Asad Bhai",
    "aymen fatima volunteer giki": "Aymen Sister",
    "ba cha giki volunteer": "",
    "donor giki good": "",
    "emaan giki 500 donor": "Emaan Sister",
    "farhan ali giki best volunt": "Farhan Bhai",
    "faris giki donor": "Faris Bhai",
    "fateha giki donor": "Fateha Sister",
    "fatima giki donor": "Fatima Sister",
    "fatima zafar giki donor": "Fatima Sister",
    "giki 500 girl": "",
    "giki donor": "",
    "giki saim donor ali": "Saim Bhai",
    "hajira giki donor 500": "Hajira Sister",
    "hamza 399 giki": "Hamza Bhai",
    "haris giki 1500": "Haris Bhai",
    "hassan 10k afzal giki": "Hassan Bhai",
    "maheera giki donor": "Maheera Sister",
    "mehliqqa khattak giki": "Mehliqqa Sister",
    "minahil giki": "Minahil Sister",
    "muarij donor giki": "Muarij Bhai",
    "mubashar giki donor younas": "Mubashar Bhai",
    "mustufa basit giki donor": "Mustufa Bhai",
    "naufal giki": "Naufal Bhai",
    "ramna giki": "Ramna Sister",
    "ramsha giki donkr khan": "Ramsha Sister",
    "ranaaziz giki donor": "Aziz Bhai",
    "sanawar giki": "Sanawar Bhai",
    "sani giki best": "Sani Bhai",
    "shah giki donor": "Shah Bhai",
    "sheikh jr giki": "Sheikh Bhai",
    "sufyan sajid giki donor": "Sufyan Bhai",
    "tooba afzal donor giki": "Tooba Sister",
    "wajiha giki": "Wajiha Sister",
    "warfansameekhan giki 500 donor": "",
    "yumna giki": "Yumna Sister",
    "zb giki donor": "",
    "giki donor 1000": "",
}
# For anyone added later: a known woman's name gets "Sister", a known man's name "Bhai", anything else just the name.
WOMEN = set(
    "aiman aimen aisha alina amna anam aqsa areeba arooj ayesha aymen emaan eman esha fateha fatima hafsa hajira "
    "hania hiba hira iqra javeria kainat khadija laiba mahnoor maheera maryam mehliqqa minahil momina noor "
    "rabia ramna ramsha sadia saima sana sara sidra sobia tooba ume urooj wajiha yumna zainab zoya".split()
)
MEN = set(
    "abdullah adeel ahmad ahmed ali anas arslan asad aziz bilal daniyal farhan faris hamza haris hassan husnain "
    "ibrahim imran irfan junaid kamran muarij mubashar muhammad mustafa mustufa naufal omer saad saim salman "
    "sanawar sani shah shahzaib sheikh sufyan talha umar usman waleed waqas yasir zain zeeshan".split()
)


def _key(label):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", clean_name(label).lower()).split())


def greeting(label):
    """What {name} becomes: "Asad Bhai", "Areeba Sister", just "Zoha", or "" when the contact has no real name."""
    key = _key(label)
    if key in GREETING:
        return GREETING[key]
    first = first_name(label)[0]
    if not first:
        return ""
    low = first.lower()
    return first + (" Sister" if low in WOMEN else " Bhai" if low in MEN else "")


def fill_name(text, name):
    """Put the greeting where {name} is; with no greeting the sentence closes up ("Salam {name}, share" -> "Salam,
    share"), so nobody reads "friend" or a label."""
    text = str(text or "")
    if "{name}" not in text:
        return text
    name = str(name or "").strip()
    if name:
        return text.replace("{name}", name)
    text = text.replace("{name}", "")
    text = re.sub(r"[ \t]+([,.!?؟،])", r"\1", text)  # "Salam , share" -> "Salam, share"
    text = re.sub(r"(^|\n)[ \t]*[,،][ \t]*", r"\1", text)  # a line that now starts with a comma
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+(\n|$)", r"\1", text).strip()
    return text[:1].upper() + text[1:]  # "{name}, please share" -> "Please share"


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

    @staticmethod
    def first_name(label):
        """(what {name} becomes, gender word). The greeting already carries Bhai / Sister."""
        return greeting(label), ""

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

    def add_test_people(self):
        """Ahmad test and Zain test, added once at the top (with the owner's list; not in previews or tests).
        Removed later, they stay removed."""
        store = self.app.STORE
        if not store or not self.test_people_on() or store.get(self.TEST_FLAG):
            return
        with self.lock:
            if store.get(self.TEST_FLAG):
                return
            for name, phone in TEST_PEOPLE:
                self.book.add(name, phone, source="Giki test: goes to the GiveLife test group")
            store.put(self.TEST_FLAG, {"time": time.time()})

    TEST_FLAG = "giki_test_people"

    def test_people_on(self):
        """With the owner's list (not in previews or tests)."""
        path = self.seed_path()
        return bool(path and path.is_file())

    def waiting_ids(self, skip=True):
        """Who DM all would message now: everyone, minus those already messaged for this case."""
        out = []
        for r in self.book.recipients("all"):
            if r.get("deleted") or not r.get("phone"):
                continue
            if skip and (self.book.contacted(r) or r.get("delivery") in ("Uncertain", "Sending")):
                continue
            out.append(r["id"])
        return out

    partner = (
        None  # Giki 2: opening Giki also moves the chosen people over (whichever page opens first)
    )

    def view(self, query=""):
        self.seed_once()
        self.add_test_people()
        if self.partner is not None:
            self.partner.move_from_giki()
        out = super().view(query)
        out["pace"] = self.pace_values()
        out["waiting"] = len(self.waiting_ids())
        out["resumable"] = self.resumable()
        # Waiting / DMed tabs: who already got this case (or may have: never sent again by DM all)
        records = {r["id"]: r for r in self.book._load()["records"]}
        for item in out.get("items", []):
            r = records.get(item.get("id")) or {}
            sent = self.book.contacted(r)
            unsure = not sent and r.get("delivery") in ("Uncertain", "Sending")
            item["dmed"] = bool(sent or unsure)
            item["dmed_at"] = r.get("last_sent_at") if sent else None
            item["dmed_unsure"] = unsure
        return out

    def resumable(self):
        """After Stop DMs (or a stop of any kind) in the last 36 hours: how many people are still waiting, for
        Resume DMs. 0 while sending, or when nothing was stopped."""
        jobs = self.jobs.export_jobs().get("jobs", [])
        j = jobs[-1] if jobs else None
        if not j or self.jobs.active:
            return 0
        stopped = j.get("state") in ("Stopped", "Interrupted") and (
            time.time() - j.get("updated_at", 0) <= self.jobs.AUTO_WINDOW
        )
        remaining = self.jobs._remaining(j, allow_expired=True) if stopped else None
        return len(remaining or []) + len(self.jobs.half_sent())

    def resume(self, body):
        """Resume DMs: DM all again for the people still waiting, with today's case and share message and the saved
        timer. The first DM goes at once."""
        for _ in range(
            40
        ):  # a batch that is still stopping (finishing its person): wait up to 40 s
            if not self.jobs.active:
                break
            time.sleep(1)
        if self.jobs.active:
            raise ValueError("The DMs are still stopping. Try again in a few seconds.")
        with self.jobs.REPAIR_LOCK:
            self.jobs._settle_in_flight()
        if not self.resumable():
            raise ValueError("Nothing to resume. Press DM all to start again.")
        j = self.jobs.export_jobs()["jobs"][-1]
        # first: anyone a Stop or a restart left half-sent gets only what they are missing (2nd, 3rd, share)
        finished = self.jobs.finish_half_sent(j["id"])
        j = self.jobs.export_jobs()["jobs"][-1]
        self.jobs.check_chat_complete(j)
        remaining = self.jobs._remaining(j, allow_expired=True)
        if not remaining:
            return {
                "job": self.jobs.status(),
                "reply": f"Finished {finished} people who were missing part of their messages. Everyone has it now.",
            }
        # Resume starts at once (the owner's choice): only the people still waiting, nobody twice
        result = self.send_all(
            {"request_id": body.get("request_id"), "delay_seconds": 0},
            resume_ids=remaining,
            resume_extras={k: j[k] for k in ("after", "after_files") if k in j},
        )
        result["reply"] = "DMs resumed. Nobody who already got it gets it again."
        return result

    def _share(self, text=None, required=True):
        share = (text if isinstance(text, str) and text.strip() else self.message()).strip()
        if not share and required:
            raise ValueError("Write the share message first (tap Write, under the list).")
        if len(share) > FOLLOW_MAX:
            raise ValueError(
                f"The share message can be up to {FOLLOW_MAX:,} characters, because it follows the case."
            )
        return share

    def send_all(self, body, hold_until=None, *, resume_ids=None, resume_extras=None):
        """DM all: each person gets the case first (poster and the Group msgs text, then the PDF / video that are on),
        then the share message the owner wrote. One person at a time with the saved timer. Never twice."""
        share = self._share()
        delay = body.get("delay_seconds", 0)
        if type(delay) is not int or delay not in self.START_DELAYS:
            raise ValueError("Choose Send now, 5, 10, 15, 30 minutes, 1 hour or 2 hours.")
        case = self.case_text()
        if not isinstance(case, str) or not case.strip():
            raise ValueError("The case message is empty. Write it in Group msgs first.")
        pace = self.pace(body)
        extras = self.case_extras() if resume_extras is None else resume_extras
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
                    or old.get("chunk") != pace["chunk"]
                    or old.get("rests") != pace["rests"]
                    or old.get("after") != extras.get("after")
                    or old.get("after_files") != extras.get("after_files")
                    or old.get("custom_template") != case
                    or old.get("follow_up") != share
                ):
                    raise ValueError(
                        "This request was already used for another Giki batch. Check its delivery status."
                    )
                return {
                    "job": self.jobs._public(old),
                    "reply": "This Giki batch is already tracked. Its original send time is unchanged.",
                }
            ids = self.waiting_ids(body.get("skip_contacted", True) is not False)
            if resume_ids is not None:
                waiting = set(ids)
                ids = [ident for ident in resume_ids if ident in waiting]
            if not ids:
                raise ValueError("Everyone in the list was already messaged for this case.")
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
                hold_until=hold_until or (time.time() + delay if delay else None),
                **extras,
            )
            self.jobs._update(result["job"]["id"], start_delay_seconds=delay)
        result["reply"] = (
            f"Giki DMs scheduled to start in {delay // 60} minutes. The case goes first, then your share message."
            if delay
            else "Giki DMs started. Each person gets the case first, then your share message."
        )
        return result

    def send_case(self, body):
        """DM Case to one person: the case (poster with the Group msgs text), the 2nd / 3rd messages ticked in Timer,
        then the share message. The same as DM all, for one person. With no share message written, the case still
        goes."""
        case = self.case_text()
        case = case.strip() if isinstance(case, str) else ""
        if not case or len(case) > 8000:
            raise ValueError("The case message is empty or too long. Edit it in Group msgs first.")
        share = self._share(required=False)
        return self.jobs.start(
            "selected",
            body.get("gap_seconds", 180),
            ids=[self.book.resolve(body.get("id", ""))["id"]],
            limit=1,
            request_id=body.get("request_id"),
            poster=True,
            skip_contacted=False,
            custom_template=case,
            follow_up=share or None,
            **self.case_extras(),
        )

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
        import group_extras  # the Test sends the 2nd / 3rd messages with the case itself

        extras = group_extras.extras_for(self.app.STORE, "giki")
        return self.app.start_giki_test(case, share, **extras, line=self.LINE)  # answers at once

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

        # the 2nd / 3rd messages ticked in Timer, in order: the batch sends each as its own recorded step
        files = dict(group_extras.after_items(self.app.STORE, "giki"))
        return {"after": list(files), "after_files": files}

    def mutate(self, body):
        if body.get("action") == "import":
            return self.import_numbers(body.get("text"), dry_run=body.get("dry_run") is True)
        if body.get("action") == "pace":
            return self.set_pace(body)
        if body.get("action") == "send_all":
            return self.send_all(body)
        if body.get("action") == "test":
            return self.test(body)
        if body.get("action") == "send_case":
            return self.send_case(body)
        if body.get("action") == "resume":
            return self.resume(body)
        if body.get("action") == "to_waiting":
            return self.to_waiting(body.get("id", ""))
        if body.get("action") == "all_to_waiting":
            return self.all_to_waiting()
        return super().mutate(body)

    def to_waiting(self, ident):
        """Move to Waiting (the ··· menu in DMed): this person is treated as not messaged for this case, so DM all
        sends them the whole sequence again. Nothing is sent now. Earlier half-sent records of them are closed,
        so Resume never adds a second copy of a message on top."""
        r = self.book.resolve(ident)
        self._back_to_waiting({r["id"]})
        return {"reply": r["name"] + " is back in Waiting."}

    def all_to_waiting(self):
        """Move to Waiting for everyone in DMed at once (a new case): same as Move to Waiting, person by person."""
        with self.book.lock:
            ids = {
                r["id"]
                for r in self.book._load()["records"]
                if not r.get("deleted")
                and r.get("phone")
                and (self.book.contacted(r) or r.get("delivery") in ("Uncertain", "Sending"))
            }
        if not ids:
            raise ValueError("Nobody is in DMed.")
        self._back_to_waiting(ids)
        return {"reply": f"{len(ids)} people are back in Waiting.", "moved": len(ids)}

    def _back_to_waiting(self, ids):
        if self.jobs.active:
            raise ValueError("Stop the DMs first, then move people back to Waiting.")
        with self.book.lock:
            data = self.book._load()
            for rec in data["records"]:
                if rec["id"] in ids:
                    rec.update(
                        dm_sent=False,
                        delivery="Not contacted",
                        last_sent_at=None,
                        follow_up_state=None,
                    )
            self.book._save(data)
        jobs = self.jobs._load()
        for j in jobs.get("jobs", []):
            for receipt in j.get("receipts", []):
                if receipt.get("id") in ids:
                    receipt["seq"] = 0  # never "finished" by Resume: DM all sends the full sequence
        self.jobs._save(jobs)

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


# ------------------------------------------------------------------------------------------------ Giki 2
# The people the owner moved from Giki to Giki 2 (15 Nov). Ramsha Khan Donor Gikii had no number: added on the page.
MOVE_TO_GIKI2 = {
    "Emaan Giki 500 Donor",
    "Muarij Donor Giki",
    "Anas Giki 140",
    "Hamza 399 Giki",
    "minahil★ Giki",
    "Giki 500 Girl",
    "Areeba Malik Giki",
    "Ali Donor Giki",
    "warfansameekhan Giki 500 Donor",
    "Haris Giki 1500",
    "Hajira Giki Donor 500",
}
MOVE_FLAG = "giki2_moved_v1"
WAITING_FLAG = "giki2_all_waiting_v1"
CASE_MARKS = (
    "dm_sent",
    "delivery",
    "last_sent_at",
    "sent_count",
    "follow_up_state",
    "follow_up_at",
    "last_dm_key",
)


class Giki2Book(GikiBook):
    KEY = "giki2_book"
    FILE = "giki2-book.json"


class Giki2Delivery(GikiDelivery):
    KEY = "giki2_delivery"
    FILE = "giki2-delivery.json"
    CLAIM = "giki2_batch_request_"


class Giki2Volunteers(GikiVolunteers):
    """The Giki 2 page: the very same page and messages as Giki (share message, case, Timer and the 2nd / 3rd
    messages are shared), with its own people, its own batches and its own WhatsApp (line "giki2")."""

    BOOK = Giki2Book
    DELIVERY = Giki2Delivery
    LINE = "giki2"
    TEST_FLAG = "giki2_test_people"

    source = None  # the Giki list, set by the donors hub: the people moved from it come from there

    def seed_path(self):
        return None  # its people are added on the page (+ Add, Add many)

    def view(self, query=""):
        self.move_from_giki()
        self.all_waiting_once()
        return super().view(query)

    def all_waiting_once(self):
        """Once, after the move (the owner asked, 15 Nov): everyone on Giki 2 back to Waiting, so DM all here sends
        to them from the Giki 2 WhatsApp. Never while Giki 2 is sending."""
        store = self.app.STORE
        if not store or not store.get(MOVE_FLAG) or store.get(WAITING_FLAG) or self.jobs.active:
            return
        with self.lock:
            if store.get(WAITING_FLAG):
                return
            self.book.import_case_fields(None)  # this case's marks back to the start: not messaged
            store.put(WAITING_FLAG, {"time": time.time()})

    def move_from_giki(self):
        """Once: the people the owner chose (MOVE_TO_GIKI2) leave the Giki list for Giki 2, with their numbers and
        their "already messaged" marks for this case, so nobody gets the same DMs from both WhatsApps. Waits while a
        Giki batch is sending."""
        store, src = self.app.STORE, self.source
        if not store or src is None or store.get(MOVE_FLAG) or src.jobs.active:
            return
        with self.lock:
            if store.get(MOVE_FLAG):
                return
            moved = []
            for r in src.book._load()["records"]:
                if r.get("deleted") or r.get("name") not in MOVE_TO_GIKI2 or not r.get("phone"):
                    continue
                self.book.add(r["name"], r["phone"], source="Moved from Giki")
                data = self.book._load()
                mine = next(x for x in data["records"] if x["phone"] == r["phone"])
                for key in CASE_MARKS:  # this case's marks travel with them: never messaged twice
                    if key in r:
                        mine[key] = r[key]
                self.book._save(data)
                src.book.delete(r["id"])
                moved.append(r["name"])
            store.put(MOVE_FLAG, {"moved": moved, "time": time.time()})

    def test_people_on(self):
        return (
            os.environ.get("GIKI_SEED_FILE") != ""
        )  # Ahmad test / Zain test on top (not in previews or tests)
