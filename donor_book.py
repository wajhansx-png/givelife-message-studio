"""Private donor registry. Public views use opaque IDs, never phone numbers."""
import copy, json, math, re, threading, time, unicodedata, uuid
from decimal import Decimal
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
    KEY='donor_book';FILE='donor-book.json'
    def __init__(self, folder, store=None):
        self.path=Path(folder)/self.FILE; self.store=store; self.lock=threading.RLock();self._cache=None
    def _load(self):
        if self._cache is not None:return copy.deepcopy(self._cache)
        raw=self.store.get(self.KEY) if self.store else None
        if raw is None and self.path.exists(): raw=json.loads(self.path.read_text(encoding='utf-8'))
        if raw is None: raw={'version':1,'records':[]}
        if not isinstance(raw,dict) or not isinstance(raw.get('records'),list):
            raise ValueError('Donor records are unavailable. No changes were made.')
        if self._ensure_rankings(raw):self._save(raw)
        self._cache=copy.deepcopy(raw);return copy.deepcopy(raw)
    def _ensure_rankings(self,raw):
        changed=False
        counters=raw.setdefault('ranking_next',{})
        for flag,field in (('important','important_order'),('top_donor','top_order')):
            last=max([int(counters.get(flag,0) or 0)]+[r[field] for r in raw['records'] if type(r.get(field)) is int and r[field]>0])
            # Historical marking times were never recorded. Seed legacy members
            # once in their existing display order, then append every new member.
            for row in sorted(raw['records'],key=self.queue_key):
                if row.get(flag) and not (type(row.get(field)) is int and row[field]>0):
                    last+=1;row[field]=last;changed=True
            if counters.get(flag)!=last:counters[flag]=last;changed=True
        return changed
    def _save(self,data):
        self._ensure_rankings(data)
        if self.store: self.store.put(self.KEY,data)
        self._cache=copy.deepcopy(data)
        tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');tmp.replace(self.path)
    @staticmethod
    def worth(r):
        """Known giving only: this case's amount (if donated) + saved usual amount. Unknown stays None, never 0."""
        cur=float(r.get('amount') or 0) if r.get('donated') else 0.0;hist=float(r.get('receipt_total') or 0) or float(r.get('normal_amount') or 0)
        return {'current_amount':cur or None,'historical_amount':hist or None,'known_total':(cur+hist) or None,'activity':int(cur>0)+int(hist>0)+int(bool(r.get('donated')) and not cur and not hist)}
    @classmethod
    def rank_key(cls,r):
        w=cls.worth(r);return (-(w['known_total'] or 0),-w['activity'],r.get('top_order') or 10**9,r['id'])
    @staticmethod
    def group_key(r):
        return (str(r.get('group') or ''),r.get('group_order') or 10**9,r['id'])
    def _public(self,r):
        keys=('id','group','group_order','top_donor','top_order','important_order','top_rank','important_rank','donor_rank','important','donated','amount','normal_amount','source','created_at','updated_at','last_sent_at','delivery','deleted','follow_up_state','dm_name','dm_salutation','dm_profile_source','receipt_total','receipt_rank','receipt_source','receipt_report_date')
        # A confirmed DM is never forgotten: a later failed or pending attempt cannot erase "DM sent".
        sent=bool(r.get('dm_sent') or r.get('delivery')=='Sent' or r.get('last_sent_at'))
        return {**{k:(hide_numbers(r.get(k,'')) if k=='dm_name' else r.get(k)) for k in keys},**self.worth(r),'unverified':not self.worth(r)['known_total'],'name':hide_numbers(r['name']),'notes':hide_numbers(r.get('notes','')),'number_hidden':True,'has_number':bool(r.get('phone')),'dm_sent':sent,'sent_count':int(r.get('sent_count') or (1 if sent else 0))}
    @staticmethod
    def contacted(r):
        return bool(r.get('dm_sent') or r.get('delivery')=='Sent' or r.get('last_sent_at'))
    @staticmethod
    def queue_key(r):
        """Default order for unranked audiences; Important and Top use their saved orders."""
        sent=bool(r.get('dm_sent') or r.get('delivery')=='Sent' or r.get('last_sent_at'))
        return (not r['important'],sent,float(r.get('last_sent_at') or 0) if sent else 0.0,(r.get('important_order') or 0) if r['important'] else 0,name_key(r['name']),r['id']) # Important in the order they were starred
    def list(self,tab='all',query=''):
        if tab not in ('all','important','top','donated','not_donated','not_contacted'): raise ValueError('Choose a donor tab.')
        with self.lock:
            records=[r for r in self._load()['records'] if not r.get('deleted')]
            counts={'top':sum(bool(r.get('top_donor')) for r in records),'all':len(records),'important':sum(bool(r['important']) for r in records),'donated':sum(bool(r['donated']) for r in records)}
            counts['not_donated']=counts['all']-counts['donated']
            counts['not_contacted']=sum(not r['donated'] and not self.contacted(r) for r in records)
            counts['donated_amount']=float(sum((Decimal(str(r.get('amount',0) or 0)) for r in records if r.get('donated')),Decimal(0)))
            counts['receipt_ranked']=sum(type(r.get('receipt_rank')) is int for r in records)
            counts['receipt_total']=sum(int(r.get('receipt_total') or 0) for r in records)
            for flag,field,rank in (('important','important_order','important_rank'),('top_donor','top_order','top_rank')):
                for index,row in enumerate(sorted((r for r in records if r.get(flag) and not (flag=='top_donor' and r.get('group'))),key=(self.rank_key if flag=='top_donor' else lambda r:(r.get(field) or 0,r['id']))),1):row[rank]=index
            # A named group (e.g. GIKI) is numbered 1.. in its own saved order, under its own heading.
            for index,row in enumerate(sorted((r for r in records if r.get('top_donor') and r.get('group')),key=self.group_key),1):row['top_rank']=index
            for index,row in enumerate(sorted(records,key=self.rank_key),1):row['donor_rank']=index
            q=str(query).strip().casefold(); digits=re.sub(r'\D','',q)
            rows=[r for r in records if (tab=='all' or tab=='important' and r['important'] or tab=='top' and r.get('top_donor') or tab=='donated' and r['donated'] or tab=='not_donated' and not r['donated'] or tab=='not_contacted' and not r['donated'] and not self.contacted(r)) and (not q or q in r['name'].casefold() or q in r.get('notes','').casefold() or len(digits)>=4 and digits in r['phone'])]
            rows.sort(key=(lambda r:((1,)+self.group_key(r)) if r.get('group') else (0,)+self.rank_key(r)) if tab=='top' else self.queue_key)
            return {'items':[self._public(r) for r in rows],'counts':counts}
    def add(self,name='',phone='',text='',source='Added in studio'):
        if text: name,phone=parse_contact(text,name)
        phone=normalize_phone(phone) if str(phone or '').strip() else '';name=str(name or 'Donor').strip()
        if len(name)>120 or len(name)<1: raise ValueError('Use a name or label of 1–120 characters.')
        with self.lock:
            data=self._load(); old=next((r for r in data['records'] if (r['phone']==phone if phone else (not r['phone'] and name_key(r['name'])==name_key(name)))),None)
            if old:
                if old.get('deleted'): old['deleted']=False;old['updated_at']=time.time();self._save(data)
                return {'donor':self._public(old),'duplicate':True,'reply':'This donor is already in your list.'}
            now=time.time();r={'id':uuid.uuid4().hex,'name':name,'phone':phone,'important':False,'donated':False,'amount':0,'normal_amount':0,'notes':'','source':source,'created_at':now,'updated_at':now,'deleted':False,'last_sent_at':None,'delivery':'Not contacted'}
            data['records'].append(r);self._save(data)
            return {'donor':self._public(r),'duplicate':False,'reply':'Added '+hide_numbers(name)+'. Number hidden.'}
    def add_contacts(self,records,self_phone):
        """Validate a pasted audience completely, then save its unique contacts once."""
        if not isinstance(records,list) or not 1<=len(records)<=20:
            raise ValueError('Paste a contact list with 1–20 records.')
        own_phone=normalize_phone(self_phone);prepared=[];seen=set();duplicates=0
        for record in records:
            if not isinstance(record,dict):raise ValueError('Each pasted contact must be an object.')
            name=record.get('name');phone=normalize_phone(record.get('phone',''))
            if not isinstance(name,str) or not 1<=len(name.strip())<=120:
                raise ValueError('Use a name or label of 1–120 characters for each pasted contact.')
            if phone==own_phone:raise ValueError('Your own account is excluded from pasted donors.')
            if phone in seen:duplicates+=1;continue
            seen.add(phone);prepared.append((name.strip(),phone))
        with self.lock:
            data=self._load();known={r['phone']:r for r in data['records']};donors=[];added=0;changed=False;now=time.time()
            for name,phone in prepared:
                row=known.get(phone)
                if row is not None:
                    duplicates+=1
                    if row.get('deleted'):row.update(deleted=False,updated_at=now);changed=True
                else:
                    row={'id':uuid.uuid4().hex,'name':name,'phone':phone,'important':False,'donated':False,'amount':0,'normal_amount':0,'notes':'','source':'Pasted DM list','created_at':now,'updated_at':now,'deleted':False,'last_sent_at':None,'delivery':'Not contacted'}
                    data['records'].append(row);known[phone]=row;added+=1;changed=True
                donors.append(self._public(row))
            if changed:self._save(data)
            return {'donors':donors,'added':added,'duplicates':duplicates}
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
    def update(self,donor,expected_updated_at=None,**changes):
        allowed={'top_donor','name','important','donated','amount','normal_amount','notes','phone','dm_name','dm_salutation'}
        if not changes or set(changes)-allowed: raise ValueError('Choose a donor field to update.')
        if any(k in changes and not isinstance(changes[k],bool) for k in ('important','top_donor','donated')): raise ValueError('Use true or false for donor status.')
        if 'amount' in changes and (type(changes['amount']) not in (int,float) or not math.isfinite(changes['amount']) or not 0<=changes['amount']<=100000000): raise ValueError('Enter a valid donated amount.')
        if 'normal_amount' in changes and (type(changes['normal_amount']) not in (int,float) or not math.isfinite(changes['normal_amount']) or not 0<=changes['normal_amount']<=100000000): raise ValueError('Enter a valid normal donation amount.')
        if 'name' in changes and (not isinstance(changes['name'],str) or not 1<=len(changes['name'].strip())<=120): raise ValueError('Use a name of 1–120 characters.')
        if 'notes' in changes and (not isinstance(changes['notes'],str) or len(changes['notes'])>2000): raise ValueError('Keep notes under 2,000 characters.')
        if expected_updated_at is not None and (type(expected_updated_at) not in (int,float) or not math.isfinite(expected_updated_at) or expected_updated_at<0):
            raise ValueError('Invalid donor update version. Refresh the donor page.')
        if 'phone' in changes: changes['phone']=normalize_phone(changes['phone'])
        if 'dm_name' in changes:
            from dm_profile_import import valid_dm_name
            if not valid_dm_name(changes['dm_name']):
                raise ValueError('Choose a simple first name, or leave DM name empty.')
        if 'dm_salutation' in changes and changes['dm_salutation'] not in ('Brother','Sister','Neutral'):
            raise ValueError('Choose Bhai, Sister or name only.')
        if changes.get('donated') is False: changes['amount']=0
        with self.lock:
            r=self.resolve(donor)
            data=self._load(); row=next((x for x in data['records'] if x['id']==r['id'] and not x.get('deleted')),None)
            if row is None:raise ValueError('This donor was removed. Refresh the donor page.')
            if 'phone' in changes and row.get('phone'):raise ValueError('This donor already has a number. It cannot be changed here.')
            if changes.get('phone') and any(x['id']!=row['id'] and x.get('phone')==changes['phone'] and not x.get('deleted') for x in data['records']):raise ValueError('Another donor already has this number.')
            if expected_updated_at is not None and expected_updated_at!=row.get('updated_at'):
                raise ValueError('This donor changed since you opened it. Refresh before saving your edit.')
            if changes.get('top_donor') and not row.get('top_donor') and not row.get('important'):
                raise ValueError('Mark this donor Important before adding them to Top donors.')
            for flag,field in (('important','important_order'),('top_donor','top_order')):
                if changes.get(flag) is True and not row.get(flag):
                    counters=data.setdefault('ranking_next',{});counters[flag]=int(counters.get(flag,0))+1;changes[field]=counters[flag]
                elif changes.get(flag) is False:changes[field]=None
            if changes.get('donated') is True and not row.get('donated') and row.get('last_dm_key') and time.time()-float(row.get('last_sent_at') or 0)<=self.DM_CREDIT_WINDOW:
                learned=data.get('dm_learning',{}).get(row['last_dm_key'])
                if learned:learned['wins']=int(learned.get('wins',0))+1
            if 'name' in changes and changes['name']!=row.get('name') and row.get('dm_profile_source')=='name_based_suggestion':
                row.update(dm_name='',dm_salutation='',dm_profile_source='')
            if 'dm_name' in changes or 'dm_salutation' in changes:
                changes['dm_profile_source']='owner'
            row.update(changes,updated_at=max(time.time(),math.nextafter(float(row.get('updated_at',0)),math.inf)));self._save(data)
            return {'donor':self._public(row),'reply':'Updated '+hide_numbers(row['name'])+'.'}
    def delete(self,donor):
        r=self.resolve(donor)
        with self.lock:
            data=self._load();row=next(x for x in data['records'] if x['id']==r['id']);row.update(deleted=True,updated_at=time.time());self._save(data)
        return {'id':r['id'],'reply':'Removed '+hide_numbers(r['name'])+' from the active donor list.','undo_available':True}
    def has_phone(self,phone):
        """True when this number is a saved (not deleted) contact in the donor book."""
        try:phone=normalize_phone(phone)
        except ValueError:return False
        with self.lock:
            return any(r.get('phone')==phone and not r.get('deleted') for r in self._load()['records'])
    def normal_amount_for_phone(self,phone):
        if not phone:return 0
        try:phone=normalize_phone(phone)
        except ValueError:return 0
        with self.lock:
            data=self._load();row=next((r for r in data['records'] if r.get('phone')==phone and not r.get('deleted')),None)
        return int(row.get('normal_amount') or 0) if row else 0
    def clear_important(self):
        """Deselect every Important (and Top) donor at once; the next stars start a fresh send order."""
        with self.lock:
            data=self._load();now=time.time();n=0
            for r in data['records']:
                if r.get('important') and not r.get('deleted'):
                    r.update(important=False,important_order=None,top_donor=False,top_order=None,updated_at=max(now,math.nextafter(float(r.get('updated_at',0)),math.inf)));n+=1
            data.setdefault('ranking_next',{}).update(important=0,top_donor=0)
            self._save(data)
            return {'cleared':n,'reply':f'Deselected {n} Important donor'+('' if n==1 else 's')+'.'}
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
                known.add(phone);data['records'].append({'id':uuid.uuid4().hex,'name':name,'phone':phone,'important':False,'donated':False,'amount':0,'normal_amount':0,'notes':'','source':source,'created_at':now,'updated_at':now,'deleted':False,'last_sent_at':None,'delivery':'Not contacted'});added+=1
            self._save(data)
        return {'added':added,'reply':f'Imported {added} contacts. Existing statuses and notes were preserved.'}
    def recipients(self,scope='important',ids=None,limit=None):
        if scope not in ('all','important','top','donated','not_donated','selected'):raise ValueError('Choose an audience.')
        with self.lock:
            rows=[r for r in self._load()['records'] if not r.get('deleted') and r.get('phone') and (scope=='all' or scope=='selected' and r['id'] in (ids or []) or scope=='important' and r['important'] or scope=='top' and r.get('top_donor') or scope=='donated' and r['donated'] or scope=='not_donated' and not r['donated'])]
            rows.sort(key=self.rank_key if scope=='top' else self.queue_key)
            return copy.deepcopy(rows[:limit] if limit else rows)
    CASE_FIELDS={'follow_up_state':None,'top_donor':False,'top_order':None,'important_order':None,'important':False,'donated':False,'amount':0,'delivery':'Not contacted','last_sent_at':None,'sent_count':0,'dm_sent':False}
    def export_case_fields(self):
        with self.lock:return {r['id']:{k:copy.deepcopy(r.get(k,d)) for k,d in self.CASE_FIELDS.items()} for r in self._load()['records']}
    def import_case_fields(self,fields=None):
        """Put every person's case-specific marks back (stars, donated, DM sent). Without a saved set they start from zero."""
        with self.lock:
            data=self._load();fields=fields or {}
            for r in data['records']:
                for k,d in self.CASE_FIELDS.items():r[k]=copy.deepcopy(fields.get(r['id'],{}).get(k,d))
                r['updated_at']=time.time()
            self._save(data)
    def follow_up(self,ident,state):
        with self.lock:
            data=self._load();r=next((r for r in data['records'] if r['id']==ident),None)
            if r:r['follow_up_state']=state;r['follow_up_at']=time.time();self._save(data)
    def delivery(self,ident,state,stamp=None,text=None):
        with self.lock:
            data=self._load();r=next((r for r in data['records'] if r['id']==ident),None)
            if not r:return
            r['delivery']=state
            if state=='Sent':
                r['last_sent_at']=stamp or time.time();r['dm_sent']=True;r['sent_count']=int(r.get('sent_count') or 0)+1
                if text and str(text).strip():
                    # Remember which wording this person got, so a later donation teaches future DMs.
                    key=dm_text_key(text);r['last_dm_key']=key
                    learn=data.setdefault('dm_learning',{});row=learn.setdefault(key,{'text':str(text)[:2000],'sent':0,'wins':0})
                    row['sent']+=1;row['last']=r['last_sent_at']
                    if len(learn)>80:
                        for old in sorted(learn,key=lambda k:learn[k].get('last',0))[:len(learn)-80]:learn.pop(old,None)
            self._save(data)

    DM_CREDIT_WINDOW=7*86400
    def proven_dm_texts(self,limit=2,min_sent=5):
        """Real DM wordings that donors answered with a donation, best first."""
        with self.lock:
            rows=[r for r in self._load().get('dm_learning',{}).values() if r.get('wins') and r.get('sent',0)>=min_sent]
        rows.sort(key=lambda r:-((r['wins']+1)/(r['sent']+2)))
        return [r['text'] for r in rows[:limit]]

