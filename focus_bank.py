"""Owner-source wording banks. Generated text never replaces the saved original."""

import copy, hashlib, threading, time, uuid, re
import quality, ai_call
import dm_variants, message_rules


BATCH = 5  # versions written per click, and per background top-up while sending
MAX_VERSIONS = 40  # ceiling for one message's saved versions
TOP_UP_AT = 2  # when this few unused versions remain in a round, the next batch starts
RETRY_AFTER = (
    120,
    300,
    900,
    1800,
)  # seconds to wait before retrying a failed top-up (last one repeats)


class VersionsPaused(ValueError):
    """An automatic send must wait: every saved version was used and the next batch is not ready."""


class FocusBank:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.running = set()

    def _load(self):
        return self.app.STORE.get("focus_wording", {}) if self.app.STORE else {}

    def _put(self, data):
        if not self.app.STORE:
            raise ValueError("Persistent storage is unavailable. Nothing was changed.")
        self.app.STORE.put("focus_wording", data)

    def get(self, kind):
        with self.app.LOCK, self.lock:
            data = self._load()
            row = data.get(kind)
            if row and row.get("state") == "Generating" and not row.get("batch"):
                # Saved by the old workflow, which wrote versions on every save. Never generate on its own.
                row.update(state="Ready" if row.get("items") else "Not generated", error="")
                data[kind] = row
                self._put(data)
            if row and clean_items(
                row.get("source", ""), row.get("items", []), row.get("manual")
            ) != [x for x in row.get("items", []) if isinstance(x, str) and x.strip()]:
                row["items"] = clean_items(row["source"], row["items"], row.get("manual"))
                row.pop("local_fallback", None)
                if not row["items"] and row.get("state") in ("Ready", "Partial"):
                    row["state"] = "Not generated"
                data[kind] = row
                self._put(data)
            current = self.app.get_message(kind)["text"]
            changed = bool(row and current != row["source"] and current not in row.get("items", []))
            if row:
                self._spawn(kind, row)  # a batch the owner started that a restart interrupted
            result = copy.deepcopy(
                row or {"source": current, "items": [], "state": "Not generated", "revision": ""}
            )
            result["drafts"] = {k: self.app.get_message(k)["text"] for k in ("group", "dm")}
        # A chat edit is a new source too; never resurrect an older bank over it.
        return self.save(kind, current) if changed else result

    def save(self, kind, text, revision=None):
        if (
            kind not in ("group", "dm")
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 10000
        ):
            raise ValueError("Enter a message, up to 10,000 characters.")
        with self.app.LOCK, self.lock:
            data = self._load()
            old = data.get(kind, {})
            if revision is not None and old.get("revision", "") != revision:
                raise ValueError(
                    "This message changed on another screen. Reload before saving; your text remains in this editor."
                )
            if old.get("source") == text:
                return copy.deepcopy(old)
            # Archive owner text before replacing it, without touching other campaign data.
            history = (old.get("history", []) + ([old["source"]] if old.get("source") else []))[
                -20:
            ]
            ident = hashlib.sha256(text.encode()).hexdigest()
            row = {
                "source": text,
                "revision": ident,
                "items": [],
                "state": "Not generated",
                "generator": GEN,
                "history": history,
                "updated": time.time(),
            }
            self.app.save_draft(kind, text)
            data[kind] = row
            if kind == "group" and not data.get("dm", {}).get("custom"):
                dm = "Brother, " + text
                self.app.save_draft("dm", dm)
                data["dm"] = {
                    "source": dm,
                    "revision": hashlib.sha256(dm.encode()).hexdigest(),
                    "items": [],
                    "state": "Not generated",
                    "generator": GEN,
                    "history": [],
                    "updated": time.time(),
                }
            if kind == "dm":
                row["custom"] = True
            self._put(data)
        return self.get(kind)  # saving never writes versions; that is the Generate button

    def owner_style(self, exclude="", limit=3):
        """The owner's own recent messages, newest first, as style examples for new versions."""
        with self.lock:
            data = self._load()
        out, seen = [], {wording_key(exclude)} if exclude else set()
        rows = [data.get(k) or {} for k in ("group", "dm")]
        # Approved = what the owner wrote or hand-edited; hand edits come first, they show taste best.
        texts = (
            [t for r in rows for t in r.get("manual", []) or []]
            + [r.get("source", "") for r in rows]
            + [t for r in rows for t in reversed(r.get("history", []))]
        )
        for text in texts:
            if not isinstance(text, str) or not text.strip():
                continue
            key = wording_key(text)
            others = out + ([exclude] if exclude else [])
            if key not in seen and not any(text.endswith(o) or o.endswith(text) for o in others):
                out.append(text)
            seen.add(key)
            if len(out) >= limit:
                break
        return out

    def start(self, kind):
        self._spawn(kind, self.get(kind))

    def _spawn(self, kind, row):
        with self.app.LOCK, self.lock:
            key = (kind, row.get("revision"))
            if row.get("state") != "Generating" or not row.get("batch") or key in self.running:
                return
            self.running.add(key)
        threading.Thread(target=self._generate, args=(kind, row, key), daemon=True).start()

    def generate(self, kind, auto=False):
        """Write the next BATCH versions. Only the owner's click or the sending top-up starts this."""
        with self.app.LOCK, self.lock:
            data = self._load()
            row = data.get(kind)
            if not row or not str(row.get("source", "")).strip():
                raise ValueError("Save your message first.")
            if row.get("state") == "Generating":
                return self.get(kind)  # one batch at a time, never doubled
            items = clean_items(row["source"], row.get("items", []), row.get("manual"))
            if len(items) >= MAX_VERSIONS:
                raise ValueError(f"{len(items)} versions are saved already. That is the limit.")
            row.update(
                items=items,
                state="Generating",
                error="",
                batch={"goal": len(items) + BATCH, "auto": bool(auto), "at": time.time()},
                auto_failed=False if not auto else row.get("auto_failed", False),
                auto_fails=0 if not auto else row.get("auto_fails", 0),
            )
            self._put(data)
        self.start(kind)
        return self.get(kind)

    def _generate(self, kind, row, key):
        source = row["source"]
        prior = row.get("items", [])
        goal = int((row.get("batch") or {}).get("goal") or len(prior) + BATCH)
        auto = bool((row.get("batch") or {}).get("auto"))
        items = [
            t
            for i, t in enumerate(prior)
            if t in row.get("manual", []) or not reject_reason(source, t, prior[:i])
        ]
        last_error = ""
        reasons = {}  # why candidates were rejected, over the whole run (shown if it falls short)

        def why(tally):
            top = sorted(tally.items(), key=lambda kv: -kv[1])[:3]
            return "; ".join(f"{r} ({n}x)" if n > 1 else r for r, n in top)

        try:
            api = dm_variants.assistant.client()
            if api is None and len(items) < goal:
                raise ValueError(
                    "AI is not connected. Your original is saved; retry when connected."
                )
            # Whole-message rewrites in small batches (big batches get truncated), each one checked for
            # facts, payment lines, formatting and real difference. Accepted versions are saved at once, so
            # a later failure never loses them and a retry only asks for what is missing.
            waits = list(dm_variants.AI_BACKOFF)
            for attempt in range(6 + len(waits)):
                if attempt - (len(dm_variants.AI_BACKOFF) - len(waits)) >= 6:
                    break  # extra rounds only make up for rate-limit waits
                if len(items) >= goal:
                    break
                if not self.current(kind, row["revision"]):
                    with self.lock:
                        self.running.discard(key)
                    return
                prompt = dm_variants._prompt(
                    source, min(5, goal - len(items)), row.get("avoid", []) + items
                )
                prompt += message_rules.version_rules(source)
                if last_error:
                    prompt += (
                        "\nThe previous attempt was rejected because: "
                        + last_error
                        + " Correct that and keep everything else."
                    )
                last_error = ""
                tried = {}
                try:
                    candidates = dm_variants._call(api, prompt)
                except Exception as exc:
                    last_error = str(exc)[:180]
                    reasons[last_error] = reasons.get(last_error, 0) + 1
                    if dm_variants.ai_fatal(last_error):
                        raise
                    if dm_variants.ai_transient(last_error) and waits:
                        dm_variants._sleep(waits.pop(0))  # rate limit / server hiccup: wait, retry
                    continue
                passed = []
                for text in candidates:
                    text = text.replace("\r\n", "\n").strip() if isinstance(text, str) else ""
                    # The app, not the AI, keeps Quran/payment lines and each line's language.
                    text = dm_variants.repair(source, text) if text else text
                    reason = reject_reason(source, text, items + passed)
                    if reason:
                        tried[reason] = tried.get(reason, 0) + 1
                        reasons[reason] = reasons.get(reason, 0) + 1
                        continue
                    passed.append(text)
                last_error = why(tried)
                # One batched AI review of naturalness/taste for versions that passed every code rule.
                verdicts = quality.review(
                    ai_call.chat,
                    source,
                    passed,
                    self.owner_style(exclude=source),
                    dm_variants.CORRECTIONS() or [],
                )
                for text, verdict in zip(passed, verdicts):
                    if verdict:
                        last_error = verdict
                        reasons[verdict] = reasons.get(verdict, 0) + 1
                        continue
                    items.append(text)
                    if len(items) >= goal:
                        break
                # Keep every accepted version even when a later model call fails.
                if not self.record(kind, row["revision"], {"items": items, "progress": len(items)}):
                    with self.lock:
                        self.running.discard(key)
                    return
            if len(items) < goal:
                raise ValueError(
                    f"{len(items) - (goal - BATCH)} of {BATCH} new versions passed every check. "
                    + (why(reasons) or "The AI did not return enough different versions.")
                    + "."
                    + " Your original and the versions already saved are kept."
                )
            result = {
                "items": items,
                "state": "Ready",
                "error": "",
                "generator": GEN,
                "batch": None,
                "auto_failed": False,
                "auto_fails": 0,
            }
        except Exception as exc:
            with self.lock:
                fails = int((self._load().get(kind) or {}).get("auto_fails", 0) or 0)
            result = {
                "items": items,
                "state": "Partial" if items else "Needs retry",
                "error": str(exc)[:350],
                "generator": GEN,
                "batch": None,
                "auto_failed": auto,
                "auto_fails": fails + 1 if auto else 0,
                "auto_failed_at": time.time() if auto else 0,
            }
        try:
            print(
                "wording_generation",
                kind,
                "ready=" + str(len(items)),
                "state=" + result["state"],
                flush=True,
            )
            self.record(kind, row["revision"], result)
        finally:
            with self.lock:
                self.running.discard(key)

    def current(self, kind, revision):
        with self.lock:
            return self._load().get(kind, {}).get("revision") == revision

    def record(self, kind, revision, values):
        with self.lock:
            data = self._load()
            if data.get(kind, {}).get("revision") != revision:
                return False
            data[kind].update(copy.deepcopy(values))
            self._put(data)
            return True

    @staticmethod
    def _unused(keys, recent, span=None):
        """How many of these versions have not been sent in the current round."""
        used = set(recent[-(span or len(keys)) :]) if keys else set()
        return len([k for k in keys if k not in used])

    @staticmethod
    def _retry_due(row):
        """A failed automatic top-up tries again on its own after a growing wait (2, 5, 15, 30 min)."""
        fails = max(1, int(row.get("auto_fails", 0) or 0))
        wait = RETRY_AFTER[min(fails, len(RETRY_AFTER)) - 1]
        return time.time() - float(row.get("auto_failed_at", 0) or 0) >= wait

    def heal(self):
        """No clicks needed: start the next 5 whenever few unused versions remain, and retry failures."""
        if not self.app.STORE:
            return
        for kind in ("group", "dm"):
            with self.app.LOCK, self.lock:
                row = self._load().get(kind)
                if not row or row.get("state") == "Generating":
                    continue
                items = verified_items(
                    row.get("source", ""), row.get("items", []), row.get("manual")
                )
                keys = list(
                    dict.fromkeys(wording_key(v) for v in items if isinstance(v, str) and v.strip())
                )
                saved = self.app.STORE.get("focus_" + kind + "_rotation", {}) or {}
                recent = [k for k in saved.get("recent", []) if isinstance(k, str)]
                if kind == "dm" and saved.get("revision") != row.get("revision"):
                    recent = []
                self._top_up(kind, row, len(keys), self._unused(keys, recent))

    def _top_up(self, kind, row, count, unused):
        """While sending: when few unused versions remain, write the next batch in the background."""
        if (
            not count
            or count >= MAX_VERSIONS
            or unused > TOP_UP_AT
            or row.get("state") == "Generating"
            or (row.get("auto_failed") and not self._retry_due(row))  # backed off, not every minute
            or dm_variants.assistant.client() is None
        ):
            return
        try:
            self.generate(kind, auto=True)
        except Exception:
            pass  # sending must never break because a top-up could not start

    def next_dm_version(self):
        """Next saved main-screen DM version, from a persisted cursor (never the clock)."""
        with self.app.LOCK, self.lock:
            if not self.app.STORE:
                return None
            row = self.get("dm")
            pool = []
            seen = set()
            for value in verified_items(
                row.get("source", ""), row.get("items", []), row.get("manual")
            ):
                if isinstance(value, str) and value.strip() and wording_key(value) not in seen:
                    pool.append(value)
                    seen.add(wording_key(value))
            if not pool:
                return None
            saved = self.app.STORE.get("focus_dm_rotation", {}) or {}
            cursor = (
                int(saved.get("next_index", 0) or 0) % len(pool)
                if saved.get("revision") == row.get("revision")
                else 0
            )
            if len(pool) > 1 and saved.get("last_key") == wording_key(pool[cursor]):
                cursor = (cursor + 1) % len(pool)
            value = pool[cursor]
            keys = [wording_key(v) for v in pool]
            recent = (
                [k for k in saved.get("recent", []) if isinstance(k, str)]
                if saved.get("revision") == row.get("revision")
                else []
            )
            recent = (recent + [wording_key(value)])[-40:]
            self.app.STORE.put(
                "focus_dm_rotation",
                {
                    "revision": row.get("revision"),
                    "next_index": (cursor + 1) % len(pool),
                    "last_key": wording_key(value),
                    "recent": recent,
                },
            )
            self._top_up("dm", row, len(pool), self._unused(keys, recent))
            return value

    def manual(self, kind, texts):
        if (
            not isinstance(texts, list)
            or len(texts) > 10
            or any(not isinstance(t, str) or len(t) > 10000 for t in texts)
        ):
            raise ValueError("Use up to 10 messages, each under 10,000 characters.")
        texts = [t.strip() for t in texts if t.strip()]
        if not texts:
            raise ValueError("Add at least one message.")
        if len({wording_key(t) for t in texts}) != len(texts):
            raise ValueError("Each manual message must be different.")
        with self.app.LOCK, self.lock:
            data = self._load()
            row = data.get(kind)
            if not row:
                raise ValueError("Save your original message first.")
            row.update(
                manual=texts,
                items=texts,
                revision=uuid.uuid4().hex,
                state="Ready",
                error="",
                batch=None,
                generator=GEN,
            )
            self._put(data)
        return self.get(kind)

    def ensure_group_ready(self):
        """Group versions ready to send, without an LLM: the AI rewrites plus the saved message itself.

        Every version keeps the owner's exact lines; nothing is ever added above or below.
        Older quick fallbacks that wrapped the message in extra lines are dropped.
        """
        with self.app.LOCK, self.lock:
            if not self.app.STORE:
                raise ValueError("Persistent Group rotation is unavailable. Nothing sent.")
            row = self.get("group")
            if not row.get("source", "").strip():
                raise ValueError("Save a Group message before sending. Nothing sent.")
            data = self._load()
            saved = data.get("group")
            if not saved:
                saved = {
                    "source": row["source"],
                    "items": [],
                    "revision": hashlib.sha256(row["source"].encode()).hexdigest(),
                    "state": "Not generated",
                    "generator": GEN,
                }
                data["group"] = saved
                self._put(data)
            return copy.deepcopy(saved)

    def reserve_groups(self, caption, count, auto=False):
        """Reserve only saved Group-tab versions, cycling all ten across Auto/manual sends.

        The persisted cursor is shared by every group sender. Uncertain sends stay
        consumed so they are never accidentally repeated after a restart.
        """
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 10:
            raise ValueError("Choose between 1 and 10 group recipients per batch.")
        with self.app.LOCK, self.lock:
            row = self.ensure_group_ready()
            items = row.get("items", [])
            pool = []
            seen = set()
            for value in verified_items(row["source"], items, row.get("manual")):
                signature = wording_key(value)
                if signature not in seen:
                    pool.append(value)
                    seen.add(signature)
            written = [wording_key(v) for v in pool]
            if len(pool) < 10 and wording_key(row["source"]) not in seen:
                pool.append(row["source"])
            saved = self.app.STORE.get("focus_group_rotation", {}) or {}
            revision = row.get("revision")
            cursor = (
                int(saved.get("next_index", 0) or 0) % len(pool)
                if saved.get("revision") == revision
                else 0
            )
            last = saved.get("last_key")
            # Wording already sent is remembered by its text, not its position, so versions arriving
            # mid-generation or a new revision can never bring back a recently sent wording.
            recent = [k for k in saved.get("recent", []) if isinstance(k, str)] or (
                [last] if last else []
            )
            if auto and written:
                unused = self._unused(written, recent, len(pool))
                if not unused and (row.get("state") == "Generating" or row.get("auto_failed")):
                    if row.get("state") != "Generating":
                        self._top_up(
                            "group", row, len(written), unused
                        )  # retries by itself when due
                        row = self.ensure_group_ready()
                    raise VersionsPaused(
                        "Every saved version was used and the next 5 are not ready. This send waits."
                        if row.get("state") == "Generating"
                        else "Every saved version was used and the next 5 could not be made. "
                        "Auto posting is paused for Group and retries on its own."
                    )
            window = len(pool) - 1
            selected = []
            for _ in range(count):
                blocked = set(recent[-window:]) if window > 0 else set()
                for step in range(len(pool)):
                    if wording_key(pool[(cursor + step) % len(pool)]) not in blocked:
                        cursor = (cursor + step) % len(pool)
                        break
                value = pool[cursor]
                selected.append(value)
                last = wording_key(value)
                recent = (recent + [last])[-20:]
                cursor = (cursor + 1) % len(pool)
            self.app.STORE.put(
                "focus_group_rotation",
                {"revision": revision, "next_index": cursor, "last_key": last, "recent": recent},
            )
            self._top_up("group", row, len(written), self._unused(written, recent, len(pool)))
            return selected

    def retry(self, kind, fresh=False):
        """Try again = the next batch of 5. Regenerate = drop the saved versions and write a fresh 5."""
        with self.lock:
            data = self._load()
            if kind not in data:
                raise ValueError("Save your message first.")
            row = data[kind]
            if fresh:
                row["avoid"] = list(dict.fromkeys(row.get("avoid", []) + row.get("items", [])))[
                    -100:
                ]
                row.update(
                    items=row.get("manual", [])[:],
                    revision=uuid.uuid4().hex,
                    state="Not generated",
                    batch=None,
                )
            row["auto_failed"] = False
            self._put(data)
        return self.generate(kind)


