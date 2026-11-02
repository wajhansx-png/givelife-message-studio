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

    @staticmethod
    def _clean_name(raw):
        name = re.sub(r'(?im)^\s*(?:\d{1,2}[.)]|[-\u2022*>])\s+', '', raw)
        name = re.sub(r'(?i)\b(?:name|naam|number|no|phone|mobile|mob|cell|contact|whatsapp|wa|dm|to)\s*[:=#-]\s*', ' ', name)
        return name.strip(' \t,;:|/\u2013\u2014-').strip()

    @staticmethod
    def _numbers(line):
        """Phone matches in a line. Pakistani numbers separated only by spaces are split apart."""
        found = []
        for m in _PHONE.finditer(line):
            try:
                normalize_phone(m[0])
                found.append((m.start(), m.end(), m[0], False))
                continue
            except ValueError:
                pass
            compact = re.sub(r'\D', '', m[0])
            parts = re.findall(r'(?:0092|92|0)?3\d{9}', compact)
            if len(parts) > 1 and ''.join(parts) == compact:
                found.append((m.start(), m.end(), parts[0], False))
                found.extend((m.end(), m.end(), part, True) for part in parts[1:])
            else:
                found.append((m.start(), m.end(), m[0], False))
        return found

    def preview(self, text, gap_seconds=240):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError('Paste a name and phone number per line, for up to 20 donors.')
        if type(gap_seconds) not in (int, float) or not math.isfinite(gap_seconds) or not 60 <= gap_seconds <= 600:
            raise ValueError('Choose a gap from 1 to 10 minutes.')
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not 1 <= len(lines) <= 40:
            raise ValueError('Paste up to 20 donors.')
        own = normalize_phone(self.self_phone())
        records = []
        known = set()
        duplicates = 0
        counter = 0
        for index, line in enumerate(lines, 1):
            matches = self._numbers(line)
            if not matches:
                raise ValueError(f'Line {index}: use one name and one valid phone number.')
            # Text before each number is its name. A single number may also have its name after it.
            names, cursor = [], 0
            for start, end, _, inner in matches:
                names.append('' if inner else self._clean_name(line[cursor:start]))
                cursor = max(cursor, end)
            tail = self._clean_name(line[cursor:])
            if len(matches) == 1:
                names[0] = names[0] or tail
            elif any(names) and not all(names):
                raise ValueError(f'Line {index}: put a name before every number, or paste numbers only.')
            for (_, _, number, _), name in zip(matches, names):
                counter += 1
                try:
                    phone = normalize_phone(number)
                except ValueError:
                    raise ValueError(f'Line {index}: enter a valid phone number with its country code.') from None
                if phone == own:
                    raise ValueError(f'Line {index}: your connected account is excluded from donor sending.')
                name = name or f'Donor {counter}'
                if not 1 <= len(name) <= 120 or re.search(r'[\x00-\x1f\x7f]', name):
                    raise ValueError(f'Line {index}: add a name or label of 1\u2013120 characters.')
                # Extra long digit sequences cannot become a public label, including
                # malformed second numbers that the complete phone matcher rejected.
                if re.search(r'\d(?:[\s().-]*\d){6}', name):
                    raise ValueError(f'Line {index}: use one name and one valid phone number.')
                if phone in known:
                    duplicates += 1
                    continue
                known.add(phone)
                records.append({'name': name, 'phone': phone})
        if len(records) > 20:
            raise ValueError('Paste up to 20 different donors per batch.')
        gap = float(gap_seconds)
        plan = [{'position': i + 1, 'name': hide_numbers(r['name']), 'after_seconds': round(i * gap)} for i, r in enumerate(records)]
        token = secrets.token_urlsafe(32)
        with self.lock:
            self._prune()
            while len(self.prepared) >= 50:
                self.prepared.popitem(last=False)
            self.prepared[token] = {'records': records, 'expires': time.monotonic() + 600,
                                    'duplicates': duplicates, 'attempt': None}
        return {'token': token, 'names': [hide_numbers(r['name']) for r in records],
                'count': len(records), 'duplicates': duplicates,
                'gap_seconds': gap, 'plan': plan, 'total_seconds': plan[-1]['after_seconds'] if plan else 0,
                'warnings': [f'{duplicates} repeated line(s) removed; the first name is used.'] if duplicates else [],
                'expires_in': 600}

    def start(self, token, gap_seconds=240, request_id=None, poster=True, message=None, attachment=None):
        if attachment is not None and (not isinstance(attachment,str) or not re.fullmatch('[a-f0-9]{32}',attachment)):raise ValueError('Choose the attachment again.')
        if message is not None and (not isinstance(message,str) or not message.strip() or len(message)>8000):raise ValueError("Write a message of 1 to 8,000 characters.")
        if type(gap_seconds) not in (float, int) or not math.isfinite(gap_seconds) or not 60 <= gap_seconds <= 600:
            raise ValueError('Choose a gap from 1 to 10 minutes.')
        if type(poster) is not bool:
            raise ValueError('Poster must be on or off.')
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,100}', request_id):
            raise ValueError('Invalid send request. Preview the pasted donors again.')
        if not isinstance(token, str):
            raise ValueError('Preview the pasted donors again before sending.')
        options = (float(gap_seconds), poster, request_id, message, attachment)
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
            if message is not None:body['custom_template']=message
            if attachment:body.update(attachment=attachment,poster=False)
            result = (self.starter or self.jobs.start)(**body)
            result['saved'] = {'added': saved['added'],
                               'duplicates': saved['duplicates'] + prepared['duplicates']}
            result['reply'] += f" Saved {saved['added']} new donor(s) to your Donors list; existing donor details were preserved."
            prepared['result'] = copy.deepcopy(result)
            # Raw pasted phones are no longer needed after a successful start.
            prepared['records'] = []
            return result

