"""Bounded, persistent, source-labelled memory and feedback. No model training."""
import collections, hashlib, json, os, re, threading, time, uuid
from pathlib import Path
from state_shapes import mapping, records

def safe_text(text, limit=6000):
 text=str(text or '')
 for name in ('DEEPSEEK_API_KEY','UI_ACCESS_KEY','DB_URI'):
  secret=os.environ.get(name,'')
  if len(secret)>8:text=text.replace(secret,'[private credential]')
 text=re.sub(r'(?i)\bsk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9_.-]{12,}|postgres(?:ql)?://[^\s]+','[private credential]',text)
 return text[:limit]

def tokens(text):
 return set(re.findall(r'[\w\u0600-\u06ff]{2,}',str(text).casefold()))-set('the this that with from have your what when then send message please'.split())

def preference_key(text):
 return 'format:markup' if re.search(r'(?i)bold|italic',text) else 'format:spacing' if re.search(r'(?i)paragraph|spacing',text) else 'format:structure' if re.search(r'(?i)format|structure',text) else 'greeting' if re.search(r'(?i)logical name|unclear name|no name|brother|sister',text) else 'donation_order' if '2000' in text.replace(',','') and '1000' in text.replace(',','') and re.search(r'(?i)first|before|order',text) else None

class Knowledge:
 def __init__(self,folder,store=None):
  self.file=Path(folder)/'assistant-knowledge.json';self.store=store;self.lock=threading.RLock()
  saved=store.get('assistant_knowledge',{}) if store else {}
  if not saved and self.file.exists():
   try:saved=self.file.read_text(encoding='utf-8')
   except OSError:pass
  saved=mapping(saved)
  self.data={k:[x for x in records(saved.get(k)) if isinstance(x,dict)] for k in ('entries','turns','feedback','traces')}
  self.data['pending']=mapping(saved.get('pending'))
  self.sync_error=None
 def save(self):
  with self.lock:
   self.data['entries']=self.data['entries'][-1000:];self.data['turns']=self.data['turns'][-2000:]
   self.data['feedback']=self.data['feedback'][-500:];self.data['traces']=self.data['traces'][-200:]
   raw=json.dumps(self.data,ensure_ascii=False);temp=self.file.with_suffix('.tmp')
   temp.write_text(raw,encoding='utf-8');os.replace(temp,self.file)
   if self.store:
    try:self.store.put('assistant_knowledge',json.loads(raw));self.sync_error=None
    except Exception:self.sync_error='Cloud memory sync is pending; a local copy is saved.'
 def archive(self,who,text,turn_id=None):
  text=safe_text(text)
  if not text.strip():return
  with self.lock:
   if turn_id and any(x.get('id')==turn_id for x in self.data['turns']):return
   if self.data['turns'] and self.data['turns'][-1].get('who')==who and self.data['turns'][-1].get('text')==text:return
   self.data['turns'].append({'id':turn_id or uuid.uuid4().hex,'who':who,'text':text,'time':time.time(),'source':'owner_input' if who=='you' else 'app_output'})
   self.save()
 def remember(self,text,source='owner_preference',source_id=None):
  text=safe_text(text,1000).strip()
  if not text:raise ValueError('Write the preference or correction to remember.')
  key=preference_key(text)
  with self.lock:
   for e in self.data['entries']:
    if e.get('active') and e.get('text')==text:return e
   item={'id':uuid.uuid4().hex,'text':text,'source':source,'source_id':source_id,'time':time.time(),'active':True,'key':key}
   if key:
    for e in self.data['entries']:
     if e.get('key')==key and e.get('active'):e['active']=False;e['superseded_by']=item['id']
   self.data['entries'].append(item);self.save();return item
 def import_legacy(self,items):
  with self.lock:
   known={e.get('text') for e in self.data['entries']};added=False
   for old in items:
    text=safe_text(old.get('rule',''),1000).strip()
    if not text or text in known:continue
    key=preference_key(text)
    # A newer, explicit current-format memory wins over an imported legacy rule.
    active=not (key and any(e.get('active') and e.get('key')==key and e.get('source')!='legacy_owner_preference' for e in self.data['entries']))
    self.data['entries'].append({'id':'legacy-'+hashlib.sha256(text.encode()).hexdigest()[:20],'text':text,'source':'legacy_owner_preference','time':old.get('time',0) if isinstance(old.get('time',0),(int,float)) else 0,'active':active,'key':key});known.add(text);added=True
   if added:self.save()
 def forget(self,ident):
  with self.lock:
   found=False
   for e in self.data['entries']:
    if e.get('id')==ident:e['active']=False;found=True
   self.save();return found
 def retrieve(self,query,limit=8):
  query_tokens=tokens(query);out=[]
  with self.lock:
   entries=[dict(x) for x in self.data['entries'] if isinstance(x,dict) and x.get('active')]
   turns=[dict(x) for x in self.data['turns'] if isinstance(x,dict)]
  for item in entries:
   overlap=len(query_tokens & tokens(item.get('text','')))
   item['score']=4+overlap*3+(2 if item.get('key') else 0);out.append(item)
  for item in turns:
   overlap=len(query_tokens & tokens(item.get('text','')))
   if overlap>=2:out.append({**item,'score':overlap*2,'source':'historical_'+item.get('source','app_output')})
  for item in self.data['feedback'][-30:]:
   correction=item.get('correction','')
   if correction and query_tokens & tokens(correction):out.append({'id':item['id'],'text':correction,'time':item.get('time',0),'source':'owner_reported_issue','score':5+len(query_tokens & tokens(correction))})
  out.sort(key=lambda e:(e['score'],e.get('time',0)),reverse=True)
  return [{k:v for k,v in e.items() if k not in ('score','active')} for e in out[:limit]]
 def feedback(self,turn_id,correction='',remember=False):
  with self.lock:
   reply=next((x for x in reversed(self.data['turns']) if x.get('id')==turn_id and x.get('who')=='app'),None)
   if not reply:raise ValueError('This reply is no longer available. Describe the correction in chat.')
   correction=safe_text(correction,1500).strip()
   category='recipient' if re.search(r'(?i)name|recipient|number|contact',correction) else 'format' if re.search(r'(?i)bold|italic|format|paragraph|spacing',correction) else 'action' if re.search(r'(?i)send|sent|post|delete|stop',correction) else 'response'
   item={'id':uuid.uuid4().hex,'turn_id':turn_id,'correction':correction,'category':category,'status':'confirmed_by_owner','time':time.time()}
   self.data['feedback'].append(item)
   if remember and correction:self.remember(correction,'owner_confirmed_correction',item['id'])
   self.save();return item
 def report_correction(self,text):
  if not re.search(r'(?i)\b(wrong|incorrect|mistake|i meant|not what i|you misunderstood)\b',text):return
  with self.lock:
   self.data['feedback'].append({'id':uuid.uuid4().hex,'correction':safe_text(text,1500),'category':'reported_response','status':'reported_needs_review','time':time.time()});self.save()
 def trace(self,item):
  with self.lock:self.data['traces'].append({**item,'time':time.time()});self.save()
 def summary(self):
  with self.lock:
   return {'entries':[e for e in self.data['entries'] if e.get('active')], 'feedback_count':sum(x.get('status')=='confirmed_by_owner' for x in self.data['feedback']),'reported_count':sum(x.get('status')=='reported_needs_review' for x in self.data['feedback']),'sync_warning':self.sync_error,
     'patterns':dict(collections.Counter(x.get('category','response') for x in self.data['feedback'])),
     'archived_turns':len(self.data['turns']),'pending':self.data['pending'],'retention':{'turns':2000,'memories':1000,'feedback':500}}
