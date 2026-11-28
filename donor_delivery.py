"""Explicit donor batches, saved receipts and no automatic replay after restart."""

import traceback, logging
from donor_book import _clone  # fast private copies (see there)
import copy, hashlib, json, math, random, re, threading, time, uuid
from contextlib import ExitStack, nullcontext
from functools import wraps
from pathlib import Path
from donor_book import hide_numbers, normalize_phone


def serialized_start(fn):
    @wraps(fn)
    def call(self, *args, **kwargs):
        with self.start_lock:
            self._starting_claim = None
            try:
                return fn(self, *args, **kwargs)
            except Exception:
                if self._starting_claim:
                    key, claim = self._starting_claim
                    try:
                        self.store.put(
                            key,
                            {
                                **claim,
                                "state": "Interrupted",
                                "error": "Batch startup did not finish. Check delivery results before starting a new request.",
                            },
                        )
                    except Exception:
                        pass  # Keep the original durable claim even when its status cannot be updated.
                raise
            finally:
                self._starting_claim = None

    return call


class DonorDelivery:
    KEY = "donor_delivery"
    FILE = "donor-delivery.json"
    KIND = "donor_batch"
    CLAIM = "donor_batch_request_"

    def __init__(
        self,
        folder,
        store,
        book,
        send,
        caption,
        connected,
        held,
        eligible,
        name_for,
        variants=None,
        case_closed=None,
        reserve=None,
        refresh_caption=None,
        balance=None,
    ):
        self.path = Path(folder) / self.FILE
        self.store = store
        self.book = book
        self.send = send
        self.chat_scope = nullcontext
        self.caption = caption
        self.connected = connected
        self.held = held
        self.eligible = eligible
        self.name_for = name_for
        self.lock = threading.RLock()
        self.start_lock = threading.RLock()
        self.boot = uuid.uuid4().hex
        self.stop = threading.Event()
        self.active = None
        self.manual_sent_at = 0
        self.manual_inflight = threading.Event()
        self.tried_at = None  # when the last message was handed to WhatsApp
        self.variants = variants
        self.case_closed = case_closed or (lambda: False)
        # Round selection advances the shared rotation cursor (same one single DMs use);
        # `variants` stays a pure/deterministic peek, used only for the mid-batch amount
        # refresh below, so refreshing never re-rotates or skips bank entries. Read both
        # live (not snapshotted here) so tests that swap `.variants` after construction
        # still take effect.
        self.reserve = reserve
        self.refresh_caption = refresh_caption
        self.balance = balance
        self._cache = None

    def _load(self):
        if self._cache is not None:
            return _clone(self._cache)
        raw = self.store.get(self.KEY) if self.store else None
        if raw is None and self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._cache = raw if isinstance(raw, dict) else {"jobs": []}
        return _clone(self._cache)

    # Every send step saves the whole history (database + file). Old batches kept every person's full message, so it
    # grew to megabytes per save: slow sends, busy CPU, heavy database disk use. Past every resume / repair window
    # (36 h) only the record is kept: who, when, what went. Nothing that a later send or resume reads is dropped.
    SLIM_AFTER = 48 * 3600
    HEAVY = ("caption", "captions", "personal_names", "custom_template")

    def _slim(self, jobs):
        cut = time.time() - self.SLIM_AFTER
        for j in jobs[:-1]:
            if j.get("state") in ("Starting", "Sending", "Waiting"):
                continue
            if (j.get("updated_at") or j.get("created_at") or 0) >= cut:
                continue
            for k in self.HEAVY:
                j.pop(k, None)
            for r in j.get("receipts", []):
                if isinstance(r, dict):
                    r.pop("after_ids", None)

    def _save(self, data):
        data["jobs"] = data["jobs"][-100:]
        self._slim(data["jobs"])
        if self.store:
            self.store.put(self.KEY, data)
        self._cache = _clone(data)
        if self.store:
            return  # the database is the record; the file copy is only for running without one
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def status(self):
        with self.lock:
            data = self._load()
            jobs = data.get("jobs", [])
            changed = False
            for j in jobs:
                if (
                    j.get("state") in ("Sending", "Waiting", "Starting")
                    and j.get("boot") != self.boot
                ):
                    j.update(
                        state="Interrupted",
                        error="The service restarted. Starting again by itself; nobody already sent is repeated."
                        if j.get("auto")
                        else "The service restarted. No automatic retry. Check receipts before starting again.",
                    )
                    changed = True
            if changed:
                self._save(data)
            if not jobs:
                return {"state": "Idle", "sent": 0, "skipped": 0, "failed": 0, "total": 0}
            out = self._public(jobs[-1])
            left = self._remaining(jobs[-1])
            # Older releases combined self-account and opt-out exclusions. Explain
            # legacy receipts from current verified records without replaying them.
            for receipt in out.get("receipts", []):
                if receipt.get("state") == "Skipped: opted out or blocked":
                    try:
                        phone = self.book.resolve(receipt["id"])["phone"]
                        reason = getattr(self, "exclusion_reason", lambda p: "")(phone)
                    except (ValueError, KeyError):
                        reason = ""
                    receipt["state"] = "Skipped: " + (
                        reason
                        or "Excluded by an earlier batch. Start a new batch to check eligibility again."
                    )

            if left is not None:
                out["resumable"] = len(left)
            elif jobs[-1].get("state") in ("Stopped", "Interrupted") and self.incomplete_chat(jobs[-1]):
                out["resumable"] = 1
                out["error"] = (
                    "1 of them did not get all their messages yet. Review the current chat and resume."
                )
            elif jobs[-1].get("state") == "Interrupted" and jobs[-1].get("auto") and not self.active:
                # a restart after the last person: nothing starts again, so never say it will
                half = self._half_sent_in(jobs[-1])
                if half:
                    out["error"] = (
                        f"The service restarted. {len(half)} of them did not get all their messages yet: "
                        "press Resume DMs to send only what is missing."
                    )
                else:
                    out.update(state="Completed", error="")
            out["waiting"] = self._waiting(jobs[-1])
            j = jobs[-1]
            seen = {r.get("id") for r in j.get("receipts", [])}
            out["pending"] = (
                len([i for i in j.get("ids", []) if i not in seen])
                if j.get("state") in ("Starting", "Sending", "Waiting", "Stopped", "Interrupted")
                else 0
            )
            if j.get("chunk"):
                out["batches"] = j.get("batches") or -(-j["total"] // j["chunk"])
                out["batch"] = j.get("batch", 1)
                out["next_batch_size"] = (
                    min(j["chunk"], out["pending"]) if j.get("next_batch_at") else None
                )
            return out

    RESUME_WINDOW = 12 * 3600

    def _done(self, j):
        """People who must not get this batch's DM again: sent, unconfirmed, or caught mid-send."""
        done = {
            r["id"]
            for r in j.get("receipts", [])
            if r.get("state") in ("Sent", "Uncertain")
            or str(r.get("state", "")).startswith("Skipped")
        }
        for ident in j.get("ids", []):
            try:
                record = self.book.resolve(ident)
                confirmed_after_start = bool(
                    j.get("created_at")
                    and record.get("last_sent_at")
                    and record["last_sent_at"] >= j["created_at"]
                )
                if record.get("delivery") == "Sending" or confirmed_after_start:
                    done.add(ident)
            except ValueError:
                pass
        return done

    def _remaining(self, j, allow_expired=False):
        """Who is still waiting in a recently stopped batch, or None when it cannot be continued."""
        if (
            j.get("state") not in ("Stopped", "Interrupted")
            or not allow_expired
            and time.time() - j.get("updated_at", 0)
            > (self.AUTO_WINDOW if j.get("auto") else self.RESUME_WINDOW)
        ):
            return None
        done = self._done(j)
        left = [i for i in j.get("ids", []) if i not in done]
        return left or None

    def _waiting(self, j):
        """Names still to come in this batch, in order (numbers hidden). Empty once it has finished."""
        if j.get("state") not in ("Starting", "Sending", "Waiting", "Stopped", "Interrupted"):
            return []
        seen = {r.get("id") for r in j.get("receipts", [])}
        names = []
        for ident in j.get("ids", []):
            if ident in seen:
                continue
            try:
                names.append(hide_numbers(self.book.resolve(ident)["name"]))
            except ValueError:
                pass
        return names[:100]

    def _public(self, j):
        result = {
            k: copy.deepcopy(v)
            for k, v in j.items()
            if k
            not in (
                "boot",
                "caption",
                "captions",
                "ids",
                "signature",
                "request_signature",
                "personal_names",
                "custom_template",
                "sending",
            )
        }
        if result.get("state") == "Completed" and not result.get("sent") and result.get("skipped"):
            result.update(
                state="Nothing sent",
                error="This earlier batch skipped its recipients. No DM was sent.",
            )
        return result

    def person(self, j):
        """The person being sent to right now and how many of their messages went: {"name", "done", "steps"}, or
        None between people. Steps = the case message, then each 2nd / 3rd / video / PDF, then the share message."""
        name = j.get("current") or ""
        if j.get("state") != "Sending" or not name:
            return None
        last = (j.get("receipts") or [None])[-1]
        current = last if last and last.get("name") == name else {}
        plan = self._receipt_plan(j, current)
        kinds = plan["kinds"]
        steps = 1 + len(kinds) + bool(plan["follow_up"])
        done = 0
        if last and last.get("name") == name and last.get("state") == "Sent":
            got = last.get("steps")
            if got is None and "plan" not in last and "after" not in j:
                done = steps  # files went with the first message, as one step
            else:
                done = 1 + sum(1 for k in kinds if (got or {}).get(k) == "Sent")
                done += 1 if last.get("follow_up") == "Sent" else 0
        return {"name": name, "done": min(done, steps), "steps": steps}

    def brief(self):
        """Small and cheap (copies only the newest batch, no lookups): what the Report page shows live."""
        with self.lock:
            if self._cache is None:
                self._load()
            jobs = (self._cache or {}).get("jobs") or []
            j = copy.deepcopy(jobs[-1]) if jobs else {}
        state = j.get("state") or "Idle"
        return {
            "state": state,
            "active": bool(self.active) and state in ("Starting", "Sending", "Waiting"),
            "sent": (j.get("previous_sent") or 0) + (j.get("sent") or 0),
            "total": j.get("original_total") or j.get("total") or 0,
            "current": j.get("current") or "",
            "next_at": j.get("next_at"),
            "person": self.person(j),
        }

    def _update(self, ident, **fields):
        with self.lock:
            data = self._load()
            j = next(x for x in data["jobs"] if x["id"] == ident)
            j.update(fields, updated_at=time.time())
            self._save(data)
            if (
                self.store
                and hasattr(self.store, "claim")
                and j.get("request_signature")
                and fields.get("state")
                in ("Completed", "Stopped", "Interrupted", "Nothing sent", "Failed")
            ):
                key = self.CLAIM + hashlib.sha256(j["request_id"].encode()).hexdigest()
                self.store.put(key, j)
            return _clone(j)

    def _claimed_start(self, claim, request_signature):
        if not isinstance(claim, dict) or not claim.get("request_signature"):
            raise ValueError(
                "This earlier request is already tracked. Check delivery results before starting a new request."
            )
        if claim["request_signature"] != request_signature:
            raise ValueError(
                "This request was already used for a different batch. Refresh before sending."
            )
        # A crash between claiming and saving a job must never reserve wording or dispatch again.
        return {
            "job": self._public(claim),
            "reply": "This donor batch is already tracked. Check its delivery results; it was not started again.",
        }

    @serialized_start
    def start(
        self,
        scope="important",
        gap_seconds=60,
        ids=None,
        limit=None,
        request_id=None,
        poster=True,
        run=True,
        personal_names=None,
        chunk=None,
        rest_seconds=1200,
        fresh=False,
        rests=None,
        jitter=None,
        skip_contacted=None,
        hold_until=None,
        custom_template=None,
        attachment=None,
        resume_id=None,
        follow_up=None,
        owner=None,
        origin=None,
        pdf=False,
        video=False,
        after=None,
        after_files=None,
    ):
        if type(pdf) is not bool or type(video) is not bool:
            raise ValueError("PDF and video must be on or off.")
        if after_files is not None and (
            not isinstance(after_files, dict)
            or set(after_files) != set(after or [])
            or any(
                not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{32}", v)
                for v in after_files.values()
            )
        ):
            raise ValueError("Review the selected attachments.")
        if after is not None and (
            not isinstance(after, list) or any(k not in self.EXTRA_LABEL for k in after)
        ):
            raise ValueError("Choose the Poster pic, PDF or Video for the messages after the case.")
        if after is None and self.store is not None:
            import group_extras

            # the owner put the files in a different order (1st, 2nd, 3rd): each goes as its own recorded step
            after = group_extras.dm_after(self.store, pdf, video)
        if follow_up is not None and (
            not isinstance(follow_up, str) or not follow_up.strip() or len(follow_up) > 2000
        ):
            raise ValueError("Write the follow-up message first (up to 2,000 characters).")
        if attachment is not None and (
            not isinstance(attachment, str) or not re.fullmatch("[a-f0-9]{32}", attachment)
        ):
            raise ValueError("Choose the attachment again.")
        if custom_template is not None and (
            scope != "selected"
            or not isinstance(custom_template, str)
            or not custom_template.strip()
            or len(custom_template) > 8000
        ):
            raise ValueError(
                "Write a custom message for selected recipients (up to 8,000 characters)."
            )
        if (
            type(gap_seconds) not in (float, int)
            or not math.isfinite(gap_seconds)
            or not 5 <= gap_seconds <= 600
        ):
            raise ValueError("Choose a gap from 5 seconds to 10 minutes. Suggested: 3–5 minutes.")
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 1000):
            raise ValueError("Choose a recipient count of 1–1,000.")
        if type(poster) is not bool:
            raise ValueError("Poster must be on or off.")
        if chunk is not None and (type(chunk) is not int or not 1 <= chunk <= 20):
            raise ValueError("Choose 1–20 DMs per round.")
        if (
            type(rest_seconds) not in (float, int)
            or not math.isfinite(rest_seconds)
            or not 60 <= rest_seconds <= 7200
        ):
            raise ValueError("Choose a rest between rounds from 1 to 120 minutes.")
        if rests is not None:
            if (
                not isinstance(rests, list)
                or not 1 <= len(rests) <= 50
                or any(
                    type(x) not in (float, int) or not math.isfinite(x) or not 60 <= x <= 86400
                    for x in rests
                )
            ):
                raise ValueError("Choose each pause between batches from 1 minute to 24 hours.")
            rests = [float(x) for x in rests]
        elif chunk:
            rests = [float(rest_seconds)]
        if jitter is not None:
            if (
                not isinstance(jitter, dict)
                or any(
                    type(jitter.get(k)) not in (float, int) or not -300 <= jitter[k] <= 600
                    for k in ("min", "max")
                )
                or jitter["min"] > jitter["max"]
            ):
                raise ValueError(
                    "Random gap: choose a minimum and maximum change in seconds, minimum first."
                )
            jitter = {"min": float(jitter["min"]), "max": float(jitter["max"])}
        gap = max(5.0, float(gap_seconds))
        rid = str(request_id or uuid.uuid4().hex)
        if not 1 <= len(rid) <= 100:
            raise ValueError("Invalid send request.")
        request_signature = hashlib.sha256(
            json.dumps(
                [
                    scope,
                    gap,
                    ids,
                    limit,
                    poster,
                    personal_names,
                    chunk,
                    rests,
                    jitter,
                    skip_contacted,
                    hold_until,
                    custom_template,
                    attachment,
                    resume_id,
                    follow_up,
                    owner,
                    origin,
                    fresh,
                    *([pdf, video] if pdf or video else []),
                    *([after] if after is not None else []),
                    *([after_files] if after_files is not None else []),
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        claim_key = self.CLAIM + hashlib.sha256(rid.encode()).hexdigest()
        with self.lock:
            # A different process may have written a job since this instance cached it.
            if self.store:
                persisted = self.store.get(self.KEY)
                if isinstance(persisted, dict):
                    self._cache = copy.deepcopy(persisted)
            previous = next(
                (job for job in self._load().get("jobs", []) if job.get("request_id") == rid),
                None,
            )
        if previous:
            previous_signature = previous.get("request_signature")
            if previous_signature is None:
                # Old jobs predate request signatures. Recreate their original signature
                # using the captions and recipient snapshot they already reserved.
                legacy = [
                    scope,
                    gap,
                    ids,
                    limit,
                    poster,
                    previous.get("captions"),
                    custom_template,
                    attachment,
                    personal_names,
                    chunk,
                    rests,
                    jitter,
                    hold_until,
                    previous.get("ids"),
                ]
                previous_signature = hashlib.sha256(
                    json.dumps(legacy, sort_keys=True).encode()
                ).hexdigest()
                matches = previous_signature == previous.get("signature")
            else:
                matches = previous_signature == request_signature
            if not matches:
                raise ValueError(
                    "This request was already used for a different batch. Refresh before sending."
                )
            return {
                "job": self._public(previous),
                "reply": "This request is already tracked. It was not started again.",
            }
        if self.store and hasattr(self.store, "claim"):
            claim = self.store.get(claim_key)
            if claim:
                return self._claimed_start(claim, request_signature)
        if self.case_closed():
            raise ValueError(
                "The case is complete (Rs. 0 left), so no donor DMs were started. Set a new amount left first if you need to ask again."
            )
        if self.held():
            raise ValueError("Sending is on hold. Resume it before starting DMs.")
        caption = custom_template if custom_template is not None else self.caption()
        if not isinstance(caption, str) or not caption.strip():
            raise ValueError("The saved DM message is empty. Edit it first.")
        cap = min(limit or 1000, 1000) if chunk else min(limit or 20, 20)
        skip = bool(chunk) if skip_contacted is None else bool(skip_contacted)
        order = None
        if scope == "selected":
            if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
                raise ValueError("Choose the recipients again.")
            order = {ident: index for index, ident in enumerate(dict.fromkeys(ids))}
        rows = self.book.recipients(scope, order, None)
        already = 0
        if skip and scope != "selected":
            # Someone whose last DM was unconfirmed or caught mid-send is never asked again by a skip-contacted batch.
            fresh_rows = [
                r
                for r in rows
                if not self.book.contacted(r) and r.get("delivery") not in ("Uncertain", "Sending")
            ]
            already = len(rows) - len(fresh_rows)
            rows = fresh_rows
        if order is not None:
            rows.sort(key=lambda row: order[row["id"]])
        rows = rows[:cap]
        if personal_names is not None:
            if (
                scope != "selected"
                or not isinstance(personal_names, dict)
                or not isinstance(ids, list)
                or set(personal_names) != set(ids)
            ):
                raise ValueError("Invalid pasted donor names. Preview the donors again.")
            for value in personal_names.values():
                if (
                    not isinstance(value, (tuple, list))
                    or len(value) != 2
                    or not isinstance(value[0], str)
                    or value[1] not in ("Brother", "Sister")
                ):
                    raise ValueError("Invalid pasted donor name.")
        resumed = ""
        self.status()
        with self.lock:
            jobs = self._load().get("jobs", [])
            prev = jobs[-1] if jobs else None
        if resume_id:
            prev = next((j for j in jobs if j.get("id") == resume_id), None)
        if resume_id and (
            not prev
            or prev.get("id") != resume_id
            or prev.get("scope") != scope
            or prev.get("state") not in ("Stopped", "Interrupted")
        ):
            raise ValueError(
                "The stopped batch changed. Check its delivery results before resuming."
            )
        same_selection = bool(
            prev
            and prev.get("owner") == owner
            and prev.get("origin") == origin
            and prev.get("custom_template") == custom_template
            and prev.get("attachment") == attachment
            and (scope != "selected" or prev.get("ids") == list(dict.fromkeys(ids or [])))
        )
        left = (
            self._remaining(prev, allow_expired=bool(resume_id))
            if prev
            and not fresh
            and prev.get("scope") == scope
            and (bool(resume_id) or same_selection)
            else None
        )
        if resume_id and left is None:
            raise ValueError(
                "Everyone in the stopped batch was already handled. Nothing was sent again."
            )
        same_batch = (
            prev
            and not fresh
            and prev.get("scope") == scope
            and (bool(resume_id) or same_selection)
        )
        recent = prev and time.time() - prev.get("updated_at", 0) <= (
            self.AUTO_WINDOW if prev.get("auto") else self.RESUME_WINDOW
        )
        if (
            left is None
            and same_batch
            and recent
            and prev.get("state") in ("Stopped", "Interrupted")
        ):
            # The stopped batch already reached everyone (sent or unconfirmed). Starting a new one would DM them again.
            done = self._done(prev)
            unsure = sum(1 for r in prev.get("receipts", []) if r.get("state") == "Uncertain")
            raise ValueError(
                f"Everyone in your last batch was already handled ({len(done) - unsure} sent"
                + (f", {unsure} not confirmed: check WhatsApp" if unsure else "")
                + '). Nothing was sent again. Choose "Start over" to send to everyone again.'
            )
        if left is not None:
            if resume_id:
                follow_up = prev.get("follow_up")
                pdf, video = bool(prev.get("pdf")), bool(prev.get("video"))
                after = prev.get("after")
                after_files = prev.get("after_files")
            by = {r["id"]: r for r in self.book.recipients(scope, order, None)}
            mine = [by[i] for i in left if i in by]
            if not mine:
                raise ValueError(
                    "Everyone left in the stopped batch is gone or excluded. Choose Start over to send to the whole list again."
                )
            skipped = len(prev["ids"]) - len(left)
            rows = mine[: min(limit or 1000, 1000) if chunk else min(limit or 20, 20)]
            if personal_names is not None:
                keep = {r["id"] for r in rows}
                personal_names = {k: v for k, v in personal_names.items() if k in keep}
                ids = [i for i in (ids or []) if i in keep]
            resumed = f"Continuing your stopped batch: {skipped} already handled (sent or unconfirmed) are skipped, {len(rows)} left. "
        if not rows:
            raise ValueError(
                'Everyone in this audience was already contacted. Tick "include people already contacted" to send again.'
                if already
                else "There are no donors in this audience."
            )
        with self.lock:
            if self.active:
                raise ValueError(
                    "A donor batch is already running. Stop it or wait for it to finish."
                )
            if not self.store:
                raise ValueError("Persistent sending records are unavailable. Nothing was sent.")
            if not self._connected_soon():
                raise ValueError("WhatsApp is disconnected. Link it before sending.")
            ident = uuid.uuid4().hex
            now = time.time()
            reservation = {
                "id": ident,
                "request_id": rid,
                "request_signature": request_signature,
                "boot": self.boot,
                "state": "Starting",
                "total": len(rows),
                "sent": 0,
                "skipped": 0,
                "failed": 0,
                "created_at": now,
            }
            if hasattr(self.store, "claim"):
                if not self.store.claim(claim_key, reservation):
                    return self._claimed_start(self.store.get(claim_key), request_signature)
                self._starting_claim = (claim_key, reservation)
        # Each round of up to `chunk` people reserves its own versions from the shared
        # rotation cursor, so later rounds (and later batches, and single DMs) continue
        # forward through the bank instead of reusing the same first few versions.
        picker = self.reserve or self.variants
        size = chunk or len(rows)
        captions = []
        preserved = {}
        if resume_id and prev and len(prev.get("captions", [])) == len(prev.get("ids", [])):
            preserved = dict(zip(prev["ids"], prev["captions"]))
            if any(
                not isinstance(preserved.get(r["id"]), str) or not preserved[r["id"]].strip()
                for r in rows
            ):
                preserved = {}
        for start in range(0, len(rows), size):
            part = len(rows[start : start + size])
            if preserved:
                captions += [preserved[r["id"]] for r in rows[start : start + size]]
                continue
            texts = picker(part) if picker and custom_template is None else [caption] * part
            # Start with whatever versions are ready (even fewer than the round size). The
            # shared cursor rotates through them in order, so a round larger than the bank
            # reuses earlier versions, never back to back. Missing ones fill in behind.
            if (
                picker
                and custom_template is None
                and (
                    not isinstance(texts, list)
                    or len(texts) != part
                    or any(not isinstance(text, str) or not text.strip() for text in texts)
                    or (part > 1 and len(set(texts)) < 2)
                )
            ):
                raise ValueError(
                    "Save at least 2 different messages in Messages before starting this batch."
                )
            captions += texts
        signature = hashlib.sha256(
            json.dumps(
                [
                    scope,
                    gap,
                    ids,
                    limit,
                    poster,
                    captions,
                    custom_template,
                    attachment,
                    personal_names,
                    chunk,
                    rests,
                    jitter,
                    hold_until,
                    [r["id"] for r in rows],
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.lock:
            data = self._load()
            previous = next((j for j in data["jobs"] if j.get("request_id") == rid), None)
            if previous:
                if previous["signature"] != signature:
                    raise ValueError(
                        "This request was already used for a different batch. Refresh before sending."
                    )
                return {
                    "job": self._public(previous),
                    "reply": "This request is already tracked. It was not started again.",
                }
            job = {
                "id": ident,
                "request_id": rid,
                "signature": signature,
                "request_signature": request_signature,
                "boot": self.boot,
                "scope": scope,
                "gap_seconds": gap,
                "poster": poster,
                "ids": [r["id"] for r in rows],
                "caption": caption,
                "captions": captions,
                "state": "Starting",
                "sent": 0,
                "skipped": 0,
                "failed": 0,
                "total": len(rows),
                "current": "",
                "receipts": [],
                "created_at": now,
                "updated_at": now,
                "next_at": None,
            }
            job.update(auto=True, batch=1, hold_until=hold_until)
            if origin:
                job["origin"] = origin
            if self.balance:
                job["caption_balance"] = (
                    prev.get("caption_balance", self.balance()) if preserved else self.balance()
                )
            if left is not None:
                confirmed_ids = {
                    r["id"] for r in prev.get("receipts", []) if r.get("state") == "Sent"
                }
                for donor_id in prev[
                    "ids"
                ]:  # not `ident`: that is this batch's own id (self.active below)
                    try:
                        record = self.book.resolve(donor_id)
                        if record.get("last_sent_at") and record["last_sent_at"] >= prev.get(
                            "created_at", float("inf")
                        ):
                            confirmed_ids.add(donor_id)
                    except ValueError:
                        pass
                job.update(
                    original_total=prev.get("original_total", prev["total"]),
                    previous_sent=prev.get("previous_sent", 0) + len(confirmed_ids),
                    chunk_offset=prev.get("chunk_offset", 0) + len(prev["ids"]) - len(left),
                )
                unfinished = prev.get("resume_from") or prev["id"]
                job["resume_from"] = unfinished
            if chunk:
                job.update(
                    chunk=chunk, rest_seconds=rests[0], rests=rests, batches=-(-len(rows) // chunk)
                )
            if jitter:
                job["jitter"] = jitter
            if personal_names is not None:
                job["personal_names"] = copy.deepcopy(personal_names)
            if custom_template is not None:
                job["custom_template"] = custom_template
            if follow_up:
                job["follow_up"] = follow_up.strip()
            if pdf:
                job["pdf"] = True  # the case's PDF follows each DM (poster + caption first)
            if video:
                job["video"] = True  # then its video
            if after is not None:
                job["after"] = list(
                    after
                )  # Giki: the 2nd / 3rd messages, each its own recorded step
            if after_files is not None:
                job["after_files"] = dict(after_files)
            if owner:
                job["owner"] = str(owner)[:40]  # which Reports > Auto control started this batch
            if attachment:
                job["attachment"] = attachment
            data["jobs"].append(job)
            self._save(data)
            if self._starting_claim:
                self.store.put(claim_key, job)
                self._starting_claim = None
            self.active = ident
            self.stop.clear()
        if run:
            threading.Thread(target=self._run, args=(copy.deepcopy(job),), daemon=True).start()
        pauses = ", ".join(f"{x / 60:g}" for x in (job.get("rests") or []))
        rounds = (
            (
                f" {job['batches']} batches of up to {chunk}. Pause between batches: {pauses} min. Everything continues by itself, even with the app closed. Say stop any time."
                if job.get("chunk")
                else ""
            )
            + (
                f" Gap between DMs varies by {jitter['min']:g} to {jitter['max']:+g} seconds."
                if jitter
                else ""
            )
            + (f" {already} already contacted were left out." if already else "")
        )
        return {
            "job": self._public(job),
            "reply": resumed
            + f"Started {len(rows)} {scope.replace('_', ' ')} donor DMs. First sends now; next DMs {(f'{gap:g} sec' if gap < 60 else f'{gap / 60:g} min')} apart, with different wording for each person. Prior confirmed sends do not prevent this explicit batch."
            + rounds
            + (" Short gaps can get a number restricted by WhatsApp." if gap < 60 else ""),
        }

    def configure(self, ident, settings):
        """Change only future dispatch settings of this exact existing job."""
        allowed = {"gap_seconds", "chunk", "rests", "poster", "jitter", "follow_up", "pdf", "video"}
        if not isinstance(settings, dict) or not settings or set(settings) - allowed:
            raise ValueError("Choose gap, batch size, pauses or poster settings.")
        values = copy.deepcopy(settings)
        if "gap_seconds" in values and (
            type(values["gap_seconds"]) not in (int, float)
            or not math.isfinite(values["gap_seconds"])
            or not 5 <= values["gap_seconds"] <= 600
        ):
            raise ValueError("Choose a gap from 5 seconds to 10 minutes.")
        if "chunk" in values and (
            type(values["chunk"]) is not int or not 1 <= values["chunk"] <= 20
        ):
            raise ValueError("Choose 1 to 20 people per batch.")
        if "poster" in values and type(values["poster"]) is not bool:
            raise ValueError("Poster must be on or off.")
        for flag in ("pdf", "video"):
            if flag in values and type(values[flag]) is not bool:
                raise ValueError("PDF and video must be on or off.")
        if "follow_up" in values:
            fu = values["follow_up"]
            if fu is not None and (not isinstance(fu, str) or not fu.strip() or len(fu) > 2000):
                raise ValueError("Write the follow-up message first (up to 2,000 characters).")
            values["follow_up"] = fu.strip() if fu else None
        if "rests" in values and (
            not isinstance(values["rests"], list)
            or not 1 <= len(values["rests"]) <= 50
            or any(
                type(x) not in (int, float) or not math.isfinite(x) or not 60 <= x <= 86400
                for x in values["rests"]
            )
        ):
            raise ValueError("Choose pauses from 1 minute to 24 hours.")
        jitter = values.get("jitter")
        if jitter is not None and (
            not isinstance(jitter, dict)
            or any(
                type(jitter.get(k)) not in (int, float)
                or not math.isfinite(jitter[k])
                or not -300 <= jitter[k] <= 600
                for k in ("min", "max")
            )
            or jitter["min"] > jitter["max"]
        ):
            raise ValueError("Check the random gap range.")
        with self.lock:
            data = self._load()
            job = next((j for j in data["jobs"] if j.get("id") == ident), None)
            if (
                not job
                or job.get("state") not in ("Starting", "Sending", "Waiting")
                or self.active != ident
            ):
                raise ValueError("This batch is no longer running. No new batch was started.")
            values.update(
                settings_revision=job.get("settings_revision", 0) + 1, updated_at=time.time()
            )
            job.update(values)
            if job.get("chunk"):
                job["batches"] = -(-(job.get("original_total") or job["total"]) // job["chunk"])
            self._save(data)
            running = getattr(self, "running_job", None)
            if running and running.get("id") == ident:
                running.update(values)
            return {
                "job": self._public(job),
                "reply": "Settings saved. The existing batch continues; sent DMs are unchanged.",
            }

    stop_at = 0.0

    def cancel(self):
        self.stop_at = time.time()
        self.stop.set()
        return {
            "reply": "Stopping the donor batch. Any message already in flight may still complete.",
            "job": self.status(),
        }

    def export_jobs(self):
        with self.lock:
            return self._load()

    def import_jobs(self, data=None):
        with self.lock:
            data = (
                data
                if isinstance(data, dict) and isinstance(data.get("jobs"), list)
                else {"jobs": []}
            )
            self._save(copy.deepcopy(data))

    def _gap(self, j):
        """The wait before the next DM. 3 min or more: random from the chosen gap up to 7 min (never a robotic rhythm).
        Under 3 min (the owner chose seconds or a short gap): the chosen gap, varied up to 25% so it is not exact."""
        base = float(j["gap_seconds"])
        if j.get("origin") == "auto_toggle" and j.get("jitter"):
            x, floor = base, 5.0  # Auto: exactly the chosen gap, varied only by the chosen seconds
        elif base >= 180.0:
            x, floor = random.uniform(base, max(base, 420.0)), 180.0
        else:
            x, floor = random.uniform(base, base * 1.25), 5.0
        jit = j.get("jitter")
        return max(floor, x + random.uniform(jit["min"], jit["max"])) if jit else x

    def _rest(self, j, batch):
        rests = j.get("rests") or [j.get("rest_seconds", 1200)]
        return float(rests[min(max(batch, 1), len(rests)) - 1])

    def _sleep_until(self, due):
        """Wait in short steps so Stop answers fast. True when the owner stopped it."""
        while time.time() < due:
            context = getattr(self, "wait_context", None)
            if context:
                waiting, base, phase = context
                revised = base + self._rest(waiting, phase)
                if revised != due:
                    due = revised
                    self._update(waiting["id"], next_at=due, next_batch_at=due)
                    if time.time() >= due:
                        break
            if self.stop.wait(min(2, max(0.1, due - time.time()))):
                return True
        return self.stop.is_set()

    def _fresh_caption(self, j, index):
        """The wording saved when the batch started, but with today's amount: donations that arrive while a long batch waits
        between DMs must not be sent as an old balance."""
        if "custom_template" in j:
            ident = j["ids"][index]
            name = (j.get("personal_names", {}).get(ident) or ("", "Brother"))[0]
            return j["custom_template"].replace("{name}", name or "Bhai")
        captions = j.get("captions", [j["caption"]] * len(j["ids"]))
        saved = captions[index]
        if self.reserve:
            return (
                self.refresh_caption(saved, j.get("caption_balance"))
                if self.refresh_caption
                else saved
            )
        if not self.variants:
            return saved
        try:
            size = j.get("chunk") or len(j["ids"])
            fresh = self.variants(min(size, len(j["ids"])))
            return (
                fresh[index % size]
                if isinstance(fresh, list)
                and index % size < len(fresh)
                and isinstance(fresh[index % size], str)
                and fresh[index % size].strip()
                else saved
            )
        except Exception:
            return saved

    @staticmethod
    def follow_text(template, name, gender):
        """'{name}' becomes the saved greeting: Sohaib Bhai / Areeba Sister / just the name."""
        word = "Sister" if gender == "Sister" else "" if gender == "Neutral" and name else "Bhai"
        return template.replace("{name}", (name + " " + word).strip() if name else word or "Bhai")

    EXTRA_LABEL = {"pdf": "PDF", "video": "video", "poster": "poster picture"}

    @staticmethod
    def _after_kinds(j):
        """What follows the first message, in order: the Giki 2nd / 3rd messages, or the DM video then PDF."""
        if "after" in j:
            return list(j["after"])
        return [k for k in ("video", "pdf") if j.get(k)]

    def _receipt_plan(self, j, receipt):
        return receipt.get("plan", {"kinds": self._after_kinds(j), "follow_up": j.get("follow_up")})

    def _send_extras(self, j, r, name, gender, receipts, sent, skipped):
        """After the first message was confirmed: what follows it, in order (DMs: the video, then the PDF; Giki: the
        2nd, then the 3rd message), only those ticked for this batch, each its own recorded step. A step that still
        fails stops the batch before the next file or person."""
        steps = receipts[-1].setdefault("steps", {}) if receipts else {}
        marks = receipts[-1].setdefault("after_ids", {}) if receipts else {}
        for kind in self._after_kinds(j):
            if self.held():  # Stop lets this person finish; only a hold (wrong WhatsApp) cuts it
                return "Cancelled", ""
            if not self.eligible(r["phone"]):
                return "Skipped: opted out or blocked", ""
            body = {
                "target": "phone",
                "phone": r["phone"],
                "message": "",
                "poster": False,
                "kind": "dm_extra",
                "extra": kind,
                "file_id": (j.get("after_files") or {}).get(kind),
                "name": name,
                "gender": gender,
            }
            state, problem = self._send_step(
                j,
                receipts,
                body,
                sent,
                skipped,
                note=lambda mark, kind=kind: self._mark_attempt(j, receipts, steps, kind, marks, kind, mark),
                label="The " + self.EXTRA_LABEL[kind],
            )
            self._mark(j, receipts, steps, kind, state)
            if state != "Sent":
                return state, problem
        return "Sent", ""

    def _send_step(self, j, receipts, body, sent, skipped, note, label):
        """One message after the first one, finishing the person (Stop does not cut it). Returns (state, problem):
        Sent; Not sent (it did not go: Resume sends it); Uncertain (it may have gone: never sent again); Cancelled."""
        try:
            res = self._dispatch(
                j, body, receipts, sent, skipped, finish=True, note=note
            )
        except ValueError as e:
            return "Not sent", hide_numbers(e)
        except Exception:
            return "Uncertain", f"{label} was not confirmed. Check WhatsApp. No automatic retry."
        if res is None:
            return "Cancelled", ""
        if not isinstance(res, dict) or res.get("code") != "SUCCESS":
            if isinstance(res, dict) and res.get("not_sent"):
                return "Not sent", f"{label} did not go after {self.HEAL_TRIES} tries. Resume DMs sends it."
            return "Uncertain", f"{label} was not confirmed. Check WhatsApp. No automatic retry."
        return "Sent", ""

    def _mark_attempt(self, j, receipts, steps, field, marks, key, mark):
        """Persist the step and its recovery marker together before handing it to WhatsApp."""
        steps[field] = "Sending"
        marks[key] = mark
        self._update(j["id"], receipts=receipts)

    REDO = (None, "Not sent", "Cancelled")  # never went: safe to send. "Uncertain" may have: never again

    def _checkable(self, receipt, key):
        """A step caught mid-send ("Sending") whose chat mark was kept: the chat tells whether it went."""
        return self.seen is not None and isinstance((receipt.get("after_ids") or {}).get(key), str)

    def _todo(self, j, receipt):
        """What a person whose first message went still needs: ([after kinds], share message?)."""
        if receipt.get("state") != "Sent" or not receipt.get("seq"):
            return [], False  # only sequences recorded step by step; an older record is never sent again
        if receipt.get("after_poster") == "Uncertain":
            return [], False
        plan = self._receipt_plan(j, receipt)
        steps = receipt.get("steps") or {}
        kinds = []
        blocked = False
        for kind in plan["kinds"]:
            state = steps.get(kind)
            if state == "Sent":
                continue
            if state in self.REDO or (state == "Sending" and self._checkable(receipt, kind)):
                kinds.append(kind)
            else:
                blocked = True
                break
        if "plan" not in receipt and "steps" not in receipt and "after" not in j and receipt.get("extras") not in self.REDO:
            kinds = []  # an older receipt: its files were sent together, as one step
        fu = receipt.get("follow_up")
        share = not blocked and bool(plan["follow_up"]) and (
            fu in self.REDO or fu == "Sending" and self._checkable(receipt, "share")
        )
        return kinds, share

    def incomplete_chat(self, j):
        """The first chat that still needs confirmation before this batch can resume."""
        flight = j.get("sending") or {}
        receipts = list(j.get("receipts", []))
        if flight.get("id"):
            receipts.append({"id": flight["id"], "state": "Uncertain"})
        for receipt in receipts:
            state = receipt.get("state")
            if state != "Uncertain" and (state != "Sent" or not receipt.get("seq")):
                continue
            plan = self._receipt_plan(j, receipt)
            steps = receipt.get("steps") or {}
            legacy_files_sent = "plan" not in receipt and not steps and receipt.get("extras") == "Sent"
            incomplete_files = receipt.get("after_poster") == "Uncertain" or (
                not legacy_files_sent and any(steps.get(kind) != "Sent" for kind in plan["kinds"])
            )
            incomplete_share = plan["follow_up"] and receipt.get("follow_up") != "Sent"
            if state == "Sent" and not incomplete_files and not incomplete_share:
                continue
            try:
                record = self.book.resolve(receipt["id"])
            except ValueError:
                continue
            if not self.eligible(record["phone"]):
                continue
            if state == "Uncertain":
                if record.get("delivery") in ("Uncertain", "Sending"):
                    return hide_numbers(record["name"])
                continue
            share_sent = record.get("follow_up_state") == "Sent" and (
                (record.get("follow_up_at") or 0) >= (receipt.get("time") or 0)
            )
            if incomplete_files or (incomplete_share and not share_sent):
                return hide_numbers(record["name"])
        return ""

    def check_chat_complete(self, j):
        name = self.incomplete_chat(j)
        if name:
            raise ValueError(f"Check {name}'s WhatsApp chat. The remaining recipients are still waiting.")

    def half_sent(self):
        """People from batches of the last 36 hours that a Stop, a refusal or a restart left half-sent."""
        out = []
        for j in self.export_jobs().get("jobs", []):
            if j.get("state") in ("Starting", "Sending", "Waiting") or (
                time.time() - j.get("updated_at", 0) > self.AUTO_WINDOW
            ):
                continue
            for item in self._half_sent_in(j):
                if item[1].get("id") not in {o[1].get("id") for o in out}:
                    out.append(item)
        return out

    def _half_sent_in(self, j):
        """The half-sent people of one batch: [(job, receipt, kinds, share)]. Takes no lock."""
        out = []
        for receipt in j.get("receipts", []):
            kinds, share = self._todo(j, receipt)
            if share and receipt.get("follow_up") != "Sending":
                try:  # the share message already reached them after this case (an earlier Resume): never again
                    record = self.book.resolve(receipt["id"])
                    share = not (
                        record.get("follow_up_state") == "Sent"
                        and (record.get("follow_up_at") or 0) >= (receipt.get("time") or 0)
                    )
                except ValueError:
                    share = False
            if kinds or share:
                out.append((j, receipt, kinds, share))
        return out

    def finish_half_sent(self, job_id=None):
        """Send each half-sent person only what they are missing (2nd, 3rd, share message), in order. Something
        that may already have gone is never sent again. Returns how many people were finished."""
        with self.REPAIR_LOCK:  # Resume and the restart repair never run together (each would send it once)
            return self._finish_half_sent(job_id)

    REPAIR_LOCK = threading.Lock()

    def _settle_in_flight(self):
        """A person whose first message was being sent when the service stopped (no record of how it ended): the chat
        tells. It went = recorded as sent, so their next steps follow; it did not = they wait for the next send."""
        for j in self.export_jobs().get("jobs", []):
            flight = j.get("sending")
            if not isinstance(flight, dict) or j.get("state") in ("Starting", "Sending", "Waiting"):
                continue
            ident, mark = flight.get("id"), flight.get("after")
            try:
                r = self.book.resolve(ident)
            except ValueError:
                r = None
            if r and not any(x.get("id") == ident for x in j.get("receipts", [])):
                if r.get("delivery") == "Sent" and (r.get("last_sent_at") or 0) >= j["created_at"]:
                    found = True
                elif r.get("delivery") == "Sending" and isinstance(mark, str) and self.seen:
                    body = {
                        "target": "phone",
                        "phone": r["phone"],
                        "poster": j.get("poster", True),
                        "attachment": j.get("attachment"),
                        "kind": self.KIND,
                        "message": flight.get("message", ""),
                    }
                    try:
                        found = self.seen(body, mark)
                    except Exception:
                        found = None
                elif r.get("delivery") == "Sending":
                    continue
                else:
                    found = ""
                if found is None:
                    continue  # cannot tell now: left as it is (never sent twice); looked at again next time
                if found:
                    now = time.time()
                    self.book.delivery(ident, "Sent", now)
                    j.setdefault("receipts", []).append(
                        {
                            "id": ident,
                            "name": hide_numbers(r["name"]),
                            "state": "Sent",
                            "time": now,
                            "seq": 1,
                            "plan": self._receipt_plan(j, flight),
                        }
                    )
                else:
                    self.book.delivery(ident, "Not sent")  # it did not go: they are waiting again
            receipts = j.get("receipts", [])
            self._update(
                j["id"],
                receipts=receipts,
                sent=sum(r.get("state") == "Sent" for r in receipts),
                sending=None,
            )

    def _finish_half_sent(self, job_id=None):
        self._settle_in_flight()
        people = self.half_sent() if job_id is None else self._half_sent_in(self._job_for_repair(job_id))
        finished = 0
        for j, receipt, kinds, share in people:
            if self.held() or self.case_closed() or not self.connected():
                break
            with self.chat_scope():
                if not self._finish_person(j, receipt, kinds, share, j["receipts"]):
                    break
            finished += 1
        return finished

    def _job_for_repair(self, job_id):
        return next((j for j in self.export_jobs()["jobs"] if j["id"] == job_id), {})

    def _finish_person(self, j, receipt, kinds, share, receipts):
        """Send one person only what they are missing (their 2nd, 3rd, share message), in order. Something that may
        already have gone is never sent again. True when they now have everything."""
        try:
            r = self.book.resolve(receipt["id"])
        except ValueError:
            return False
        if not self.eligible(r["phone"]):
            return False
        name, gender = (j.get("personal_names") or {}).get(receipt["id"]) or self.name_for(
            r if r.get("dm_salutation") else r["name"]
        )
        steps = receipt.setdefault("steps", {})
        marks = receipt.setdefault("after_ids", {})
        ok = True
        for kind in kinds:
            body = {
                "target": "phone",
                "phone": r["phone"],
                "message": "",
                "poster": False,
                "kind": "dm_extra",
                "extra": kind,
                "file_id": (j.get("after_files") or {}).get(kind),
                "name": name,
                "gender": gender,
            }
            state = self._repair_step(j, receipts, body, steps, kind, marks, kind)
            steps[kind] = state
            self._update(j["id"], receipts=receipts)
            if state != "Sent":
                return False
        if share:
            body = {
                "target": "phone",
                "phone": r["phone"],
                "message": self.follow_text(self._receipt_plan(j, receipt)["follow_up"], name, gender),
                "poster": False,
                "kind": "owner_text",
                "attachment": None,
                "first_in_batch": False,
                "name": name,
                "gender": gender,
            }
            state = self._repair_step(j, receipts, body, receipt, "follow_up", marks, "share")
            receipt["follow_up"] = state
            self.book.follow_up(receipt["id"], state)
            self._update(j["id"], receipts=receipts)
            ok = ok and state == "Sent"
        return ok

    def _repair_step(self, j, receipts, body, holder, field, marks, key):
        """One missing step of a half-sent person (holder[field] is its state). A step caught mid-send is first looked
        up in the chat: there = it went; not there = it is sent now; cannot tell = never sent again."""
        if holder.get(field) == "Sending":
            try:
                found = self.seen(body, marks.get(key)) if self.seen else None
            except Exception:
                found = None
            if found:
                return "Sent"
            if found is None:
                # Keep the recovery marker usable when the chat history is temporarily offline.
                return "Sending"
        return self._send_now(
            body,
            note=lambda mark: self._mark_attempt(j, receipts, holder, field, marks, key, mark),
        )

    def _send_now(self, body, note=None):
        """One repair send, with the same chat check as a batch send. Returns Sent / Not sent / Uncertain."""
        deadline = time.time() + 60
        tries = 0
        while True:
            if self.held() or self.case_closed() or not self.eligible(body["phone"]):
                return "Cancelled"
            mark = self._peek(body)
            if note:
                note(mark)
            try:
                res = self.send(body)
            except ValueError as e:
                if str(e).startswith(self.TRANSIENT) and time.time() < deadline:
                    time.sleep(3)
                    continue
                return "Not sent"
            except Exception:
                res = {"code": "UNCERTAIN", "message": "Send not confirmed."}
            if isinstance(res, dict) and res.get("code") == "SUCCESS":
                return "Sent"
            message = str(res.get("message") or "") if isinstance(res, dict) else ""
            if message.startswith("WhatsApp disconnected") and time.time() < deadline:
                time.sleep(3)
                continue
            verdict = self._check_chat(body, mark, res)
            if verdict == "sent":
                return "Sent"
            if verdict == "unknown":
                return "Uncertain"
            tries += 1
            if tries >= self.HEAL_TRIES:
                return "Not sent"

    def _peek(self, body):
        """The chat's newest message id just before a send, or None when there is no chat check."""
        if self.peek is None:
            return None
        try:
            return self.peek(body)
        except Exception:
            return None

    def _check_chat(self, body, mark, result):
        """After an unclear or failed answer: "sent" (the message is in the chat), "not sent" (it is not there), or
        "unknown" (the chat cannot be read: then nothing is sent again). An unclear answer may be a slow upload, so
        the chat is watched for up to 2 minutes; a clear error gets two quick looks."""
        if mark is None or self.seen is None:
            return "unknown"
        unclear = (
            not isinstance(result, dict)
            or result.get("code") == "UNCERTAIN"
            or "not confirmed" in str(result.get("message") or "").lower()
        )
        for pause in self.HEAL_WATCH if unclear and not self.stop.is_set() else self.HEAL_QUICK:
            time.sleep(pause)
            try:
                found = self.seen(body, mark)
            except Exception:
                found = None
            if found is None:
                return "unknown"
            if found:
                return "sent"
        return "not sent"

    def _mark(self, j, receipts, steps, kind, state):
        """Record one step of a person's sequence at once, so after a restart it is known exactly what went."""
        steps[kind] = state
        self._update(j["id"], receipts=receipts)

    def _send_follow_up(self, j, r, name, gender, receipts, sent, skipped):
        """Only after the first message was confirmed. Stop lets it go (the person already has the case); a hold cuts
        it. With the chat check, an unclear answer is looked up before it is ever sent again."""
        if self.held():
            return "Cancelled", ""
        if not self.eligible(r["phone"]):
            return "Skipped: opted out or blocked", ""
        marks = receipts[-1].setdefault("after_ids", {}) if receipts else {}
        return self._send_step(
            j,
            receipts,
            {
                "target": "phone",
                "phone": r["phone"],
                "message": self.follow_text(j["follow_up"], name, gender),
                "poster": False,
                "kind": "owner_text",
                "attachment": None,
                "first_in_batch": False,
                "name": name,
                "gender": gender,
            },
            sent,
            skipped,
            note=lambda mark: self._mark_attempt(
                j, receipts, receipts[-1], "follow_up", marks, "share", mark
            ),
            label="The share message",
        )

    TRANSIENT = (
        "WhatsApp is disconnected",
        "The Giki WhatsApp is disconnected",  # the Giki line's own words: refused before sending, so wait the same way
        "WhatsApp disconnected",
        "Persistent send records are unavailable",
        "Another send is running",
    )
    # Problems with one person, never with the batch: record Skipped and carry on.
    PER_RECIPIENT = ("This recipient", "Your own account", "Enter a valid phone")

    def _connected_soon(self, tries=4):
        """Connected now, or within a few seconds: a one-second blip of the WhatsApp check is not "disconnected"."""
        for attempt in range(tries):
            if self.connected():
                return True
            if attempt < tries - 1:
                time.sleep(1)
        return False

    WAIT_STEPS = (15,)  # seconds before looking again when WhatsApp is not there; the last one repeats

    def _wait_step(self, n):
        """The wait before the n-th look again (1 = the first)."""
        return self.WAIT_STEPS[min(n, len(self.WAIT_STEPS)) - 1]

    def _pause(self, seconds, finish):
        """Wait while sending. True = stop now. Finishing a person (their case already went) never stops on Stop:
        their remaining messages go first, so nobody gets half a sequence."""
        if not finish:
            return self.stop.wait(seconds)
        if not self.stop.is_set():
            self.stop.wait(seconds)
        else:
            time.sleep(min(seconds, 2))
        return False

    def _dispatch(self, j, body, receipts, sent, skipped, finish=False, note=None, chat=None):
        """Send one DM. Waits for WhatsApp / storage to come back instead of giving up (30 min; 3 min while
        finishing a person whose case already went). With the chat check (peek / seen), an unclear or failed answer
        is looked up in the chat: there = sent; not there = sent again (HEAL_TRIES in all); cannot tell = as before."""
        deadline = time.time() + (180 if finish else 1800)
        tries = waits = 0
        locked = False
        while True:
            if finish and self.stop.is_set():  # Stop pressed: finish this person only if WhatsApp answers soon
                deadline = min(deadline, (self.stop_at or time.time()) + 30)
            if not self.connected():
                self._update(
                    j["id"],
                    state="Waiting",
                    next_at=None,
                    current="Waiting for WhatsApp to reconnect",
                    sent=sent,
                    skipped=skipped,
                    receipts=receipts,
                )
                while not self.connected():
                    if time.time() >= deadline:
                        raise ValueError(
                            "WhatsApp stayed disconnected for 30 minutes. Reconnect it, then press Continue."
                        )
                    waits += 1
                    if self._pause(self._wait_step(waits), finish):
                        return None
                self._update(j["id"], state="Sending", current="")  # back: the page no longer says waiting
            if self.stop.is_set() and not finish:
                return None
            if chat is not None and not locked:
                chat.enter_context(self.chat_scope())
                locked = True
                if self.stop.is_set() or self.held():
                    return None
            mark = self._peek(body)  # the chat's newest message from just before this send
            if note:
                note(mark)
            self.tried_at = time.time()
            try:
                if body.get("target") != "phone":
                    raise ValueError("DM mode requires a person, not a group.")
                normalize_phone(body.get("phone"))
            except ValueError as error:
                logging.getLogger(__name__).warning(
                    "Refused mismatched DM recipient type; nothing sent."
                )
                raise ValueError(
                    "DM recipient does not match this sending mode. Nothing sent."
                ) from error
            try:
                result = self.send(body)
            except ValueError as e:
                if str(e).startswith(self.TRANSIENT) and time.time() < deadline:
                    if locked:
                        chat.close()
                        locked = False
                    waits += 1
                    if self._pause(self._wait_step(waits), finish):
                        return None
                    continue
                raise
            except Exception:
                if mark is None:
                    raise
                result = {"code": "UNCERTAIN", "message": "Send not confirmed."}
            message = str(result.get("message", "")) if isinstance(result, dict) else ""
            if isinstance(result, dict) and result.get("code") == "ERROR":
                # Refused before anything left the phone, so it is safe to wait and try this person again.
                if message.startswith("WhatsApp disconnected") and time.time() < deadline:
                    if locked:
                        chat.close()
                        locked = False
                    waits += 1
                    if self._pause(self._wait_step(waits), finish):
                        return None
                    continue
                if message.startswith("On hold"):
                    return None
            if mark is not None and (not isinstance(result, dict) or result.get("code") != "SUCCESS"):
                verdict = self._check_chat(body, mark, result)
                if verdict == "sent":
                    return {"code": "SUCCESS", "results": {}, "message": "Confirmed in the WhatsApp chat."}
                if verdict == "not sent":
                    tries += 1
                    if tries < self.HEAL_TRIES:
                        continue  # it did not go: send it again
                    return {
                        "code": "NOT_SENT",
                        "not_sent": True,
                        "message": f"It did not go after {self.HEAL_TRIES} tries.",
                    }
            return result

    def _run(self, j):
        self.running_job = j
        receipts = []
        sent = skipped = failed = 0
        last_completion = None
        last_case = None  # when the last person's first message was handed to WhatsApp
        state = "Completed"
        error = ""
        chunk = j.get("chunk")
        gap_next = float(j["gap_seconds"])
        done_here = set()
        chat = ExitStack()
        try:
            if j.get("resume_from"):
                prior = self._job_for_repair(j["resume_from"])
                if prior.get("sending") or self.incomplete_chat(prior):
                    self.finish_half_sent(prior["id"])
                    pending = self.incomplete_chat(self._job_for_repair(prior["id"]))
                    if pending:
                        state = "Stopped"
                        error = f"Check {pending}'s WhatsApp chat. The remaining recipients are still waiting."
                        return
                self._update(j["id"], resume_from=None)
            hold = j.get("hold_until")
            if hold and hold > time.time():
                self._update(
                    j["id"],
                    state="Waiting",
                    next_at=hold,
                    next_batch_at=hold,
                    current="Waiting for the next batch time",
                )
                if self._sleep_until(hold):
                    state = "Stopped"
                    return
            for index, ident in enumerate(j["ids"]):
                chat.close()
                chunk = j.get("chunk")
                if self.stop.is_set():
                    state = "Stopped"
                    break
                if self.held():
                    state = "Stopped"
                    error = "Sending is on hold."
                    break
                if self.case_closed():
                    state = "Stopped"
                    error = "The case is complete (Rs. 0 left), so the rest of this batch was stopped before sending."
                    break
                if ident in done_here:
                    continue
                phase_index = index + j.get("chunk_offset", 0)
                if (
                    chunk
                    and phase_index
                    and phase_index % chunk == 0
                    and last_completion is not None
                ):
                    rest_from = last_case if self.REST_FROM_CASE else last_completion
                    rest = rest_from + self._rest(j, phase_index // chunk)
                    self._update(
                        j["id"],
                        state="Waiting",
                        next_at=rest,
                        next_batch_at=rest,
                        batch=phase_index // chunk + 1,
                        current=f"Resting before batch {phase_index // chunk + 1}",
                        sent=sent,
                        skipped=skipped,
                        receipts=receipts,
                    )
                    self.wait_context = (j, rest_from, phase_index // chunk)
                    try:
                        stopped = self._sleep_until(rest)
                    finally:
                        self.wait_context = None
                    if stopped:
                        state = "Stopped"
                        break
                    self._update(j["id"], next_batch_at=None)
                try:
                    r = self.book.resolve(ident)
                except ValueError:
                    skipped += 1
                    receipts.append({"id": ident, "name": "Removed donor", "state": "Skipped"})
                    continue
                if not self.eligible(r["phone"]):
                    skipped += 1
                    receipts.append(
                        {
                            "id": ident,
                            "name": hide_numbers(r["name"]),
                            "state": "Skipped: "
                            + getattr(self, "exclusion_reason", lambda p: "recipient excluded")(
                                r["phone"]
                            ),
                        }
                    )
                    continue
                if (
                    last_completion is not None
                    or self.manual_inflight.is_set()
                    or self.manual_sent_at > j["created_at"]
                ):
                    due = max(last_case or 0, self.manual_sent_at) + gap_next
                    if self.manual_inflight.is_set() or time.time() < due:
                        self._update(
                            j["id"],
                            state="Waiting",
                            next_at=due,
                            current="Waiting between DMs",
                            sent=sent,
                            skipped=skipped,
                            receipts=receipts,
                        )
                    settings_revision = j.get("settings_revision", 0)
                    while self.manual_inflight.is_set() or time.time() < due:
                        if settings_revision != j.get("settings_revision", 0):
                            settings_revision = j.get("settings_revision", 0)
                            gap_next = self._gap(j)
                        if self.stop.wait(min(0.5, max(0.1, due - time.time()))):
                            break
                        new_due = max(last_case or 0, self.manual_sent_at) + gap_next
                        if new_due != due:
                            due = new_due
                            self._update(j["id"], next_at=due)
                    if self.stop.is_set():
                        state = "Stopped"
                        break
                # Recheck deletion, hold and receipt at dispatch, not just selection time.
                try:
                    r = self.book.resolve(ident)
                except ValueError:
                    # deleted while the batch waited between DMs: counted AND listed, like the first look above
                    skipped += 1
                    done_here.add(ident)
                    receipts.append({"id": ident, "name": "Removed donor", "state": "Skipped"})
                    continue
                if self.held():
                    state = "Stopped"
                    error = "Sending is on hold."
                    break
                if self.case_closed():
                    state = "Stopped"
                    error = "The case is complete (Rs. 0 left), so the rest of this batch was stopped before sending."
                    break
                if not self.eligible(r["phone"]):
                    skipped += 1
                    receipts.append(
                        {
                            "id": ident,
                            "name": hide_numbers(r["name"]),
                            "state": "Skipped: "
                            + getattr(self, "exclusion_reason", lambda p: "recipient excluded")(
                                r["phone"]
                            ),
                        }
                    )
                    continue
                created = float(j.get("created_at") or 0)
                if created and float(r.get("last_sent_at") or 0) >= created:
                    # Another route (the owner's tap, Auto, another batch) messaged this person after this batch
                    # started: never twice. The same rule Resume already uses (see _done).
                    skipped += 1
                    done_here.add(ident)
                    receipts.append(
                        {"id": ident, "name": hide_numbers(r["name"]), "state": "Skipped: already messaged"}
                    )
                    continue
                name, gender = (
                    j["personal_names"][ident]
                    if "personal_names" in j
                    else self.name_for(r if r.get("dm_salutation") else r["name"])
                )
                self._update(
                    j["id"],
                    state="Sending",
                    next_at=None,
                    current=hide_numbers(r["name"]),
                    batch=(phase_index // chunk + 1) if chunk else 1,
                    sent=sent,
                    skipped=skipped,
                    receipts=receipts,
                )
                # Settings edited mid-upload belong to the next chat.
                current_job = dict(j)
                plan = self._receipt_plan(current_job, {})
                self.book.delivery(ident, "Sending")
                self.tried_at = None

                def record_attempt(mark):
                    self._update(
                        j["id"],
                        sending={
                            "id": ident,
                            "after": mark,
                            "plan": plan,
                            "message": caption_now,
                        },
                    )

                try:
                    caption_now = self._fresh_caption(current_job, index)
                    result = self._dispatch(
                        current_job,
                        {
                            "target": "phone",
                            "phone": r["phone"],
                            "message": caption_now,
                            "poster": current_job["poster"],
                            "kind": "owner_text" if "custom_template" in j else self.KIND,
                            "attachment": j.get("attachment"),
                            "first_in_batch": sent == 0,
                            "after_steps": "after" in j,
                            "name": name,
                            "gender": gender,
                        },
                        receipts,
                        sent,
                        skipped,
                        chat=chat,
                        note=record_attempt
                        if self.peek or plan["kinds"] or plan["follow_up"]
                        else None,
                    )
                except ValueError as e:
                    self.book.delivery(ident, "Not sent")
                    if str(e).startswith(self.PER_RECIPIENT):
                        # One blocked / opted-out / already-contacted person never stops the batch.
                        skipped += 1
                        done_here.add(ident)
                        receipts.append(
                            {
                                "id": ident,
                                "name": hide_numbers(r["name"]),
                                "state": "Skipped: " + hide_numbers(e).rstrip("."),
                            }
                        )
                        continue
                    state = "Stopped"
                    error = hide_numbers(e)
                    break
                except Exception:
                    self.book.delivery(ident, "Uncertain")
                    failed += 1
                    receipts.append(
                        {"id": ident, "name": hide_numbers(r["name"]), "state": "Uncertain"}
                    )
                    state = "Stopped"
                    error = "The current chat's first message was not confirmed. Check WhatsApp."
                    break
                if result is None:
                    self.book.delivery(ident, "Not sent")
                    state = "Stopped"
                    break
                last_completion = time.time()
                last_case = self.tried_at or last_completion
                done_here.add(ident)
                gap_next = self._gap(j)
                if not isinstance(result, dict) or result.get("code") != "SUCCESS":
                    # checked in the chat: it did not go = Not sent (they wait for the next send); else Uncertain
                    gone = "Not sent" if isinstance(result, dict) and result.get("not_sent") else "Uncertain"
                    self.book.delivery(ident, gone)
                    failed += 1
                    receipts.append({"id": ident, "name": hide_numbers(r["name"]), "state": gone})
                    state = "Stopped"
                    error = (
                        "The current chat's first message did not go. Resume DMs to try it again."
                        if gone == "Not sent"
                        else "The current chat's first message was not confirmed. Check WhatsApp."
                    )
                    break
                sent += 1
                self.book.delivery(ident, "Sent", last_completion, text=caption_now)
                receipts.append(
                    {
                        "id": ident,
                        "name": hide_numbers(r["name"]),
                        "state": "Sent",
                        "time": last_completion,
                        "seq": 1,  # every later step of this person is recorded: only these can be finished later
                        "plan": plan,
                    }
                )
                self._update(j["id"], sent=sent, skipped=skipped, receipts=receipts)
                if any(part.get("code") != "SUCCESS" for part in result.get("after") or []):
                    receipts[-1].update(after_poster="Uncertain", extras="Uncertain")
                    state = "Stopped"
                    error = "The current chat's after poster was not confirmed. Check WhatsApp."
                    break
                if plan["kinds"]:
                    ex, ex_error = self._send_extras(current_job, r, name, gender, receipts, sent, skipped)
                    receipts[-1]["extras"] = ex
                    last_completion = time.time()
                    self._update(j["id"], sent=sent, skipped=skipped, receipts=receipts)
                    if ex != "Sent":
                        state = "Stopped"
                        error = ex_error or "The current chat's attachments did not finish."
                        break
                if plan["follow_up"]:
                    fu, fu_error = self._send_follow_up(current_job, r, name, gender, receipts, sent, skipped)
                    receipts[-1]["follow_up"] = fu
                    self.book.follow_up(ident, fu)
                    last_completion = time.time()
                    self._update(j["id"], sent=sent, skipped=skipped, receipts=receipts)
                    if fu != "Sent":
                        state = "Stopped"
                        error = fu_error or "The current chat's follow-up did not finish."
                        break
        except Exception:
            traceback.print_exc()
            state = "Stopped"
            error = "The batch could not continue reliably. Check receipts before starting again."
        finally:
            chat.close()
            if not sent and skipped == len(j["ids"]) and state == "Completed":
                state = "Nothing sent"
                error = "All selected recipients were excluded. See the recipient results; this batch did not send any DM."
            if self.shutting_down and state == "Stopped" and not error:
                state = "Interrupted"  # a deploy, not the owner: carry on by itself after the restart
                error = "The service restarted. Starting again by itself; nobody already sent is repeated."
            final = dict(
                state=state,
                error=error,
                sent=sent,
                skipped=skipped,
                failed=failed,
                receipts=receipts,
                next_at=None,
                next_batch_at=None,
                current="",
                sending=None,
            )
            if state not in ("Stopped", "Interrupted"):
                final.update(caption="", captions=[], personal_names={})
            try:
                self._settle(j["id"], final)
            finally:
                with self.lock:
                    self.active = None  # always freed, so one storage failure can never block every later batch

    SETTLE_TRIES = 3

    def _settle(self, ident, final):
        """Record how a batch ended. If the database is briefly unavailable, retry a few times, then at
        least correct the in-memory record so the screen shows the truth and a later restart marks it
        Interrupted. Never raises: this runs while the worker is shutting down."""
        for attempt in range(self.SETTLE_TRIES):
            try:
                self._update(ident, **final)
                return True
            except Exception:
                if attempt + 1 < self.SETTLE_TRIES:
                    time.sleep(0.5 * (attempt + 1))
        with self.lock:
            try:
                for job in (self._cache or {}).get("jobs", []):
                    if job.get("id") == ident:
                        job.update(final, updated_at=time.time())
            except Exception:
                pass
        print("[donor-delivery] final state could not be saved; kept in memory", flush=True)
        return False

    def recover(self, allow_stopped=False):
        """After a restart, carry on with a batch the owner already confirmed. People sent, unconfirmed or caught
        mid-send are skipped, so nobody gets a second DM. Returns the started job or None."""
        if self.REPAIR_AFTER_RESTART and not self.active:
            try:
                self.status()
                self.finish_half_sent()  # first the person a restart cut in the middle of their messages
            except Exception:
                traceback.print_exc()
        with self.lock:
            self.status()
            jobs = self._load().get("jobs", [])
            j = jobs[-1] if jobs else None
        if (not self.REPAIR_AFTER_RESTART and j and j.get("auto") and not self.active
            and j.get("state") == "Interrupted" and j.get("boot") != self.boot
            and time.time() - j.get("updated_at", 0) <= self.AUTO_WINDOW
            and (j.get("sending") or self.incomplete_chat(j))):
            self.finish_half_sent(j["id"])
            j = self._job_for_repair(j["id"])
            if self.incomplete_chat(j):
                return None
        if (
            not j
            or not j.get("auto")
            or (self.REPAIR_AFTER_RESTART and self.incomplete_chat(j))
            or j.get("state")
            not in (("Interrupted", "Stopped") if allow_stopped else ("Interrupted",))
            or not self._remaining(j)
            or (j.get("boot") == self.boot and not allow_stopped)
            or self.active
            or time.time() - j.get("updated_at", 0) > self.AUTO_WINDOW
        ):
            return None
        hold = max((j.get(key) or 0 for key in ("hold_until", "next_batch_at", "next_at")))
        # A crash can land after a receipt but before the next wait was stored.
        completed = [r.get("time", 0) for r in j.get("receipts", []) if r.get("state") == "Sent"]
        for ident in j.get("ids", []):
            try:
                stamp = self.book.resolve(ident).get("last_sent_at") or 0
                if stamp >= j.get("created_at", 0):
                    completed.append(stamp)
            except ValueError:
                pass
        if completed:
            wait = float(j["gap_seconds"])
            handled = j.get("chunk_offset", 0) + len(self._done(j))
            if j.get("chunk") and handled and handled % j["chunk"] == 0:
                wait = max(wait, self._rest(j, handled // j["chunk"]))
            hold = max(hold, max(completed) + wait)

        args = dict(
            scope=j["scope"],
            gap_seconds=j["gap_seconds"],
            poster=j.get("poster", True),
            hold_until=hold if hold and hold > time.time() else None,
            skip_contacted=False,
            resume_id=j["id"],
            limit=j["total"],
        )
        if j.get("chunk"):
            args.update(chunk=j["chunk"], rests=j.get("rests"))
        if j.get("jitter"):
            args["jitter"] = j["jitter"]
        if "custom_template" in j:
            args["custom_template"] = j["custom_template"]
        if j.get("attachment"):
            args["attachment"] = j["attachment"]
        if j.get("follow_up"):
            args["follow_up"] = j["follow_up"]
        if j.get("pdf"):
            args["pdf"] = True
        if j.get("video"):
            args["video"] = True
        if "after" in j:
            args["after"] = list(j["after"])
        if "after_files" in j:
            args["after_files"] = dict(j["after_files"])
        if j.get("owner"):
            args["owner"] = j["owner"]
        if j.get("origin"):
            args["origin"] = j["origin"]
        if j["scope"] == "selected":
            if j.get("personal_names"):
                args.update(ids=j["ids"], personal_names=j["personal_names"], limit=len(j["ids"]))
            elif self.NAMES_AT_SEND:  # a list whose greeting is made at each send (Volunteers, Giki)
                args.update(ids=j["ids"], limit=len(j["ids"]))
            else:
                return None
        return self.start(**args, request_id="auto-" + uuid.uuid4().hex)

    AUTO_WINDOW = 36 * 3600
    REPAIR_AFTER_RESTART = False  # True: lists whose people get a sequence (Volunteers, Giki)
    # Self-healing (a list on its own WhatsApp: Giki). peek(body): the newest message id this WhatsApp sent in that
    # chat ("" = none, None = cannot read). seen(body, after): the id of a message of this send's type sent after
    # `after` ("" = not there, None = cannot tell). An unclear or failed answer is looked up in the chat before
    # anything is sent again: found = it went (never sent twice); not there = it did not go, so it is sent again.
    peek = None
    seen = None
    HEAL_TRIES = 3  # a message is tried at most 3 times
    HEAL_WATCH = (5, 10, 15, 30, 60)  # an unclear answer may be a slow upload: watch the chat up to 2 minutes
    HEAL_QUICK = (3, 5)  # a clear error from WhatsApp: two quick looks
    REST_FROM_CASE = False  # Giki also measures the break between batches from the opening message
    shutting_down = False  # set by the server's shutdown (a deploy): see server.graceful_exit
    NAMES_AT_SEND = False  # True: a picked-people batch needs no pasted names to carry on after a restart
