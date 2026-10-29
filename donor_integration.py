"""Shared donor UI/chat commands and private delivery integration."""
import re, time, hashlib, uuid, threading
from donor_book import DonorBook, normalize_phone, parse_contact, hide_numbers, send_request, PHONE
from donor_delivery import DonorDelivery

class DonorIntegration:
    def __init__(self,app):
        self.app=app;self.book=DonorBook(app.DATA,app.STORE)
        from donor_messages import MessageBank
        self.messages=MessageBank(app);self.paused=bool(app.STORE.get('donor_dm_pause',False)) if app.STORE else False
        self.jobs=DonorDelivery(app.DATA,app.STORE,self.book,app.send_custom,lambda:app.get_message('dm')['text'],app.wa_ok,lambda:app.on_hold() or self.paused,self.eligible,self.personal_name,self.messages.captions)
        from donor_paste import PastedDonors
        self.pasted=PastedDonors(self.book,self.jobs,lambda:app.OWNER_PHONE,lambda label:self.personal_name(label,explicit=True),self._start_pasted_batch)
        self.manual_lock=threading.RLock()
        self.revision=0
    def pause_personal(self):
        self.revision+=1
        self.paused=True
        if self.app.STORE:self.app.STORE.put('donor_dm_pause',True)
        self.jobs.cancel();self.app.CAMPAIGN['stop']=True;self.app.ENGINE.set_dms(False,self.app.ENGINE.s.get('dm_daily',30))
        return {'reply':'Personal DMs stopped (paused). Group posting and its timers are unchanged.'}
    def resume_personal(self):
        was_paused=self.paused
        self.paused=False
        if self.app.STORE and was_paused:self.app.STORE.put('donor_dm_pause',False)
        return 'Personal DM sending is available again. Group posting is unchanged.'
    def start_batch(self,**body):
        self.resume_personal();body.setdefault('gap_seconds',240)
        if not body.get('chunk'):body.setdefault('limit',20)
        return self.jobs.start(**body)
    def _start_pasted_batch(self,**body):
        if self.app.CAMPAIGN.get('running'):raise ValueError('Another DM campaign is running. Stop it before starting a donor batch.')
        return self.start_batch(**body)
    def send_one(self,ident,request_id):
        """Each explicit click is a new immediate send; repeated request IDs never resend."""
        if not self.app.STORE:raise ValueError('Persistent sending records are unavailable.')
        self.resume_personal()
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,100}',request_id):raise ValueError('Invalid send request. Refresh the donor page.')
        r=self.book.resolve(ident);key='donor_manual_'+hashlib.sha256(request_id.encode()).hexdigest()
        with self.manual_lock:
            old=self.app.STORE.get(key)
            if old:
                if old.get('id')!=r['id']:raise ValueError('This request belongs to another donor.')
                return {**old,'repeated_request':True}
            reservation={'id':r['id'],'code':'UNCERTAIN','reply':'This send is already tracked. Check WhatsApp before starting another send.'}
            if hasattr(self.app.STORE,'claim'):
                if not self.app.STORE.claim(key,reservation):return self.app.STORE.get(key,reservation)
            else:self.app.STORE.put(key,reservation)
            name,gender=self.personal_name(r['name']);self.jobs.manual_inflight.set()
            try:
                self.book.delivery(r['id'],'Sending')
                result=self.app.send_custom({'target':'phone','phone':r['phone'],'message':self.app.get_message('dm')['text'],'poster':True,'kind':'donor_manual','name':name,'gender':gender})
                confirmed=isinstance(result,dict) and result.get('code')=='SUCCESS'
                if confirmed:self.jobs.manual_sent_at=time.time()
                state='Sent' if confirmed else 'Uncertain';self.book.delivery(r['id'],state)
                output={'id':r['id'],'code':'SUCCESS' if confirmed else 'UNCERTAIN','reply':'WhatsApp confirmed the DM.' if confirmed else 'Delivery not confirmed. Check WhatsApp before another manual send.'}
                self.app.STORE.put(key,output);return output
            except ValueError as e:
                self.book.delivery(r['id'],'Not sent');self.app.STORE.put(key,{'id':r['id'],'code':'NOT_SENT','reply':str(e)});raise
            except Exception:
                self.book.delivery(r['id'],'Uncertain');raise
            finally:self.jobs.manual_inflight.clear()
    def eligible(self,phone):
        a=self.app
        if phone==normalize_phone(a.OWNER_PHONE):return False
        import hashlib
        digests=[hashlib.sha256(jid.encode()).hexdigest() for jid in (phone,phone+'@s.whatsapp.net')]
        keys=[prefix+d for d in digests for prefix in ('dm_recipient_','optout_')]
        values=a.STORE.get_many(keys) if a.STORE and hasattr(a.STORE,'get_many') else {k:a.STORE.get(k) for k in keys} if a.STORE else {}
        for digest in digests:
            if digest in a.BLOCKED-getattr(a,'CAMPAIGN_CONTACTED',set()) or values.get('optout_'+digest):return False
        # An earlier send (even an uncertain one) never stops a deliberate new send.
        return True
    def personal_name(self,label,explicit=False):
        # Donor labels are metadata. Random/business labels fall back to Brother.
        raw_label=str(label)
        label=re.sub(r'(?i)\b(?:donors?|donir|donkr|donoe|good|best|new|perm)\b',' ',str(label))
        label=re.sub(r'[^\w\s\'-]',' ',label).strip()
        first=self.app.clean_first_name(raw_label if explicit else label)
        if explicit and re.search(r'(?i)\b(?:preview|demo|sample|random)\b',raw_label):first=''
        known=set('abdul abdullah abdur abid abbas adil adnan aftab ahmad ahmed akhtar ali aman amaan amir ammar arman asad asif awais ayyan basit bilal danish fahad faisal farhan gul habib hafiz hajra hammad hamza haris hashim hashir hassan haseeb haider humza hussain hysam hidayat ibrahim ihtesham imran iqbal ishfaq jawad junaid kashif khurram moeed mohammad mohsin moiz mubeen mudassar muaz muhammad muhammed nadeem nabeel naseeb owais raza rao ramail saif sajid salman samad saqlain shaheer shahid shoaib siraj sohaib syed taha tanveer umair umar usman wajdan wajid waqar yasir yousuf yousaf zaid zain zaryab zeeshan'.split())|self.app.FEMALE
        if not explicit and first.casefold() not in known:first=''
        return first,('Sister' if first.casefold() in self.app.FEMALE else 'Brother')
    def mutate(self,body):
        action=body.get('action')
        if action=='add':
            p=body.get('phone','')
            if p and normalize_phone(p)==normalize_phone(self.app.OWNER_PHONE):raise ValueError('This is your connected account. It is excluded from donor sending.')
            if body.get('text'):
                _,p=parse_contact(body['text'],body.get('name',''))
                if p==normalize_phone(self.app.OWNER_PHONE):raise ValueError('Your own account is excluded.')
            return self.book.add(body.get('name',''),body.get('phone',''),body.get('text',''))
        if action=='update':return self.book.update(body.get('id',''),expected_updated_at=body.get('expected_updated_at'),**{k:v for k,v in body.items() if k in ('name','important','donated','amount','notes')})
        if action=='delete':return self.book.delete(body.get('id',''))
        if action=='restore':return self.book.restore(body.get('id',''))
        if action=='import':return self.book.import_contacts(body.get('records'),self.app.OWNER_PHONE)
        raise ValueError('Unknown donor action.')
    def command(self,text,request_id=None):
        import chat_policy,manual_commands
        raw=str(text).strip();t=chat_policy.owner_text(raw).strip()
        if t.casefold() in ('hold','pause','wait','stop') and self.jobs.active:return self.pause_personal()
        if t.casefold() in ('resume','continue','unhold') and self.paused and not self.app.on_hold():return {'reply':self.resume_personal()}
        if re.search(r"(?i)\b(dont|don't|do not|never)\b",t) or manual_commands.question_request(t):return None
        if re.search(r'(?i)\band then\b|;|\badd\b.+\band\b',t):return None
        if re.match(r'(?i)^(?:please\s+)?(?:add|save|register|create)\s+(?:this\s+|new\s+)?donor\b',t) and PHONE.search(raw):
            return self.mutate({'action':'add','text':raw})
        if re.fullmatch(r'(?i)(?:show|list|view)(?: me)?(?: the)?(?: all| important| donated| not donated)? donors?',t):
            scope='important' if 'important' in t.casefold() else 'not_donated' if 'not donated' in t.casefold() else 'donated' if 'donated' in t.casefold() else 'all'
            data=self.book.list(scope);names=[r['name'] for r in data['items']]
            return {'reply':f'{len(names)} {scope.replace("_"," ")} donors. '+(', '.join(names[:12])+('…' if len(names)>12 else '') if names else 'Add donors or change the filter.'),'donors_changed':True}
        remove=re.fullmatch(r'(?i)(?:please\s+)?(?:remove|delete)\s+(?:donor\s+(.+)|(.+?)\s+from (?:the )?donors?(?: list)?)',t)
        if remove:return self.book.delete((remove[1] or remove[2]).strip())
        mark=re.fullmatch(r'(?i)(?:please\s+)?(?:mark|make|set)\s+(?:donor\s+)?(.+?)\s+(?:as\s+)?(not important|important|not donated|donated)(?:\s+(?:rs\.?\s*)?(\d[\d,]*))?',t)
        if mark:
            what=mark[2].casefold();fields={'important':not what.startswith('not ')} if 'important' in what else {'donated':not what.startswith('not ')}
            if mark[3] and fields.get('donated'):fields['amount']=int(mark[3].replace(',',''))
            return self.book.update(mark[1],**fields)
        control=manual_commands.dm_control(t)
        if control=='stop_dms':return self.pause_personal()
        if control=='resume_dms':return {'reply':self.resume_personal()}
        send=send_request(t)
        if send and chat_policy.intent(raw)['send']:
            if self.app.CAMPAIGN.get('running'):raise ValueError('Another DM campaign is running. Stop it before starting a donor batch.')
            return self.start_batch(**send,request_id=request_id)
        return None
    def model_tool(self,prompt,request_id,action,**args):
        import chat_policy
        owner=chat_policy.owner_text(prompt);low=owner.casefold()
        if action=='list':return self.book.list(args.get('scope','all'),args.get('query',''))
        if chat_policy.intent(prompt)['negative'] or chat_policy.intent(prompt)['query']:raise ValueError('This request does not authorize changing or messaging donors.')
        if action=='add':
            if not re.search(r'(?i)\b(add|save|register|create)\b',owner):raise ValueError('No donor addition was requested.')
            phones=[]
            for m in PHONE.finditer(prompt):
                try:phones.append(normalize_phone(m[0]))
                except ValueError:pass
            if normalize_phone(args.get('phone')) not in phones:raise ValueError('The donor number must be provided by you in this request.')
            if args.get('name') and args['name'].casefold() not in prompt.casefold():raise ValueError('The saved name must come from your instruction.')
            return self.mutate({'action':'add','phone':args['phone'],'name':args.get('name','Donor')})
        if action=='send':
            expected=send_request(owner)
            if not expected:
                segment=re.search(r'(?i)\b(?:send|dm|sned|sebd)\s+(?:to\s+)?(?:all\s+|important\s+|not donated\s+|donated\s+)?donors?\b[^;]*',owner)
                if segment:expected=send_request(segment[0])
            if not expected or not chat_policy.intent(prompt)['send']:raise ValueError('Name the donor audience and gap in a direct send request.')
            if args.get('scope',expected['scope'])!=expected['scope'] or float(args.get('gap_seconds',expected['gap_seconds']))!=expected['gap_seconds']:raise ValueError('Audience or gap differs from your instruction.')
            return self.start_batch(**expected,request_id=request_id)
        if action=='stop':
            if not re.search(r'(?i)\b(stop|cancel|pause)\b',owner):raise ValueError('No cancellation was requested.')
            return self.pause_personal()
        ident=args.get('id') or args.get('query');r=self.book.resolve(ident)
        # A retrieved ID is not permission to change a different donor.
        if r['id'] not in owner and not any(name and name.casefold() in low for name in (r['name'],args.get('query',''))):raise ValueError('Name the donor to change in your instruction.')
        if action=='remove':
            if not re.search(r'(?i)\b(remove|delete)\b',owner):raise ValueError('No donor removal was requested.')
            return self.book.delete(r['id'])
        if action=='update':
            changes={k:v for k,v in args.items() if k in ('name','important','donated','amount','notes')}
            if 'important' in changes:
                if 'important' not in low or changes['important'] != (not bool(re.search(r'(?i)\b(not important|unmark|unstar|remove.*important)\b',owner))):raise ValueError('Importance does not match your instruction.')
            if 'donated' in changes:
                if 'donat' not in low or changes['donated'] != (not bool(re.search(r'(?i)\b(not donated|undonated)\b',owner))):raise ValueError('Donation status does not match your instruction.')
            if 'amount' in changes and str(changes['amount']) not in owner.replace(',',''):raise ValueError('Donation amount differs from your instruction.')
            if 'name' in changes and not re.search(r'(?i)\b(name|rename|call)\b',owner):raise ValueError('No donor name change was requested.')
            if 'notes' in changes and not re.search(r'(?i)\b(note|notes|record)\b',owner):raise ValueError('No note was requested.')
            return self.book.update(r['id'],**changes)
        raise ValueError('Unknown donor tool action.')

