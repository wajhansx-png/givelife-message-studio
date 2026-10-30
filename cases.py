"""Cases: each case (for example "Yousuf") keeps its own amount, captions, stars, donated marks, DM-sent marks and batch history.
Closing one saves it; a new case starts from zero; any saved case can be opened again. Donor and volunteer names and numbers are shared."""
import copy, json, re, threading, time, uuid

class Cases:
    KEY='cases'
    def __init__(self,app,hub):
        self.app=app;self.hub=hub;self.lock=threading.RLock()
    # --- registry
    def _load(self):
        raw=self.app.STORE.get(self.KEY) if self.app.STORE else None
        if raw is None and (self.app.DATA/'cases.json').exists():raw=json.loads((self.app.DATA/'cases.json').read_text(encoding='utf-8'))
        if not isinstance(raw,dict) or not raw.get('cases'):
            cid=uuid.uuid4().hex;raw={'current':cid,'cases':[{'id':cid,'name':'Current case','created_at':time.time(),'snapshot':None}]};self._save(raw)
        return raw
    def _save(self,data):
        if self.app.STORE:self.app.STORE.put(self.KEY,data)
        (self.app.DATA/'cases.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    # --- what a case holds
    def _capture(self):
        h=self.hub;a=self.app
        return {'state':(a.DATA/'state.md').read_text(encoding='utf-8-sig'),'drafts':a.DRAFT.read_text(encoding='utf-8') if a.DRAFT.exists() else '',
                'donors':h.book.export_case_fields(),'volunteers':h.volunteers.book.export_case_fields(),
                'jobs':h.jobs.export_jobs(),'vjobs':h.volunteers.jobs.export_jobs(),
                'bank':a.STORE.get('donor_messages') if a.STORE else None,'saved_at':time.time()}
    def _summary(self,snap):
        m=re.search(r'^LEFT:\s*(\d+)',snap.get('state',''),re.M);donors=snap.get('donors',{})
        return {'left':int(m[1]) if m else None,'donors':len(donors),'donated':sum(1 for d in donors.values() if d.get('donated')),'donated_amount':sum(float(d.get('amount') or 0) for d in donors.values() if d.get('donated')),'sent':sum(1 for d in donors.values() if d.get('dm_sent') or d.get('delivery')=='Sent'),'important':sum(1 for d in donors.values() if d.get('important'))}
    def _apply(self,snap,left=None):
        h=self.hub;a=self.app
        if snap:
            (a.DATA/'state.md').write_text(snap['state'],encoding='utf-8');a.persist_file('campaign',a.DATA/'state.md')
            if snap.get('drafts'):a.DRAFT.write_text(snap['drafts'],encoding='utf-8');a.persist_file('drafts',a.DRAFT)
            h.book.import_case_fields(snap.get('donors'));h.volunteers.book.import_case_fields(snap.get('volunteers'))
            h.jobs.import_jobs(snap.get('jobs'));h.volunteers.jobs.import_jobs(snap.get('vjobs'))
            bank=snap.get('bank')
        else:
            state=(a.DATA/'state.md').read_text(encoding='utf-8-sig')
            for key in ('LEFT','POSTER_LEFT'):state=re.sub(r'^'+key+r':.*$',key+': '+str(left),state,flags=re.M) if re.search(r'^'+key+':',state,re.M) else key+': '+str(left)+'\n'+state
            (a.DATA/'state.md').write_text(state,encoding='utf-8');a.persist_file('campaign',a.DATA/'state.md')
            h.book.import_case_fields(None);h.volunteers.book.import_case_fields(None);h.jobs.import_jobs(None);h.volunteers.jobs.import_jobs(None);bank=None
            a.regenerate_drafts(left)
        if a.STORE:a.STORE.put('donor_messages',bank if isinstance(bank,dict) else {})
        h.messages.cache=None
        try:(a.DATA/'donor-messages.json').unlink()
        except OSError:pass
    def _busy(self):
        if self.hub.jobs.active or self.hub.volunteers.jobs.active:raise ValueError('A DM batch is still running. Pause it first, then change the case.')
    # --- public
    def view(self):
        with self.lock:
            d=self._load();cur=d['current'];out=[]
            for c in d['cases']:
                snap=self._capture() if c['id']==cur else c.get('snapshot')
                s=self._summary(snap) if snap else {'left':None}
                out.append({'id':c['id'],'name':c['name'],'current':c['id']==cur,'created_at':c['created_at'],**s})
            return {'current':cur,'cases':out}
    def rename(self,cid,name):
        name=str(name or '').strip()
        if not 1<=len(name)<=60:raise ValueError('Name the case in 1 to 60 characters.')
        with self.lock:
            d=self._load();c=next((c for c in d['cases'] if c['id']==cid),None)
            if not c:raise ValueError('That case was not found.')
            c['name']=name;self._save(d);return self.view()
    def new(self,name,left):
        name=str(name or '').strip()
        if not 1<=len(name)<=60:raise ValueError('Name the new case, for example the child\'s name.')
        if type(left) is bool or not isinstance(left,(int,float)) or not 0<left<=100000000:raise ValueError('Enter the amount needed for the new case.')
        with self.lock:
            self._busy();d=self._load()
            cur=next(c for c in d['cases'] if c['id']==d['current']);cur['snapshot']=self._capture()
            cid=uuid.uuid4().hex;d['cases'].append({'id':cid,'name':name,'created_at':time.time(),'snapshot':None});d['current']=cid
            self._apply(None,int(left));self._save(d)
            return {**self.view(),'reply':f'Saved "{cur["name"]}" and started "{name}" from zero. Names and numbers are kept; stars, donated and DM-sent marks start fresh.'}
    def switch(self,cid):
        with self.lock:
            self._busy();d=self._load()
            if cid==d['current']:return self.view()
            target=next((c for c in d['cases'] if c['id']==cid),None)
            if not target:raise ValueError('That case was not found.')
            cur=next(c for c in d['cases'] if c['id']==d['current']);cur['snapshot']=self._capture()
            self._apply(target.get('snapshot'),None) if target.get('snapshot') else self._apply(None,self._summary(cur['snapshot'])['left'] or 0)
            d['current']=cid;self._save(d)
            return {**self.view(),'reply':f'Opened "{target["name"]}". "{cur["name"]}" is saved.'}