def dm_text_key(text):
    import hashlib
    return hashlib.sha1(' '.join(str(text).split()).encode('utf-8')).hexdigest()[:16]

def send_request(text):
    """Only direct registry batches; content edits and schedules stay in the AI workflow."""
    t=str(text).strip()
    if not re.match(r'(?i)^(?:please\s+)?(?:send|dm|message|sned|sebd)\b',t) or not re.search(r'(?i)\bdonors?\b',t):return None
    if re.search(r"(?i)\b(dont|don't|do not|never|tomorrow|schedule|at|every day|write|rewrite|make|create|draft|emotional|urgent|urgency|caption|say|saying)\b|[\"“]",t):return None
    scope='top' if re.search(r'(?i)\btop donors?\b',t) else 'important' if re.search(r'(?i)\bimportant\b',t) else 'not_donated' if re.search(r'(?i)\b(?:not donated|undonated)\b',t) else 'donated' if re.search(r'(?i)\bdonated\b',t) else 'all'
    unit=lambda n,u:float(n)*(3600 if u.lower().startswith('h') else 60)
    pause=re.search(r'(?i)(\d+(?:\.\d+)?)\s*(minutes?|mins?|m|hours?|hrs?|h)\s*(?:break|pause|rest|gap|delay|wait)?\s*between\s+(?:the\s+)?batch(?:es)?|batch(?:es)?\s*(?:gap|pause|rest|delay)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(minutes?|mins?|m|hours?|hrs?|h)',t)
    rests=[unit(pause[1] or pause[3],pause[2] or pause[4])] if pause else None
    if not pause:
        # "then rest 20 minutes" / "20 min rest" is the pause between batches, never the gap between DMs.
        pause=re.search(r'(?i)\b(?:rest|break|pause)\s*(?:for|of|=|:)?\s*(?P<n>\d+(?:\.?\d+)?)\s*(?P<u>minutes?|mins?|hours?|hrs?)\b|(?P<n2>\d+(?:\.?\d+)?)\s*(?P<u2>minutes?|mins?|hours?|hrs?)\s+(?:rest|break)\b',t)
        if pause:rests=[unit(pause['n'] or pause['n2'],pause['u'] or pause['u2'])]
    t_gap=(t[:pause.start()]+' '+t[pause.end():]) if pause else t
    jitter={'min':-10,'max':15} if re.search(r'(?i)\brandom(?:ly|ize|ise|ized|ised)?\b',t) else None
    gap=re.search(r'(?i)(\d+(?:\.\d+)?)\s*(seconds?|secs?|sec|s|minutes?|mins?|min|m|hours?|hrs?|h)\b',t_gap)
    seconds=float(gap[1])*(3600 if gap[2].lower().startswith('h') else 60 if gap[2].lower().startswith('m') else 1) if gap else 240
    limit=re.search(r'(?i)\b(first|top|send(?: to)?|dm)\s+(\d+)\s+(?:(?:dms?|messages?)\s+(?:to\s+)?)?(?:important\s+)?donors?\b',t)
    n=int(limit[2]) if limit else None
    # "send 20 dms" is a round size: the rest of the audience follows by itself. "first 20" is an exact total.
    exact=bool(limit) and limit[1].lower() in ('first','top')
    rounds=20 if n and n>20 else None if exact else n
    return {'scope':scope,'gap_seconds':seconds,'limit':n if exact or (n and n>20) else None,'chunk':rounds,'rests':rests,'jitter':jitter,'poster':not bool(re.search(r'(?i)\b(?:without|no)\s+(?:the\s+)?(?:poster|picture|image|pic)\b|\b(?:poster|picture|image|pic)\s+off\b|\btext only\b',t))}