def _unbalanced(line):
    body = re.sub(r"^\s*[*•-]\s+", "", line)  # a leading "* " is a WhatsApp bullet, not bold
    if "http" in body:
        return False
    return any(body.count(m) % 2 for m in "*_~")


def format_problem(source, text, bullets=True):
    """'' unless WhatsApp formatting broke: an unpaired * _ ~ marker, or a bullet line lost or added."""
    if any(_unbalanced(x) for x in text.split("\n")) and not any(
        _unbalanced(x) for x in source.split("\n")
    ):
        return "a bold/italic marker is unpaired (broken formatting)"
    if not bullets:  # a free draft may change its layout; versions must keep it
        return ""
    count = lambda t: sum(bool(re.match(r"^\s*[*•-]\s+\S", x)) for x in t.split("\n"))
    if count(text) != count(source):
        return "a bullet line was lost or added"
    return ""


def wording_key(text):
    return hashlib.sha256(
        re.sub(r"\s+", " ", re.sub(r"[*_]", "", text)).strip().casefold().encode()
    ).hexdigest()


GEN = 5


def reject_reason(source, text, existing=(), novelty=True):
    """'' when a reworded version is safe to save, else the plain reason it was rejected.

    Judged on meaning and structure, not character count: the same facts, amounts, payment lines,
    emojis and WhatsApp markers, within the shared length range, and rewritten throughout
    (not just a new first line)."""
    if not isinstance(text, str) or not text.strip():
        return "empty text"
    source = str(source).replace("\r\n", "\n").strip()
    text = text.replace("\r\n", "\n").strip()
    hard = quality.hard_reason(source, text)
    if hard:
        return hard
    if novelty and (
        text == source
        or text in existing
        or wording_key(text) in {wording_key(t) for t in [source, *existing]}
    ):
        return "repeated wording"
    if dm_variants.language_changed(source, text):
        return "language changed; keep English lines English and Urdu lines Urdu"
    if message_rules.is_pdf_message(source):
        bad = message_rules.problems(text)
        if bad:
            return "PDF rule: " + bad[0]
    low, high = dm_variants.length_range(source)
    if not low <= len(text) <= high:
        return f"length {len(text)} is outside {low}-{high} characters"
    bad = format_problem(source, text)
    if bad:
        return bad
    if dm_variants._shape(text) != dm_variants._shape(source):
        return "line breaks, blank lines or bold/italic markers changed"
    if dm_variants._emojis(text) != dm_variants._emojis(source):
        return "an emoji changed or moved"
    if dm_variants._numbers(text) != dm_variants._numbers(source):
        return "a number, amount or phone number changed"
    for line in source.split("\n"):
        if (
            any(
                t in line.lower()
                for t in ("easypaisa", "jazzcash", "account", "03097458815", "wajdan")
            )
            and line.strip() not in text
        ):
            return "a payment line changed"
    if not novelty:
        return ""  # sending only re-checks facts, amounts, language and format; variety was checked at writing
    minimum = 2 if len(dm_variants._editable_lines(source)) >= 3 else 1
    if (
        dm_variants._meaningful_changes(source, text) < minimum
        or dm_variants._similarity(source, text) > 0.81
    ):
        return "not deeply rewritten; change the opening AND the body wording"
    if any(
        dm_variants._similarity(text, other) > 0.87 for other in existing if isinstance(other, str)
    ):
        return "too similar to another version"
    return ""


def verified_items(source, items, manual=()):
    """Saved versions that still pass every fact, amount, language and format check against the original.
    Re-run before a send, so a version that was changed or damaged after saving is never used."""
    return [
        v
        for v in clean_items(source, items, manual)
        if v in (manual or ()) or not reject_reason(source, v, novelty=False)
    ]


def is_wrapped(source, value):
    """An old quick fallback: the saved message verbatim with lines added around it."""
    return (
        isinstance(value, str)
        and value.strip() != str(source).strip()
        and str(source).strip() in value
    )


def clean_items(source, items, manual=()):
    """Saved versions safe to show or send: no wrapped copies, no duplicates, and no version the
    AI moved into another language (Urdu or Roman Urdu for an English message). Versions the
    owner wrote by hand are kept as written."""
    out, seen = [], set()
    for value in items or []:
        if not isinstance(value, str) or not value.strip() or is_wrapped(source, value):
            continue
        if value not in (manual or ()) and dm_variants.language_changed(source, value):
            continue
        key = wording_key(value)
        if key not in seen:
            out.append(value)
            seen.add(key)
    return out
