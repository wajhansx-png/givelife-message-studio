"""Explicit donor batches, saved receipts and no automatic replay after restart."""
import copy, hashlib, json, math, random, re, threading, time, uuid
from pathlib import Path
from donor_book import hide_numbers

class DonorDelivery:
    KEY='donor_delivery';FILE='donor-delivery.json';KIND='donor_batch';CLAIM='donor_batch_request_'
    def __init__(self,folder,store,book,send,caption,connected,held,eligible,name_for,variants=None,case_closed=None):
        self.path=Path(folder)/self.FILE;self.store=store;self.book=book
        self.send=send;self.caption=caption;self.connected=connected;self.held=held;self.eligible=eligible;self.name_for=name_for
        self.lock=threading.RLock();self.boot=uuid.uuid4().hex;self.stop=threading.Event();self.active=None
        self.manual_sent_at=0;self.manual_inflight=threading.Event()
        self.variants=variants;self.case_closed=case_closed or (lambda:False)
        self._cache=None
    def _load(self):
        if self._cache is not None:return copy.deepcopy(self._cache)
        raw=self.store.get(self.KEY) if self.store else None
        if raw is None and self.path.exists():raw=json.loads(self.path.read_text(encoding='utf-8'))
        self._cache=raw if isinstance(raw,dict) else {'jobs':[]};return copy.deepcopy(self._cache)
    def _save(self,data):
        data['jobs']=data['jobs'][-100:]
        if self.store:self.store.put(self.KEY,data)
        self._cache=copy.deepcopy(data)
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');tmp.replace(self.path)
    def status(self):
        with self.lock:
            data=self._load();jobs=data.get('jobs',[])
            changed=False
            for j in jobs:
                if j.get('state') in ('Sending','Waiting','Starting') and j.get('boot')!=self.boot:
                    j.update(state='Interrupted',error='The service restarted. Starting again by itself; nobody already sent is repeated.' if j.get('auto') else 'The service restarted. No automatic retry. Check receipts before starting again.',next_at=None)
                    changed=True
            if changed:self._save(data)
            if not jobs:return {'state':'Idle','sent':0,'skipped':0,'failed':0,'total':0}
            out=self._public(jobs[-1]);left=self._remaining(jobs[-1])
            # Older releases combined self-account and opt-out exclusions. Explain
            # legacy receipts from current verified records without replaying them.
            for receipt in out.get('receipts',[]):
                if receipt.get('state')=='Skipped: opted out or blocked':
                    try:
                        phone=self.book.resolve(receipt['id'])['phone']
                        reason=getattr(self,'exclusion_reason',lambda p:'')(phone)
                    except (ValueError,KeyError):reason=''
                    receipt['state']='Skipped: '+(reason or 'Excluded by an earlier batch. Start a new batch to check eligibility again.')

            if left is not None:out['resumable']=len(left)
            out['waiting']=self._waiting(jobs[-1])
            j=jobs[-1];seen={r.get('id') for r in j.get('receipts',[])}
            out['pending']=len([i for i in j.get('ids',[]) if i not in seen]) if j.get('state') in ('Starting','Sending','Waiting','Stopped','Interrupted') else 0
            if j.get('chunk'):
                out['batches']=j.get('batches') or -(-j['total']//j['chunk']);out['batch']=j.get('batch',1)
                out['next_batch_size']=min(j['chunk'],out['pending']) if j.get('next_batch_at') else None
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
        if j.get('state') not in ('Stopped','Interrupted') or time.time()-j.get('updated_at',0)>(self.AUTO_WINDOW if j.get('auto') else self.RESUME_WINDOW):return None
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
        result={k:copy.deepcopy(v) for k,v in j.items() if k not in ('boot','caption','captions','ids','signature','personal_names','custom_template')}
        if result.get('state')=='Completed' and not result.get('sent') and result.get('skipped'):
            result.update(state='Nothing sent',error='This earlier batch skipped its recipients. No DM was sent.')
        return result
    def _update(self,ident,**fields):
        with self.lock:
            data=self._load();j=next(x for x in data['jobs'] if x['id']==ident);j.update(fields,updated_at=time.time());self._save(data)
            return copy.deepcopy(j)
    def start(self,scope='important',gap_seconds=60,ids=None,limit=None,request_id=None,poster=True,run=True,personal_names=None,chunk=None,rest_seconds=1200,fresh=False,rests=None,jitter=None,skip_contacted=None,hold_until=None,custom_template=None,attachment=None):
        if attachment is not None and (not isinstance(attachment,str) or not re.fullmatch('[a-f0-9]{32}',attachment)):raise ValueError('Choose the attachment again.')
        if custom_template is not None and (scope!='selected' or not isinstance(custom_template,str) or not custom_template.strip() or len(custom_template)>8000):raise ValueError("Write a custom message for selected recipients (up to 8,000 characters).")
        if self.case_closed():raise ValueError('The case is complete (Rs. 0 left), so no donor DMs were started. Set a new amount left first if you need to ask again.')
        if type(gap_seconds) not in (float,int) or not math.isfinite(gap_seconds) or not 0<gap_seconds<=600:raise ValueError('Choose a gap from 1 to 10 minutes. Suggested: 3–5 minutes.')
        if limit is not None and (type(limit) is not int or not 1<=limit<=1000):raise ValueError('Choose a recipient count of 1–1,000.')
        if type(poster) is not bool:raise ValueError('Poster must be on or off.')
        if chunk is not None and (type(chunk) is not int or not 1<=chunk<=20):raise ValueError('Choose 1–20 DMs per round.')
        if type(rest_seconds) not in (float,int) or not math.isfinite(rest_seconds) or not 60<=rest_seconds<=7200:raise ValueError('Choose a rest between rounds from 1 to 120 minutes.')
        if rests is not None:
            if not isinstance(rests,list) or not 1<=len(rests)<=50 or any(type(x) not in (float,int) or not math.isfinite(x) or not 60<=x<=86400 for x in rests):raise ValueError('Choose each pause between batches from 1 minute to 24 hours.')
            rests=[float(x) for x in rests]
        elif chunk:rests=[float(rest_seconds)]
        if jitter is not None:
            if not isinstance(jitter,dict) or any(type(jitter.get(k)) not in (float,int) or not -300<=jitter[k]<=600 for k in ('min','max')) or jitter['min']>jitter['max']:raise ValueError('Random gap: choose a minimum and maximum change in seconds, minimum first.')
            jitter={'min':float(jitter['min']),'max':float(jitter['max'])}
        if self.held():raise ValueError('Sending is on hold. Resume it before starting DMs.')
        caption=custom_template if custom_template is not None else self.caption()
        if not isinstance(caption,str) or not caption.strip():raise ValueError('The saved DM message is empty. Edit it first.')
        gap=max(60,float(gap_seconds));rid=str(request_id or uuid.uuid4().hex)
        if not 1<=len(rid)<=100:raise ValueError('Invalid send request.')
        cap=min(limit or 1000,1000) if chunk else min(limit or 20,20)
        skip=bool(chunk) if skip_contacted is None else bool(skip_contacted)
        rows=self.book.recipients(scope,ids,None);already=0
        if skip and scope!='selected':
            fresh_rows=[r for r in rows if not self.book.contacted(r)];already=len(rows)-len(fresh_rows);rows=fresh_rows
        rows=rows[:cap]
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
        same_batch=prev and not fresh and prev.get('scope')==scope and (scope!='selected' or set(prev.get('ids',[]))&set(ids or []))
        recent=prev and time.time()-prev.get('updated_at',0)<=(self.AUTO_WINDOW if prev.get('auto') else self.RESUME_WINDOW)
        if left is None and same_batch and recent and prev.get('state') in ('Stopped','Interrupted'):
            # The stopped batch already reached everyone (sent or unconfirmed). Starting a new one would DM them again.
            done=self._done(prev);unsure=sum(1 for r in prev.get('receipts',[]) if r.get('state')=='Uncertain')
            raise ValueError(f'Everyone in your last batch was already handled ({len(done)-unsure} sent'+(f', {unsure} not confirmed: check WhatsApp' if unsure else '')+'). Nothing was sent again. Choose "Start over" to send to everyone again.')
        if left is not None:
            by={r['id']:r for r in self.book.recipients(scope,ids,None)};mine=[by[i] for i in left if i in by]
            if not mine:raise ValueError('Everyone left in the stopped batch is gone or excluded. Choose Start over to send to the whole list again.')
            skipped=len(prev['ids'])-len(left);rows=mine[:min(limit or 1000,1000) if chunk else min(limit or 20,20)]
            if personal_names is not None:
                keep={r['id'] for r in rows};personal_names={k:v for k,v in personal_names.items() if k in keep};ids=[i for i in (ids or []) if i in keep]
            resumed=f'Continuing your stopped batch: {skipped} already handled (sent or unconfirmed) are skipped, {len(rows)} left. '
        if not rows:raise ValueError('Everyone in this audience was already contacted. Tick "include people already contacted" to send again.' if already else 'There are no donors in this audience.')
        # Each round of up to `chunk` people gets its own different wordings; rounds may reuse them.
        size=chunk or len(rows);captions=[]
        for start in range(0,len(rows),size):
            part=len(rows[start:start+size])
            texts=self.variants(part) if self.variants and custom_template is None else [caption]*part
            if self.variants and custom_template is None and (not isinstance(texts,list) or len(texts)!=part or any(not isinstance(text,str) or not text.strip() for text in texts) or len(set(texts))!=part):raise ValueError('Prepare enough different messages in Messages before starting this batch.')
            captions+=texts
        signature=hashlib.sha256(json.dumps([scope,gap,ids,limit,poster,captions,custom_template,attachment,personal_names,chunk,rests,jitter,hold_until,[r['id'] for r in rows]],sort_keys=True).encode()).hexdigest()
        with self.lock:
            data=self._load();previous=next((j for j in data['jobs'] if j.get('request_id')==rid),None)
            if previous:
                if previous['signature']!=signature:raise ValueError('This request was already used for a different batch. Refresh before sending.')
                return {'job':self._public(previous),'reply':'This request is already tracked. It was not started again.'}
            if self.active:raise ValueError('A donor batch is already running. Stop it or wait for it to finish.')
            if not self.store:raise ValueError('Persistent sending records are unavailable. Nothing was sent.')
            if not self.connected():raise ValueError('WhatsApp is disconnected. Link it before sending.')
            ident=uuid.uuid4().hex;now=time.time()
            claim_key=self.CLAIM+hashlib.sha256(rid.encode()).hexdigest()
            reservation={'id':ident,'signature':signature,'state':'Starting','total':len(rows),'sent':0,'skipped':0,'failed':0}
            if hasattr(self.store,'claim') and not self.store.claim(claim_key,reservation):
                existing=self.store.get(claim_key,reservation)
                if existing.get('signature')!=signature:raise ValueError('This request was already used for another donor batch.')
                return {'job':self._public(existing),'reply':'This donor batch is already tracked. It was not started again.'}
            job={'id':ident,'request_id':rid,'signature':signature,'boot':self.boot,'scope':scope,'gap_seconds':gap,'poster':poster,'ids':[r['id'] for r in rows],'caption':caption,'captions':captions,'state':'Starting','sent':0,'skipped':0,'failed':0,'total':len(rows),'current':'','receipts':[],'created_at':now,'updated_at':now,'next_at':None}
            job.update(auto=True,batch=1,hold_until=hold_until)
            if chunk and len(rows)>chunk:job.update(chunk=chunk,rest_seconds=rests[0],rests=rests,batches=-(-len(rows)//chunk))
            if jitter:job['jitter']=jitter
            if personal_names is not None:job['personal_names']=copy.deepcopy(personal_names)
            if custom_template is not None:job['custom_template']=custom_template
            if attachment:job['attachment']=attachment
            data['jobs'].append(job);self._save(data);self.active=ident;self.stop.clear()
        if run:threading.Thread(target=self._run,args=(copy.deepcopy(job),),daemon=True).start()
        pauses=', '.join(f'{x/60:g}' for x in (job.get('rests') or []));rounds=(f" {job['batches']} batches of up to {chunk}. Pause between batches: {pauses} min. Everything continues by itself, even with the app closed. Say stop any time." if job.get('chunk') else '')+(f" Gap between DMs varies by {jitter['min']:g} to {jitter['max']:+g} seconds." if jitter else '')+(f" {already} already contacted were left out." if already else '')
        return {'job':self._public(job),'reply':resumed+f'Started {len(rows)} {scope.replace("_"," ")} donor DMs. First sends now; next DMs {gap/60:g} min apart, with different wording for each person. Prior confirmed sends do not prevent this explicit batch.'+rounds+(' The minimum gap is 1 minute.' if gap_seconds<60 else '')}
    def cancel(self):
        self.stop.set()
        return {'reply':'Stopping the donor batch. Any message already in flight may still complete.','job':self.status()}
    def export_jobs(self):
        with self.lock:return self._load()
    def import_jobs(self,data=None):
        with self.lock:
            data=data if isinstance(data,dict) and isinstance(data.get('jobs'),list) else {'jobs':[]};self._save(copy.deepcopy(data))
    def _gap(self,j):
        """The wait before the next DM: the chosen gap, varied a little when random gaps are on. Never under 60 s."""
        base=float(j['gap_seconds']);jit=j.get('jitter')
        return max(60.0,base+random.uniform(jit['min'],jit['max'])) if jit else base
    def _rest(self,j,batch):
        rests=j.get('rests') or [j.get('rest_seconds',1200)];return float(rests[min(max(batch,1),len(rests))-1])
    def _sleep_until(self,due):
        """Wait in short steps so Stop answers fast. True when the owner stopped it."""
        while time.time()<due:
            if self.stop.wait(min(2,max(.1,due-time.time()))):return True
        return self.stop.is_set()
    def _fresh_caption(self,j,index):
        """The wording saved when the batch started, but with today's amount: donations that arrive while a long batch waits
        between DMs must not be sent as an old balance."""
        if 'custom_template' in j:
            ident=j['ids'][index];name=(j.get('personal_names',{}).get(ident) or ('','Brother'))[0]
            return j['custom_template'].replace('{name}',name or 'Brother')
        captions=j.get('captions',[j['caption']]*len(j['ids']));saved=captions[index]
        if not self.variants:return saved
        try:
            size=j.get('chunk') or len(j['ids']);fresh=self.variants(min(size,len(j['ids'])))
            return fresh[index%size] if isinstance(fresh,list) and index%size<len(fresh) and isinstance(fresh[index%size],str) and fresh[index%size].strip() else saved
        except Exception:return saved
    def _dispatch(self,j,body,receipts,sent,skipped):
        """Send one DM. Waits for WhatsApp to come back instead of giving up."""
        while True:
            if not self.connected():
                deadline=time.time()+1800
                self._update(j['id'],state='Waiting',next_at=None,current='Waiting for WhatsApp to reconnect',sent=sent,skipped=skipped,receipts=receipts)
                while not self.connected():
                    if time.time()>=deadline:raise ValueError('WhatsApp stayed disconnected for 30 minutes. Reconnect it, then press Continue.')
                    if self.stop.wait(15):return None
            return self.send(body)
    def _run(self,j):
        receipts=[];sent=skipped=failed=0;last_completion=None;state='Completed';error='';chunk=j.get('chunk');gap_next=float(j['gap_seconds']);done_here=set()
        try:
            hold=j.get('hold_until')
            if hold and hold>time.time():
                self._update(j['id'],state='Waiting',next_at=hold,next_batch_at=hold,current='Waiting for the next batch time')
                if self._sleep_until(hold):
                    self._update(j['id'],state='Stopped',next_at=None,next_batch_at=None,current='');self.active=None;return
            for index,ident in enumerate(j['ids']):
                if self.stop.is_set():state='Stopped';break
                if self.held():state='Stopped';error='Sending is on hold.';break
                if self.case_closed():state='Stopped';error='The case is complete (Rs. 0 left), so the rest of this batch was stopped before sending.';break
                if ident in done_here:continue
                if chunk and index and index%chunk==0 and last_completion is not None:
                    rest=last_completion+self._rest(j,index//chunk)
                    self._update(j['id'],state='Waiting',next_at=rest,next_batch_at=rest,batch=index//chunk+1,current=f"Resting before batch {index//chunk+1}",sent=sent,skipped=skipped,receipts=receipts)
                    if self._sleep_until(rest):state='Stopped';break
                    self._update(j['id'],next_batch_at=None)
                try:r=self.book.resolve(ident)
                except ValueError:skipped+=1;receipts.append({'id':ident,'name':'Removed donor','state':'Skipped'});continue
                if not self.eligible(r['phone']):
                    skipped+=1;receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Skipped: '+getattr(self,'exclusion_reason',lambda p:'recipient excluded')(r['phone'])});continue
                if last_completion is not None or self.manual_inflight.is_set() or self.manual_sent_at>j['created_at']:
                    due=max(last_completion or 0,self.manual_sent_at)+gap_next;self._update(j['id'],state='Waiting',next_at=due,current='Waiting between DMs',sent=sent,skipped=skipped,receipts=receipts)
                    while self.manual_inflight.is_set() or time.time()<due:
                        if self.stop.wait(min(.5,max(.1,due-time.time()))):break
                        new_due=max(last_completion or 0,self.manual_sent_at)+gap_next
                        if new_due!=due:due=new_due;self._update(j['id'],next_at=due)
                    if self.stop.is_set():state='Stopped';break
                # Recheck deletion, hold and receipt at dispatch, not just selection time.
                try:r=self.book.resolve(ident)
                except ValueError:skipped+=1;continue
                if self.held():state='Stopped';error='Sending is on hold.';break
                if self.case_closed():state='Stopped';error='The case is complete (Rs. 0 left), so the rest of this batch was stopped before sending.';break
                if not self.eligible(r['phone']):
                    skipped+=1;receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Skipped: '+getattr(self,'exclusion_reason',lambda p:'recipient excluded')(r['phone'])});continue
                name,gender=j['personal_names'][ident] if 'personal_names' in j else self.name_for(r['name'])
                self._update(j['id'],state='Sending',next_at=None,current=hide_numbers(r['name']),batch=(index//chunk+1) if chunk else 1,sent=sent,skipped=skipped,receipts=receipts)
                self.book.delivery(ident,'Sending')
                try:result=self._dispatch(j,{'target':'phone','phone':r['phone'],'message':self._fresh_caption(j,index),'poster':j['poster'],'kind':'owner_text' if 'custom_template' in j else self.KIND,'attachment':j.get('attachment'),'first_in_batch':sent==0,'name':name,'gender':gender},receipts,sent,skipped)
                except ValueError as e:
                    self.book.delivery(ident,'Not sent');state='Stopped';error=hide_numbers(e);break
                except Exception:
                    self.book.delivery(ident,'Uncertain');failed+=1;receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Uncertain'});state='Stopped';error='Delivery was not confirmed. Check WhatsApp. No automatic retry.';break
                if result is None:self.book.delivery(ident,'Not sent');state='Stopped';break
                last_completion=time.time();done_here.add(ident);gap_next=self._gap(j)
                if not isinstance(result,dict) or result.get('code')!='SUCCESS':
                    self.book.delivery(ident,'Uncertain');failed+=1;receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Uncertain'});state='Stopped';error='Delivery was not confirmed. Check WhatsApp. No automatic retry.';break
                sent+=1;self.book.delivery(ident,'Sent',last_completion);receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Sent','time':last_completion})
                self._update(j['id'],sent=sent,skipped=skipped,receipts=receipts)
        except Exception:
            state='Stopped';error='The batch could not continue reliably. Check receipts before starting again.'
        finally:
            if not sent and skipped==len(j['ids']) and state=='Completed':state='Nothing sent';error='All selected recipients were excluded. See the recipient results; this batch did not send any DM.'
            self._update(j['id'],state=state,error=error,sent=sent,skipped=skipped,failed=failed,receipts=receipts,next_at=None,next_batch_at=None,current='',caption='',captions=[],personal_names={})
            with self.lock:self.active=None
    def recover(self):
        """After a restart, carry on with a batch the owner already confirmed. People sent, unconfirmed or caught
        mid-send are skipped, so nobody gets a second DM. Returns the started job or None."""
        with self.lock:
            self.status();jobs=self._load().get('jobs',[]);j=jobs[-1] if jobs else None
        if not j or not j.get('auto') or j.get('state')!='Interrupted' or not self._remaining(j) or j.get('boot')==self.boot or self.active or time.time()-j.get('updated_at',0)>self.AUTO_WINDOW:return None
        hold=j.get('next_batch_at') or j.get('next_at')
        args=dict(scope=j['scope'],gap_seconds=j['gap_seconds'],poster=j.get('poster',True),hold_until=hold if hold and hold>time.time() else None,skip_contacted=False)
        if j.get('chunk'):args.update(chunk=j['chunk'],rests=j.get('rests'))
        if j.get('jitter'):args['jitter']=j['jitter']
        if 'custom_template' in j:args['custom_template']=j['custom_template']
        if j.get('attachment'):args['attachment']=j['attachment']
        if j['scope']=='selected':
            if not j.get('personal_names'):return None
            args.update(ids=j['ids'],personal_names=j['personal_names'],limit=len(j['ids']))
        return self.start(**args,request_id='auto-'+uuid.uuid4().hex)
    AUTO_WINDOW=36*3600
