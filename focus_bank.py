"""Owner-source wording banks. Generated text never replaces the saved original."""

import copy, hashlib, threading, time, uuid, re
import dm_variants, message_rules


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
            if (
                row
                and row.get("generator", 0) < GEN
                and (
                    row.get("state") == "Needs retry"
                    or row.get("state") == "Partial"
                    and not row.get("manual")
                )
            ):
                row.update(generator=GEN, state="Generating", error="")
                data[kind] = row
                self._put(data)
            if row and any(is_wrapped(row.get("source", ""), x) for x in row.get("items", [])):
                row["items"] = clean_items(row["source"], row["items"])
                row.pop("local_fallback", None)
                if row.get("state") == "Ready" and len(row["items"]) < 10:
                    row["state"] = "Partial"
                if row.get("state") == "Partial":
                    row["error"] = f"{len(row['items'])} rewrites ready. Press Retry for more."
                data[kind] = row
                self._put(data)
            current = self.app.get_message(kind)["text"]
            changed = bool(row and current != row["source"] and current not in row.get("items", []))
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
                "state": "Generating",
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
                    "state": "Generating",
                    "generator": GEN,
                    "history": [],
                    "updated": time.time(),
                }
            if kind == "dm":
                row["custom"] = True
            self._put(data)
            kinds = [kind] + (
                ["dm"] if kind == "group" and not data.get("dm", {}).get("custom") else []
            )
        for k in kinds:
            self.start(k)
        return self.get(kind)

    def owner_style(self, exclude="", limit=3):
        """The owner's own recent messages, newest first, as style examples for new versions."""
        with self.lock:
            data = self._load()
        out, seen = [], {wording_key(exclude)} if exclude else set()
        rows = [data.get(k) or {} for k in ("group", "dm")]
        texts = [r.get("source", "") for r in rows] + [
            t for r in rows for t in reversed(r.get("history", []))
        ]
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
        row = self.get(kind)
        with self.app.LOCK, self.lock:
            key = (kind, row["revision"])
            if row["state"] != "Generating" or key in self.running:
                return
            self.running.add(key)
        threading.Thread(target=self._generate, args=(kind, row, key), daemon=True).start()

    def _generate(self, kind, row, key):
        source = row["source"]
        prior = row.get("items", [])
        items = [
            t
            for i, t in enumerate(prior)
            if t in row.get("manual", []) or not reject_reason(source, t, prior[:i])
        ]
        last_error = ""
        try:
            api = dm_variants.assistant.client()
            if api is None and len(items) < 10:
                raise ValueError(
                    "AI is not connected. Your original is saved; retry when connected."
                )
            # Whole-message rewrites in small batches (big batches get truncated), each one checked for
            # facts, payment lines, formatting and real difference. Accepted versions are saved at once, so
            # a later failure never loses them and a retry only asks for what is missing.
            for attempt in range(6):
                if len(items) >= 10:
                    break
                if not self.current(kind, row["revision"]):
                    with self.lock:
                        self.running.discard(key)
                    return
                prompt = dm_variants._prompt(
                    source, min(5, 10 - len(items)), row.get("avoid", []) + items
                )
                prompt += message_rules.version_rules(source)
                if last_error:
                    prompt += (
                        "\nThe previous attempt was rejected because: "
                        + last_error
                        + " Correct that and keep everything else."
                    )
                try:
                    candidates = dm_variants._call(api, prompt)
                except Exception as exc:
                    last_error = str(exc)[:180]
                    if any(code in last_error for code in ("401", "403", "429")):
                        raise
                    continue
                for text in candidates:
                    text = text.replace("\r\n", "\n").strip() if isinstance(text, str) else ""
                    reason = reject_reason(source, text, items)
                    if reason:
                        last_error = reason
                        continue
                    items.append(text)
                    if len(items) >= 10:
                        break
                # Keep every accepted version even when a later model call fails.
                if not self.record(kind, row["revision"], {"items": items, "progress": len(items)}):
                    with self.lock:
                        self.running.discard(key)
                    return
            if len(items) != 10:
                raise ValueError(
                    str(len(items))
                    + "/10 versions ready. "
                    + (last_error or "The AI did not return enough different versions.")
                    + " Original kept; press Retry."
                )
            result = {"items": items, "state": "Ready", "error": "", "generator": GEN}
        except Exception as exc:
            result = {
                "items": items,
                "state": "Partial" if items else "Needs retry",
                "error": str(exc)[:350],
                "generator": GEN,
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

    def next_dm_version(self):
        """Next saved main-screen DM version, from a persisted cursor (never the clock)."""
        with self.app.LOCK, self.lock:
            if not self.app.STORE:
                return None
            row = self.get("dm")
            pool = []
            seen = set()
            for value in row.get("items", []):
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
            self.app.STORE.put(
                "focus_dm_rotation",
                {
                    "revision": row.get("revision"),
                    "next_index": (cursor + 1) % len(pool),
                    "last_key": wording_key(value),
                },
            )
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
                state="Ready" if len(texts) == 10 else "Partial",
                error="",
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

    def reserve_groups(self, caption, count):
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
            for value in clean_items(row["source"], items):
                signature = wording_key(value)
                if signature not in seen:
                    pool.append(value)
                    seen.add(signature)
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
            selected = []
            for _ in range(count):
                # A new bank revision may share wording with the previous one.
                if last and wording_key(pool[cursor]) == last:
                    cursor = (cursor + 1) % len(pool)
                value = pool[cursor]
                selected.append(value)
                last = wording_key(value)
                cursor = (cursor + 1) % len(pool)
            self.app.STORE.put(
                "focus_group_rotation",
                {"revision": revision, "next_index": cursor, "last_key": last},
            )
            return selected

    def retry(self, kind, fresh=False):
        with self.lock:
            data = self._load()
            if kind not in data:
                raise ValueError("Save your message first.")
            if fresh:
                row = data[kind]
                row["avoid"] = list(dict.fromkeys(row.get("avoid", []) + row.get("items", [])))[
                    -100:
                ]
                row["items"] = row.get("manual", [])[:]
                row["revision"] = uuid.uuid4().hex
            data[kind]["state"] = "Generating"
            data[kind]["error"] = ""
            self._put(data)
        self.start(kind)
        return self.get(kind)


def wording_key(text):
    return hashlib.sha256(
        re.sub(r"\s+", " ", re.sub(r"[*_]", "", text)).strip().casefold().encode()
    ).hexdigest()


GEN = 5


def reject_reason(source, text, existing=()):
    """'' when a reworded version is safe to save, else the plain reason it was rejected.

    Judged on meaning and structure, not character count: the same facts, amounts, payment lines,
    emojis and WhatsApp markers, within the shared length range, and rewritten throughout
    (not just a new first line)."""
    if not isinstance(text, str) or not text.strip():
        return "empty text"
    source = str(source).replace("\r\n", "\n").strip()
    text = text.replace("\r\n", "\n").strip()
    if (
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


def is_wrapped(source, value):
    """An old quick fallback: the saved message verbatim with lines added around it."""
    return isinstance(value, str) and value.strip() != str(source).strip() and str(source).strip() in value


def clean_items(source, items):
    out, seen = [], set()
    for value in items or []:
        if not isinstance(value, str) or not value.strip() or is_wrapped(source, value):
            continue
        key = wording_key(value)
        if key not in seen:
            out.append(value)
            seen.add(key)
    return out
