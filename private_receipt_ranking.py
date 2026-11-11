"""Private, idempotent receipt-evidence ranking; no contact names in source control.

Totals come from donor-shared screenshots across cases, NOT bank-confirmed payments.
The importer never changes current-case donated flags, current-case amounts, or DM state.
"""

import base64
import copy
import json
import time
import zlib

from donor_book import DonorBook, name_key

BASIS = "donor-shared receipt screenshots (not independently bank-verified)"
REPORT = "2026-11-06"


def parse_payload(encoded):
    if not isinstance(encoded, str) or not 1 <= len(encoded) <= 16000:
        raise ValueError("Missing or oversized private ranking payload.")
    compressed = base64.b64decode(encoded, validate=True)
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, 16000)
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise ValueError("Invalid or oversized private ranking payload.")
    records = json.loads(raw)
    if not isinstance(records, list) or len(records) != 35:
        raise ValueError("The supplied screenshot report must have exactly 35 ranked entries.")
    seen = set()
    totals = []
    for i, row in enumerate(records, 1):
        if not isinstance(row, dict):
            raise ValueError("Invalid ranking entry.")
        name, amount = row.get("name"), row.get("total")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("Invalid ranking name.")
        if type(amount) is not int or not 0 < amount <= 100_000_000:
            raise ValueError("Invalid screenshot amount.")
        norm = name_key(name)
        if not norm or norm in seen:
            raise ValueError("Duplicate or invalid ranking name.")
        if totals and amount > totals[-1]:
            raise ValueError("Ranking must be ordered from largest total to smallest.")
        seen.add(norm)
        totals.append(amount)
    if sum(totals) != 43261:
        raise ValueError("Screenshot report checksum mismatch. No changes made.")
    return records


def import_rankings(store, folder, encoded):
    ranked = parse_payload(encoded)
    book = DonorBook(folder, store)
    with book.lock:
        original = book._load()
        changed = copy.deepcopy(original)
        lookup = {}
        for row in changed["records"]:
            if row.get("deleted"):
                continue
            lookup.setdefault(name_key(row.get("name", "")), []).append(row)
        if any(len(lookup.get(name_key(entry["name"]), [])) != 1 for entry in ranked):
            raise ValueError("Some donor labels are absent or ambiguous. No changes made.")
        updated = already = owner_preserved = 0
        now = time.time()
        for rank, item in enumerate(ranked, 1):
            row = lookup[name_key(item["name"])][0]
            if row.get("receipt_rank") == rank and row.get("receipt_total") == item["total"]:
                already += 1
                continue
            # A previous manual Top selection is not erased. Only newly ranked
            # contacts are added to Top; Important, donation history, and delivery
            # flags remain untouched.
            top_was_manually_unset = row.get("receipt_rank") is not None and not row.get(
                "top_donor"
            )
            row.update(
                receipt_total=item["total"],
                receipt_rank=rank,
                receipt_source=BASIS,
                receipt_report_date=REPORT,
                updated_at=now,
            )
            if not top_was_manually_unset and not row.get("top_donor"):
                row["top_donor"] = True
                row["top_order"] = rank
            elif row.get("top_donor") and not row.get("top_order"):
                row["top_order"] = rank
            if top_was_manually_unset:
                owner_preserved += 1
            updated += 1
        if updated:
            book._save(changed)
    reread = store.get(DonorBook.KEY)
    if not isinstance(reread, dict) or not isinstance(reread.get("records"), list):
        raise RuntimeError("Ranking database readback failed.")
    by_name = {name_key(x.get("name", "")): x for x in reread["records"] if not x.get("deleted")}
    if any(
        by_name[name_key(item["name"])].get("receipt_total") != item["total"]
        or by_name[name_key(item["name"])].get("receipt_rank") != rank
        for rank, item in enumerate(ranked, 1)
    ):
        raise RuntimeError("Ranking database verification failed.")
    return {
        "ranked": len(ranked),
        "receipt_total": sum(item["total"] for item in ranked),
        "newly_saved": updated,
        "already_saved": already,
        "owner_preserved": owner_preserved,
        "verified": len(ranked),
    }
