"""Private, owner-correctable DM address profiles.

A name can suggest a form of address, but it does not establish someone's gender.
Store only the suggested greeting fields, never a gender identity.
"""
import base64
import copy
import json
import re
import time
import zlib

from donor_book import DonorBook, normalize_phone

SALUTATIONS = {"Brother", "Sister", "Neutral"}
MAX_RAW = 150_000
NAME = re.compile(r"[A-Za-z][A-Za-z'-]{1,24}")


def valid_dm_name(value):
    """One conservative Latin-script first name, or empty for anonymous contacts."""
    return isinstance(value, str) and (
        not value or (len(value) <= 30 and NAME.fullmatch(value) is not None)
    )


def decode_profiles(encoded):
    if not isinstance(encoded, str) or not 1 <= len(encoded) <= 140_000:
        raise ValueError("Invalid DM profile payload.")
    compressed = base64.b64decode(encoded, validate=True)
    obj = zlib.decompressobj()
    raw = obj.decompress(compressed, MAX_RAW + 1)
    if len(raw) > MAX_RAW or not obj.eof or obj.unconsumed_tail or obj.unused_data:
        raise ValueError("Invalid or oversized DM profile payload.")
    profiles = json.loads(raw)
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 250:
        raise ValueError("Expected a list of up to 250 DM profiles.")
    out = []
    seen = set()
    for row in profiles:
        if not isinstance(row, dict):
            raise ValueError("Invalid profile entry.")
        phone = normalize_phone(row.get("phone"))
        name = row.get("dm_name")
        address = row.get("dm_salutation")
        if phone in seen or not valid_dm_name(name) or address not in SALUTATIONS:
            raise ValueError("Invalid, repeated, or ambiguous DM profile.")
        seen.add(phone)
        out.append((phone, name, address))
    return out


def import_profiles(store, folder, payload):
    """Apply only to existing donors. Never overwrite a manual owner correction."""
    profiles = decode_profiles(payload)
    registry = DonorBook(folder, store)
    with registry.lock:
        original = registry._load()
        new = copy.deepcopy(original)
        by_phone = {r.get("phone"): r for r in new["records"] if not r.get("deleted")}
        missing = [phone for phone, _, _ in profiles if phone not in by_phone]
        if missing:
            raise ValueError("A donor was not found; no profile changes were saved.")
        updated = unchanged = owner_preserved = 0
        stamp = time.time()
        for phone, name, address in profiles:
            row = by_phone[phone]
            if row.get("dm_profile_source") == "owner":
                owner_preserved += 1
                continue
            if row.get("dm_name") == name and row.get("dm_salutation") == address:
                unchanged += 1
                continue
            row.update(
                dm_name=name,
                dm_salutation=address,
                dm_profile_source="name_based_suggestion",
                updated_at=stamp,
            )
            updated += 1
        if updated:
            registry._save(new)
    saved = store.get(DonorBook.KEY)
    if not isinstance(saved, dict) or not isinstance(saved.get("records"), list):
        raise RuntimeError("DM profiles were not verified in persistent storage.")
    stored = {r.get("phone"): r for r in saved["records"]}
    verified = sum(
        1 for phone, name, address in profiles
        if (stored[phone].get("dm_profile_source") == "owner"
            or (stored[phone].get("dm_name") == name
                and stored[phone].get("dm_salutation") == address))
    )
    if verified != len(profiles):
        raise RuntimeError("DM profile verification failed.")
    return {
        "input": len(profiles),
        "updated": updated,
        "unchanged": unchanged,
        "owner_preserved": owner_preserved,
        "verified": verified,
    }
