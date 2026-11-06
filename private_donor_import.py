"""Private one-time donor label import.

The contact payload is supplied only via a temporary Render environment variable.
No contact names/numbers are committed, exposed in logs, or sent to WhatsApp.
"""
import base64
import copy
import hashlib
import json
import time
import uuid
import zlib

from donor_book import DonorBook, normalize_phone

LABELS = {"Donor", "GIKI", "Donir"}
MAX_BYTES = 150_000


def _decode(payload):
    if not isinstance(payload, str) or not payload or len(payload) > 100_000:
        raise ValueError("Missing or oversized import payload.")
    compressed = base64.b64decode(payload, validate=True)
    unzip = zlib.decompressobj()
    raw = unzip.decompress(compressed, MAX_BYTES)
    if not unzip.eof or unzip.unconsumed_tail or unzip.unused_data:
        raise ValueError("Incomplete or oversized import payload.")
    entries = json.loads(raw)
    if not isinstance(entries, list) or not 1 <= len(entries) <= 250:
        raise ValueError("Invalid contacts list.")
    prepared = []
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Invalid contact entry.")
        name, label = item.get("name"), item.get("label")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("Invalid contact name.")
        if label not in LABELS:
            raise ValueError("Invalid contact label.")
        phone = normalize_phone(item.get("phone", ""))
        if phone in seen:
            raise ValueError("Duplicate phone within import payload.")
        seen.add(phone)
        prepared.append((name.strip(), phone, label))
    return prepared, hashlib.sha256(raw).hexdigest()[:12]


def import_from_environment(store, folder, payload):
    """Atomically add only missing phones; preserve all existing donor statuses."""
    prepared, digest = _decode(payload)  # all validation happens before any database change
    book = DonorBook(folder, store)
    added, existing = 0, 0
    with book.lock:
        current = book._load()
        updated = copy.deepcopy(current)
        known = {row.get("phone") for row in updated["records"]}
        now = time.time()
        for name, phone, label in prepared:
            if phone in known:
                existing += 1
                continue
            updated["records"].append({
                "id": uuid.uuid4().hex,
                "name": name,
                "phone": phone,
                "important": False,
                "donated": False,
                "amount": 0,
                "normal_amount": 0,
                "notes": "",
                "source": "WhatsApp label 2026-11-06: " + label,
                "created_at": now,
                "updated_at": now,
                "deleted": False,
                "last_sent_at": None,
                "delivery": "Not contacted",
            })
            known.add(phone)
            added += 1
        if added:
            book._save(updated)
    # Verify persisted database, not the in-process cache.
    saved = store.get(DonorBook.KEY)
    if not isinstance(saved, dict) or not isinstance(saved.get("records"), list):
        raise RuntimeError("Donor database verification failed.")
    actual = {row.get("phone") for row in saved["records"]}
    if any(phone not in actual for _, phone, _ in prepared):
        raise RuntimeError("Donor import was not fully persisted.")
    return {
        "batch": digest,
        "input": len(prepared),
        "added": added,
        "already_existing": existing,
        "db_total": len(saved["records"]),
    }
