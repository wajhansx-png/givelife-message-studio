"""Private donor registry. Public views use opaque IDs, never phone numbers."""
import copy, datetime, hashlib, json, math, re, threading, time, unicodedata, uuid
from pathlib import Path

PHONE = re.compile(r'(?<!\w)(?:\+|00)?\d[\d ()-]{6,23}\d(?!\w)')

def normalize_phone(value):
    value = str(value or '').strip()
    if not re.fullmatch(r'[+\d\s().-]+', value):
        raise ValueError('Enter a valid phone number with its country code.')
    phone = re.sub(r'\D', '', value)
    if phone.startswith('00'): phone = phone[2:]
    if re.fullmatch(r'03\d{9}', phone): phone = '92' + phone[1:]
    if not re.fullmatch(r'[1-9]\d{7,14}', phone):
        raise ValueError('Enter a valid phone number. Pakistani 03 numbers are also accepted.')
    return phone

def hide_numbers(value):
    return PHONE.sub('[number hidden]', str(value or ''))

def name_key(value):
    return re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', str(value))).strip().casefold()

def parse_contact(text, name=''):
    text = str(text or '').strip()
    matches = list(PHONE.finditer(text))
    valid=[]
    for m in matches:
        try: valid.append((m, normalize_phone(m[0])))
        except ValueError: pass
    if len(valid) != 1: raise ValueError('Add one donor at a time: a name and one phone number.')
    match, phone = valid[0]
    label = str(name or '').strip() or (text[:match.start()]+' '+text[match.end():]).strip(' ,;:-\n')
    label = re.sub(r'(?i)^(?:(?:please |this |new )?(?:add|save|register|create)\s+)?(?:this |new )?donor\s*[:=-]?\s*', '', label)
    label = re.sub(r'(?i)\b(?:phone(?: number)?|number|name)\s*[:=-]?\s*', '', label).strip(' ,;:-\n')
    return label or 'Donor', phone

