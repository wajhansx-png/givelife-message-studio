"""Explicit donor batches, saved receipts and no automatic replay after restart."""
import copy, hashlib, json, math, threading, time, uuid
from pathlib import Path
from donor_book import hide_numbers

class DonorDelivery:
    def __init__(self,folder,store,book,send,caption,connected,held,eligible,name_for):
        self.path=Path(folder)/'donor-delivery.json';self.store=store;self.book=book
        self.send=send;self.caption=caption;self.connected=connected;self.held=held;self.eligible=eligible;self.name_for=name_for
        self.lock=threading.RLock();self.boot=uuid.uuid4().hex;self.stop=threading.Event();self.active=None
        self.manual_sent_at=0;self.manual_inflight=threading.Event()
    def _load(self):
        raw=self.store.get('donor_delivery') if self.store else None
        if raw is None and self.path.exists():raw=json.loads(self.path.read_text(encoding='utf-8'))
        return raw if isinstance(raw,dict) else {'jobs':[]}
    def _save(self,data):
        data['jobs']=data['jobs'][-100:]
        if self.store:self.store.put('donor_delivery',data)
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
            return self._public(jobs[-1]) if jobs else {'state':'Idle','sent':0,'skipped':0,'failed':0,'total':0}
    def _public(self,j):
        return {k:copy.deepcopy(v) for k,v in j.items() if k not in ('boot','caption','ids','signature')}
    def _update(self,ident,**fields):
        with self.lock:
            data=self._load();j=next(x for x in data['jobs'] if x['id']==ident);j.update(fields,updated_at=time.time());self._save(data)
            return copy.deepcopy(j)
    def start(self,scope='important',gap_seconds=60,ids=None,limit=None,request_id=None,poster=True,run=True):
        if type(gap_seconds) not in (float,int) or not math.isfinite(gap_seconds) or not 0<gap_seconds<=86400:raise ValueError('Choose a gap between 1 second and 24 hours. The existing minimum is 60 seconds.')
        if limit is not None and (type(limit) is not int or not 1<=limit<=1000):raise ValueError('Choose a recipient count of 1–1,000.')
        if type(poster) is not bool:raise ValueError('Poster must be on or off.')
        if self.held():raise ValueError('Sending is on hold. Resume it before starting DMs.')
        caption=self.caption()
        if not isinstance(caption,str) or not caption.strip():raise ValueError('The saved DM message is empty. Edit it first.')
        gap=max(60,float(gap_seconds));rid=str(request_id or uuid.uuid4().hex)
        if not 1<=len(rid)<=100:raise ValueError('Invalid send request.')
        rows=self.book.recipients(scope,ids,limit)
        if not rows:raise ValueError('There are no donors in this audience.')
        signature=hashlib.sha256(json.dumps([scope,gap,ids,limit,poster,caption],sort_keys=True).encode()).hexdigest()
        with self.lock:
            data=self._load();previous=next((j for j in data['jobs'] if j.get('request_id')==rid),None)
            if previous:
                if previous['signature']!=signature:raise ValueError('This request was already used for a different batch. Refresh before sending.')
                return {'job':self._public(previous),'reply':'This request is already tracked. It was not started again.'}
            if self.active:raise ValueError('A donor batch is already running. Stop it or wait for it to finish.')
            if not self.store:raise ValueError('Persistent sending records are unavailable. Nothing was sent.')
            if not self.connected():raise ValueError('WhatsApp is disconnected. Link it before sending.')
            ident=uuid.uuid4().hex;now=time.time()
            job={'id':ident,'request_id':rid,'signature':signature,'boot':self.boot,'scope':scope,'gap_seconds':gap,'poster':poster,'ids':[r['id'] for r in rows],'caption':caption,'state':'Starting','sent':0,'skipped':0,'failed':0,'total':len(rows),'current':'','receipts':[],'created_at':now,'updated_at':now,'next_at':None}
            data['jobs'].append(job);self._save(data);self.active=ident;self.stop.clear()
        if run:threading.Thread(target=self._run,args=(copy.deepcopy(job),),daemon=True).start()
        return {'job':self._public(job),'reply':f'Started {scope.replace("_"," ")} donors: {len(rows)} selected, {gap:g}s minimum gap, Important first. Already-contacted or uncertain numbers are skipped.'+(' Your requested gap was raised to the existing 60-second minimum.' if gap_seconds<60 else '')}
    def cancel(self):
        self.stop.set()
        return {'reply':'Stopping the donor batch. Any message already in flight may still complete.','job':self.status()}
    def _run(self,j):
        receipts=[];sent=skipped=failed=0;last_completion=None;state='Completed';error=''
        try:
            for ident in j['ids']:
                if self.stop.is_set():state='Stopped';break
                if self.held():state='Stopped';error='Sending is on hold.';break
                try:r=self.book.resolve(ident)
                except ValueError:skipped+=1;receipts.append({'id':ident,'name':'Removed donor','state':'Skipped'});continue
                if not self.eligible(r['phone']):
                    skipped+=1;receipts.append({'id':ident,'name':hide_numbers(r['name']),'state':'Skipped: already contacted, blocked or uncertain'});continue
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
                name,gender=self.name_for(r['name'])
                self._update(j['id'],state='Sending',next_at=None,current=hide_numbers(r['name']),sent=sent,skipped=skipped,receipts=receipts)
                self.book.delivery(ident,'Sending')
                try:result=self.send({'target':'phone','phone':r['phone'],'message':j['caption'],'poster':j['poster'],'kind':'donor_registry','name':name,'gender':gender})
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
            self._update(j['id'],state=state,error=error,sent=sent,skipped=skipped,failed=failed,receipts=receipts,next_at=None,current='')
            with self.lock:self.active=None

