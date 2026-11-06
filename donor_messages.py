"""Instant, editable wording bank from the saved DM or an owner-supplied message."""

import copy, hashlib, json, threading, time, uuid

import dm_composer
import dm_templates
import dm_variants
import draft_workflow


class MessageBank:
    def __init__(self, app):
        self.app = app
        self.path = app.DATA / "donor-messages.json"
        self.lock = threading.RLock()
        self.gen_lock = threading.Lock()
        self.cache = None
        self.regeneration_running = set()

    def _source(self):
        return self.app.get_message("dm")["text"]

    def _fingerprint(self, source):
        return hashlib.sha256(
            (dm_templates.VERSION + "\0" + str(source or "")).encode()
        ).hexdigest()

    def _guard(self):
        """A long generation must not overwrite a newer owner instruction."""
        guard = getattr(self.app, "OWNER_GUARD", None)
        revision = getattr(guard, "revision", None)
        current = getattr(self.app, "OWNER_REVISION", None)
        if revision is not None and current is not None and revision != current:
            raise ValueError(
                "Superseded by your newer instruction. The message bank was not changed."
            )

    def _save(self, data):
        if self.app.STORE:
            self.app.STORE.put("donor_messages", data)
        self.cache = copy.deepcopy(data)
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _entries(self, texts):
        return [
            {"id": f"wording-{i + 1:02d}", "text": text, "enabled": True}
            for i, text in enumerate(texts)
        ]

    def _sync_amount(self, data):
        """Keep a custom bank aligned with the current campaign balance."""
        try:
            current = self.app.read_left()
        except (OSError, ValueError, TypeError):
            return
        old = data.get("left")
        if not isinstance(old, int) or old == current:
            data["left"] = current
            return
        changed = False
        for field in ("items", "previous_items"):
            for row in data.get(field, []):
                if isinstance(row, dict) and isinstance(row.get("text"), str):
                    row["text"] = draft_workflow.update_amount(row["text"], old, current)
                    changed = True
        for field in ("origin", "base"):
            if isinstance(data.get(field), str):
                data[field] = draft_workflow.update_amount(data[field], old, current)
                changed = True
        data["left"] = current
        if changed:
            generation = data.get("generation")
            if isinstance(generation, dict) and generation.get("state") == "Generating":
                generation.update(
                    state="Superseded",
                    error="The remaining amount changed. Retry to use the updated message.",
                )
            data["updated_at"] = time.time()
            self._save(data)

    def _build(self, source):
        left = self.app.read_left()
        case_name = self.app.active_case_name()
        # A new case must never inherit Yousuf's medical symptoms or name from
        # the legacy message bank; generic drafts are used until facts are entered.
        if case_name.casefold() in ("yousuf", "current case"):
            messages = [dm_templates.build(i, left) for i in range(dm_templates.COUNT)]
        else:
            messages = [self.app.build_dm(i, left, case_name) for i in range(dm_templates.COUNT)]
        entries = self._entries(messages)
        return {
            "fingerprint": self._fingerprint(source),
            "items": entries,
            "updated_at": time.time(),
            "source": "Structured saved DM; varied wording, not a delivery guarantee",
            "mode": "structured",
            "origin": str(source or ""),
            "requested": dm_templates.PRIMARY_COUNT,
            "left": left,
        }

    def get(self):
        with self.lock:
            source = self._source()
            fingerprint = self._fingerprint(source)
            if self.cache is None:
                self.cache = self.app.STORE.get("donor_messages") if self.app.STORE else None
                if self.cache is None and self.path.exists():
                    self.cache = json.loads(self.path.read_text(encoding="utf-8"))
            # A custom bank is deliberately kept after the DM screen changes.
            # It is only replaced by an explicit regenerate or a new generate.
            if isinstance(self.cache, dict) and self.cache.get("mode") == "custom":
                self._sync_amount(self.cache)
            elif not isinstance(self.cache, dict) or self.cache.get("fingerprint") != fingerprint:
                self._save(self._build(source))
            # A persisted in-progress job resumes after a service restart. One local
            # worker owns its id; repeated polling never starts duplicate workers.
            self._launch_regeneration(self.cache)
            out = copy.deepcopy(self.cache)
            # Saved wordings written before "EASYPAISA ONLY" show (and send) the current payment line.
            for row in out.get("items") or []:
                if isinstance(row, dict) and isinstance(row.get("text"), str):
                    row["text"] = dm_composer.payment_fix(row["text"])
            return out

    def _launch_regeneration(self, data):
        generation = data.get("generation") or {}
        ident = generation.get("id")
        if (
            generation.get("state") != "Generating"
            or not ident
            or ident in self.regeneration_running
        ):
            return
        self.regeneration_running.add(ident)
        threading.Thread(
            target=self._regenerate_worker, args=(copy.deepcopy(generation),), daemon=True
        ).start()

    def start_regeneration(self):
        """Acknowledge immediately; preserve each verified version as it arrives."""
        with self.lock:
            data = self.get()
            items = data.get("items") or []
            if not items or not isinstance(items[0].get("text"), str):
                raise ValueError("Save Message 1 before regenerating.")
            source = items[0]["text"]
            if not dm_composer.complete(source):
                raise ValueError(
                    "Keep the complete message with its paragraphs, amount and payment details."
                )
            previous = data.get("generation") or {}
            if previous.get("state") == "Generating":
                return data
            retry = previous.get("state") == "Partial" and previous.get("source") == source
            accepted = list(previous.get("accepted", [])) if retry else []
            # Keep the existing twenty-message capacity for batches; Message 1 is
            # the owner's original, with nineteen rewritten versions following it.
            generation = {
                "id": uuid.uuid4().hex,
                "source": source,
                "target": 20,
                "accepted": accepted,
                "state": "Generating",
                "error": "",
                "ready": 1 + len(accepted),
                "started_at": time.time(),
            }
            # Keep the last complete approved bank as the sending source until this one is done.
            # A half-finished earlier attempt must not replace a healthy one.
            if not retry and len(self._sendable(items)) >= self.MIN_VERSIONS:
                data["previous_items"] = items
            data.update(
                mode="custom",
                origin=source,
                fingerprint=self._fingerprint(source),
                items=self._entries([source] + accepted),
                generation=generation,
                updated_at=time.time(),
                warning="",
            )
            self._save(data)
            self._launch_regeneration(data)
            return copy.deepcopy(data)

    def _generation_current(self, generation):
        data = self.cache
        current = data.get("generation", {}) if isinstance(data, dict) else {}
        items = data.get("items", []) if isinstance(data, dict) else []
        return (
            current.get("id") == generation["id"]
            and current.get("state") == "Generating"
            and bool(items)
            and items[0].get("text") == generation["source"]
        )

    def _regenerate_worker(self, generation):
        source, ident = generation["source"], generation["id"]
        accepted = list(generation.get("accepted", []))
        prior = list(accepted)

        def record(candidates, state="Generating", error=""):
            with self.lock:
                if not self._generation_current(generation):
                    return False
                values = list(dict.fromkeys(prior + list(candidates)))
                values = [
                    text
                    for text in values
                    if isinstance(text, str) and text.strip() and text != source
                ]
                values = values[: generation["target"] - 1]
                data = copy.deepcopy(self.cache)
                data["items"] = self._entries([source] + values)
                data["generation"].update(
                    accepted=values, ready=1 + len(values), state=state, error=error
                )
                data.update(updated_at=time.time(), warning=error)
                if state == "Ready":
                    data.pop("previous_items", None)
                elif state == "Partial" and 1 + len(values) < self.MIN_VERSIONS:
                    # Too few new versions to send from: the earlier approved bank is what DMs use,
                    # so show exactly that again. The new versions stay saved for Retry.
                    earlier = data.get("previous_items")
                    if len(self._sendable(earlier)) >= self.MIN_VERSIONS:
                        data["items"] = earlier
                        data["generation"]["error"] = (
                            (error.rstrip(". ") + ". ") if error else ""
                        ) + (
                            f"Your earlier {len(earlier)} messages are in use again; "
                            f"{len(values)} new version(s) are saved. Press Regenerate to continue."
                        )
                        data["warning"] = data["generation"]["error"]
                accepted[:] = values
                self._save(data)
                return True

        try:
            with self.gen_lock:
                with self.lock:
                    if not self._generation_current(generation):
                        return
                # Continue productive partial batches automatically, with a finite
                # budget. Provider failures stop here; no endless background retry.
                for _ in range(3):
                    prior = list(accepted)
                    missing = generation["target"] - 1 - len(prior)
                    if not missing:
                        break
                    result = dm_variants.generate(
                        source, missing, avoid=[source] + prior, progress=record, allow_partial=True
                    )
                    if not record(result) or not result:
                        break
                complete = len(accepted) >= generation["target"] - 1
                record(
                    accepted[len(prior) :],
                    "Ready" if complete else "Partial",
                    ""
                    if complete
                    else "Some versions are ready. Retry to finish the remaining versions.",
                )
        except Exception as exc:
            # The callback already saved accepted work. A failure never resets it.
            record(accepted[len(prior) :], "Partial", str(exc)[:350])
        finally:
            with self.lock:
                self.regeneration_running.discard(ident)

    def generate(self, source, count=10, total=20):
        """Build a bank from a message the owner pasted. Returns the saved bank."""
        source = dm_variants.clean_source(source)
        if not dm_composer.complete(source):
            raise ValueError(
                "Paste the complete message with its paragraphs, amount and payment details."
            )
        count = max(1, min(20, int(count or 10)))
        total = max(count, min(20, int(total or 20)))
        if self.gen_lock.locked():
            # A background regeneration owns the model for minutes; waiting here would hang the
            # request until the browser gives up, with no clear result.
            raise ValueError(
                "Messages are still being written in the background. Wait until they finish, then try again."
            )
        with self.gen_lock:
            warning = ""
            left = self.app.read_left()
            canonical = dm_templates.matches(source)
            if canonical:
                texts = [dm_templates.build(i, left) for i in range(total)]
                requested = count
            else:
                texts = dm_variants.generate(source, count)
                requested = len(texts)
                if total > len(texts):
                    try:
                        texts += dm_variants.generate(source, total - len(texts), avoid=texts)
                    except ValueError as exc:
                        warning = str(exc)
            texts = texts[:20]
            data = {
                "fingerprint": self._fingerprint(source),
                "items": self._entries(texts),
                "updated_at": time.time(),
                "source": "Generated from the message you supplied; same structure and facts",
                "mode": "structured" if canonical else "custom",
                "origin": source,
                "requested": min(requested, len(texts)),
                "warning": warning,
                "left": left,
            }
            self._guard()
            with self.lock:
                self._save(data)
            return copy.deepcopy(data)

    def set_base(self, text):
        """Save the owner's base message as the only message. No versions are made until
        the owner presses Generate 20 versions (start_regeneration)."""
        text = dm_variants.clean_source(text) if isinstance(text, str) else text
        if not isinstance(text, str) or len(text) > 10000 or not dm_composer.complete(text):
            raise ValueError('Keep the complete base message: paragraphs, remaining amount and payment details.')
        with self.lock:
            data = self.get()
            if (data.get('generation') or {}).get('state') == 'Generating':
                data['generation'].update(state='Superseded', error='A new base message was saved. Press Generate 20 versions.')
            data.update(mode='custom', origin=text, fingerprint=self._fingerprint(text), base=text,
                        items=self._entries([text]), previous_items=data.get('items') or [],
                        generation={}, updated_at=time.time(), warning='',
                        source='Base message; press Generate 20 versions to create the others')
            self._save(data)
            return copy.deepcopy(data)

    TEST_KEY = 'donor_test_rotation'

    def next_test(self):
        """The next saved version for a Test DM. One version repeats; with twenty, each test is the next one."""
        with self.lock:
            texts = [row['text'] for row in self.get().get('items') or []
                     if isinstance(row, dict) and row.get('enabled', True) and isinstance(row.get('text'), str) and row['text'].strip()]
            if not texts:
                raise ValueError('Save a base message first. Nothing was sent.')
            revision = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
            saved = (self.app.STORE.get(self.TEST_KEY, {}) if self.app.STORE else self.__dict__.get('_test_cursor', {})) or {}
            index = int(saved.get('next_index', 0) or 0) % len(texts) if saved.get('revision') == revision else 0
            cursor = {'revision': revision, 'next_index': (index + 1) % len(texts)}
            if self.app.STORE:
                self.app.STORE.put(self.TEST_KEY, cursor)
            else:
                self._test_cursor = cursor
            return index + 1, len(texts), texts[index]

    def update(self, ident, text):
        if not isinstance(text, str) or len(text) > 10000 or not dm_composer.complete(text):
            raise ValueError(
                "Keep the complete case message, paragraphs, remaining amount and payment details."
            )
        with self.lock:
            data = self.get()
            row = next((r for r in data["items"] if r["id"] == ident), None)
            if row is None:
                raise ValueError("Message not found.")
            row["text"] = text
            if isinstance(data.get("generation"), dict):
                data["generation"].update(
                    state="Superseded",
                    error="A message changed. Retry regeneration to use your latest edit.",
                )
            if ident == "wording-01":
                # An owner-edited master becomes authoritative even when the
                # main DM draft is later changed in the other app screen.
                data["mode"] = "custom"
                data["origin"] = text
                data["fingerprint"] = self._fingerprint(text)
            data["updated_at"] = time.time()
            self._save(data)
            return {"saved": True, "item": row}

    def captions(self, count):
        items = [r["text"] for r in self.get()["items"] if r.get("enabled")]
        if len(set(items)) < count:
            raise ValueError(
                "Prepare enough different messages in Messages before starting this batch."
            )
        return items[:count]

    ROTATION_KEY = "donor_single_rotation"
    MIN_VERSIONS = 10

    @staticmethod
    def _sendable(rows):
        """Distinct, non-empty, enabled texts from bank rows (order kept)."""
        return [
            row["text"]
            for row in rows or []
            if isinstance(row, dict)
            and row.get("enabled", True)
            and isinstance(row.get("text"), str)
            and row["text"].strip()
        ]

    def _rotation_texts(self):
        """Validated, enabled Donors > Messages texts (the only source any DM route may use).

        While a regeneration is still writing the new versions, the bank on screen can briefly
        hold fewer than MIN_VERSIONS. The previously approved bank (kept in `previous_items`
        until the new one is complete) keeps sending in the meantime, so starting Regenerate
        never stops DMs; the newly written versions take over as soon as there are enough."""
        bank = self.get()
        texts = self._sendable(bank.get("items"))
        generation = bank.get("generation") or {}
        if len(texts) < self.MIN_VERSIONS and generation.get("state") != "Ready":
            earlier = self._sendable(bank.get("previous_items"))
            if len(earlier) >= self.MIN_VERSIONS and len(earlier) == len(set(earlier)):
                texts = earlier
        texts = list(dict.fromkeys(texts))  # a repeated wording is sent once per round, never an error
        if not texts:
            raise ValueError("Saved Donors Messages are missing. Open Messages and save one. Nothing was sent.")
        if any(not dm_composer.complete(text) for text in texts):
            raise ValueError(
                "A saved donor message is incomplete. Edit it in Donors > Messages before sending."
            )
        return texts

    def _reserve(self, count):
        """Reserve the next `count` saved Donors > Messages versions from the ONE shared
        cursor used by every donor-DM route: single clicks (reserve_one) and batch/Auto
        rounds (reserve_round) advance the same persisted pointer, in persistent storage,
        so nobody gets repeated or near-repeated wording just because a different sending
        method was used. Uncertain sends stay consumed so a restart never replays them.
        """
        if not self.app.STORE:
            raise ValueError("Saved DM rotation is unavailable. Nothing was sent.")
        texts = self._rotation_texts()
        revision = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
        saved = self.app.STORE.get(self.ROTATION_KEY, {}) or {}
        index = (
            int(saved.get("next_index", 0) or 0) % len(texts)
            if saved.get("revision") == revision
            else 0
        )
        last = saved.get("last_text")
        if len(texts) > 1 and last == texts[index]:
            index = (index + 1) % len(texts)
        selected = []
        for _ in range(count):
            value = texts[index]
            selected.append(value)
            index = (index + 1) % len(texts)
        self.app.STORE.put(
            self.ROTATION_KEY,
            {"revision": revision, "next_index": index, "last_text": selected[-1]},
        )
        return selected

    def reserve_one(self):
        """Reserve the next saved Donors > Messages version for an explicit single DM.

        All explicit one-person sends use exactly what the owner sees in
        Donors > Messages (not get_message('dm') or older templates).
        """
        with self.lock:
            return self._reserve(1)[0]

    def reserve_round(self, count):
        """Reserve `count` saved versions for one batch/Auto round, from the same shared
        cursor as reserve_one. Call this once per round at batch start, not per dispatch:
        the resulting assignment is fixed for the round and re-amount-synced later via
        captions()/the bank's own amount refresh, not by reserving again.
        """
        with self.lock:
            picked = self._reserve(count)
        self._top_up()
        return picked

    TARGET_VERSIONS = 20
    TOP_UP_COOLDOWN = 300  # seconds; a failing provider is tried once per batch start, not per round

    def _top_up(self):
        """Sending never waits for all 20 versions. When an earlier regeneration stopped part-way
        (state Partial, e.g. 14 of 20 ready), finish the rest in the background while this batch
        goes out. Only the retry path is used, so every saved version is kept; the batch in
        flight rotates the versions it already has, and later rounds pick up the new ones."""
        try:
            with self.lock:
                data = self.get()
                generation = data.get("generation") or {}
                items = data.get("items") or []
                if generation.get("state") != "Partial" or not items:
                    return
                if generation.get("source") != items[0].get("text"):
                    return
                if len(set(self._sendable(items))) >= self.TARGET_VERSIONS:
                    return
                if time.time() - float(generation.get("started_at") or 0) < self.TOP_UP_COOLDOWN:
                    return
                self.start_regeneration()
        except Exception:
            pass  # topping up is best effort and must never stop a send
