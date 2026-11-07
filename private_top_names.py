"""One-time private name-only Top donors import; no contacts are sent or published."""
import json
import time
import uuid

from donor_book import DonorBook, name_key


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
