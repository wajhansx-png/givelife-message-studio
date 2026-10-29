"""Explicit donor batches, saved receipts and no automatic replay after restart."""
import copy, hashlib, json, math, threading, time, uuid
from pathlib import Path
from donor_book import hide_numbers

class DonorDelivery:
    def __init__(self,folder,store,book,send,caption,connected,held,eligible,name_for,variants=None):
        self.path=Path(folder)/'donor-delivery.json';self.store=store;self.book=book
        self.send=send;self.caption=caption;self.connected=connected;self.held=held;self.eligible=eligible;self.name_for=name_for
        self.lock=threading.RLock();self.boot=uuid.uuid4().hex;self.stop=threading.Event();self.active=None
        self.manual_sent_at=0;self.manual_inflight=threading.Event()
        self.variants=variants
        self._cache=None
    def _load(self):
        if self._cache is not None:return copy.deepcopy(self._cache)
        raw=self.store.get('donor_delivery') if self.store else None
        if raw is None and self.path.exists():raw=json.loads(self.path.read_text(encoding='utf-8'))
        self._cache=raw if isinstance(raw,dict) else {'jobs':[]};return copy.deepcopy(self._cache)
    def _save(self,data):
        data['jobs']=data['jobs'][-100:]
        if self.store:self.store.put('donor_delivery',data)
        self._cache=copy.deepcopy(data)
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');tmp.replace(self.path)
    def status(self):
        with self.lock:
            data=self._load();jobs=data.get('jobs',[])
            changed=False
            for j in jobs:
                if j.get('state') in ('Sending','Waiting','Starting') and j.get('boot')!=self.boot:
                    j.update(state='Interrupted',error='The service restarted. No automatic retry. Check receipts before starting again.',next_at=None)
                    changed=True
            if changed:self._save(data)
            if not jobs:return {'state':'Idle','sent':0,'skipped':0,'failed':0,'total':0}
            out=self._public(jobs[-1]);left=self._remaining(jobs[-1])
            if left is not None:out['resumable']=len(left)
            out['waiting']=self._waiting(jobs[-1])
            return out
    RESUME_WINDOW=12*3600
    def _done(self,j):
        """People who must not get this batch's DM again: sent, unconfirmed, or caught mid-send."""
        done={r['id'] for r in j.get('receipts',[]) if r.get('state') in ('Sent','Uncertain')}
        for ident in j.get('ids',[]):
            try:
                if self.book.resolve(ident).get('delivery')=='Sending':done.add(ident)
            except ValueError:pass
        return done
    def _remaining(self,j):
        """Who is still waiting in a recently stopped batch, or None when it cannot be continued."""
        if j.get('state') not in ('Stopped','Interrupted') or time.time()-j.get('updated_at',0)>self.RESUME_WINDOW:return None
        done=self._done(j);left=[i for i in j.get('ids',[]) if i not in done]
        return left or None
    def _waiting(self,j):
        """Names still to come in this batch, in order (numbers hidden). Empty once it has finished."""
        if j.get('state') not in ('Starting','Sending','Waiting','Stopped','Interrupted'):return []
        seen={r.get('id') for r in j.get('receipts',[])};names=[]
        for ident in j.get('ids',[]):
            if ident in seen:continue
            try:names.append(hide_numbers(self.book.resolve(ident)['name']))
            except ValueError:pass
        return names[:100]
    def _public(self,j):
        result={k:copy.deepcopy(v) for k,v in j.items() if k not in ('boot','caption','captions','ids','signature','personal_names')}
        if result.get('state')=='Completed' and not result.get('sent') and result.get('skipped'):
            result.update(state='Nothing sent',error='This earlier batch skipped its recipients. No DM was sent.')
        return result
    def _update(self,ident,**fields):
        with self.lock:
            data=self._load();j=next(x for x in data['jobs'] if x['id']==ident);j.update(fields,updated_at=time.time());self._save(data)
            return copy.deepcopy(j)
    def start(self,scope='important',gap_seconds=60,ids=None,limit=None,request_id=None,poster=True,run=True,personal_names=None,chunk=None,rest_seconds=1200,fresh=False):
        if type(gap_seconds) not in (float,int) or not math.isfinite(gap_seconds) or not 0<gap_seconds<=600:raise ValueError('Choose a gap from 1 to 10 minutes. Suggested: 3–5 minutes.')
        if limit is not None and (type(limit) is not int or not 1<=limit<=1000):raise ValueError('Choose a recipient count of 1–1,000.')
        if type(poster) is not bool:raise ValueError('Poster must be on or off.')
        if chunk is not None and (type(chunk) is not int or not 1<=chunk<=20):raise ValueError('Choose 1–20 DMs per round.')
        if type(rest_seconds) not in (float,int) or not math.isfinite(rest_seconds) or not 60<=rest_seconds<=7200:raise ValueError('Choose a rest between rounds from 1 to 120 minutes.')
        if self.held():raise ValueError('Sending is on hold. Resume it before starting DMs.')
        caption=self.caption()
        if not isinstance(caption,str) or not caption.strip():raise ValueError('The saved DM message is empty. Edit it first.')
        gap=max(60,float(gap_seconds));rid=str(request_id or uuid.uuid4().hex)
        if not 1<=len(rid)<=100:raise ValueError('Invalid send request.')
        rows=self.book.recipients(scope,ids,min(limit or 1000,1000) if chunk else min(limit or 20,20))
        if personal_names is not None:
            if scope!='selected' or not isinstance(personal_names,dict) or not isinstance(ids,list) or set(personal_names)!=set(ids):raise ValueError('Invalid pasted donor names. Preview the donors again.')
            for value in personal_names.values():
                if not isinstance(value,(tuple,list)) or len(value)!=2 or not isinstance(value[0],str) or value[1] not in ('Brother','Sister'):raise ValueError('Invalid pasted donor name.')
            order={ident:index for index,ident in enumerate(ids)}
            rows.sort(key=lambda row:order[row['id']])
        resumed='';self.status()
        with self.lock:
            jobs=self._load().get('jobs',[]);prev=jobs[-1] if jobs else None
        left=self._remaining(prev) if prev and not fresh and prev.get('scope')==scope and (scope!='selected' or set(prev.get('ids',[]))&set(ids or [])) else None
        if left is not None:
            by={r['id']:r for r in self.book.recipients(scope,ids,None)};mine=[by[i] for i in left if i in by]
            if not mine:raise ValueError('Everyone left in the stopped batch is gone or excluded. Choose Start over to send to the whole list again.')
            skipped=len(prev['ids'])-len(left);rows=mine[:min(limit or 1000,1000) if chunk else min(limit or 20,20)]
            if personal_names is not None:
                keep={r['id'] for r in rows};personal_names={k:v for k,v in personal_names.items() if k in keep};ids=[i for i in (ids or []) if i in keep]
            resumed=f'Continuing your stopped batch: {skipped} already handled (sent or unconfirmed) are skipped, {len(rows)} left. '
        if not rows:raise ValueError('There are no donors in this audience.')
        # Each round of up to `chunk` people gets its own different wordings; rounds may reuse them.
        size=chunk or len(rows);captions=[]
        for start in range(0,len(rows),size):
            part=len(rows[start:start+size])
            texts=self.variants(part) if self.variants else [caption]*part
            if self.variants and (not isinstance(texts,list) or len(texts)!=part or any(not isinstance(text,str) or not text.strip() for text in texts) or len(set(texts))!=part):raise ValueError('Prepare enough different messages in Messages before starting this batch.')
            captions+=texts
        signature=hashlib.sha256(json.dumps([scope,gap,ids,limit,poster,captions,personal_names,chunk,rest_seconds,[r['id'] for r in rows]],sort_keys=True).encode()).hexdigest()
        with self.lock:
            data=self._load();previous=next((j for j in data['jobs'] if j.get('request_id')==rid),None)
            if previous:
                if previous['signature']!=signature:raise ValueError('This request was already used for a different batch. Refresh before sending.')
                return {'job':self._public(previous),'reply':'This request is already tracked. It was not started again.'}
            if self.active:raise ValueError('A donor batch is already running. Stop it or wait for it to finish.')
            if not self.store:raise ValueError('Persistent sending records are unavailable. Nothing was sent.')
            if not self.connected():raise ValueError('WhatsApp is disconnected. Link it before sending.')
            ident=uuid.uuid4().hex;now=time.time()
            claim_key='donor_batch_request_'+hashlib.sha256(rid.encode()).hexdigest()
            reservation={'id':ident,'signature':signature,'state':'Starting','total':len(rows),'sent':0,'skipped':0,'failed':0}
            if hasattr(self.store,'claim') and not self.store.claim(claim_key,reservation):
                existing=self.store.get(claim_key,reservation)
                if existing.get('signature')!=signature:raise ValueError('This request was already used for another donor batch.')
                return {'job':self._public(existing),'reply':'This donor batch is already tracked. It was not started again.'}
            job={'id':ident,'request_id':rid,'signature':signature,'boot':self.boot,'scope':scope,'gap_seconds':gap,'poster':poster,'ids':[r['id'] for r in rows],'caption':caption,'captions':captions,'state':'Starting','sent':0,'skipped':0,'failed':0,'total':len(rows),'current':'','receipts':[],'created_at':now,'updated_at':now,'next_at':None}
            if chunk and len(rows)>chunk:job.update(chunk=chunk,rest_seconds=float(rest_seconds))
            if personal_names is not None:job['personal_names']=copy.deepcopy(personal_names)
            data['jobs'].append(job);self._save(data);self.active=ident;self.stop.clear()
        if run:threading.Thread(target=self._run,args=(copy.deepcopy(job),),daemon=True).start()
        rounds=f' Then the next {chunk} start automatically {rest_seconds/60:g} min after each round, same gap, until all {len(rows)} are done. Say stop any time.' if job.get('chunk') else ''
        return {'job':self._public(job),'reply':resumed+f'Started {len(rows)} {scope.replace("_"," ")} donor DMs. First sends now; next DMs {gap/60:g} min apart, with different wording for each person. Prior confirmed sends do not prevent this explicit batch.'+rounds+(' The minimum gap is 1 minute.' if gap_seconds<60 else '')}
    def cancel(self):
        self.stop.set()
        return {'reply':'Stopping the donor batch. Any message already in flight may still complete.','job':self.status()}
    def _run(self,j):
        receipts=[];sent=skipped=failed=0;last_completion=None;state='Completed';error=''
        try:
            for index,ident in enumerate(j['ids']):
                if self.stop.is_set():state='Stopped';break
                if self.held():state='Stopped';error='Sending is on hold.';break
                if j.get('chunk') and index and index%j['chunk']==0 and last_completion is not None:
                    rest=last_completion+j['rest_seconds'];self._update(j['id'],state='Waiting',next_at=rest,current=f"Resting before the next {j['chunk']}",sent=sent,skipped=skipped,receipts=receipts)
                    while time.time()<rest:
                        if self.stop.wait(min(.5,max(.1,rest-time.time()))):break
                    if self.stop.is_set():state='Stopped';break
                try:r=self.book.resolve(ident)
                except ValueError:skipped+=1;receipts.append({'id':ident,'name':'Removed donor','state':'Skipped'});continue
                if not self.eligible(r['phone']):
                    skipped+=1;receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Skipped: opted out or blocked'});continue
                if last_completion is not None or self.manual_inflight.is_set() or self.manual_sent_at>j['created_at']:
                    due=max(last_completion or 0,self.manual_sent_at)+j['gap_seconds'];self._update(j['id'],state='Waiting',next_at=due,current='Waiting between DMs',sent=sent,skipped=skipped,receipts=receipts)
                    while self.manual_inflight.is_set() or time.time()<due:
                        if self.stop.wait(min(.5,max(.1,due-time.time()))):break
                        new_due=max(last_completion or 0,self.manual_sent_at)+j['gap_seconds']
                        if new_due!=due:due=new_due;self._update(j['id'],next_at=due)
                    if self.stop.is_set():state='Stopped';break
                # Recheck deletion, hold and receipt at dispatch, not just selection time.
                try:r=self.book.resolve(ident)
                except ValueError:skipped+=1;continue
                if self.held():state='Stopped';error='Sending is on hold.';break
                if not self.eligible(r['phone']):skipped+=1;continue
                name,gender=j['personal_names'][ident] if 'personal_names' in j else self.name_for(r['name'])
                self._update(j['id'],state='Sending',next_at=None,current=hide_numbers(r['name']),sent=sent,skipped=skipped,receipts=receipts)
                self.book.delivery(ident,'Sending')
                try:result=self.send({'target':'phone','phone':r['phone'],'message':j.get('captions',[j['caption']]*len(j['ids']))[index],'poster':j['poster'],'kind':'donor_batch','first_in_batch':sent==0,'name':name,'gender':gender})
                except ValueError as e:
                    self.book.delivery(ident,'Not sent');state='Stopped';error=hide_numbers(e);break
                except Exception:
                    self.book.delivery(ident,'Uncertain');failed+=1;receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Uncertain'});state='Stopped';error='Delivery was not confirmed. Check WhatsApp. No automatic retry.';break
                last_completion=time.time()
                if not isinstance(result,dict) or result.get('code')!='SUCCESS':
                    self.book.delivery(ident,'Uncertain');failed+=1;receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Uncertain'});state='Stopped';error='Delivery was not confirmed. Check WhatsApp. No automatic retry.';break
                sent+=1;self.book.delivery(ident,'Sent',last_completion);receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Sent','time':last_completion})
                self._update(j['id'],sent=sent,skipped=skipped,receipts=receipts)
        except Exception:
            state='Stopped';error='The batch could not continue reliably. Check receipts before starting again.'
        finally:
            if not sent and skipped==len(j['ids']) and state=='Completed':state='Nothing sent';error='All selected recipients were excluded. See the recipient results; this batch did not send any DM.'
            self._update(j['id'],state=state,error=error,sent=sent,skipped=skipped,failed=failed,receipts=receipts,next_at=None,current='',caption='',captions=[],personal_names={})
            with self.lock:self.active=None

