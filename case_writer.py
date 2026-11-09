"""Editable, per-case writing notes and a reviewable message; never sends."""

import json
import threading
import time

import message_styles
from draft_workflow import remaining_amount
from message_library import library_for
from persist import atomic_write


class CaseWriter:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()

    def identity(self):
        return self.app.donors().cases.view()["current"]

    def _load(self, ident):
        key = "manual_case_message_" + ident
        value = self.app.STORE.get(key) if self.app.STORE else None
        path = self.app.DATA / (key + ".json")
        if value is None and path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
        return value or {
            "case_id": ident,
            "revision": 0,
            "details": "",
            "style": "ur_en",
            "text": "",
        }

    def _write(self, value):
        key = "manual_case_message_" + value["case_id"]
        value["updated_at"] = time.time()
        atomic_write(self.app.DATA / (key + ".json"), json.dumps(value, ensure_ascii=False))
        if self.app.STORE:
            self.app.STORE.put(key, value)

    def view(self):
        with self.lock:
            value = self._load(self.identity())
            return {
                **value,
                "left": self.app.read_left(),
                "saved_messages": library_for(self.app).count(),
            }

    def save(self, body):
        with self.lock:
            ident = self.identity()
            if body.get("case_id") != ident:
                raise ValueError(
                    "The active case changed. Reopen Write Case; your earlier notes are kept."
                )
            value = self._load(ident)
            if body.get("revision") != value["revision"]:
                raise ValueError(
                    "This case draft changed on another screen. Your typed text is still in this editor."
                )
            details, text, style = body.get("details"), body.get("text"), body.get("style")
            if not isinstance(details, str) or len(details) > 12000:
                raise ValueError("Enter case details in at most 12,000 characters.")
            if not isinstance(text, str) or len(text) > 10000:
                raise ValueError("Keep the generated message within 10,000 characters.")
            if style not in message_styles.STYLES:
                raise ValueError("Choose one of the four message styles.")
            changed_text = text != value.get("text")
            changed = changed_text or details != value["details"] or style != value["style"]
            if changed:
                if changed_text and text.strip():
                    library_for(self.app).record(
                        "dm",
                        text,
                        source="case_editor",
                        quality="owner",
                        context={"case_id": ident},
                    )
                value.update(
                    details=details, text=text, style=style, revision=value["revision"] + 1
                )
                self._write(value)
            return {**value, "left": self.app.read_left()}

    def generate(self, body):
        value = self.save(body)
        if not value["details"].strip():
            raise ValueError("Write the case details first.")
        ident, revision, left = value["case_id"], value["revision"], value["left"]
        written_left = remaining_amount(value["details"])
        if written_left is not None and written_left != left:
            raise ValueError(
                f"Your notes say Rs. {written_left:,} left; the current case balance is Rs. {left:,}. Correct the notes or update the case balance before generating."
            )
        # The existing writer assembles the amount, donor math, approved verse and payment block.
        result = self.app.message_style(
            {
                "kind": "dm",
                "style": value["style"],
                "case_details": value["details"],
                "current": value.get("text", ""),
            }
        )
        library_for(self.app).record(
            "dm",
            result["text"],
            source="manual_case",
            quality="validated",
            context={"case_id": ident, "details": value["details"], "left": left},
        )
        with self.lock:
            current = self._load(ident)
            if (
                self.identity() != ident
                or current["revision"] != revision
                or self.app.read_left() != left
            ):
                raise ValueError(
                    "The case details or balance changed while writing. Your newer notes are safe; generate again."
                )
            current.update(
                text=result["text"],
                generated_details=value["details"],
                generated_left=left,
                generated_style=value["style"],
                revision=revision + 1,
            )
            self._write(current)
            return {**current, "left": left, "saved_messages": library_for(self.app).count()}

    def use(self, body):
        with self.lock:
            value = self.save(body)
            if not value.get("generated_details"):
                raise ValueError("Generate a message first.")
            if (
                value["details"] != value["generated_details"]
                or value.get("generated_left") != self.app.read_left()
                or value.get("generated_style") != value["style"]
            ):
                raise ValueError(
                    "The case details or balance changed. Generate again before using this message."
                )
            self.app.donors().messages.set_base(value["text"])
            self.app.save_draft("dm", value["text"])
            return {**value, "used": True}