class DonorBook:
    def __init__(self, folder, store=None):
        self.path=Path(folder)/'donor-book.json'; self.store=store; self.lock=threading.RLock();self._cache=None
    def _load(self):
        if self._cache is not None:return copy.deepcopy(self._cache)
        raw=self.store.get('donor_book') if self.store else None
        if raw is None and self.path.exists(): raw=json.loads(self.path.read_text(encoding='utf-8'))
        if raw is None: raw={'version':1,'records':[]}
        if not isinstance(raw,dict) or not isinstance(raw.get('records'),list):
            raise ValueError('Donor records are unavailable. No changes were made.')
        self._cache=copy.deepcopy(raw);return copy.deepcopy(raw)
    def _save(self,data):
        if self.store: self.store.put('donor_book',data)
        self._cache=copy.deepcopy(data)
        tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');tmp.replace(self.path)
    def _public(self,r):
        keys=('id','important','donated','amount','source','created_at','updated_at','last_sent_at','delivery','deleted')
        return {**{k:r.get(k) for k in keys},'name':hide_numbers(r['name']),'notes':hide_numbers(r.get('notes','')),'number_hidden':True}
    def list(self,tab='all',query=''):
        if tab not in ('all','important','donated','not_donated'): raise ValueError('Choose a donor tab.')
        with self.lock:
            records=[r for r in self._load()['records'] if not r.get('deleted')]
            counts={'all':len(records),'important':sum(bool(r['important']) for r in records),'donated':sum(bool(r['donated']) for r in records)}
            counts['not_donated']=counts['all']-counts['donated']
            counts['donated_amount']=sum(float(r.get('amount',0) or 0) for r in records if r.get('donated'))
            q=str(query).strip().casefold(); digits=re.sub(r'\D','',q)
            rows=[r for r in records if (tab=='all' or tab=='important' and r['important'] or tab=='donated' and r['donated'] or tab=='not_donated' and not r['donated']) and (not q or q in r['name'].casefold() or q in r.get('notes','').casefold() or len(digits)>=4 and digits in r['phone'])]
            rows.sort(key=lambda r:(not r['important'],name_key(r['name']),r['id']))
            return {'items':[self._public(r) for r in rows],'counts':counts}
    def add(self,name='',phone='',text='',source='Added in studio'):
        if text: name,phone=parse_contact(text,name)
        phone=normalize_phone(phone);name=str(name or 'Donor').strip()
        if len(name)>120 or len(name)<1: raise ValueError('Use a name or label of 1–120 characters.')
        with self.lock:
            data=self._load(); old=next((r for r in data['records'] if r['phone']==phone),None)
            if old:
                if old.get('deleted'): old['deleted']=False;old['updated_at']=time.time();self._save(data)
                return {'donor':self._public(old),'duplicate':True,'reply':'This donor is already in your list.'}
            now=time.time();r={'id':uuid.uuid4().hex,'name':name,'phone':phone,'important':False,'donated':False,'amount':0,'notes':'','source':source,'created_at':now,'updated_at':now,'deleted':False,'last_sent_at':None,'delivery':'Not contacted'}
            data['records'].append(r);self._save(data)
            return {'donor':self._public(r),'duplicate':False,'reply':'Added '+hide_numbers(name)+'. Number hidden.'}
    def resolve(self,value):
        query=str(value or '').strip()
        if not query: raise ValueError('Name the donor to change.')
        with self.lock:
            records=[r for r in self._load()['records'] if not r.get('deleted')]
            exact=[r for r in records if r['id']==query or name_key(r['name'])==name_key(query)]
            if not exact:
                try: p=normalize_phone(query);exact=[r for r in records if r['phone']==p]
                except ValueError: pass
            if not exact: exact=[r for r in records if name_key(query) in name_key(r['name'])]
            if len(exact)!=1: raise ValueError('More than one donor matches. Use the donor page to select one.' if exact else 'No donor matches that name. Search the Donors page or add them first.')
            return copy.deepcopy(exact[0])
    def update(self,donor,**changes):
        r=self.resolve(donor)
        allowed={'name','important','donated','amount','notes'}
        if not changes or set(changes)-allowed: raise ValueError('Choose a donor field to update.')
        if any(k in changes and not isinstance(changes[k],bool) for k in ('important','donated')): raise ValueError('Use true or false for donor status.')
        if 'amount' in changes and (type(changes['amount']) not in (int,float) or not math.isfinite(changes['amount']) or not 0<=changes['amount']<=100000000): raise ValueError('Enter a valid donated amount.')
        if 'name' in changes and (not isinstance(changes['name'],str) or not 1<=len(changes['name'].strip())<=120): raise ValueError('Use a name of 1–120 characters.')
        if 'notes' in changes and (not isinstance(changes['notes'],str) or len(changes['notes'])>2000): raise ValueError('Keep notes under 2,000 characters.')
        if changes.get('donated') is False: changes['amount']=0
        with self.lock:
            data=self._load(); row=next(x for x in data['records'] if x['id']==r['id'])
            row.update(changes,updated_at=time.time());self._save(data)
            return {'donor':self._public(row),'reply':'Updated '+hide_numbers(row['name'])+'.'}
    def delete(self,donor):
        r=self.resolve(donor)
        with self.lock:
            data=self._load();row=next(x for x in data['records'] if x['id']==r['id']);row.update(deleted=True,updated_at=time.time());self._save(data)
        return {'id':r['id'],'reply':'Removed '+hide_numbers(r['name'])+' from the active donor list.','undo_available':True}
    def restore(self,ident):
        with self.lock:
            data=self._load();r=next((r for r in data['records'] if r['id']==ident),None)
            if not r:raise ValueError('Donor not found.')
            r['deleted']=False;r['updated_at']=time.time();self._save(data)
            return {'donor':self._public(r),'reply':'Donor restored.'}
    def import_contacts(self,records,self_phone):
        if not isinstance(records,list) or len(records)>1000:raise ValueError('Import a contact list with up to 1,000 records.')
        prepared=[]
        for r in records:
            if not isinstance(r,dict):raise ValueError('Each imported contact must be an object.')
            phone=normalize_phone(r.get('phone',''))
            if r.get('is_self') or phone==normalize_phone(self_phone):continue
            prepared.append((str(r.get('name') or 'Member').strip()[:120],phone,'Donor label' if r.get('donor_label') else 'GiveLife main member'))
        added=0
        with self.lock:
            data=self._load();known={r['phone'] for r in data['records']};now=time.time()
            for name,phone,source in prepared:
                if phone in known:continue
                known.add(phone);data['records'].append({'id':uuid.uuid4().hex,'name':name,'phone':phone,'important':False,'donated':False,'amount':0,'notes':'','source':source,'created_at':now,'updated_at':now,'deleted':False,'last_sent_at':None,'delivery':'Not contacted'});added+=1
            self._save(data)
        return {'added':added,'reply':f'Imported {added} contacts. Existing statuses and notes were preserved.'}
    def recipients(self,scope='important',ids=None,limit=None):
        if scope not in ('all','important','donated','not_donated','selected'):raise ValueError('Choose an audience.')
        with self.lock:
            rows=[r for r in self._load()['records'] if not r.get('deleted') and (scope=='all' or scope=='selected' and r['id'] in (ids or []) or scope=='important' and r['important'] or scope=='donated' and r['donated'] or scope=='not_donated' and not r['donated'])]
            rows.sort(key=lambda r:(not r['important'],r['created_at'],r['id']))
            return copy.deepcopy(rows[:limit] if limit else rows)
    def delivery(self,ident,state,stamp=None):
        with self.lock:
            data=self._load();r=next((r for r in data['records'] if r['id']==ident),None)
            if not r:return
            r['delivery']=state
            if state=='Sent':r['last_sent_at']=stamp or time.time()
            self._save(data)

def send_request(text):
    """Only direct registry batches; content edits and schedules stay in the AI workflow."""
    t=str(text).strip()
    if not re.match(r'(?i)^(?:please\s+)?(?:send|dm|message|sned|sebd)\b',t) or not re.search(r'(?i)\bdonors?\b',t):return None
    if re.search(r"(?i)\b(dont|don't|do not|never|tomorrow|schedule|at|every day|write|rewrite|make|create|draft|emotional|urgent|urgency|caption|say|saying)\b|[\"“]",t):return None
    scope='important' if re.search(r'(?i)\bimportant\b',t) else 'not_donated' if re.search(r'(?i)\b(?:not donated|undonated)\b',t) else 'donated' if re.search(r'(?i)\bdonated\b',t) else 'all'
    gap=re.search(r'(?i)(\d+(?:\.\d+)?)\s*(seconds?|secs?|sec|s|minutes?|mins?|min|m|hours?|hrs?|h)\b',t)
    seconds=float(gap[1])*(3600 if gap[2].lower().startswith('h') else 60 if gap[2].lower().startswith('m') else 1) if gap else 240
    limit=re.search(r'(?i)\b(?:first|top|send(?: to)?|dm)\s+(\d+)\s+(?:important\s+)?donors?\b',t)
    return {'scope':scope,'gap_seconds':seconds,'limit':int(limit[1]) if limit else None,'poster':not bool(re.search(r'(?i)\b(?:without|no) (?:poster|picture|image)\b|\btext only\b',t))}

