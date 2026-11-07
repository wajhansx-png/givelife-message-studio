"""One-time private name-only Top donors import; no contacts are sent or published."""
import base64
import json
import time
import uuid

from donor_book import DonorBook, name_key, normalize_phone


IMPORT_ID = 'giki_top_names_2026_11_07'


def import_top_names(store, folder, payload, import_id=IMPORT_ID):
    names = json.loads(payload)
    if not isinstance(names, list) or not 1 <= len(names) <= 100:
        raise ValueError('Expected a list of 1-100 names.')
    if any(not isinstance(n, str) or not 1 <= len(n.strip()) <= 120 for n in names):
        raise ValueError('Invalid donor name.')
    names = [n.strip() for n in names]
    if len({name_key(n) for n in names}) != len(names):
        raise ValueError('Duplicate name in private import.')

    book = DonorBook(folder, store)
    with book.lock:
        data = book._load()
        if import_id in data.get('applied_name_imports', []):
            return {'input': len(names), 'added': 0, 'matched': 0, 'ambiguous': 0, 'already_applied': 1}
        added = matched = ambiguous = 0
        now = time.time()
        for name in names:
            choices = [r for r in data['records'] if not r.get('deleted') and name_key(r['name']) == name_key(name)]
            if len(choices) > 1:
                ambiguous += 1
                continue
            if choices:
                row = choices[0]
                matched += 1
            else:
                row = {
                    'id': uuid.uuid4().hex, 'name': name, 'phone': '',
                    'important': False, 'top_donor': False,
                    'donated': False, 'amount': 0, 'normal_amount': 0,
                    'notes': '', 'source': 'GIKI name-only import',
                    'created_at': now, 'updated_at': now,
                    'deleted': False, 'last_sent_at': None,
                    'delivery': 'Not contacted',
                }
                data['records'].append(row)
                added += 1
            row['important'] = True
            row['top_donor'] = True
        data.setdefault('applied_name_imports', []).append(import_id)
        book._save(data)
        return {'input': len(names), 'added': added, 'matched': matched, 'ambiguous': ambiguous, 'already_applied': 0}


GROUP_IMPORT_ID = "giki_top_group_2026_11_07"


def import_top_group(store, folder, payload_b64, group="GIKI", import_id=GROUP_IMPORT_ID):
    """One-time private import of a named Top-donor group with its numbers, in the given order.

    payload_b64 is base64 of a JSON list of {"name", "phone"} (held only in a Render env var).
    Donors already known by number, or by name with no number yet, are updated, never duplicated.
    """
    entries = json.loads(base64.b64decode(payload_b64, validate=True))
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise ValueError("Expected a list of 1-100 donors.")
    prepared, seen = [], set()
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("Invalid donor entry.")
        name = item["name"].strip()
        if not 1 <= len(name) <= 120:
            raise ValueError("Invalid donor name.")
        phone = normalize_phone(item.get("phone", ""))
        if phone in seen:
            raise ValueError("Duplicate number in private import.")
        seen.add(phone)
        prepared.append((name, phone))

    book = DonorBook(folder, store)
    with book.lock:
        data = book._load()
        if import_id in data.get("applied_name_imports", []):
            return {
                "input": len(prepared),
                "added": 0,
                "matched": 0,
                "ambiguous": 0,
                "already_applied": 1,
            }
        live = [r for r in data["records"] if not r.get("deleted")]
        by_phone = {r["phone"]: r for r in live if r.get("phone")}
        added = matched = ambiguous = 0
        now = time.time()
        for order, (name, phone) in enumerate(prepared, 1):
            row = by_phone.get(phone)
            if row is None:
                choices = sorted(
                    (
                        r
                        for r in live
                        if not r.get("phone") and name_key(r["name"]) == name_key(name)
                    ),
                    key=lambda r: r.get("created_at") or 0,
                )
                if len(choices) > 1:
                    ambiguous += 1
                row = choices[0] if choices else None
                if row is not None:
                    row["phone"] = phone
                    by_phone[phone] = row
            if row is None:
                row = {
                    "id": uuid.uuid4().hex,
                    "name": name,
                    "phone": phone,
                    "important": True,
                    "top_donor": True,
                    "donated": False,
                    "amount": 0,
                    "normal_amount": 0,
                    "notes": "",
                    "source": group + " Top group import",
                    "created_at": now,
                    "updated_at": now,
                    "deleted": False,
                    "last_sent_at": None,
                    "delivery": "Not contacted",
                }
                data["records"].append(row)
                live.append(row)
                by_phone[phone] = row
                added += 1
            else:
                matched += 1
            row["top_donor"] = True
            row["group"] = group
            row["group_order"] = order
            row["updated_at"] = now
        data.setdefault("applied_name_imports", []).append(import_id)
        book._save(data)
        return {
            "input": len(prepared),
            "added": added,
            "matched": matched,
            "ambiguous": ambiguous,
            "already_applied": 0,
        }
