"""Explicit donor batches, saved receipts and no automatic replay after restart."""

import traceback
import copy, hashlib, json, math, random, re, threading, time, uuid
from functools import wraps
from pathlib import Path
from donor_book import hide_numbers


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
            return copy.deepcopy(self._cache)
        raw = self.store.get(self.KEY) if self.store else None
        if raw is None and self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._cache = raw if isinstance(raw, dict) else {"jobs": []}
        return copy.deepcopy(self._cache)

    def _save(self, data):
        data["jobs"] = data["jobs"][-100:]
        if self.store:
            self.store.put(self.KEY, data)
        self._cache = copy.deepcopy(data)
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
            )
        }
        if result.get("state") == "Completed" and not result.get("sent") and result.get("skipped"):
            result.update(
                state="Nothing sent",
                error="This earlier batch skipped its recipients. No DM was sent.",
            )
        return result

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
            return copy.deepcopy(j)

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
    ):
        if type(pdf) is not bool or type(video) is not bool:
            raise ValueError("PDF and video must be on or off.")
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
        rows = self.book.recipients(scope, ids, None)
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
            order = {ident: index for index, ident in enumerate(ids)}
            rows.sort(key=lambda row: order[row["id"]])
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
        left = (
            self._remaining(prev, allow_expired=bool(resume_id))
            if prev
            and not fresh
            and prev.get("scope") == scope
            and (scope != "selected" or set(prev.get("ids", [])) & set(ids or []))
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
            and (scope != "selected" or set(prev.get("ids", [])) & set(ids or []))
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
            by = {r["id"]: r for r in self.book.recipients(scope, ids, None)}
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
            if not self.connected():
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
        restarting = bool(resume_id and prev and prev.get("boot") != self.boot)
        if restarting and len(prev.get("captions", [])) == len(prev.get("ids", [])):
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

    def cancel(self):
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

    EXTRA_LABEL = {"pdf": "PDF", "video": "video"}

    def _send_extras(self, j, r, name, gender, receipts, sent, skipped):
        """After the DM (poster + caption) was confirmed: the case's PDF, then its video, only those ticked for this
        batch. Never retried; one that is not confirmed stops the next one and the batch (check WhatsApp)."""
        for kind in ("video", "pdf"):  # same order as the groups: the video, then the PDF
            if not j.get(kind):
                continue
            if self.stop.is_set() or self.held():
                return "Cancelled", ""
            if not self.eligible(r["phone"]):
                return "Skipped: opted out or blocked", ""
            try:
                res = self._dispatch(
                    j,
                    {
                        "target": "phone",
                        "phone": r["phone"],
                        "message": "",
                        "poster": False,
                        "kind": "dm_extra",
                        "extra": kind,
                        "name": name,
                        "gender": gender,
                    },
                    receipts,
                    sent,
                    skipped,
                )
            except ValueError as e:
                return "Not sent", hide_numbers(e)
            except Exception:
                return "Uncertain", f"The {self.EXTRA_LABEL[kind]} was not confirmed. Check WhatsApp. No automatic retry."
            if res is None:
                return "Cancelled", ""
            if not isinstance(res, dict) or res.get("code") != "SUCCESS":
                return "Uncertain", f"The {self.EXTRA_LABEL[kind]} was not confirmed. Check WhatsApp. No automatic retry."
        return "Sent", ""

    def _send_follow_up(self, j, r, name, gender, receipts, sent, skipped):
        """Only after the poster DM was confirmed. Never retried; an uncertain follow-up stops the batch."""
        if self.stop.is_set() or self.held():
            return "Cancelled", ""
        if not self.eligible(r["phone"]):
            return "Skipped: opted out or blocked", ""
        try:
            res = self._dispatch(
                j,
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
                receipts,
                sent,
                skipped,
            )
        except ValueError as e:
            return "Not sent", hide_numbers(e)
        except Exception:
            return "Uncertain", "Follow-up was not confirmed. Check WhatsApp. No automatic retry."
        if res is None:
            return "Cancelled", ""
        if not isinstance(res, dict) or res.get("code") != "SUCCESS":
            return "Uncertain", "Follow-up was not confirmed. Check WhatsApp. No automatic retry."
        return "Sent", ""

    TRANSIENT = (
        "WhatsApp is disconnected",
        "WhatsApp disconnected",
        "Persistent send records are unavailable",
        "Another send is running",
    )
    # Problems with one person, never with the batch: record Skipped and carry on.
    PER_RECIPIENT = ("This recipient", "Your own account", "Enter a valid phone")

    def _dispatch(self, j, body, receipts, sent, skipped):
        """Send one DM. Waits for WhatsApp / storage to come back instead of giving up (30 min)."""
        deadline = time.time() + 1800
        while True:
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
                    if self.stop.wait(15):
                        return None
            if self.stop.is_set():
                return None
            try:
                result = self.send(body)
            except ValueError as e:
                if str(e).startswith(self.TRANSIENT) and time.time() < deadline:
                    if self.stop.wait(15):
                        return None
                    continue
                raise
            message = str(result.get("message", "")) if isinstance(result, dict) else ""
            if isinstance(result, dict) and result.get("code") == "ERROR":
                # Refused before anything left the phone, so it is safe to wait and try this person again.
                if message.startswith("WhatsApp disconnected") and time.time() < deadline:
                    if self.stop.wait(15):
                        return None
                    continue
                if message.startswith("On hold"):
                    return None
            return result

    def _run(self, j):
        self.running_job = j
        receipts = []
        sent = skipped = failed = 0
        uncertain_run = 0
        last_completion = None
        state = "Completed"
        error = ""
        chunk = j.get("chunk")
        gap_next = float(j["gap_seconds"])
        done_here = set()
        try:
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
                    rest = last_completion + self._rest(j, phase_index // chunk)
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
                    self.wait_context = (j, last_completion, phase_index // chunk)
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
                    due = max(last_completion or 0, self.manual_sent_at) + gap_next
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
                        new_due = max(last_completion or 0, self.manual_sent_at) + gap_next
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
                    skipped += 1
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
                self.book.delivery(ident, "Sending")
                try:
                    result = self._dispatch(
                        j,
                        {
                            "target": "phone",
                            "phone": r["phone"],
                            "message": (caption_now := self._fresh_caption(j, index)),
                            "poster": j["poster"],
                            "kind": "owner_text" if "custom_template" in j else self.KIND,
                            "attachment": j.get("attachment"),
                            "first_in_batch": sent == 0,
                            "name": name,
                            "gender": gender,
                        },
                        receipts,
                        sent,
                        skipped,
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
                    uncertain_run += 1
                    last_completion = time.time()
                    gap_next = self._gap(j)
                    done_here.add(ident)
                    receipts.append(
                        {"id": ident, "name": hide_numbers(r["name"]), "state": "Uncertain"}
                    )
                    if uncertain_run >= self.UNCERTAIN_STOP:
                        state = "Stopped"
                        error = f"{uncertain_run} deliveries in a row were not confirmed. Check WhatsApp. Those people are never retried."
                        break
                    self._update(j["id"], failed=failed, receipts=receipts)
                    continue
                if result is None:
                    self.book.delivery(ident, "Not sent")
                    state = "Stopped"
                    break
                last_completion = time.time()
                done_here.add(ident)
                gap_next = self._gap(j)
                if not isinstance(result, dict) or result.get("code") != "SUCCESS":
                    self.book.delivery(ident, "Uncertain")
                    failed += 1
                    uncertain_run += 1
                    receipts.append(
                        {"id": ident, "name": hide_numbers(r["name"]), "state": "Uncertain"}
                    )
                    if uncertain_run >= self.UNCERTAIN_STOP:
                        state = "Stopped"
                        error = f"{uncertain_run} deliveries in a row were not confirmed. Check WhatsApp. Those people are never retried."
                        break
                    self._update(j["id"], failed=failed, receipts=receipts)
                    continue
                uncertain_run = 0
                sent += 1
                self.book.delivery(ident, "Sent", last_completion, text=caption_now)
                receipts.append(
                    {
                        "id": ident,
                        "name": hide_numbers(r["name"]),
                        "state": "Sent",
                        "time": last_completion,
                    }
                )
                self._update(j["id"], sent=sent, skipped=skipped, receipts=receipts)
                if j.get("pdf") or j.get("video"):
                    ex, ex_error = self._send_extras(j, r, name, gender, receipts, sent, skipped)
                    receipts[-1]["extras"] = ex
                    last_completion = time.time()
                    self._update(j["id"], sent=sent, skipped=skipped, receipts=receipts)
                    if ex_error:
                        state = "Stopped"
                        error = ex_error
                        break
                if j.get("follow_up"):
                    fu, fu_error = self._send_follow_up(j, r, name, gender, receipts, sent, skipped)
                    receipts[-1]["follow_up"] = fu
                    self.book.follow_up(ident, fu)
                    last_completion = time.time()
                    self._update(j["id"], sent=sent, skipped=skipped, receipts=receipts)
                    if fu_error:
                        state = "Stopped"
                        error = fu_error
                        break
        except Exception:
            traceback.print_exc()
            state = "Stopped"
            error = "The batch could not continue reliably. Check receipts before starting again."
        finally:
            if not sent and skipped == len(j["ids"]) and state == "Completed":
                state = "Nothing sent"
                error = "All selected recipients were excluded. See the recipient results; this batch did not send any DM."
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
                caption="",
                captions=[],
                personal_names={},
            )
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
        with self.lock:
            self.status()
            jobs = self._load().get("jobs", [])
            j = jobs[-1] if jobs else None
        if (
            not j
            or not j.get("auto")
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
        if j.get("owner"):
            args["owner"] = j["owner"]
        if j.get("origin"):
            args["origin"] = j["origin"]
        if j["scope"] == "selected":
            if not j.get("personal_names"):
                return None
            args.update(ids=j["ids"], personal_names=j["personal_names"], limit=len(j["ids"]))
        return self.start(**args, request_id="auto-" + uuid.uuid4().hex)

    AUTO_WINDOW = 36 * 3600
    UNCERTAIN_STOP = 3  # consecutive unconfirmed deliveries before a batch pauses
