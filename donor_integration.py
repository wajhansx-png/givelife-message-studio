"""Shared donor UI/chat commands and private delivery integration."""

import re, time, hashlib, threading, uuid, copy, datetime as dt
from donor_book import DonorBook, normalize_phone, parse_contact, send_request, PHONE
from donor_delivery import DonorDelivery


class DonorIntegration:
    def __init__(self, app):
        self.app = app
        self.book = DonorBook(app.DATA, app.STORE)
        from donor_messages import MessageBank

        self.messages = MessageBank(app)
        self.paused = bool(app.STORE.get("donor_dm_pause", False)) if app.STORE else False
        self.jobs = DonorDelivery(
            app.DATA,
            app.STORE,
            self.book,
            app.send_custom,
            lambda: self.messages.captions(1)[0],
            app.wa_ok,
            lambda: app.on_hold() or self.paused,
            self.eligible,
            self.personal_name,
            self.messages.captions,
            lambda: app.read_left() <= 0,
            reserve=self.messages.reserve_round,
            refresh_caption=lambda text,old:app.caption_facts.current(app,app.draft_workflow.update_amount(text,old,app.read_left()) if type(old) is int else text),
            balance=app.read_left,
        )
        self.jobs.exclusion_reason = self.exclusion_reason
        from donor_paste import PastedDonors

        self.pasted = PastedDonors(
            self.book,
            self.jobs,
            lambda: app.OWNER_PHONE,
            lambda label: self.personal_name(label, explicit=True),
            self._start_pasted_batch,
        )
        self.manual_lock = threading.RLock()
        self.control_lock = threading.RLock()
        from volunteers import Volunteers

        self.volunteers = Volunteers(app, self.eligible)
        from team_tasks import TeamTasks

        self.team = TeamTasks(app)
        from cases import Cases

        self.cases = Cases(app, self)
        self.revision = 0
        self._resume_due = None

    def pause_personal(self):
        with self.control_lock:
            return self._pause_personal()

    def _pause_personal(self):
        self.cancel_resume()
        if not self.paused and self.app.STORE:
            # Remember what was running so a second press can resume the whole automation.
            eng = self.app.ENGINE.s
            job = self.jobs.status()
            if not self.jobs.active and not job.get("resumable"):
                job = {}
            batch = (
                {
                    k: job[k]
                    for k in (
                        "scope",
                        "gap_seconds",
                        "poster",
                        "chunk",
                        "rests",
                        "rest_seconds",
                        "jitter",
                    )
                    if job.get(k) is not None
                }
                if job.get("scope") in ("all", "important", "top", "donated", "not_donated")
                else None
            )
            if batch:
                batch.update(limit=job["total"], resume_id=job["id"], skip_contacted=False)
            elif job.get("scope") == "selected":
                batch = self._selected_batch(job)
            self.app.STORE.put(
                "donor_dm_resume",
                {
                    "engine": bool(eng.get("dm_enabled")),
                    "daily": eng.get("dm_daily", 30),
                    "batch": batch,
                },
            )
        self.revision += 1
        self.paused = True
        if self.app.STORE:
            self.app.STORE.put("donor_dm_pause", True)
        self.jobs.cancel()
        self.app.CAMPAIGN["stop"] = True
        self.app.ENGINE.set_dms(False, self.app.ENGINE.s.get("dm_daily", 30))
        return {
            "reply": "DMs stopped (paused). Group posting is unchanged. Press Resume DMs to continue everything.",
            "paused": True,
        }

    def _selected_batch(self, job):
        """Resume settings for a pasted/bulk batch: the same people, names, message and attachment as the stopped job."""
        jobs = self.jobs.export_jobs().get("jobs", [])
        raw = next((x for x in reversed(jobs) if x.get("id") == job.get("id")), None)
        if not raw or not raw.get("ids") or not raw.get("personal_names"):
            return None
        batch = {
            k: raw[k]
            for k in (
                "gap_seconds",
                "poster",
                "chunk",
                "rests",
                "jitter",
                "custom_template",
                "attachment",
            )
            if raw.get(k) is not None
        }
        batch.update(
            scope="selected",
            ids=list(raw["ids"]),
            personal_names=copy.deepcopy(raw["personal_names"]),
            limit=len(raw["ids"]),
            resume_id=raw["id"],
            skip_contacted=False,
        )
        return batch

    def resume_personal(self):
        with self.control_lock:
            return self._resume_personal()

    def _resume_personal(self):
        self.cancel_resume()
        was_paused = self.paused
        self.paused = False
        if self.app.STORE and was_paused:
            self.app.STORE.put("donor_dm_pause", False)
        return "Personal DM sending is available again. Group posting is unchanged."

    def resume_all(self):
        with self.control_lock:
            return self._resume_all()

    def _resume_all(self):
        """Second press of Stop DMs: lift the pause, turn Auto DMs back on if they were on, and
        continue the stopped batch (nobody already sent is repeated)."""
        if self.jobs.active:
            raise ValueError(
                "The batch is still stopping. Wait for its current message to finish, then resume."
            )
        self.cancel_resume()
        info = (self.app.STORE.get("donor_dm_resume") if self.app.STORE else None) or {}
        notes = ["DMs resumed."]
        self.resume_personal()
        if info.get("batch"):
            try:
                batch = dict(info["batch"])
                jobs = self.jobs.export_jobs().get("jobs", [])
                last = jobs[-1] if jobs else {}
                if batch.get("resume_id"):
                    last = next((j for j in jobs if j.get("id") == batch["resume_id"]), {})
                # Upgrade older pause records using the actual stopped job, not default batch settings.
                if not batch.get("resume_id"):
                    if last.get("scope") != batch.get("scope") or last.get("state") not in (
                        "Stopped",
                        "Interrupted",
                        "Completed",
                    ):
                        raise ValueError(
                            "The stopped batch is unavailable. Check delivery before choosing a new batch."
                        )
                    batch = {
                        k: last[k]
                        for k in (
                            "scope",
                            "gap_seconds",
                            "poster",
                            "chunk",
                            "rests",
                            "rest_seconds",
                            "jitter",
                        )
                        if last.get(k) is not None
                    }
                    batch.update(resume_id=last["id"], limit=last["total"], skip_contacted=False)
                drained = (
                    last.get("id") == batch["resume_id"]
                    and bool(last.get("ids"))
                    and set(last["ids"]) <= self.jobs._done(last)
                )
                if drained:
                    notes.append("The stopped batch already finished; nobody was sent again.")
                else:
                    self.start_batch(**batch, request_id="resume-" + uuid.uuid4().hex)
                    notes.append(
                        "The stopped batch continues with its saved settings; nobody already handled is repeated."
                    )
            except Exception:
                self.paused = True
                if self.app.STORE:
                    self.app.STORE.put("donor_dm_pause", True)
                raise
        if info.get("engine"):
            notes.append(self.app.ENGINE.set_dms(True, info.get("daily", 30)))
        if self.app.STORE:
            self.app.STORE.put("donor_dm_resume", {})
        try:
            self.app.log_resume("Donor DMs")
        except Exception:
            pass
        return {"reply": " ".join(notes), "paused": False}

    RESUME_KEY = "donor_resume_schedule"

    def resume_status(self):
        value = self.app.STORE.get(self.RESUME_KEY, {}) if self.app.STORE else {}
        return (
            {k: value[k] for k in ("id", "due", "label", "state", "error") if k in value}
            if isinstance(value, dict)
            else {}
        )

    def cancel_resume(self):
        if not self.app.STORE:
            return
        value = self.app.STORE.get(self.RESUME_KEY, {})
        if isinstance(value, dict) and value.get("state") in ("Pending", "Failed", "Uncertain"):
            value["state"] = "Cancelled"
            self.app.STORE.put(self.RESUME_KEY, value)
        self._resume_due = False

    def schedule_resume(self, when, request_id=None):
        if not isinstance(when, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", when):
            raise ValueError("Choose a date and clock time in Pakistan time (PKT).")
        try:
            clock = dt.datetime.fromisoformat(when).replace(
                tzinfo=dt.timezone(dt.timedelta(hours=5))
            )
            due = clock.timestamp()
        except ValueError:
            raise ValueError("Choose a valid date and clock time.") from None
        now = time.time()
        if not now < due <= now + 366 * 86400:
            raise ValueError("Choose a future time within the next year (PKT).")
        with self.control_lock:
            if not self.app.STORE:
                raise ValueError("Persistent storage is unavailable. Nothing was scheduled.")
            if not self.paused:
                raise ValueError("Stop DMs before scheduling a resume.")
            old = self.app.STORE.get(self.RESUME_KEY, {})
            if request_id and old.get("request_id") == request_id:
                if old.get("due") != due:
                    raise ValueError("That request was already used for another time.")
                return {
                    "reply": "This resume is already saved.",
                    "paused": self.paused,
                    "resume": self.resume_status(),
                }
            value = {
                "id": uuid.uuid4().hex,
                "request_id": request_id,
                "due": due,
                "label": clock.strftime("%d %b %Y, %I:%M %p PKT"),
                "state": "Pending",
            }
            self.app.STORE.put(self.RESUME_KEY, value)
            self._resume_due = due
            return {
                "reply": "DMs will resume at "
                + value["label"]
                + " using your saved setup. Nothing sends before then.",
                "paused": True,
                "resume": self.resume_status(),
            }

    def tick_resume(self, now=None):
        # The background loop calls this every second. Remember in memory when nothing is scheduled
        # so the database is not queried (and kept awake) once a second; schedule/cancel update it.
        if now is None:
            due = self._resume_due
            if due is False or (due is not None and due > time.time()):
                return
        with self.control_lock:
            value = self.app.STORE.get(self.RESUME_KEY, {}) if self.app.STORE else {}
            if not isinstance(value, dict):
                return
            if now is None:
                self._resume_due = (
                    value["due"]
                    if value.get("state") == "Pending"
                    and isinstance(value.get("due"), (int, float))
                    else (None if value.get("state") == "Dispatching" else False)
                )
            if value.get("state") == "Dispatching":
                value.update(
                    state="Uncertain",
                    error="The service restarted during resume. Check delivery before resuming again.",
                )
                self.app.STORE.put(self.RESUME_KEY, value)
                return
            if value.get("state") != "Pending" or value.get("due", 0) > (
                time.time() if now is None else now
            ):
                return
            if not self.paused:
                self.cancel_resume()
                return
            if self.jobs.active:
                return  # let an in-flight Stop finish first
            value["state"] = "Dispatching"
            self.app.STORE.put(self.RESUME_KEY, value)
            try:
                self.resume_all()
                value["state"] = "Completed"
            except Exception as error:
                value.update(state="Failed", error=str(error))
            self.app.STORE.put(self.RESUME_KEY, value)

    def toggle(self):
        return self.resume_all() if self.paused else self.pause_personal()

    def test_dm(self, poster=True):
        """Send the next saved donor message (its own test cursor, never the donor rotation) to the test number, marked TEST."""
        if type(poster) is not bool:
            raise ValueError("Poster must be on or off.")
        import dm_composer

        number, total, text = self.messages.next_test()
        result = self.app.send_dm_test(dm_composer.personalize(text, "", "Brother"), poster)
        return {**result, "version": number, "total": total, "reply": f"Test DM sent: version {number} of {total}."}

    PREFS_KEY = "donor_batch_prefs"

    def prefs(self):
        """How the owner usually runs a donor batch, learned from his last confirmed one."""
        saved = self.app.STORE.get(self.PREFS_KEY) if self.app.STORE else None
        return saved if isinstance(saved, dict) else {}

    def _learn(self, body):
        if not self.app.STORE or not body.get("chunk"):
            return
        keep = {
            k: body[k]
            for k in ("gap_seconds", "chunk", "rests", "jitter", "poster")
            if body.get(k) is not None
        }
        keep["skip_contacted"] = body.get("skip_contacted", True)
        self.app.STORE.put(self.PREFS_KEY, keep)

    def start_batch(self, **body):
        with self.control_lock:
            return self._start_batch(**body)

    FOLLOW_KEY = "donor_follow_up"

    def follow_up_text(self):
        saved = self.app.STORE.get(self.FOLLOW_KEY) if self.app.STORE else None
        return str((saved or {}).get("text", "")) if isinstance(saved, dict) else ""

    def set_follow_up(self, text):
        if not isinstance(text, str) or len(text) > 2000:
            raise ValueError("Keep the follow-up under 2,000 characters.")
        if not self.app.STORE:
            raise ValueError("Persistent storage is unavailable.")
        self.app.STORE.put(self.FOLLOW_KEY, {"text": text.strip()})
        return {"follow_up": text.strip(), "reply": "Follow-up message saved."}

    def _follow_up_for(self, wanted):
        if wanted is not True:
            return None
        text = self.follow_up_text()
        if not text:
            raise ValueError("Write the follow-up in Messages → Follow-Up Message first.")
        return text

    def _start_batch(self, **body):
        body["follow_up"] = self._follow_up_for(body.get("follow_up"))
        if body["follow_up"] is None:
            body.pop("follow_up")
        self.resume_personal()
        body.setdefault("gap_seconds", 240)
        if not body.get("chunk"):
            body.setdefault("limit", 20)
        result = self.jobs.start(**body)
        self._learn(body)
        return result

    def usual_batch(self, text, request_id, scope="important"):
        """One short ask ("send dms") runs the whole Important list the way he usually does it. No dialog."""
        saved = self.prefs()
        again = bool(re.search(r"(?i)\b(again|everyone|everybody|all of them)\b", text))
        plan = dict(
            scope=scope,
            chunk=saved.get("chunk") or 20,
            gap_seconds=saved.get("gap_seconds") or 240,
            poster=saved.get("poster", True),
            skip_contacted=False if again else saved.get("skip_contacted", True),
        )
        for key in ("rests", "jitter"):
            if saved.get(key):
                plan[key] = saved[key]
        result = self.start_batch(**plan, request_id=request_id)
        pause = ", ".join(f"{x / 60:g}" for x in (plan.get("rests") or [1200]))
        how = (
            f"Using your usual way: {plan['chunk']} per batch, {(str(round(plan['gap_seconds'])) + ' sec') if plan['gap_seconds'] < 60 else format(plan['gap_seconds'] / 60, 'g') + ' min'} between DMs, {pause} min pause between batches"
            + (", random gaps" if plan.get("jitter") else "")
            + (". " if saved else " (first time, standard settings). ")
        )
        result["reply"] = (
            how
            + result["reply"]
            + ' You do not need to do anything else. Say stop to pause; say "dm important again" to include people already contacted.'
        )
        return result

    def _start_pasted_batch(self, **body):
        if self.app.CAMPAIGN.get("running"):
            raise ValueError(
                "Another DM campaign is running. Stop it before starting a donor batch."
            )
        if body.get("attachment"):
            import batch_media

            batch_media.load(self.app.STORE, body["attachment"], self.app.ATT)
        rows = self.book.recipients("selected", body.get("ids"), None)
        if rows and not any(self.eligible(r["phone"]) for r in rows):
            raise ValueError("Not sent: " + self.exclusion_reason(rows[0]["phone"]))
        return self.start_batch(**body)

    def send_one(self, ident, request_id, poster=True, follow_up=False):
        """Each explicit click is a new immediate send; repeated request IDs never resend."""
        if not self.app.STORE:
            raise ValueError("Persistent sending records are unavailable.")
        if type(poster) is not bool:
            raise ValueError("Poster must be on or off.")
        follow_text = self._follow_up_for(True if follow_up is True else None)
        self.resume_personal()
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", request_id):
            raise ValueError("Invalid send request. Refresh the donor page.")
        r = self.book.resolve(ident)
        if not r.get("phone"):
            raise ValueError("This donor has no number yet. Open the ··· menu and add one.")
        key = "donor_manual_" + hashlib.sha256(request_id.encode()).hexdigest()
        with self.manual_lock:
            old = self.app.STORE.get(key)
            if old:
                if old.get("id") != r["id"]:
                    raise ValueError("This request belongs to another donor.")
                return {**old, "repeated_request": True}
            reservation = {
                "id": r["id"],
                "code": "UNCERTAIN",
                "reply": "This send is already tracked. Check WhatsApp before starting another send.",
            }
            if hasattr(self.app.STORE, "claim"):
                if not self.app.STORE.claim(key, reservation):
                    return self.app.STORE.get(key, reservation)
            else:
                self.app.STORE.put(key, reservation)
            name, gender = self.personal_name(r)
            self.jobs.manual_inflight.set()
            try:
                self.book.delivery(r["id"], "Sending")
                # Source of truth: only the visible saved Donors > Messages versions.
                # Reserving consumes a version even if delivery becomes uncertain.
                caption = self.messages.reserve_one()
                result = self.app.send_custom(
                    {
                        "target": "phone",
                        "phone": r["phone"],
                        "message": caption,
                        "poster": poster,
                        "kind": "donor_manual",
                        "name": name,
                        "gender": gender,
                    }
                )
                confirmed = isinstance(result, dict) and result.get("code") == "SUCCESS"
                if confirmed:
                    self.jobs.manual_sent_at = time.time()
                state = "Sent" if confirmed else "Uncertain"
                self.book.delivery(r["id"], state, text=caption if state == "Sent" else None)
                fu = None
                if follow_text and confirmed:
                    fu = self._single_follow_up(r, name, gender, follow_text)
                    self.book.follow_up(r["id"], fu)
                output = {
                    "id": r["id"],
                    "code": "SUCCESS" if confirmed else "UNCERTAIN",
                    "reply": "WhatsApp confirmed the DM."
                    if confirmed
                    else "Delivery not confirmed. Check WhatsApp before another manual send.",
                    **({"follow_up": fu} if fu else {}),
                }
                self.app.STORE.put(key, output)
                return output
            except ValueError as e:
                self.book.delivery(r["id"], "Not sent")
                self.app.STORE.put(key, {"id": r["id"], "code": "NOT_SENT", "reply": str(e)})
                raise
            except Exception:
                self.book.delivery(r["id"], "Uncertain")
                raise
            finally:
                self.jobs.manual_inflight.clear()

    def _single_follow_up(self, r, name, gender, template):
        """Second message only after the first was confirmed. Never retried."""
        from donor_delivery import DonorDelivery

        if self.exclusion_reason(r["phone"]):
            return "Skipped: opted out or blocked"
        try:
            res = self.app.send_custom(
                {
                    "target": "phone",
                    "phone": r["phone"],
                    "message": DonorDelivery.follow_text(template, name, gender),
                    "poster": False,
                    "kind": "owner_text",
                    "name": name,
                    "gender": gender,
                }
            )
        except ValueError:
            return "Not sent"
        except Exception:
            return "Uncertain"
        return "Sent" if isinstance(res, dict) and res.get("code") == "SUCCESS" else "Uncertain"

    def eligible(self, phone):
        return not self.exclusion_reason(phone)

    def exclusion_reason(self, phone):
        a = self.app
        if phone == normalize_phone(a.OWNER_PHONE):
            return "This is the connected account, which is excluded from donor batches."
        import hashlib

        digests = [
            hashlib.sha256(jid.encode()).hexdigest() for jid in (phone, phone + "@s.whatsapp.net")
        ]
        keys = [prefix + d for d in digests for prefix in ("dm_recipient_", "optout_")]
        values = (
            a.STORE.get_many(keys)
            if a.STORE and hasattr(a.STORE, "get_many")
            else {k: a.STORE.get(k) for k in keys}
            if a.STORE
            else {}
        )
        for digest in digests:
            if values.get("optout_" + digest):
                return "This recipient opted out of messages."
            if digest in a.BLOCKED - getattr(a, "CAMPAIGN_CONTACTED", set()):
                return "This recipient is blocked from outreach."
        # An earlier send (even an uncertain one) never stops a deliberate new send.
        return ""

    def personal_name(self, label, explicit=False):
        # A saved donor row is authoritative for the chosen form of address;
        # labels are only hints. Suggested titles do NOT verify gender.
        if isinstance(label, dict):
            preferred = label.get("dm_name")
            address = label.get("dm_salutation")
            if isinstance(preferred, str) and address in ("Brother", "Sister", "Neutral"):
                first = self.app.clean_first_name(preferred)
                return first, address if first or address == "Sister" else "Brother"
            label = label.get("name", "")
        raw_label = str(label)
        label = re.sub(r"(?i)\b(?:donors?|donir|donkr|donoe|good|best|new|perm|member|giki|gikii|volun|expert|developer|fast|ambas|main)\b", " ", raw_label)
        label = re.sub(r"[^\w\s\'-]", " ", label)
        label = re.sub(r"\d+(?:[.,]\d+)?(?:k)?", " ", label)
        label = " ".join(label.split())
        first = self.app.clean_first_name(raw_label if explicit else label)
        if explicit and re.search(r"(?i)\b(?:preview|demo|sample|random)\b", raw_label):
            first = ""
        known = (
            set(
                "abdul abdullah abdur abid abbas adil adnan aftab ahmad ahmed akhtar ali aman amaan amir ammar arman asad asif awais ayyan basit bilal danish fahad faisal farhan gul habib hafiz hajra hammad hamza haris hashim hashir hassan haseeb haider humza hussain hysam hidayat ibrahim ihtesham imran iqbal ishfaq jawad junaid kashif khurram moeed mohammad mohsin moiz mubeen mudassar muaz muhammad muhammed nadeem nabeel naseeb owais raza rao ramail saif sajid salman samad saqlain shaheer shahid shoaib siraj sohaib syed taha tanveer umair umar usman wajdan wajid waqar yasir yousuf yousaf zaid zain zaryab zeeshan".split()
            )
            | self.app.FEMALE
            | __import__("dm_composer").FEMALE_NAMES
        )
        if not explicit and first.casefold() not in known:
            first = ""
        import dm_composer

        return first, dm_composer.gender(raw_label, first) if first else "Brother"

    def mutate(self, body):
        action = body.get("action")
        if action == "add":
            p = body.get("phone", "")
            if p and str(p).strip() and normalize_phone(p) == normalize_phone(self.app.OWNER_PHONE):
                raise ValueError(
                    "This is your connected account. It is excluded from donor sending."
                )
            if body.get("text"):
                _, p = parse_contact(body["text"], body.get("name", ""))
                if p == normalize_phone(self.app.OWNER_PHONE):
                    raise ValueError("Your own account is excluded.")
            return self.book.add(body.get("name", ""), body.get("phone", ""), body.get("text", ""))
        if action == "update":
            fields = {
                k: v
                for k, v in body.items()
                if k
                in ("name", "top_donor", "important", "donated", "amount", "normal_amount", "notes", "phone")
            }
            if "phone" in fields and self.book.resolve(body.get("id", "")).get("phone"):
                del fields["phone"]  # a saved number is never replaced from here
            return self.book.update(
                body.get("id", ""), expected_updated_at=body.get("expected_updated_at"), **fields
            )
        if action == "delete":
            return self.book.delete(body.get("id", ""))
        if action == "restore":
            return self.book.restore(body.get("id", ""))
        if action == "import":
            return self.book.import_contacts(body.get("records"), self.app.OWNER_PHONE)
        if action == "group_numbers":
            # Owner pastes "1. Name - number" lines; numbers go to the matching name-only donors (no duplicates).
            from private_top_names import merge_top_group, parse_numbered_list

            group = str(body.get("group") or "GIKI").strip()[:30] or "GIKI"
            prepared = parse_numbered_list(body.get("text"))
            own = normalize_phone(self.app.OWNER_PHONE)
            if any(phone == own for _, phone in prepared):
                raise ValueError("Your own account cannot be in this list.")
            gone = None
            if body.get("replace") is True:
                from private_top_names import remove_group

                gone = remove_group(self.book, group)  # the pasted list was checked first: nothing lost
            r = merge_top_group(self.book, prepared, group)
            with self.book.lock:
                live = [x for x in self.book._load()["records"] if not x.get("deleted")]
            have = sum(1 for x in live if x.get("group") == group and x.get("phone"))
            total = sum(1 for x in live if x.get("group") == group)
            head = (
                f"Replaced the {group} list ({gone['removed']} removed): {r['added'] + r['matched']} donors saved"
                if gone is not None
                else f"{r['matched']} numbers saved to existing donors"
                + (f", {r['added']} new added" if r["added"] else "")
            )
            return {
                **r,
                "removed": gone["removed"] if gone is not None else 0,
                "reply": head + f" under {group} Donors. {have} of {total} now have their number saved.",
            }
        if action == "remove_group":
            # Owner clears a named Top group (GIKI) so the list can be pasted again with no repeats.
            from private_top_names import remove_group

            group = str(body.get("group") or "GIKI").strip()[:30] or "GIKI"
            r = remove_group(self.book, group)
            return {
                **r,
                "reply": f"{r['removed']} {group} donors removed"
                + (f"; {r['kept']} kept (they have history) and taken out of the group" if r["kept"] else "")
                + ". Paste the list again to add them back.",
            }
        if action == "clear_important":
            return self.book.clear_important()
        raise ValueError("Unknown donor action.")

    NOT_A_NAME = r"(?!(?:send|dm|show|list|remove|delete|add|text|message|post|resend|stop|hold|resume|cancel|what|how|who|when|where|why|is|are|do|does|did|please|the|all|every|set|make|mark)\b)"

    def _donor_named(self, name):
        """The one donor this short phrase names, or None so the phrase falls through to the assistant."""
        name = re.sub(r"(?i)^(?:donor|mr|brother|sister)\s+", "", name.strip(" ."))
        if not 1 <= len(name) <= 60:
            return None
        try:
            return self.book.resolve(name)
        except ValueError:
            return None

    @staticmethod
    def _said(result, donor, what):
        result = dict(result)
        result["reply"] = f"{donor['name']}: {what}."
        return result

    def _short_donor_edit(self, t):
        """'ali important', 'star ali', 'ali donated 5000', 'sara not donated', 'ali usually 500' - no verb needed."""
        from manual_commands import UNIT, _times

        low = re.sub(r"\s+", " ", t.strip().rstrip(".!"))
        amount = lambda n, u: int(float(n.replace(",", "")) * _times(u))
        flag = re.fullmatch(
            r"(?i)" + self.NOT_A_NAME + r"(.{1,60}?)\s+(not important|unimportant|important)", low
        )
        star = re.fullmatch(r"(?i)(star|unstar|unmark)\s+(.{1,60})", low) or re.fullmatch(
            r"(?i)(important)\s+" + self.NOT_A_NAME + r"(.{1,60})", low
        )
        paid = re.fullmatch(
            r"(?i)"
            + self.NOT_A_NAME
            + r"(.{1,60}?)\s+(?:donated|gave|paid|sent|donates|gives)\s*(?:rs\.?\s*)?(\d[\d,.]*)\s*"
            + UNIT
            + r"?",
            low,
        )
        status = re.fullmatch(
            r"(?i)" + self.NOT_A_NAME + r"(.{1,60}?)\s+(not donated|donated)", low
        )
        usual = re.fullmatch(
            r"(?i)"
            + self.NOT_A_NAME
            + r"(.{1,60}?)\s+(?:normally|usually|normal|usual)(?:\s+(?:donates?|gives?|pays?|amount))?\s*(?:is\s*)?(?:rs\.?\s*)?(\d[\d,.]*)\s*"
            + UNIT
            + r"?",
            low,
        )
        if flag:
            donor = self._donor_named(flag[1])
            if donor:
                return self._said(
                    self.book.update(donor["id"], important=flag[2].casefold() == "important"),
                    donor,
                    "marked Important"
                    if flag[2].casefold() == "important"
                    else "removed from Important",
                )
        if star:
            donor = self._donor_named(star[2])
            if donor:
                on = star[1].casefold() in ("star", "important")
                return self._said(
                    self.book.update(donor["id"], important=on),
                    donor,
                    "marked Important" if on else "removed from Important",
                )
        if paid:
            donor = self._donor_named(paid[1])
            if donor:
                value = amount(paid[2], paid[3])
                return self._said(
                    self.book.update(donor["id"], donated=True, amount=value),
                    donor,
                    f"marked Donated, Rs. {value:,}",
                )
        if status:
            donor = self._donor_named(status[1])
            if donor:
                on = status[2].casefold() == "donated"
                return self._said(
                    self.book.update(donor["id"], donated=on),
                    donor,
                    "marked Donated" if on else "marked Not donated",
                )
        if usual:
            donor = self._donor_named(usual[1])
            if donor:
                value = amount(usual[2], usual[3])
                return self._said(
                    self.book.update(donor["id"], normal_amount=value),
                    donor,
                    f"usual donation set to Rs. {value:,}" if value else "usual donation cleared",
                )
        return None

    def _volunteer_command(self, raw, t):
        """Chat shortcuts for volunteers: add / remove / show / set the message / DM them. None when the text is about something else."""
        v = self.volunteers
        add = re.match(
            r"(?i)^(?:please\s+)?(?:add|save|register|create)\s+(?:this\s+|new\s+)?volunteers?\s*[:=-]?\s*(.*)$",
            raw.strip(),
            re.S,
        )
        if add:
            body = add[1].strip()
            if not PHONE.search(body):
                raise ValueError(
                    "Add a volunteer with a name and a WhatsApp number, for example: add volunteer Sara 0300 1234567."
                )
            label, phone = parse_contact(body, "")
            if label == "Donor":
                raise ValueError("Write the volunteer's name together with the number.")
            out = v.mutate({"action": "add", "name": label, "phone": phone})
            out["reply"] = f"Added {label} to volunteers."
            out["volunteers_changed"] = True
            out["donors_changed"] = True
            return out
        remove = re.fullmatch(
            r"(?i)(?:please\s+)?(?:remove|delete)\s+(?:volunteer\s+(.+)|(.+?)\s+from (?:the )?volunteers?(?: list)?)",
            t,
        )
        if remove:
            out = v.mutate({"action": "delete", "id": (remove[1] or remove[2]).strip()})
            out["reply"] = "Removed from volunteers."
            out["volunteers_changed"] = True
            out["donors_changed"] = True
            return out
        if re.fullmatch(r"(?i)(?:show|list|view)(?: me)?(?: the| all| my)* volunteers?", t):
            names = [r["name"] for r in v.book.list("all")["items"]]
            return {
                "reply": f"{len(names)} volunteer"
                + ("" if len(names) == 1 else "s")
                + ". "
                + (
                    ", ".join(names[:15]) + ("…" if len(names) > 15 else "")
                    if names
                    else "Add one with: add volunteer Name 0300 1234567."
                )
            }
        msg = re.match(
            r"(?i)^(?:please\s+)?(?:set|save|change|update)\s+(?:the\s+)?volunteers?\s+message\s*[:=-]\s*(.+)$",
            raw.strip(),
            re.S,
        )
        if msg:
            v.set_message(msg[1].strip())
            return {
                "reply": 'Saved the volunteer message. Say "dm volunteers" to send it.',
                "volunteers_changed": True,
            }
        if re.fullmatch(
            r"(?i)(?:please\s+)?(?:dm|send|message|text)\s+(?:to\s+)?(?:all\s+|the\s+|my\s+)*volunteers?",
            t,
        ):
            r = v.mutate(
                {"action": "send_all", "request_id": "chat-" + uuid.uuid4().hex, "gap_seconds": 180}
            )
            r["reply"] = r.get("reply") or "Sending the volunteer message, a few minutes apart."
            return r
        return None

    def command(self, text, request_id=None):
        import chat_policy, manual_commands

        raw = str(text).strip()
        t = chat_policy.owner_text(raw).strip()
        if t.casefold() in ("hold", "pause", "wait", "stop") and self.jobs.active:
            return self.pause_personal()
        if (
            re.fullmatch(
                r"(?i)(?:please\s+)?(?:continue|resume|carry on|go on|keep going|jari rakho|phir se shuru|start again|restart)(?:\s+(?:it|the batch|sending|dms?|donor dms?|donors?|from where (?:it )?stopped))?[.!]*",
                t,
            )
            and not self.jobs.active
        ):
            last = self.jobs.status()
            if last.get("resumable") and last.get("scope") in (
                "all",
                "important",
                "top",
                "donated",
                "not_donated",
            ):
                return self.start_batch(
                    scope=last["scope"],
                    gap_seconds=last.get("gap_seconds", 240),
                    poster=last.get("poster", True),
                    chunk=last.get("chunk"),
                    rest_seconds=last.get("rest_seconds", 1200),
                    request_id=request_id,
                )
        if (
            t.casefold() in ("resume", "continue", "unhold")
            and self.paused
            and not self.app.on_hold()
        ):
            return {"reply": self.resume_personal()}
        if re.search(r"(?i)\b(dont|don't|do not|never)\b", t) or manual_commands.question_request(
            t
        ):
            return None
        if re.search(r"(?i)\band then\b|;|\badd\b.+\band\b", t):
            return None
        volunteer = self._volunteer_command(raw, t)
        if volunteer is not None:
            return volunteer
        if re.match(
            r"(?i)^(?:please\s+)?(?:add|save|register|create)\s+(?:this\s+|new\s+)?donor\b", t
        ) and PHONE.search(raw):
            return self.mutate({"action": "add", "text": raw})
        only = re.fullmatch(
            r"(?i)(?:please\s+)?(?:add|save|register|create)\s+(?:this\s+|new\s+)?donor\s*[:=-]?\s*([^\d\n]{2,60}?)\s*(?:\(no number\)|without (?:a )?number)?",
            raw.strip(),
        )
        if only:
            return self.mutate({"action": "add", "name": only[1].strip(" ."), "phone": ""})
        if re.fullmatch(
            r"(?i)(?:show|list|view)(?: me)?(?: the)?(?: all| important| donated| not donated)? donors?",
            t,
        ):
            scope = (
                "important"
                if "important" in t.casefold()
                else "not_donated"
                if "not donated" in t.casefold()
                else "donated"
                if "donated" in t.casefold()
                else "all"
            )
            data = self.book.list(scope)
            names = [r["name"] for r in data["items"]]
            return {
                "reply": f"{len(names)} {scope.replace('_', ' ')} donors. "
                + (
                    ", ".join(names[:12]) + ("…" if len(names) > 12 else "")
                    if names
                    else "Add donors or change the filter."
                ),
                "donors_changed": True,
            }
        remove = re.fullmatch(
            r"(?i)(?:please\s+)?(?:remove|delete)\s+(?:donor\s+(.+)|(.+?)\s+from (?:the )?donors?(?: list)?)",
            t,
        )
        if remove:
            return self.book.delete((remove[1] or remove[2]).strip())
        mark = re.fullmatch(
            r"(?i)(?:please\s+)?(?:mark|make|set)\s+(?:donor\s+)?(.+?)\s+(?:as\s+)?(not important|important|not donated|donated)(?:\s+(?:rs\.?\s*)?(\d[\d,]*))?",
            t,
        )
        if mark:
            what = mark[2].casefold()
            fields = (
                {"important": not what.startswith("not ")}
                if "important" in what
                else {"donated": not what.startswith("not ")}
            )
            if mark[3] and fields.get("donated"):
                fields["amount"] = int(mark[3].replace(",", ""))
            return self.book.update(mark[1], **fields)
        short = self._short_donor_edit(t)
        if short is not None:
            return short
        # A bare "stop" while donor DMs are running can only mean those DMs.
        if self.jobs.active and re.fullmatch(
            r"(?i)(?:please\s+)?(?:stop|pause|cancel|ruk(?:\s+jao)?|band(?:\s+karo)?|bas)(?:\s+(?:it|this|now|all|sending|everything|the batch|batch|the rest|rest))?[.!]*",
            t,
        ):
            return self.pause_personal()
        control = manual_commands.dm_control(t)
        if (
            control is None
            and self.paused
            and re.search(r"(?i)\b(?:schedule|start|begin|run)\b", t)
            and re.search(r"(?i)\b(?:dms?|dm s|direct messages?)\b", t)
            and not re.search(r"(?i)\b(?:donors?|important)\b|\d+\s*(?:dms?|people|donors?)", t)
        ):
            control = "resume_dms"  # "start/schedule dms by 11am" while DMs are stopped means resume them at that time
        if control == "resume_dms":
            # "resume DMs by 11 am" means at that time, never right now.
            import timed_tasks

            due = timed_tasks.due_time(t)
            if due is not None:
                if not self.paused:
                    return {
                        "reply": "DMs are not stopped, so there is nothing to resume at that time. Nothing was changed.",
                        "paused": False,
                    }
                return self.schedule_resume(
                    dt.datetime.fromtimestamp(due, timed_tasks.PKT).strftime("%Y-%m-%dT%H:%M"),
                    request_id,
                )
        if control == "stop_dms":
            # "pause dms for 1 hour" / "hold dms till 11am" pause now and resume at that time.
            import timed_tasks

            span = re.search(r"(?i)\bfor\s+(\d+(?:\.\d+)?)\s*(min\w*|mnts?|hours?|hrs?)\b", t)
            until = re.search(
                r"(?i)\b(?:till|until)\b", t
            )  # "stop dms by 11am" is a stop at that time, which is not supported
            if span or (until and timed_tasks.due_time(t) is not None):
                due = (
                    time.time()
                    + float(span[1]) * (3600 if span[2].casefold().startswith("h") else 60)
                    if span
                    else timed_tasks.due_time(t)
                )
                result = self.pause_personal()
                try:
                    stamp = dt.datetime.fromtimestamp(due, timed_tasks.PKT).strftime(
                        "%Y-%m-%dT%H:%M"
                    )
                    later = self.schedule_resume(stamp, request_id)
                except Exception as e:
                    return {
                        "reply": result["reply"]
                        + " I could not schedule the resume: "
                        + str(e)
                        + " Press Resume DMs when ready.",
                        "paused": True,
                    }
                return {
                    "reply": "DMs stopped. " + later["reply"],
                    "paused": True,
                    "resume": later.get("resume"),
                }
            if timed_tasks.due_time(t) is not None:
                return {
                    "reply": 'I did not change anything. Say "stop dms" to stop now, or "hold dms till 11am" to stop now and resume at 11am. Stopping later at a set time is not scheduled.',
                    "paused": self.paused,
                }
            return self.pause_personal()
        if control == "resume_dms":
            return {"reply": self.resume_personal()}
        if re.fullmatch(
            r"(?i)(?:please\s+)?(?:(?:send|start|run|do)\s+(?:the\s+|my\s+)?(?:dms?|dm batch(?:es)?|batches|donor dms?)|dm\s+(?:the\s+)?(?:important|them)(?:\s+donors?)?)(?:\s+(?:to\s+)?(?:important(?:\s+donors?)?|them|now|please|again|everyone))*[.!]*",
            t,
        ):
            if self.app.CAMPAIGN.get("running"):
                raise ValueError(
                    "Another DM campaign is running. Stop it before starting a donor batch."
                )
            return self.usual_batch(t, request_id)
        send = send_request(t)
        if send and chat_policy.intent(raw)["send"]:
            if self.app.CAMPAIGN.get("running"):
                raise ValueError(
                    "Another DM campaign is running. Stop it before starting a donor batch."
                )
            return self.start_batch(**send, request_id=request_id)
        return None

    def model_tool(self, prompt, request_id, action, **args):
        import chat_policy

        owner = chat_policy.owner_text(prompt)
        low = owner.casefold()
        if action == "list":
            return self.book.list(args.get("scope", "all"), args.get("query", ""))
        if chat_policy.intent(prompt)["negative"] or chat_policy.intent(prompt)["query"]:
            raise ValueError("This request does not authorize changing or messaging donors.")
        if action == "add":
            if not re.search(r"(?i)\b(add|save|register|create)\b", owner):
                raise ValueError("No donor addition was requested.")
            phones = []
            for m in PHONE.finditer(prompt):
                try:
                    phones.append(normalize_phone(m[0]))
                except ValueError:
                    pass
            if normalize_phone(args.get("phone")) not in phones:
                raise ValueError("The donor number must be provided by you in this request.")
            if args.get("name") and args["name"].casefold() not in prompt.casefold():
                raise ValueError("The saved name must come from your instruction.")
            return self.mutate(
                {"action": "add", "phone": args["phone"], "name": args.get("name", "Donor")}
            )
        if action == "send":
            expected = send_request(owner)
            if not expected:
                segment = re.search(
                    r"(?i)\b(?:send|dm|sned|sebd)\s+(?:to\s+)?(?:all\s+|important\s+|not donated\s+|donated\s+)?donors?\b[^;]*",
                    owner,
                )
                if segment:
                    expected = send_request(segment[0])
            if not expected or not chat_policy.intent(prompt)["send"]:
                raise ValueError("Name the donor audience and gap in a direct send request.")
            if (
                args.get("scope", expected["scope"]) != expected["scope"]
                or float(args.get("gap_seconds", expected["gap_seconds"]))
                != expected["gap_seconds"]
            ):
                raise ValueError("Audience or gap differs from your instruction.")
            return self.start_batch(**expected, request_id=request_id)
        if action == "stop":
            if not re.search(r"(?i)\b(stop|cancel|pause)\b", owner):
                raise ValueError("No cancellation was requested.")
            return self.pause_personal()
        ident = args.get("id") or args.get("query")
        r = self.book.resolve(ident)
        # A retrieved ID is not permission to change a different donor.
        if r["id"] not in owner and not any(
            name and name.casefold() in low for name in (r["name"], args.get("query", ""))
        ):
            raise ValueError("Name the donor to change in your instruction.")
        if action == "remove":
            if not re.search(r"(?i)\b(remove|delete)\b", owner):
                raise ValueError("No donor removal was requested.")
            return self.book.delete(r["id"])
        if action == "update":
            changes = {
                k: v
                for k, v in args.items()
                if k in ("name", "top_donor", "important", "donated", "amount", "notes")
            }
            if "top_donor" in changes:
                if not re.search(r"(?i)\btop donors?\b", owner) or changes["top_donor"] != (
                    not bool(re.search(r"(?i)\b(remove|not|unmark)\b", owner))
                ):
                    raise ValueError("Top donor membership does not match your instruction.")
            if "important" in changes:
                if "important" not in low or changes["important"] != (
                    not bool(
                        re.search(r"(?i)\b(not important|unmark|unstar|remove.*important)\b", owner)
                    )
                ):
                    raise ValueError("Importance does not match your instruction.")
            if "donated" in changes:
                if "donat" not in low or changes["donated"] != (
                    not bool(re.search(r"(?i)\b(not donated|undonated)\b", owner))
                ):
                    raise ValueError("Donation status does not match your instruction.")
            if "amount" in changes and str(changes["amount"]) not in owner.replace(",", ""):
                raise ValueError("Donation amount differs from your instruction.")
            if "name" in changes and not re.search(r"(?i)\b(name|rename|call)\b", owner):
                raise ValueError("No donor name change was requested.")
            if "notes" in changes and not re.search(r"(?i)\b(note|notes|record)\b", owner):
                raise ValueError("No note was requested.")
            return self.book.update(r["id"], **changes)
        raise ValueError("Unknown donor tool action.")
