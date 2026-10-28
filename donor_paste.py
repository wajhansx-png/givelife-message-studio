"""Short-lived private preparation for explicit pasted donor batches."""
import copy
import math
import re
import secrets
import threading
import time
from collections import OrderedDict

from donor_book import hide_numbers, normalize_phone


_PHONE = re.compile(r'(?<!\w)(?:\+|00)?\d[\d \t().-]{6,28}\d(?!\w)')


class PastedDonors:
    def __init__(self, book, jobs, self_phone, personal_name, starter=None):
        self.book = book
        self.jobs = jobs
        self.self_phone = self_phone
        self.personal_name = personal_name
        self.starter = starter
        self.lock = threading.RLock()
        self.prepared = OrderedDict()

    def _prune(self):
        now = time.monotonic()
        for token in list(self.prepared):
            if self.prepared[token]['expires'] <= now:
                del self.prepared[token]

    def preview(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError('Paste a name and phone number per line, for up to 20 donors.')
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not 1 <= len(lines) <= 20:
            raise ValueError('Paste between 1 and 20 donor lines.')
        own = normalize_phone(self.self_phone())
        records = []
        known = set()
        duplicates = 0
        for index, line in enumerate(lines, 1):
            matches = list(_PHONE.finditer(line))
            if len(matches) != 1:
                raise ValueError(f'Line {index}: use one name and one valid phone number.')
            match = matches[0]
            try:
                phone = normalize_phone(match[0])
            except ValueError:
                raise ValueError(f'Line {index}: enter a valid phone number with its country code.') from None
            if phone == own:
                raise ValueError(f'Line {index}: your connected account is excluded from donor sending.')
            name = (line[:match.start()] + ' ' + line[match.end():]).strip(' \t,;:|/–—-') or f'Donor {index}'
            if not 1 <= len(name) <= 120 or re.search(r'[\x00-\x1f\x7f]', name):
                raise ValueError(f'Line {index}: add a name or label of 1–120 characters.')
            # Extra long digit sequences cannot become a public label, including
            # malformed second numbers that the complete phone matcher rejected.
            if re.search(r'\d(?:[\s().-]*\d){6}', name):
                raise ValueError(f'Line {index}: use one name and one valid phone number.')
            if phone in known:
                duplicates += 1
                continue
            known.add(phone)
            records.append({'name': name, 'phone': phone})
        token = secrets.token_urlsafe(32)
        with self.lock:
            self._prune()
            while len(self.prepared) >= 50:
                self.prepared.popitem(last=False)
            self.prepared[token] = {'records': records, 'expires': time.monotonic() + 600,
                                    'duplicates': duplicates, 'attempt': None}
        return {'token': token, 'names': [hide_numbers(r['name']) for r in records],
                'count': len(records), 'duplicates': duplicates,
                'warnings': [f'{duplicates} repeated line(s) removed; the first name is used.'] if duplicates else [],
                'expires_in': 600}

    def start(self, token, gap_seconds=240, request_id=None, poster=True):
        if type(gap_seconds) not in (float, int) or not math.isfinite(gap_seconds) or not 60 <= gap_seconds <= 600:
            raise ValueError('Choose a gap from 1 to 10 minutes.')
        if type(poster) is not bool:
            raise ValueError('Poster must be on or off.')
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,100}', request_id):
            raise ValueError('Invalid send request. Preview the pasted donors again.')
        if not isinstance(token, str):
            raise ValueError('Preview the pasted donors again before sending.')
        options = (float(gap_seconds), poster, request_id)
        with self.lock:
            self._prune()
            prepared = self.prepared.get(token)
            if prepared is None:
                raise ValueError('This preview expired or is unavailable. Preview the pasted donors again.')
            if prepared['attempt'] is not None:
                if prepared['attempt'] != options:
                    raise ValueError('This preview was already used. Preview again for a different batch.')
                if 'result' in prepared:
                    return copy.deepcopy(prepared['result'])
                raise ValueError('This send was already attempted. Check delivery receipts; it will not retry automatically.')
            # Reserve before any write or dispatch. A failed/uncertain start must
            # never be repeated when a browser retries its original request.
            prepared['attempt'] = options
            records = copy.deepcopy(prepared['records'])
            saved = self.book.add_contacts(records, self.self_phone())
            rows = saved['donors']
            names = {row['id']: self.personal_name(record['name'])
                     for row, record in zip(rows, records)}
            body = {'scope': 'selected', 'ids': [row['id'] for row in rows],
                    'limit': len(rows), 'gap_seconds': gap_seconds,
                    'request_id': request_id, 'poster': poster, 'personal_names': names}
            result = (self.starter or self.jobs.start)(**body)
            result['saved'] = {'added': saved['added'],
                               'duplicates': saved['duplicates'] + prepared['duplicates']}
            result['reply'] += f" Saved {saved['added']} new donor(s) to your Donors list; existing donor details were preserved."
            prepared['result'] = copy.deepcopy(result)
            # Raw pasted phones are no longer needed after a successful start.
            prepared['records'] = []
            return result

