import json, subprocess, urllib.request, urllib.parse, threading, time, uuid, datetime, math, re, secrets, os, base64, hashlib
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from persist import configured_store
import manual_commands
import dm_composer
from state_shapes import mapping, memories, history as valid_history
import chat_policy
import timed_tasks
from chat_memory import Knowledge,safe_text
from functools import wraps
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('DATA_DIR','/data/studio'))
DATA.mkdir(parents=True,exist_ok=True)
DRAFT=DATA/'drafts.json'
DEVICE=os.environ.get('WHATSAPP_DEVICE_ID','')
GOWA_URL=os.environ.get('GOWA_URL','http://127.0.0.1:3000').rstrip('/')
GROUPS={'main':('GiveLife Foundation','120363423121755785@g.us'),'community':('Upwork Community 2026','120363398623589385@g.us'),'fiverr':('Fiverr Course 2026','120363411617215937@g.us'),'upwork':('Upwork Course 2026','120363430624868021@g.us'),'uet':('Fiverr Course UET','120363412286860707@g.us'),'toprated':('Top Rated Upworkers','120363427826119453@g.us')}
FREELANCE=['community','fiverr','upwork','uet','toprated']
LAST_LOCAL={}
JOBS={};JOB_CANCEL={};REQUEST_JOBS={};LOCK=threading.RLock();SEND_LOCK=threading.RLock();ACTIVE=None
WIRE_LOCK=threading.RLock()
OWNER_REVISION=0
OWNER_GUARD=threading.local()
ASSIST_TASKS={}
EVAL_TASKS={}

def serialized_send(fn):
 @wraps(fn)
 def call(*args,**kwargs):
  with WIRE_LOCK:
   for secret_name in ('DEEPSEEK_API_KEY','UI_ACCESS_KEY','DB_URI'):
    secret=os.environ.get(secret_name,'')
    if len(secret)>8 and any(secret in str(value) for value in (*args,*kwargs.values())):raise ValueError('Private service credentials cannot be included in outgoing messages.')
   revision=getattr(OWNER_GUARD,'revision',None)
   if revision is not None and revision!=OWNER_REVISION:raise ValueError('Superseded by your newer instruction. Nothing was sent.')
   event=getattr(OWNER_GUARD,'cancel_event',None)
   if event is not None and event.is_set():return {'code':'CANCELLED','message':'Stopped by the newer instruction.'}
   return fn(*args,**kwargs)
 return call

STORE=configured_store()
BLOCKED=set(json.loads((ROOT/'campaign-blocks.json').read_text())) if (ROOT/'campaign-blocks.json').exists() else set()
def persist_file(key,path):
 if STORE:STORE.put(key,path.read_text(encoding='utf-8'))

def api(path):
 req=urllib.request.Request(GOWA_URL+path,headers={'X-Device-Id':DEVICE})
 with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)

def custom_recipient(body):
 target=str(body.get('target',''))
 if target=='test':return '120363431210327603@g.us',True
 if target in GROUPS:return GROUPS[target][1],True
 if target!='phone':raise ValueError('Choose a saved group or phone number.')
 phone=re.sub(r'[\s()+-]','',str(body.get('phone','')))
 if phone.startswith('00'):phone=phone[2:]
 if phone.startswith('03') and len(phone)==11:phone='92'+phone[1:]
 if not re.fullmatch(r'[1-9]\d{7,14}',phone):raise ValueError('Enter a valid phone number with country code, such as +92…')
 return phone,False

def send_custom(body):
 jid,is_group=custom_recipient(body);message=body.get('message','')
 if not isinstance(message,str):raise ValueError('Message must be text.')
 if not is_group and body.get('kind')=='dm_appeal':
  message=greet_text(message,body.get('name',''),body.get('gender','Brother'))
  if not dm_composer.complete(message):raise ValueError('The full DM is incomplete. Restore its paragraphs and payment details before sending.')
 if not message.strip() or len(message)>10000:raise ValueError('Write a message of 1 to 10,000 characters.')
 if not STORE:raise ValueError('Persistent send records are unavailable. Try again later.')
 if not SEND_LOCK.acquire(blocking=False):raise ValueError('Another send is running. Please wait for it to finish.')
 try:
  status=api('/devices/'+DEVICE+'/status').get('results',{})
  if not status.get('is_connected') or not status.get('is_logged_in'):raise ValueError('WhatsApp is disconnected. Tap WhatsApp to reconnect.')
  now=time.time();saved=STORE.get('last_sent',{})
  if not is_group:
   digest=hashlib.sha256(jid.encode()).hexdigest()
   if digest in BLOCKED or STORE.get('dm_recipient_'+digest):raise ValueError('This recipient was already contacted or has an uncertain send. Check WhatsApp before sending again.')
   ledger=STORE.get('dm_daily',{});day=datetime.datetime.fromtimestamp(now,datetime.timezone(datetime.timedelta(hours=5))).date().isoformat()
   if ledger.get('day')!=day:ledger={'day':day,'count':0,'last':ledger.get('last',0)}
   if ledger['count']>=50:raise ValueError('The 50-DM daily limit has been reached.')
   if now-ledger.get('last',0)<60:raise ValueError('Wait at least 60 seconds between DMs.')
   ledger.update(count=ledger['count']+1,last=now);STORE.put('dm_daily',ledger);STORE.put('dm_recipient_'+digest,{'state':'uncertain','time':now})
  # Reserve before dispatch. A network failure must not silently allow duplicates.
  try:
   if body.get('poster') is True:result=send_image(jid,message)
   else:
    req=urllib.request.Request(GOWA_URL+'/send/message',data=json.dumps({'phone':jid,'message':message}).encode(),headers={'X-Device-Id':DEVICE,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=40) as response:result=json.load(response)
  except Exception:result={'code':'UNCERTAIN','message':'Send not confirmed. Check WhatsApp before retrying.'}
  if is_group and result.get('code')=='SUCCESS':
   saved[jid]=time.time();STORE.put('last_sent',saved);LAST_LOCAL[jid]=time.time();record_delivery(jid,message,result)
  STORE.put('custom_receipt_'+uuid.uuid4().hex,{'time':now,'jid':jid,'code':result.get('code'),'message_id':result.get('results',{}).get('message_id')})
  if not is_group:STORE.put('dm_recipient_'+digest,{'state':result.get('code','UNCERTAIN'),'time':now})
  if result.get('code')=='SUCCESS':remember_manual({'kind':'text','to':jid,'text':message,'with_picture':body.get('poster') is True})
  return result
 finally:SEND_LOCK.release()

HOOKS=[
 ("Imagine it was your own 2-year-old.","If it were your child, you would not wait. Send what you can now."),
 ("Rs. 1,000 is a small bill for you. For Yousuf it is a real part of his treatment.","Do not think about the amount. Think about him. Send Rs. 1,000 or Rs. 2,000."),
 ("Everyone here will read this. If everyone only reads, he gets nothing.","Do not leave it for the next person. The next person is thinking the same."),
 ("His mother is watching him. She cannot do anything. You can.","You cannot fix his illness yourself, but you can fund his treatment."),
 ("Doctors can treat this. Only one thing is missing: people like you.","Your Rs. 1,000 or 2,000 can help him get treatment."),
 ("He is 2. He cannot ask for help. This message is his voice.","Be his voice. Send Rs. 1,000 or Rs. 2,000."),
 ("Scroll past this, and nothing changes for him. Send Rs. 1,000, and something does.","One send. One minute. It matters to a 2-year-old and his family."),
 ("Only {P2} people are needed.","Be one of the {P2}. Not tomorrow. Now.")]
DP=json.loads((ROOT/'dm_pools.json').read_text(encoding='utf-8'))

def read_left():
 state=(DATA/'state.md').read_text(encoding='utf-8-sig');m=re.search(r'^LEFT:\s*(\d+)',state,re.M);return int(m[1]) if m else 39000

def poster_left():
 m=re.search(r'^POSTER_LEFT:\s*(\d+)',(DATA/'state.md').read_text(encoding='utf-8-sig'),re.M);return int(m[1]) if m else None

def write_left(left):
 f=DATA/'state.md';state=f.read_text(encoding='utf-8-sig')
 state=re.sub(r'^LEFT:.*$','LEFT: '+str(left),state,flags=re.M) if re.search(r'^LEFT:',state,re.M) else 'LEFT: '+str(left)+'\n'+state
 f.write_text(state,encoding='utf-8');persist_file('campaign',f)

ALMOST=[("We are almost there. Only Rs. {L} left for Yousuf.","Just {P2} people can finish this today."),
 ("Rs. {L} is all that stands between Yousuf and his treatment.","Be one of the last {P2}. Today."),
 ("The last few people decide it. Rs. {L} left.","If {P2} people send Rs. 2,000 now, it is done.")]

def build_group(n,left):
 p2,p1=math.ceil(left/2000),math.ceil(left/1000)
 pool=ALMOST if 0<left<=10000 else None
 hook=(pool[n%len(pool)][0] if pool else HOOKS[n%8][0]).replace('{P2}',str(p2)).replace('{L}',f'{left:,}')
 push=(pool[(n+1)%len(pool)][1] if pool else HOOKS[(n*3+1)%8][1]).replace('{P2}',str(p2)).replace('{L}',f'{left:,}')
 return (f'*{hook}*\n\nFluid in Yousuf\'s brain *can paralyse his body and damage his eyesight.* Both his kidneys are badly swollen. 💔\n\n'
         f'*_Rs. {left:,} LEFT_*\n\n*_{p2} people donating Rs. 2,000_*\n*_OR {p1} people donating Rs. 1,000_* 🤲\n{push}\n\n'
         '*03097458815*\nEasypaisa / JazzCash (Wajdan Khan)\n\nReply *Done* after you donate.\n- GiveLife Foundation')

def build_dm(sel,left):
 p2,p1=math.ceil(left/2000),math.ceil(left/1000)
 T=[DP[i][sel[i]%len(DP[i])].replace('{L}',f'{left:,}').replace('{N}',str(p2)).replace('{M}',str(p1)) for i in range(len(DP))]
 return f'Brother, {T[0]}\n\n_{T[1]}_ 💔\n\n⚠️ *{T[2]}*\n\n🚨 {T[3]}\n\n• *_{T[4]}_* 🤲\n\n🤲 {T[5]}\n\n📲 {T[6]}'

def variant(advance):
 file=DATA/'variant-state.json';n=json.loads(file.read_text()).get('index',0) if file.exists() else 0
 if advance:file.write_text(json.dumps({'index':n+1}));persist_file('variants',file);n+=1
 return n

def dm_selection(new):
 file=DATA/'dm-state.json';sel=json.loads(file.read_text()) if file.exists() else [0]*len(DP)
 if new:
  import random
  old=sel
  while True:
   sel=[random.randrange(len(a)) for a in DP]
   if sel[0]!=old[0]:break
  file.write_text(json.dumps(sel))
 return sel

def save_draft(key,text):
 draft=json.loads(DRAFT.read_text(encoding='utf-8'));draft[key]=text;DRAFT.write_text(json.dumps(draft,ensure_ascii=False),encoding='utf-8');persist_file('drafts',DRAFT)

def next_message():
 with LOCK:
  text=build_group(variant(True),read_left());save_draft('group',text);return text

def next_dm():
 with LOCK:
  text=build_dm(dm_selection(True),read_left());save_draft('dm',text);return text

def set_left(left):
 with LOCK:
  revision=getattr(OWNER_GUARD,'revision',None)
  if revision is not None and revision!=OWNER_REVISION:raise ValueError('Superseded by your newer instruction. The amount was not changed.')
  write_left(left)
  try:ENGINE.amount_updated()
  except NameError:pass
  g=build_group(variant(False),left);d=build_dm(dm_selection(False),left)
  save_draft('group',g);save_draft('dm',d);return g,d

@serialized_send
def send_image(jid,caption,check_gap=False,_retry=True):
 if on_hold():return {'code':'ERROR','message':'On hold: you told me to wait.'}
 if jid in NEVER_GROUPS:return {'code':'ERROR','message':'This group is never used.'}
 status=api('/devices/'+DEVICE+'/status').get('results',{})
 if not status.get('is_connected') or not status.get('is_logged_in'):return {'code':'ERROR','message':'WhatsApp disconnected. Log in again.'}
 if check_gap:
  saved=STORE.get('last_sent',{}) if STORE else {}
  if jid in saved:
   age=time.time()-saved[jid]
   if age<900:return {'code':'COOLDOWN','message':f'Posted recently. Try in {math.ceil((900-age)/60)} min.'}
  messages=api('/chat/'+urllib.parse.quote(jid,safe='')+'/messages?limit=50').get('results',{}).get('data',[]);outgoing=[m for m in messages if m.get('is_from_me')]
  if outgoing:
   latest=max(datetime.datetime.fromisoformat(m['timestamp'].replace('Z','+00:00')) for m in outgoing);age=(datetime.datetime.now(datetime.timezone.utc)-latest).total_seconds()
   if age<900:return {'code':'COOLDOWN','message':f'Posted recently. Try in {math.ceil((900-age)/60)} min.'}
 cap=DATA/('caption-'+uuid.uuid4().hex+'.txt');cap.write_text(caption,encoding='utf-8')
 r=subprocess.run(['curl','-s','--max-time','40','-X','POST',GOWA_URL+'/send/image','-H',f'X-Device-Id: {DEVICE}','-F',f'phone={jid}','-F',f'image=@{DATA / "poster.jpg"};type=image/jpeg','-F',f'caption=<{cap}','-F','compress=false'],capture_output=True)
 cap.unlink(missing_ok=True)
 try:result=json.loads(r.stdout)
 except Exception:result={'code':'ERROR','message':'Send not confirmed. Check WhatsApp before retrying.'}
 if STORE:
  receipt={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'jid':jid,'code':result.get('code'),'message_id':result.get('results',{}).get('message_id')}
  STORE.put('receipt_'+uuid.uuid4().hex,receipt)
  if result.get('code')=='SUCCESS':
   saved=STORE.get('last_sent',{});saved[jid]=time.time();STORE.put('last_sent',saved)
 if result.get('code')=='SUCCESS':
  LAST_LOCAL[jid]=time.time();record_delivery(jid,caption,result)
 elif _retry and jid.endswith('@g.us') and NOT_MEMBER.search(str(result.get('message',''))):
  key=next((k for k,v in GROUPS.items() if v[1]==jid),None);chk=check_groups(True)
  if key and GROUPS[key][1]!=jid:return send_image(GROUPS[key][1],caption,check_gap,False)
  if key and GROUPS[key][0] in chk.get('missing',[]):result={'code':'ERROR','message':'The WhatsApp number linked to the studio is not in '+GROUPS[key][0]+'. Link the number that is in the groups.'}
 with (DATA/'group-send-log.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'jid':jid,'caption':caption,'response':result},ensure_ascii=False)+'\n')
 return result

QUEUED={}  # legacy timers are deliberately not resumed or recreated

def cancel_jobs(reason='Replaced by a new manual send.'):
 with LOCK:
  QUEUED.clear()
  for ident,event in JOB_CANCEL.items():
   if not JOBS.get(ident,{}).get('done'):
    event.set();JOBS[ident]['cancel_reason']=reason

def save_job(ident):
 if STORE:STORE.put('send_job_'+ident,JOBS[ident])

def get_job(ident):
 job=JOBS.get(ident)
 if job is not None:return job
 job=STORE.get('send_job_'+ident) if STORE else None
 if job and not job.get('done'):
  job.update(done=True,message='The service restarted before this send was confirmed. Check WhatsApp; it will not retry automatically.')
  if STORE:STORE.put('send_job_'+ident,job)
 return job

def start_send_job(keys,caption,manual=False,request_id=None):
 global ACTIVE
 check_hold()
 keys=list(dict.fromkeys(keys))
 if not caption.strip():raise ValueError('Message is empty.')
 if not keys or any(k not in GROUPS and k!='test' for k in keys):raise ValueError('Unknown group.')
 if request_id and not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',str(request_id)):raise ValueError('Invalid send request id.')
 with LOCK:
  existing=REQUEST_JOBS.get(request_id) if request_id else None
  if not existing and request_id and STORE:
   old=STORE.get('manual_request_'+request_id);existing=old.get('job_id') if old else None
  if existing:return existing
  if ACTIVE:
   current=JOBS.get(ACTIVE,{})
   if manual and current.get('manual') and current.get('keys')==keys and current.get('caption')==caption:
    return ACTIVE  # a double click observes the existing in-flight send; never duplicates it
   if not manual:return None
   cancel_jobs()
  ident=uuid.uuid4().hex
  JOBS[ident]={'done':False,'results':[],'message':'Sending now…','manual':bool(manual),'keys':keys,'caption':caption}
  JOB_CANCEL[ident]=threading.Event();ACTIVE=ident;LAST_JOB['id']=ident
  if request_id:
   REQUEST_JOBS[request_id]=ident
   if STORE:STORE.put('manual_request_'+request_id,{'job_id':ident})
  save_job(ident)
 threading.Thread(target=run_job,args=(ident,keys,caption),daemon=True).start()
 return ident


def run_job(job_id,keys,caption,queue=False):
 global ACTIVE
 job=JOBS[job_id];event=JOB_CANCEL.setdefault(job_id,threading.Event());last_send=None
 try:
  for key in keys:
   if event.is_set() or on_hold():break
   name,jid=('Givelife test','120363431210327603@g.us') if key=='test' else GROUPS[key]
   if last_send is not None:
    job['message']='Waiting 60 seconds between recipients before '+name;save_job(job_id)
    if event.wait(max(0,60-(time.monotonic()-last_send))):break
   with SEND_LOCK:
    if event.is_set() or on_hold():break
    job['message']='Sending to '+name;save_job(job_id)
    OWNER_GUARD.cancel_event=event
    try:result=send_image(jid,caption,not job.get('manual',False))
    finally:OWNER_GUARD.cancel_event=None
   job['results'].append({'group':name,**result});save_job(job_id)
   if result.get('code')=='SUCCESS':last_send=time.monotonic()
   elif result.get('code')!='COOLDOWN':break  # never retry an uncertain/error result
  sent=sum(r.get('code')=='SUCCESS' for r in job['results'])
  if sent and not event.is_set() and ACTIVE==job_id and json.loads(DRAFT.read_text(encoding='utf-8')).get('group')==caption:
   job['next_caption']=next_message()
  job['message']=(job.get('cancel_reason','Stopped by owner.')+' ' if event.is_set() or on_hold() else '')+f'Confirmed sent to {sent}/{len(keys)} groups.'
  job['done']=True;save_job(job_id)
  auto_log(job['message']+' '+', '.join(r['group']+(' ✓' if r.get('code')=='SUCCESS' else ' ✗ '+str(r.get('message',''))[:100]) for r in job['results']),quiet=bool(job.get('manual')))
 except Exception:
  job.update(done=True,message='Send not confirmed. Check WhatsApp before trying again.');save_job(job_id)
 finally:
  with LOCK:
   if ACTIVE==job_id:ACTIVE=None


import assistant
MEMORY=DATA/'memory.json';AUTO=DATA/'autopilot.json';AUTOLOG=[]
if STORE:
 for key,f in (('memory',MEMORY),('autopilot',AUTO)):
  v=STORE.get(key)
  if v:f.write_text(v if isinstance(v,str) else json.dumps(v),encoding='utf-8')

CHATLOG=DATA/'chat.json';RECIP=DATA/'recipient.json'
if STORE:
 for key,f in (('chat',CHATLOG),('recipient',RECIP)):
  v=STORE.get(key)
  if v:f.write_text(v if isinstance(v,str) else json.dumps(v),encoding='utf-8')
CHAT_LOCK=threading.Lock()
KNOWLEDGE=Knowledge(DATA,STORE)

def chat_get(n=300):
 try:return valid_history(CHATLOG.read_text(encoding='utf-8'))[-n:] if CHATLOG.exists() else []
 except Exception:return []

def chat_add(who,text,err=False,turn_id=None):
 who=who if who in ('you','app','auto') else 'app';text=str(text)[:4000]
 if not text.strip():return
 with CHAT_LOCK:
  items=chat_get(300);ident=str(turn_id or uuid.uuid4().hex)
  if any(x.get('id')==ident for x in items):return ident
  items.append({'id':ident,'who':who,'text':text,'err':bool(err),'t':int(time.time()*1000)})
  CHATLOG.write_text(json.dumps(items[-300:],ensure_ascii=False),encoding='utf-8');persist_file('chat',CHATLOG)
  KNOWLEDGE.archive(who,text,ident)
  return ident

def mem_get():
 try:
  old=memories(MEMORY.read_text(encoding='utf-8')) if MEMORY.exists() else []
  engine=globals().get('ENGINE')
  if engine:
   old.extend({'rule':r['text'],'time':0} for r in engine.rules() if r.get('kind')=='note' and isinstance(r.get('text'),str) and re.search(r'(?i)\b(always|never|remember|from now|in future)\b',r['text']))
  KNOWLEDGE.import_legacy(old)
  known={e.get('text') for e in KNOWLEDGE.data['entries']}
  active=[{'rule':e['text'],'time':e.get('time',0),'source':e.get('source')} for e in KNOWLEDGE.data['entries'] if e.get('active')]
  return [m for m in old if m.get('rule') not in known]+active
 except (ValueError,OSError):return []

if not KNOWLEDGE.data['turns']:
 for item in chat_get(300):KNOWLEDGE.data['turns'].append({'id':item.get('id') or uuid.uuid4().hex,'who':item['who'],'text':safe_text(item['text']),'time':item.get('t',0)/1000,'source':'owner_input' if item['who']=='you' else 'app_output'})
 if KNOWLEDGE.data['turns']:KNOWLEDGE.save()

def mem_add(rule):
 rule=str(rule).strip()[:300]
 if not rule:return 'Nothing to save.'
 m=mem_get();m.append({'rule':rule,'time':time.time()});MEMORY.write_text(json.dumps(m,ensure_ascii=False),encoding='utf-8');persist_file('memory',MEMORY)
 KNOWLEDGE.remember(rule)
 return (KNOWLEDGE.sync_error+' ' if KNOWLEDGE.sync_error else 'Saved for the future: ')+rule

HOLD=DATA/'hold.json'
if STORE:
 _v=STORE.get('hold')
 if _v:HOLD.write_text(_v if isinstance(_v,str) else json.dumps(_v),encoding='utf-8')

def on_hold():
 try:return bool(json.loads(HOLD.read_text(encoding='utf-8')).get('on')) if HOLD.exists() else False
 except Exception:return False

def check_hold():
 if on_hold():raise ValueError('On hold: you told me to wait. Say "resume" when the right WhatsApp is connected.')

def set_hold(on):
 """Hold = nothing is sent anywhere (no posts, DMs, alerts) and Auto is paused until the owner says resume."""
 on=bool(on);prev=json.loads(HOLD.read_text(encoding='utf-8')) if HOLD.exists() else {}
 if on and not prev.get('on'):
  was=auto_on();HOLD.write_text(json.dumps({'on':True,'was_auto':was,'since':time.time()}),encoding='utf-8')
  CAMPAIGN['stop']=True;cancel_jobs('Stopped by owner.')
  if was:AUTO.write_text(json.dumps({'on':False,'since':time.time()}));persist_file('autopilot',AUTO)
  persist_file('hold',HOLD);auto_log('ON HOLD: all sending stopped until you say resume.')
  return 'On hold. Nothing will be sent anywhere. Say "resume" when the right WhatsApp is connected.'
 if not on and prev.get('on'):
  HOLD.write_text(json.dumps({'on':False}),encoding='utf-8');persist_file('hold',HOLD)
  if prev.get('was_auto'):set_auto(True)
  auto_log('Hold released.')
  return 'Hold released.'+(' Auto is back on.' if prev.get('was_auto') else '')
 return 'Already on hold.' if on else 'Nothing was on hold.'

def auto_on():
 return bool(json.loads(AUTO.read_text()).get('on')) if AUTO.exists() else False

def set_auto(on):
 if on and not auto_on():ENGINE.activated()
 AUTO.write_text(json.dumps({'on':bool(on),'since':time.time()}));persist_file('autopilot',AUTO)
 auto_log('Autopilot turned '+('ON' if on else 'OFF')+'.');return ('Autopilot is on. I will post on schedule, watch replies, DM donor contacts carefully and message you on WhatsApp when I need you.'+('' if assistant.client() else ' (AI key not set yet, so I follow the fixed playbook only.)')) if on else 'Autopilot is off.'

def auto_log(text,quiet=False):
 AUTOLOG.append({'time':time.time(),'text':text,'q':quiet});del AUTOLOG[:-50]

def wa_ok():
 try:
  s=api('/devices/'+DEVICE+'/status').get('results',{});return bool(s.get('is_connected') and s.get('is_logged_in'))
 except Exception:return False

NEVER_GROUPS={'120363432572916292@g.us','120363431093838536@g.us'}  # 37-member GiveLife copy, Exclusive Upwork Course
GROUP_CHECK={'time':0,'missing':[],'checked':False}
NOT_MEMBER=re.compile(r"(?i)not participating|not in (the )?group|not-authorized|forbidden|item-not-found|failed to get group")

def my_groups():
 """Groups the linked WhatsApp number is in: [(jid, name, members)]."""
 out=[]
 for x in _items(api('/user/my/groups')):
  if not isinstance(x,dict):continue
  jid=str(x.get('JID') or x.get('jid') or x.get('id') or '')
  gn=x.get('GroupName');name=str((gn.get('Name') if isinstance(gn,dict) else '') or x.get('Name') or x.get('name') or x.get('subject') or '').strip()
  people=x.get('Participants') or x.get('participants') or []
  if jid.endswith('@g.us') and jid not in NEVER_GROUPS:out.append((jid,name,len(people) if isinstance(people,list) else 0))
 return out

def check_groups(force=False):
 """Make sure every saved group is one the linked number is in; fix a changed JID by its name."""
 if not force and time.time()-GROUP_CHECK['time']<600:return GROUP_CHECK
 GROUP_CHECK['time']=time.time()
 try:mine=my_groups()
 except Exception:return GROUP_CHECK
 if not mine:return GROUP_CHECK
 ids={j for j,_,_ in mine};missing=[];fixed={}
 for key,(name,jid) in list(GROUPS.items()):
  if jid in ids:continue
  same=[g for g in mine if g[1].strip().lower()==name.lower()]
  if same:
   best=max(same,key=lambda g:g[2])
   if key=='main' and best[2] and best[2]<80:missing.append(name);continue  # never fall back to a small copy of the main group
   GROUPS[key]=(name,best[0]);fixed[key]=best[0]
  else:missing.append(name)
 if fixed and STORE:STORE.put('group_jids',{k:GROUPS[k][1] for k in GROUPS})
 GROUP_CHECK.update(missing=missing,checked=True,fixed=list(fixed))
 return GROUP_CHECK

if STORE:
 for k,j in (STORE.get('group_jids') or {}).items():
  if k in GROUPS and j not in NEVER_GROUPS:GROUPS[k]=(GROUPS[k][0],j)

def studio_state():
 saved=STORE.get('last_sent',{}) if STORE else {}
 since={k:(round((time.time()-saved[v[1]])/60) if v[1] in saved else None) for k,v in GROUPS.items()}
 return {'left':read_left(),'whatsapp':wa_ok(),'minutes_since_post':since,'autopilot':auto_on()}

def start_group_job(key,caption):
 keys=list(GROUPS) if key=='all' else FREELANCE if key=='free' else [key]
 return start_send_job(keys,caption,manual=False)

def auto_post(target):
 caption=json.loads(DRAFT.read_text(encoding='utf-8')).get('group','')
 if not caption.strip() or not start_group_job(target,caption):auto_log('Autopilot skipped: another send is running.')


def _items(resp):
 r=resp.get('results',resp) if isinstance(resp,dict) else resp
 if isinstance(r,dict):r=r.get('data') or r.get('contacts') or r.get('chats') or []
 return r if isinstance(r,list) else []

def _norm_item(x):
 if not isinstance(x,dict):return None
 jid=str(x.get('jid') or x.get('chat_jid') or x.get('JID') or x.get('id') or '')
 name=str(x.get('name') or x.get('push_name') or x.get('display_name') or x.get('full_name') or x.get('first_name') or x.get('PushName') or x.get('FullName') or '').strip()
 return {'name':name or jid.split('@')[0],'id':jid,'group':jid.endswith('@g.us')} if jid else None

def find_data(query):
 q=str(query).strip().lower();words=[w for w in re.split(r'\s+',q) if w]
 if not words:return [],0
 found={};pool={};checked=0
 for path in ('/chats?limit=300&search='+urllib.parse.quote(q),'/chats?limit=100','/chats','/user/my/contacts'):
  try:items=_items(api(path))
  except Exception:continue
  checked+=len(items)
  for it in items:
   n=_norm_item(it)
   if not n or n['id'] in found:continue
   hay=(n['name']+' '+n['id'].split('@')[0]).lower();pool[n['id']]=n
   norm=re.sub(r'[^a-z0-9 ]','',hay)
   if all(w in hay or w in norm for w in words) or q in hay:found[n['id']]=n
 if not found and pool:
  import difflib
  for jid,n in pool.items():
   if difflib.SequenceMatcher(None,q,n['name'].lower()).ratio()>=0.62:found[jid]=n
 out=sorted(found.values(),key=lambda n:(n['group'],len(n['name'])))[:8]
 return out,checked

def find_contacts(query):
 out,checked=find_data(query)
 if not out:return f'No chat or contact matches "{query}" (checked {checked} chats and contacts). Tell the owner honestly and ask for the number.'
 return json.dumps(out,ensure_ascii=False)

SEND_LOCK2=threading.Lock();LAST_FREE_SEND=[0]

def send_free(to,text,with_picture,literal=False):
 check_hold()
 text=str(text).strip()
 if not text or len(text)>4000:raise ValueError('Message must be 1 to 4,000 characters.')
 if (manual_commands.control_payload(text) or (manual_commands.group(text) and re.search(r'(?i)\b(now|message|restart|gap|poster|send)\b',text))) and not literal:raise ValueError('That is a send instruction, not message text. Use send_appeal for the current group caption.')
 to=str(to).strip();key=manual_commands.group(to)
 if not wa_ok():raise ValueError('WhatsApp is not connected. Link it first.')
 if key:
  if key in ('all','free'):raise ValueError('Use the group appeal action for a broadcast.')
  target='120363431210327603@g.us' if key=='test' else GROUPS[key][1]
 elif to.endswith('@g.us'):
  if to not in [v[1] for v in GROUPS.values()] and to!='120363431210327603@g.us':raise ValueError('That group is not one of the foundation groups.')
  target=to
 elif to.endswith('@s.whatsapp.net'):target=to
 else:
  phone=norm_phone(to)
  if not phone:raise ValueError('That is not a valid group, contact id or phone number.')
  target=phone+'@s.whatsapp.net'
 with SEND_LOCK:
  check_hold()
  img=image_path(CHAT_IMAGE.get('id') or 'poster') if with_picture else None
  result=send_with_image(target,text,img)
 if result.get('code')!='SUCCESS':raise ValueError('Not confirmed: '+str(result.get('message',''))[:100]+' Check WhatsApp before retrying.')
 record_delivery(target,text,result)
 if target.endswith('@g.us'):
  LAST_LOCAL[target]=time.time()
  if STORE:
   saved=STORE.get('last_sent',{});saved[target]=time.time();STORE.put('last_sent',saved)
 remember_recipient(to if key else target.split('@')[0],target)
 remember_manual({'kind':'text','to':target,'text':text,'with_picture':bool(with_picture)})
 auto_log('Confirmed message sent to '+(GROUPS[key][0] if key in GROUPS else 'Givelife test' if key=='test' else '…'+target.split('@')[0][-4:]),True)
 return 'Sent.'

LAST_RECIPIENT={}
def remember_recipient(name,jid):
 LAST_RECIPIENT.clear();LAST_RECIPIENT.update(name=name,id=jid)
 try:RECIP.write_text(json.dumps(LAST_RECIPIENT),encoding='utf-8');persist_file('recipient',RECIP)
 except Exception:pass
try:
 if RECIP.exists():LAST_RECIPIENT.update(json.loads(RECIP.read_text(encoding='utf-8')))
except Exception:pass

def send_scheduled(target,text):
 t=str(target)
 keys=[k for k in GROUPS] if t=='all' else FREELANCE if t=='free' else [t] if t in GROUPS else None
 if keys:
  caption=text or json.loads(DRAFT.read_text(encoding='utf-8')).get('group','')
  if not start_keys_job(keys,caption):raise ValueError('another send is running')
  return
 send_free(t,text or json.loads(DRAFT.read_text(encoding='utf-8')).get('group',''),True)

def rule_from_text(text):
 import rules as R
 rule,msg=R.parse(text)
 return rule,msg

def send_appeal(target,request_id=None):
 t=manual_commands.group(str(target)) or str(target).strip().lower()
 keys=list(GROUPS) if t=='all' else FREELANCE if t=='free' else [t] if t in GROUPS or t=='test' else None
 if not keys:raise ValueError('Unknown group. GiveLife main is the main foundation group.')
 remember_manual({'kind':'appeal','target':t})
 if not wa_ok():raise ValueError('WhatsApp is not connected. Link it from the WhatsApp button, then send again.')
 caption=json.loads(DRAFT.read_text(encoding='utf-8')).get('group','')
 ident=start_send_job(keys,caption,manual=True,request_id=request_id)
 name='GiveLife main' if t=='main' else 'all 6 groups' if t=='all' else 'all 5 freelance groups' if t=='free' else 'Givelife test' if t=='test' else GROUPS[t][0]
 return {'reply':'Sending to '+name+' now. The automatic-post timer restarts after confirmation.','job_id':ident,'caption':caption}

def add_rule_text(text):
 if timed_tasks.requested(text):
  response=timed_chat_command(text)
  if response is not None:return response
 rule,msg=rule_from_text(text)
 if not rule:return 'That did not look like a rule.'
 ENGINE.add_rule(rule);return 'Rule added: '+msg

_TIMED=None
_TIMED_STORE=None
_TIMED_LOCK=threading.RLock()
def timed_scheduler():
 global _TIMED,_TIMED_STORE
 with _TIMED_LOCK:
  if _TIMED is None or _TIMED_STORE is not STORE:
   def dispatch(task):
    if task['action']=='resume':
     keys=[]
     for key in task['targets']:keys.extend(list(GROUPS) if key=='all' else FREELANCE if key=='free' else [key])
     if any(k not in GROUPS for k in keys):raise ValueError('Choose production groups to resume, or Auto for global resume.')
     for key in dict.fromkeys(keys):ENGINE.resume(key)
     set_hold(False)
     if not auto_on():set_auto(True)
     if on_hold() or not auto_on():raise ValueError('Resume was not fully confirmed.')
     return {'message':'Scheduled resume completed. Auto is ON; only named group pauses were lifted.'}
    if task['action']!='send':
     on=task['action']=='auto_on';reply=set_auto(on)
     if auto_on()!=on:raise ValueError('Auto mode could not be changed.')
     return {'message':reply}
    keys=[]
    for key in task['targets']:keys.extend(list(GROUPS) if key=='all' else FREELANCE if key=='free' else [key])
    keys=list(dict.fromkeys(keys))
    caption=task.get('text') or json.loads(DRAFT.read_text(encoding='utf-8'))['group']
    # A due scheduled send does not preempt the owner's current manual batch.
    with LOCK:
     if ACTIVE:raise ValueError('Another batch started. Check activity before rescheduling.')
     ident=start_send_job(keys,caption,manual=True,request_id='schedule-'+task['id']+'-'+str(int(task['due'])))
    return {'job_id':ident,'expected':len(keys)}
   def ready(task):
    if task['action'] in ('auto_off','resume'):return True
    if on_hold():return False
    return task['action']!='send' or (not ACTIVE and wa_ok())
   def cancel(ident):
    event=JOB_CANCEL.get(ident)
    if event:event.set()
   _TIMED=timed_tasks.Scheduler(DATA/'timed-tasks.json',STORE,dispatch,get_job,ready,cancel);_TIMED_STORE=STORE
  return _TIMED

def timed_chat_command(text,request_id=None):
 if not fast_command_eligible(text):return None
 if timed_tasks.parse(text) is None:return None
 return timed_scheduler().command(text,request_id)

def timed_loop():
 while True:
  try:timed_scheduler().tick()
  except Exception:
   auto_log('Timed scheduler could not read or save its records. No automatic retry of dispatched actions.');time.sleep(60)
  time.sleep(1)

CHAT_IMAGE={}
def base_chat_callbacks():
 def came(amount):
  nl=max(0,read_left()-int(amount));set_left(nl);return f'Rs. {int(amount):,} came. Rs. {nl:,} left.'
 return {'set_left':lambda left:(set_left(int(left)),f'Rs. {int(left):,} left. Messages updated.')[1],
  'money_came':came,
  'new_wording':lambda kind:(next_message() if kind=='group' else next_dm(),'New '+kind+' wording ready.')[1],
  'set_message':lambda kind,text:(save_draft(kind,text),'Message replaced.')[1],
  'remember':mem_add,'autopilot':set_auto,**engine_do(),
  'find_contact':find_contacts,'search_memory':lambda query:KNOWLEDGE.retrieve(query),'send_message':send_free,'send_dm_appeal':send_dm_appeal,'edit_dm_name':edit_dm_name,'delete_last_message':delete_last_group,'prepare_dm':prepare_dm,
  'send_appeal':lambda target:send_appeal(target),
  'recent_activity':lambda:send_status_text()+'\nRecent activity: '+(' | '.join(x['text'] for x in AUTOLOG[-4:]) or 'No new receipt this session.'),
  'add_rule':lambda text:add_rule_text(text),'schedule_task':lambda:None,'list_schedules':lambda:timed_scheduler().list(),
  'list_rules':lambda:'; '.join(f"#{r['id']} {r['text']}" for r in ENGINE.rule_list()) or 'No rules yet.',
  'delete_rule':lambda rule_id:('Rule removed.' if ENGINE.delete_rule(rule_id) else 'No such rule.'),
  'hold':set_hold,'dm_donors':lambda count=10:dm_batch_now('donors',count),'dm_group':lambda group,count=10:dm_batch_now('group',count,group),
  'dm_list':lambda people,gap_minutes,vary,start_after_minutes:start_campaign({'people':people,'gap_seconds':float(gap_minutes)*60,'vary':vary,'start_after_seconds':float(start_after_minutes)*60,'image':CHAT_IMAGE.get('id') or 'poster'})}


import autopilot, learning as learning_mod, random as _random
OWNER_PHONE=os.environ.get('OWNER_PHONE','923205069925')

@serialized_send
def send_text(jid,text):
 check_hold()
 req=urllib.request.Request(GOWA_URL+'/send/message',data=json.dumps({'phone':jid,'message':text}).encode(),headers={'X-Device-Id':DEVICE,'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)

def last_sent_by_key():
 saved=dict(LAST_LOCAL)
 if STORE:
  for jid,stamp in STORE.get('last_sent',{}).items():saved[jid]=max(saved.get(jid,0),stamp)
 return {k:saved.get(v[1]) for k,v in GROUPS.items()}

LAST_JOB={}
def last_results():
 j=JOBS.get(LAST_JOB.get('id'))
 if not j or not j.get('done'):return []
 names={v[0]:k for k,v in GROUPS.items()}
 return [(names.get(r.get('group'),r.get('group')),r.get('code'),str(r.get('message',''))) for r in j['results']]

def start_keys_job(keys,caption,queue=False):
 return bool(start_send_job([k for k in GROUPS if k in keys],caption,manual=False))

def group_messages(jid):
 return api('/chat/'+urllib.parse.quote(jid,safe='')+'/messages?limit=20').get('results',{}).get('data',[]) or []

def already_dmed(digest):
 return digest in BLOCKED or bool(STORE and (STORE.get('dm_recipient_'+digest) or STORE.get('optout_'+digest)))

FEMALE=set('ayesha aisha fatima zainab maryam mariam laiba sana hira iqra amna sawaira yusra areeba mahnoor noor kiran sadia saba rabia hina nida mehwish sidra anam anum bushra khadija asma uzma sara sarah zoya alina hajra dania rimsha mehak esha ifra aleena maham momina tehreem eman iman aiman kinza fiza javeria sobia shazia nadia farah rida ramsha warda wajeeha hafsa sumaira tayyaba uswa zara zahra nimra minahil bisma'.split())
NOT_NAME=re.compile(r'(?i)\b(web|develop|graphic|entrepreneur|official|store|shop|studio|agency|design|market|services?|tech|digital|freelanc|admin|group|team|seo|business|donor|member|upwork|fiverr)')
PERSONAL=re.compile(r"(?i)(wife|wifey|\bmom\b|\bmum\b|mother|\bdad\b|father|baba|papa|\babu\b|abbu|ammi|amma|family|bhai|\bbro\b|\bsis\b|baji|uncle|aunt|chacha|mama|khala|dada|nani|nana|\bhome\b|\blove\b|jaan|janu|honey|dear|hubby|husband|\bson\b|daughter|boss|jr account)|[\u2764\U0001F495\U0001F60D\U0001F496\U0001F48B]")

def clean_first_name(name):
 if not name or NOT_NAME.search(name):return ''
 return dm_composer.first_name(name)

def dm_text(name,tier='member'):
 left=read_left();first=clean_first_name(re.sub(r'(?i)\bdonors?\b','',str(name or '')).strip());who=(first+' ' if first else '')+('Sister' if first.lower() in FEMALE else 'Brother')
 acct='📲 *03097458815* — Easypaisa / JazzCash\nWajdan Khan (GiveLife Foundation account)'
 if tier=='repeat':return f'{who}, JazakAllah for helping Yousuf before. 🤲\n\nRs. {left:,} is still needed for his treatment. Could you help once more, or share his poster with family and friends today?\n\n{acct}'
 if tier=='reminder':return f'{who}, a gentle reminder about Yousuf. 🤲\n\nRs. {left:,} is still needed for his treatment. If you have already sent it, JazakAllah. If not, whenever you can:\n\n{acct}\n\nReply *Done* after you donate.'
 sel=[_random.randrange(len(a)) for a in DP];t=build_dm(sel,left)
 return t.replace('Brother, ',who+', ',1)

def send_dm(phone,text,digest):
 if STORE:STORE.put('dm_recipient_'+digest,{'state':'uncertain','time':time.time()})
 r=send_image(phone,text)
 if STORE:STORE.put('dm_recipient_'+digest,{'state':r.get('code','UNCERTAIN'),'time':time.time()})
 return r


ATT=DATA/'attachments';ATT.mkdir(exist_ok=True)
if STORE:
 _p=STORE.get('poster_b64')
 if _p:(DATA/'poster.jpg').write_bytes(base64.b64decode(_p))
CAMPAIGN={'running':False,'stop':False,'total':0,'sent':0,'failed':0,'skipped':0,'next_at':0,'current':'','log':[],'id':None}

def save_upload(data_url,use):
 if use=='papers':return 'papers-'+str(save_papers(data_url))
 raw=base64.b64decode(data_url.split(',',1)[-1])
 if len(raw)>8_000_000:raise ValueError('Picture is too big (max 8 MB).')
 if use=='poster':
  (DATA/'poster.jpg').write_bytes(raw)
  if STORE:STORE.put('poster_b64',base64.b64encode(raw).decode())
  return 'poster'
 aid=uuid.uuid4().hex[:12];(ATT/(aid+'.jpg')).write_bytes(raw);return aid

def image_path(image):
 if image in (None,'','none'):return None
 if image=='poster':return DATA/'poster.jpg'
 p=ATT/(re.sub(r'[^a-f0-9]','',str(image))+'.jpg');return p if p.exists() else DATA/'poster.jpg'

@serialized_send
def send_with_image(jid,caption,img):
 check_hold()
 if img is None:
  req=urllib.request.Request(GOWA_URL+'/send/message',data=json.dumps({'phone':jid,'message':caption}).encode(),headers={'X-Device-Id':DEVICE,'Content-Type':'application/json'},method='POST')
  with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)
 cap=DATA/('caption-'+uuid.uuid4().hex+'.txt');cap.write_text(caption,encoding='utf-8')
 r=subprocess.run(['curl','-s','--max-time','60','-X','POST',GOWA_URL+'/send/image','-H',f'X-Device-Id: {DEVICE}','-F',f'phone={jid}','-F',f'image=@{img};type=image/jpeg','-F',f'caption=<{cap}','-F','compress=false'],capture_output=True)
 cap.unlink(missing_ok=True)
 try:return json.loads(r.stdout)
 except Exception:return {'code':'ERROR','message':'Send not confirmed. Check WhatsApp before retrying.'}

def norm_phone(p):
 p=re.sub(r'[\s()+-]','',str(p))
 if p.startswith('00'):p=p[2:]
 if re.fullmatch(r'03\d{9}',p):p='92'+p[1:]
 return p if re.fullmatch(r'[1-9]\d{7,14}',p) else ''

def greet_text(text,name,gender):
 return dm_composer.personalize(text,clean_first_name(name),gender)

def dm_campaign(people,gap,image,vary,message,start_after,rest_every,rest_minutes):
 c=CAMPAIGN;c.update(running=True,stop=False,total=len(people),sent=0,failed=0,skipped=0,log=[],current='')
 try:
  if start_after>0:
   c['next_at']=time.time()+start_after;c['current']=f'Starting in {round(start_after/60,1)} min'
   while time.time()<c['next_at']:
    if c['stop']:return
    time.sleep(2)
  img=image_path(image)
  for i,p in enumerate(people):
   if c['stop']:c['log'].append('Stopped by owner.');return
   phone=norm_phone(p.get('phone',''));name=str(p.get('name','') or '').strip()[:30];gender=p.get('gender','Brother')
   if not phone:c['skipped']+=1;continue
   digest=hashlib.sha256((phone+'@s.whatsapp.net').encode()).hexdigest()
   if digest in BLOCKED or (STORE and STORE.get('optout_'+digest)):c['skipped']+=1;c['log'].append(f'Skipped …{phone[-4:]} (asked not to be messaged)');continue
   if STORE and STORE.get('dm_recipient_'+digest) and not p.get('again'):c['skipped']+=1;c['log'].append(f'Skipped …{phone[-4:]} (already messaged)');continue
   if not wa_ok():c['log'].append('WhatsApp disconnected. Stopped.');return
   base=dm_text(name,p['tier']) if p.get('tier') else (build_dm([_random.randrange(len(a)) for a in DP],read_left()) if (vary or not message) else message)
   text=greet_text(base,name,gender);c['current']=f'Sending to {(name+" ") if name else ""}{gender} …{phone[-4:]}'
   if STORE:STORE.put('dm_recipient_'+digest,{'state':'uncertain','time':time.time()})
   r=send_with_image(phone,text,img)
   if STORE:STORE.put('dm_recipient_'+digest,{'state':r.get('code','UNCERTAIN'),'time':time.time()})
   if r.get('code')!='SUCCESS':
    c['failed']+=1;c['log'].append(f'Failed …{phone[-4:]}: {str(r.get("message",""))[:80]}. Stopped to protect your number.');return
   c['sent']+=1;note_dm(phone);c['log'].append(f'✓ {(name+" ") if name else ""}{gender} …{phone[-4:]}')
   if i<len(people)-1:
    wait=_random.uniform(gap,gap*1.25)
    if rest_every and c['sent']%rest_every==0:wait=max(wait,rest_minutes*60);c['log'].append(f'Resting {rest_minutes} min after {c["sent"]} messages')
    c['next_at']=time.time()+wait;c['current']='Waiting'
    while time.time()<c['next_at']:
     if c['stop']:c['log'].append('Stopped by owner.');return
     time.sleep(2)
 finally:
  c['running']=False;c['current']='';c['next_at']=0
  auto_log(f'DM list finished: {c["sent"]} sent, {c["skipped"]} skipped, {c["failed"]} failed.')

def start_campaign(body):
 if CAMPAIGN['running']:raise ValueError('A DM list is already sending. Stop it first or wait.')
 people=[p for p in body.get('people',[]) if isinstance(p,dict)][:300]
 if not people:raise ValueError('No phone numbers found.')
 gap=max(45.0,float(body.get('gap_seconds',90)))
 args=(people,gap,body.get('image','poster'),bool(body.get('vary',True)),str(body.get('message','') or ''),max(0.0,float(body.get('start_after_seconds',0))),int(body.get('rest_every',10)),float(body.get('rest_minutes',10)))
 threading.Thread(target=dm_campaign,args=args,daemon=True).start()
 return f'Sending to {len(people)} people, about {round(gap/60,1)} min apart'+(f', starting in {round(args[5]/60,1)} min' if args[5] else '')+'.'


PAPERS=DATA/'papers';PAPERS.mkdir(exist_ok=True)
if STORE:
 for _i,_b in enumerate(STORE.get('papers_b64',[]) or []):(PAPERS/f'paper-{_i}.jpg').write_bytes(base64.b64decode(_b))
RECENT_LOCAL=[]

def thank_text():
 return ('JazakAllah 🤲 May Allah reward you and your family.\n\n'
  "One more favour: please share Yousuf's poster on your WhatsApp status and in your family groups. "
  'Every share reaches someone who can help.\n- GiveLife Foundation')

def share_text():
 left=read_left()
 return (f"*Rs. {left:,} is still left for Yousuf.* 💔\n\nIf you cannot donate right now, you can still help: "
  "*share this poster on your WhatsApp status* and send it to 3 friends today. Sharing costs nothing and reaches new donors. 🤲\n\n"
  "*03097458815*\nEasypaisa / JazzCash (Wajdan Khan)\n- GiveLife Foundation")

def done_text():
 return ('Alhamdulillah. The amount for Yousuf\'s treatment is complete. 🤲\n\n'
  'JazakAllah to everyone who donated, shared and prayed. May Allah reward you all.\n- GiveLife Foundation')

def sender_phone(m):
 j=str(m.get('sender_jid') or m.get('sender') or '')
 p=j.split('@')[0].split(':')[0]
 return p if j.endswith('@s.whatsapp.net') and p.isdigit() else ''

def has_papers():
 return any(PAPERS.glob('*.jpg'))

def send_papers(phone):
 files=sorted(PAPERS.glob('*.jpg'))[:6]
 if not files:return False
 for i,f in enumerate(files):
  send_with_image(phone+'@s.whatsapp.net','Medical papers for Yousuf (GiveLife Foundation).' if i==0 else '',f);time.sleep(3)
 return True

def save_papers(data_url):
 raw=base64.b64decode(data_url.split(',',1)[-1]);n=len(list(PAPERS.glob('*.jpg')))
 (PAPERS/f'paper-{n}.jpg').write_bytes(raw)
 if STORE:
  saved=STORE.get('papers_b64',[]) or [];saved.append(base64.b64encode(raw).decode());STORE.put('papers_b64',saved[-6:])
 return n+1

def note_dm(phone):
 item=[phone,time.time()]
 if STORE:
  r=[x for x in (STORE.get('recent_dms',[]) or []) if time.time()-x[1]<7*86400 and x[0]!=phone];r.append(item);STORE.put('recent_dms',r[-300:])
 else:RECENT_LOCAL.append(item);del RECENT_LOCAL[:-300]

def recent_dms():
 r=(STORE.get('recent_dms',[]) if STORE else RECENT_LOCAL) or []
 return [(p,t) for p,t in r if time.time()-t<7*86400][-60:]

def optout(phone):
 d=hashlib.sha256((phone+'@s.whatsapp.net').encode()).hexdigest()
 if STORE:STORE.put('optout_'+d,True)
 BLOCKED.add(d)

def post_text_all(text):
 def run():
  for k,(name,jid) in GROUPS.items():
   try:send_text(jid,text)
   except Exception:pass
   time.sleep(60)
 threading.Thread(target=run,daemon=True).start()

def variant_pool():
 return 'a' if 0<read_left()<=10000 else 'n'

def variant_count():
 return len(ALMOST) if variant_pool()=='a' else len(HOOKS)

def caption_variant(i):
 return build_group(int(i),read_left())

def variant_names():
 names={i:h[0].replace('{P2}','N')[:48] for i,h in enumerate(HOOKS)}
 names.update({100+i:a[0].replace('{L}','X').replace('{P2}','N')[:48] for i,a in enumerate(ALMOST)})
 return names

def goal_value():
 m=re.search(r'^GOAL:\s*(\d+)',(DATA/'state.md').read_text(encoding='utf-8-sig'),re.M);return int(m[1]) if m else 0

def update_text(came,left):
 """U1-STRESS from the message bank: money came, but no celebration."""
 p2=math.ceil(left/2000)
 return (f'🔴 *Rs. {came:,} came in. It is NOT enough.*\n\n⚠️ Fluid in Yousuf\'s brain *can still paralyse his body and damage his eyesight.* Both his kidneys are still badly swollen.\n\n'
  f'💰 *Rs. {left:,} still LEFT*\n*{p2} people x Rs. 2,000 — he needs you now*\n\n*03097458815*\nEasypaisa / JazzCash (Wajdan Khan)\nReply *Done* after you donate.\n- GiveLife Foundation')

def milestone_text(raised,left):
 p2,p1=math.ceil(left/2000),math.ceil(left/1000)
 return (f'*Rs. {raised:,} has been raised for Yousuf. Rs. {left:,} is still missing.* 💔\n\n*_{p2} people donating Rs. 2,000_*\n*_OR {p1} people donating Rs. 1,000_* 🤲\n\n'
  '*03097458815*\nEasypaisa / JazzCash (Wajdan Khan)\n\nReply *Done* after you donate.\n- GiveLife Foundation')

def job_message():
 j=JOBS.get(ACTIVE) if ACTIVE else None
 return j.get('message','') if j else ''

def recent_chats():
 out=[]
 try:items=_items(api('/chats?limit=60'))
 except Exception:return out
 for it in items:
  n=_norm_item(it)
  if n and not n['group'] and n['id'].endswith('@s.whatsapp.net'):
   phone=n['id'].split('@')[0]
   if phone!=OWNER_PHONE and not PERSONAL.search(n['name']):out.append((phone,n['name']))
 return out[:40]

def group_members(key='main'):
 jid=GROUPS[key][1]
 if jid in NEVER_GROUPS:return []
 try:data=api('/group/participants?group_id='+urllib.parse.quote(jid,safe='')).get('results',{})
 except Exception:return []
 out=[]
 for p in (data.get('participants',[]) if isinstance(data,dict) else []):
  phone=str(p.get('phone_number') or '');name=str(p.get('display_name') or '')
  if phone.isdigit() and phone!=OWNER_PHONE and not PERSONAL.search(name):out.append((phone,name))
 return out

DONOR_WORD=re.compile(r'(?i)\bdonors?\b')
def donor_contacts():
 """Existing donors: people saved in his phone with "donor" in the name, plus group members labelled donor."""
 out=[];seen=set()
 try:items=_items(api('/user/my/contacts'))
 except Exception:items=[]
 for it in items:
  n=_norm_item(it)
  if n and n['id'].endswith('@s.whatsapp.net') and DONOR_WORD.search(n['name']) and not PERSONAL.search(n['name']):
   phone=n['id'].split('@')[0]
   if phone!=OWNER_PHONE and phone not in seen:seen.add(phone);out.append((phone,n['name']))
 for phone,name in group_members('main'):
  if DONOR_WORD.search(name) and phone not in seen:seen.add(phone);out.append((phone,name))
 return out

def _batch_people(pairs,tier,count):
 """Turn (phone,name) pairs into campaign people, skipping anyone who opted out or was messaged in the last 3 days."""
 people=[]
 for phone,name in pairs:
  if len(people)>=count:break
  d=hashlib.sha256((phone+'@s.whatsapp.net').encode()).hexdigest()
  if d in BLOCKED or (STORE and STORE.get('optout_'+d)):continue
  rec=STORE.get('dm_recipient_'+d) if STORE else None
  again=False
  if rec:
   if tier=='repeat' and time.time()-float(rec.get('time',0))>3*86400:again=True
   else:continue
  first=clean_first_name(DONOR_WORD.sub('',str(name or '')).strip())
  people.append({'phone':phone,'name':first,'gender':'Sister' if first.lower() in FEMALE else 'Brother','tier':tier,'again':again})
 return people

def dm_batch_now(kind,count=10,group='main'):
 count=max(1,min(int(count or 10),50))
 if kind=='donors':
  pairs=donor_contacts()+learning_mod.repeat_donors(ENGINE.L)
  pairs=list({p:(p,n) for p,n in pairs}.values());label='existing donors';tier='repeat'
  if not pairs:return 'I found no contacts saved with "donor" in the name yet. Save donors like "Ali Donor" in your phone, or send me a list of numbers.'
 else:
  if group not in GROUPS:raise ValueError('Unknown group.')
  pairs=group_members(group);_random.shuffle(pairs);label='members of '+GROUPS[group][0];tier='member'
  if not pairs:return 'I could not read the members of '+GROUPS[group][0]+'. Check the linked WhatsApp number is in that group.'
 people=_batch_people(pairs,tier,count)
 if not people:return f'Everyone I found in {label} was already messaged recently or asked not to be.'
 msg=start_campaign({'people':people,'gap_seconds':100,'vary':True,'image':'poster','rest_every':10,'rest_minutes':10})
 return f'DMs to {len(people)} {label}. '+msg

def outreach(caps):
 """Who to DM next, best first: past donors, donor-labelled contacts, group members, saved chats."""
 picked=[];seen=set()
 def add(tier,people):
  n=0
  for phone,name in people:
   if n>=caps.get(tier,0) or phone in seen:continue
   d=hashlib.sha256((phone+'@s.whatsapp.net').encode()).hexdigest()
   if d in BLOCKED or (STORE and STORE.get('optout_'+d)):continue
   if tier!='repeat' and already_dmed(d):continue
   seen.add(phone);picked.append((phone,name,tier));n+=1
 add('repeat',learning_mod.repeat_donors(ENGINE.L))
 members=group_members();_random.shuffle(members)
 add('donor',donor_contacts())
 add('member',[(p,n) for p,n in members if not DONOR_WORD.search(n)])
 chats=recent_chats();_random.shuffle(chats);add('saved',chats)
 return picked

def ai_test():
 key=assistant.client()
 if not key:return {'ok':False,'error':'No DeepSeek key yet. Add DEEPSEEK_API_KEY in Render, then deploy.'}
 t0=time.time()
 try:text,_=assistant._call(key,'Reply with one word only.',[],[{'role':'user','content':'Reply with exactly: OK'}])
 except Exception as e:
  m=str(e);hint=' The key looks wrong or revoked.' if '401' in m or '403' in m else ' The DeepSeek balance may be empty.' if '402' in m else ' Check the internet or try again.'
  return {'ok':False,'error':m[:120]+hint}
 return {'ok':True,'ms':round((time.time()-t0)*1000),'reply':text[:40]}

ENGINE=autopilot.Engine({'DATA':DATA,'store_get':lambda k:STORE.get(k) if STORE else None,'persist':persist_file,'log':auto_log,
 'send_text':send_text,'owner_jid':lambda:OWNER_PHONE+'@s.whatsapp.net','enabled':auto_on,'read_left':read_left,'wa_ok':wa_ok,
 'busy':lambda:ACTIVE is not None,'last_sent':last_sent_by_key,'groups':lambda:list(GROUPS),'group_jids':lambda:{k:v[1] for k,v in GROUPS.items()},
 'caption':lambda:json.loads(DRAFT.read_text(encoding='utf-8')).get('group',''),'start_job':start_keys_job,'last_results':last_results,'messages':group_messages,
 'poster_left':poster_left,'sender_phone':sender_phone,'send_papers':send_papers,'has_papers':has_papers,'thank_text':thank_text,'share_text':share_text,'done_text':done_text,'post_text_all':post_text_all,'recent_dms':recent_dms,'note_dm':note_dm,'optout':optout,'send_scheduled':send_scheduled,'donor_answer':lambda q:assistant.donor_reply(q,read_left()),'already_dmed':already_dmed,'dm_text':dm_text,'send_dm':send_dm,'caption_variant':caption_variant,'variant_count':variant_count,'variant_pool':variant_pool,'variant_names':variant_names,'goal':goal_value,'milestone_text':milestone_text,'update_text':update_text,'wa_reconnect':lambda:api('/app/reconnect'),'on_hold':on_hold,'dm_busy':lambda:bool(CAMPAIGN.get('running')),'job_message':job_message,'recent_chats':recent_chats,'outreach':outreach})

def engine_do(auto_review=False):
 return {'set_pace':lambda main_minutes,freelance_minutes:ENGINE.set_pace(main_minutes,freelance_minutes),'pause_group':lambda key,hours:ENGINE.pause(key,hours),'resume_group':lambda key:ENGINE.resume(key),
  'set_group_pace':lambda target,minutes:set_group_pace(target,minutes),
  'set_quiet_hours':lambda start,end:ENGINE.set_quiet(start,end),'set_dms':lambda enabled,daily:('DMs remain off by the owner instruction.' if auto_review and enabled and not ENGINE.s.get('dm_enabled') else ENGINE.set_dms(enabled,daily)),
  'notify_owner':lambda text:(ENGINE.notify('ai-'+str(int(time.time())),text,0),'Owner told.')[1]}

PILOT=assistant.Autopilot(lambda:{**studio_state(),'autopilot':ENGINE.summary()},mem_get,lambda:engine_do(True),auto_log,auto_on)

MANUAL_STATE=DATA/'manual-context.json'
LAST_MANUAL=mapping(STORE.get('manual_context',{})) if STORE else {}
if not LAST_MANUAL and MANUAL_STATE.exists():
 try:LAST_MANUAL=mapping(MANUAL_STATE.read_text(encoding='utf-8'))
 except Exception:LAST_MANUAL={}
DELIVERIES=mapping(STORE.get('last_deliveries',{})) if STORE else {}
DM_NAMES=mapping(STORE.get('dm_names',{})) if STORE else {}
CONTACT_CONTEXT={}
if not LAST_MANUAL:
 for old in reversed(chat_get(300)):
  if old.get('who')!='you':continue
  plan=manual_commands.parse(old.get('text','')) or {}
  if plan.get('kind') in ('appeal','select'):
   LAST_MANUAL.update(kind='appeal',target=plan['target']);break

def remember_manual(value):
 global LAST_MANUAL
 value=mapping(value);LAST_MANUAL=dict(value)
 MANUAL_STATE.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
 if STORE:STORE.put('manual_context',dict(value))

def record_delivery(jid,text,result):
 if result.get('code')!='SUCCESS':return
 ident=result.get('results',{}).get('message_id')
 DELIVERIES[jid]={'message_id':ident,'text':text,'time':time.time()}
 if STORE:STORE.put('last_deliveries',DELIVERIES)

def resolve_person(to):
 key=manual_commands.group(to)
 if key:return key
 if norm_phone(to) or str(to).endswith(('@s.whatsapp.net','@g.us')):return str(to)
 found,checked=find_data(to)
 for item in found:CONTACT_CONTEXT[item['id']]=item
 exact=[x for x in found if x['name'].casefold()==str(to).casefold()]
 if len(exact)==1:return exact[0]['id']
 if len(found)==1:return found[0]['id']
 if not found:raise ValueError('No matching contact. Give the phone number.')
 KNOWLEDGE.data['pending']={'kind':'recipient','query':str(to),'candidates':found[:8],'created':time.time()};KNOWLEDGE.save()
 raise ValueError('More than one contact matches: '+', '.join(x['name']+' (…'+x['id'].split('@')[0][-4:]+')' for x in found[:4])+'. Give the full name or last four digits.')

def dm_recipient(to=None):
 target=resolve_person(to) if to else LAST_MANUAL.get('to')
 if not target or target in GROUPS or target in ('all','free','test') or str(target).endswith('@g.us'):
  raise ValueError('Which person should receive the DM? Give their contact name or number.')
 phone=norm_phone(str(target).split('@')[0])
 if not phone:raise ValueError('That is not a valid DM number.')
 return phone+'@s.whatsapp.net'

def current_dm_caption(name='',gender='Brother'):
 text=json.loads(DRAFT.read_text(encoding='utf-8')).get('dm','')
 # Repair old incomplete/flattened model output, keeping the structured saved draft otherwise.
 if not dm_composer.complete(text):text=build_dm(dm_selection(False),read_left())
 text=greet_text(text,name,gender)
 if not dm_composer.complete(text):raise ValueError('The full DM caption is incomplete. Nothing was sent.')
 return text

def edit_dm_name(name,to=''):
 jid=dm_recipient(to);first=clean_first_name(name)
 gender='Sister' if first.lower() in FEMALE else 'Brother'
 DM_NAMES[jid]={'name':first,'gender':gender}
 if STORE:STORE.put('dm_names',DM_NAMES)
 caption=current_dm_caption(first,gender)
 save_draft('dm',caption)
 remember_manual({'kind':'dm_appeal','to':jid,'name':first,'gender':gender,'text':caption,'with_picture':True})
 return 'Greeting changed to '+dm_composer.greeting(first,gender)+'. The full DM and the same recipient are kept. Nothing was sent.'

def send_dm_appeal(to='',name='',gender='Brother'):
 jid=dm_recipient(to)
 identity=DM_NAMES.get(jid) or {}
 first=identity.get('name') if identity else clean_first_name(name or CONTACT_CONTEXT.get(jid,{}).get('name',''))
 gender=identity.get('gender') if identity else ('Sister' if first.lower() in FEMALE or (first and gender=='Sister') else 'Brother')
 caption=current_dm_caption(first,gender)
 send_free(jid,caption,True)
 remember_manual({'kind':'dm_appeal','to':jid,'name':first,'gender':gender,'text':caption,'with_picture':True})
 return 'WhatsApp confirmed the full DM with poster to '+dm_composer.greeting(first,gender)+'.'

def prepare_dm(phone,name='',gender='Brother'):
 phone=norm_phone(phone)
 if not phone:raise ValueError('Provide a valid phone number before preparing the DM.')
 name=clean_first_name(name);gender='Sister' if name and gender=='Sister' else 'Brother'
 save_draft('dm',current_dm_caption(name,gender))
 return {'reply':'Full DM prepared for '+dm_composer.greeting(name,gender)+'. Nothing was sent.', 'actions':[{'type':'prepare_dm','phone':phone,'name':name,'gender':gender}]}

def delete_last_group(target=None):
 key=manual_commands.group(target or '') or (LAST_MANUAL.get('target') if LAST_MANUAL.get('kind')=='appeal' else None)
 if key not in GROUPS and key!='test':raise ValueError('Which group? Name the group whose last sent message should be deleted.')
 jid='120363431210327603@g.us' if key=='test' else GROUPS[key][1]
 entry=DELIVERIES.get(jid,{})
 ident=entry.get('message_id')
 if not ident:
  own=[m for m in group_messages(jid) if m.get('is_from_me') and m.get('id')]
  own.sort(key=lambda m:str(m.get('timestamp','')),reverse=True)
  if own:ident=own[0]['id']
 if not ident:raise ValueError('I cannot identify an own sent message in that group. No message was deleted.')
 check_hold()
 req=urllib.request.Request(GOWA_URL+'/message/'+urllib.parse.quote(str(ident),safe='')+'/revoke',data=json.dumps({'phone':jid}).encode(),headers={'X-Device-Id':DEVICE,'Content-Type':'application/json'},method='POST')
 try:
  with WIRE_LOCK:
   check_hold()
   revision=getattr(OWNER_GUARD,'revision',None)
   if revision is not None and revision!=OWNER_REVISION:raise ValueError('Superseded by a newer instruction.')
   with urllib.request.urlopen(req,timeout=20) as response:result=json.load(response)
 except Exception:raise ValueError('WhatsApp did not confirm deletion. Check the group on your phone.') from None
 if result.get('code')!='SUCCESS':raise ValueError('WhatsApp refused deletion. Check the message on your phone.')
 DELIVERIES.pop(jid,None)
 if STORE:STORE.put('last_deliveries',DELIVERIES)
 return 'WhatsApp confirmed deletion of the last own message in '+('Givelife test' if key=='test' else GROUPS[key][0])+'.'

def chat_callbacks(prompt='',revision=None,task_id=None):
 callbacks=base_chat_callbacks();cache={};verified=set();owner=chat_policy.intent(prompt)
 sending=owner['send'];dm_allowed=owner['batch']
 send_tools={'send_message','send_appeal','send_dm_appeal','dm_list','dm_donors','dm_group'}
 read_tools=chat_policy.READ
 def allowed_groups():
  keys=set(manual_commands.groups(chat_policy.owner_text(prompt)))
  if not keys:
   if LAST_MANUAL.get('kind')=='appeal':keys.add(LAST_MANUAL.get('target'))
   elif LAST_MANUAL.get('kind')=='appeals':keys.update(LAST_MANUAL.get('targets',[]))
   else:keys.update(k for k,v in GROUPS.items() if v[1]==LAST_MANUAL.get('to'))
   if LAST_MANUAL.get('to')=='120363431210327603@g.us':keys.add('test')
  keys.update(k for k,v in GROUPS.items() if v[1] in verified or v[1] in prompt)
  if 'all' in keys:keys.update(GROUPS)
  if 'free' in keys:keys.update(FREELANCE)
  return keys
 def wrapped(name,fn):
  def call(**args):
   if revision is not None and revision!=OWNER_REVISION and name not in read_tools:raise ValueError('Superseded by your newer instruction. No old action was sent.')
   if not chat_policy.permitted(name,prompt):
    if name in send_tools and not sending:raise ValueError('The current instruction does not ask to send. Nothing was sent.')
    if name in ('dm_list','dm_donors','dm_group'):raise ValueError('The current instruction does not authorize DMs. Nothing was sent.')
    raise ValueError('The current instruction does not authorize '+name+'. Nothing was changed or sent.')
   if name in send_tools and not sending:raise ValueError('The current instruction does not ask to send. Nothing was sent.')
   if name in ('dm_list','dm_donors','dm_group') and not dm_allowed:raise ValueError('The current instruction does not authorize DMs. Nothing was sent.')
   if name=='delete_last_message' and (not re.search(r'(?i)\b(delete|remove|revoke)\b',prompt) or re.search(r"(?i)\b(don'?t|do not|never)\b.*\b(delete|remove|revoke)\b",prompt)):raise ValueError('No deletion was requested. Nothing was deleted.')
   if name=='remember' and not re.search(r'(?i)\b(always|never|remember|from now|in future|yaad rakho)\b',prompt):raise ValueError('This is a current edit, not a request to save a future preference.')
   if name=='set_dms' and args.get('enabled') and not re.search(r'(?i)\b(dm|dms)\b.*\b(on|enable|start)\b|\b(enable|start)\b.*\b(dm|dms)\b',prompt):raise ValueError('DMs cannot be enabled without your current instruction.')
   if name=='autopilot' and not re.search(r'(?i)\b(auto|autopilot)\b',prompt):raise ValueError('This request does not change Auto mode.')
   if name=='dm_list':
    explicit={norm_phone(x) for x in re.findall(r'(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}',chat_policy.owner_text(prompt))}
    if any(norm_phone(p.get('phone','')) not in explicit and norm_phone(p.get('phone',''))+'@s.whatsapp.net' not in verified for p in args.get('people',[])):raise ValueError('Every DM-list recipient must come from this owner instruction or a verified lookup.')
   if name in ('set_left','money_came'):
    plans=chat_policy.financial_plans(prompt)
    expected=[p.get('amount') for p in plans if (p.get('kind')=='money')==(name=='money_came')]
    if args.get('left' if name=='set_left' else 'amount') not in expected:raise ValueError('That amount does not match the current owner instruction. No money was changed.')
   if name in ('send_message','send_dm_appeal','prepare_dm'):
    dest=str(args.get('to') or args.get('phone') or '')
    group_key=manual_commands.group(dest)
    requested=manual_commands.groups(chat_policy.owner_text(prompt))
    if group_key:
     if group_key not in allowed_groups():raise ValueError('Name the intended group before sending. This group is not authorized by the current request or selected context.')
    else:
     phone=norm_phone(dest.split('@')[0]);jid=phone+'@s.whatsapp.net' if phone else dest
     explicit={norm_phone(x) for x in re.findall(r'(?:\+?92|0092|0)?3\d{2}[\s-]?\d{7}',chat_policy.owner_text(prompt))}
     if not phone and not dest.endswith('@g.us'):
      dest=resolve_person(dest);jid=dest
     same=jid==LAST_MANUAL.get('to') and bool(re.search(r'(?i)\b(him|her|them|same|again|it|resend)\b|^send\s+(?:now|hi|ok)$',prompt.strip()))
     if jid not in verified and phone not in explicit and not same:raise ValueError('Recipient must be verified with find_contact from this instruction before sending or preparing.')
   if name=='send_appeal':
    if args.get('target') not in allowed_groups():raise ValueError('Name the intended group before sending. This group is not authorized by the current request or selected context.')
   if name=='dm_group' and args.get('group') not in allowed_groups():raise ValueError('DM members only of the group named in the owner request.')
   cache_key=name+json.dumps(args,sort_keys=True,ensure_ascii=False)
   if name in send_tools|{'delete_last_message'} and cache_key in cache:return cache[cache_key]
   previous=getattr(OWNER_GUARD,'revision',None);OWNER_GUARD.revision=revision
   try:
    if name=='schedule_task' or name=='add_rule' and timed_tasks.requested(prompt):
     result=timed_chat_command(prompt,task_id)
     if result is None:raise ValueError('Give a group/action and a future time. Nothing was scheduled or sent.')
    elif name=='send_appeal':result=send_appeal(args.get('target'),(task_id+'-'+hashlib.sha256(cache_key.encode()).hexdigest()[:16]) if task_id else None)
    elif name=='send_message':
     literal=bool(re.search(r'["“\']'+re.escape(str(args.get('text','')))+r'["”\']',prompt))
     target=resolve_person(args.get('to',''))
     custom=manual_commands.parse(prompt) or {}
     quoted=re.search(r'(?is)^(?:send|resend|text|message)\s+["“](.+?)["”]',prompt.strip())
     if quoted:args['text']=quoted[1];literal=True
     elif custom.get('kind')=='text' and not literal:args['text']=custom['text'];literal=True;args['with_picture']=bool(re.search(r'(?i)\b(poster|image|picture)\b',chat_policy.owner_text(prompt)))
     # The model selects recipients; the stored template supplies fundraising captions.
     appeal=not literal and not str(target).endswith('@g.us') and target not in GROUPS and target not in ('test','all','free') and (args.get('with_picture') or re.search(r'(?i)\b(dm|appeal|donation|poster|structure)\b',prompt) or re.search(r'(?i)Yous[au]f|03097458815',str(args.get('text',''))))
     if appeal:result=send_dm_appeal(target)
     else:result=send_free(target,args.get('text',''),args.get('with_picture',False),literal=literal)
    elif name=='find_contact':
     result=fn(**args)
     try:
      items=json.loads(result)
      for item in items:CONTACT_CONTEXT[item['id']]=item
      exact=[x for x in items if x.get('name','').casefold()==str(args.get('query','')).casefold()]
      selected=exact if len(exact)==1 else items if len(items)==1 else []
      if all(word in manual_commands.norm(prompt) for word in manual_commands.norm(args.get('query','')).split()):verified.update(x['id'] for x in selected)
     except (ValueError,TypeError,KeyError):pass
    elif name=='set_message' and args.get('kind')=='dm':
     if re.search(r'(?i)\bname\b.*\b(is|change|to)\b|\b(change|correct)\b.*\bname\b',prompt):raise ValueError('Use edit_dm_name to change only the greeting; keep the full message.')
     if not dm_composer.complete(args.get('text','')):raise ValueError('Keep the full DM with blank lines, formatting, amount, donation options and payment details. Do not replace it with a name or one-paragraph summary.')
     result=fn(**args)
    elif name=='remember':result=mem_add(prompt)
    else:result=fn(**args)
   finally:OWNER_GUARD.revision=previous
   if name in send_tools|{'delete_last_message'}:cache[cache_key]=result
   return result
  return call
 return {name:wrapped(name,fn) for name,fn in callbacks.items()}

def manual_recipient():
 global LAST_MANUAL
 LAST_MANUAL=mapping(LAST_MANUAL)
 if LAST_MANUAL.get('kind')=='appeal':
  key=LAST_MANUAL.get('target')
  return {'target':key,'name':'GiveLife main' if key=='main' else key,'id':GROUPS[key][1] if key in GROUPS else '', 'group':True}
 if LAST_MANUAL.get('kind') in ('text','dm_appeal'):return {'id':LAST_MANUAL.get('to'),'name':LAST_MANUAL.get('name') or CONTACT_CONTEXT.get(LAST_MANUAL.get('to'),{}).get('name',''),'group':str(LAST_MANUAL.get('to','')).endswith('@g.us'),'message_type':LAST_MANUAL.get('kind'),'last_caption':LAST_MANUAL.get('text','')}
 return None

def assistant_task(body):
 global OWNER_REVISION
 ident=str(body.get('request_id') or uuid.uuid4().hex)
 if not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',ident):raise ValueError('Invalid request id.')
 with LOCK:
  if ident in ASSIST_TASKS:return ident
  saved=mapping(STORE.get('assistant_task_'+ident)) if STORE else {}
  if saved:
   ASSIST_TASKS[ident]=saved if saved.get('done') else {'done':True,'error':'This request was interrupted by a restart. Check confirmed activity; it will not be repeated automatically.'}
   return ident
  OWNER_REVISION+=1;revision=OWNER_REVISION
  ASSIST_TASKS[ident]={'done':False}
  if STORE:STORE.put('assistant_task_'+ident,{'done':False,'started':time.time()})
 def run():
  try:
   text=str(body.get('text',''))[:10000];CHAT_IMAGE['id']=body.get('image');hist=chat_get(300)
   KNOWLEDGE.report_correction(text)
   if hist and hist[-1]['who']=='you' and hist[-1]['text'].strip()==text.strip():hist=hist[:-1]
   preferences=mem_get()
   output=assistant.chat(text,hist or body.get('history',[]),{**studio_state(),'last_recipient':manual_recipient(),'drafts':json.loads(DRAFT.read_text(encoding='utf-8')),'recipient_names':DM_NAMES,'retrieved':KNOWLEDGE.retrieve(text),'pending_task':KNOWLEDGE.data.get('pending',{}),'rules':ENGINE.rule_list(),'recent_activity':[x['text'] for x in AUTOLOG[-4:]],'send_status':send_status_text(),'engine':ENGINE.summary(),'suggestions':[x['text'] for x in ENGINE.suggestions()],'screen':body.get('screen',{})},preferences,chat_callbacks(text,revision,ident))
   if output is None:ASSIST_TASKS[ident].update(done=True,error='The AI is not connected. Direct commands still work.');return
   output.update(**json.loads(DRAFT.read_text(encoding='utf-8')),left=read_left(),autopilot=auto_on(),dm_identity=dm_identity())
   output['superseded']=revision!=OWNER_REVISION
   output['turn_id']=uuid.uuid4().hex
   KNOWLEDGE.archive('app',output.get('reply',''),output['turn_id'])
   KNOWLEDGE.trace({'request_id':ident,**output.get('diagnostics',{})})
   ASSIST_TASKS[ident].update(done=True,result=output)
  except Exception as e:
   ASSIST_TASKS[ident].update(done=True,error='The assistant could not complete this request: '+safe_text(e,160)+'. It will not retry automatically.')
   try:KNOWLEDGE.trace({'request_id':ident,'error':safe_text(e,160)})
   except Exception:pass
  finally:
   if STORE:STORE.put('assistant_task_'+ident,ASSIST_TASKS[ident])
 threading.Thread(target=run,daemon=True).start();return ident

def edit_donation_order():
 left=read_left();drafts=json.loads(DRAFT.read_text(encoding='utf-8'));updated={}
 for kind,text in drafts.items():
  lines=text.split('\n');indices=[i for i,line in enumerate(lines) if re.search(r'(?i)people|donat|giving|give ',line) and re.search(r'(?:1[ ,]?000|2[ ,]?000)',line)]
  if indices:
   first,last=min(indices),max(indices)
   replacement=[f'*_{math.ceil(left/2000)} people donating Rs. 2,000_*',f'*_OR {math.ceil(left/1000)} people donating Rs. 1,000_* 🤲']
   lines[first:last+1]=replacement;updated[kind]='\n'.join(lines)
  else:updated[kind]=text
 with LOCK:
  DRAFT.write_text(json.dumps(updated,ensure_ascii=False),encoding='utf-8');persist_file('drafts',DRAFT)
 return f'Rs. 2,000 option first, then Rs. 1,000. The amount left stays Rs. {left:,}.'

def remove_arrival_line():
 drafts=json.loads(DRAFT.read_text(encoding='utf-8'))
 for kind,text in drafts.items():
  lines=[line for line in text.split('\n') if not re.search(r'(?i)\b(came(?: in)?|received|has arrived|arrived)\b',line)]
  drafts[kind]=re.sub(r'\n{3,}','\n\n','\n'.join(lines)).strip()
 with LOCK:
  DRAFT.write_text(json.dumps(drafts,ensure_ascii=False),encoding='utf-8');persist_file('drafts',DRAFT)
 return f'Removed the money-arrival wording from the captions. Amount left is still Rs. {read_left():,}. No future rule was added.'

def send_selected_groups(targets,request_id=None):
 keys=[]
 for target in targets:keys.extend(list(GROUPS) if target=='all' else FREELANCE if target=='free' else [target])
 keys=list(dict.fromkeys(keys));remember_manual({'kind':'appeals','targets':targets})
 if not wa_ok():raise ValueError('WhatsApp is not connected. Link it first.')
 caption=json.loads(DRAFT.read_text(encoding='utf-8')).get('group','')
 ident=start_send_job(keys,caption,True,request_id)
 return {'reply':f'Starting the manual send to {len(keys)} selected groups now.','job_id':ident,'caption':caption}

def execute_manual_command(text,request_id=None):
 global OWNER_REVISION
 if not fast_command_eligible(text):return {'handled':False}
 timed=timed_chat_command(text,request_id)
 if timed is not None:return {'handled':True,'reply':timed}
 import rules
 pace=rules.pace_rules(text)
 rule,description=rules.parse(text)
 if not pace and rule and rule.get('kind')=='gap':pace=[rule]
 if pace:
  with LOCK:OWNER_REVISION+=1
  for item in pace:ENGINE.add_rule(item)
  return {'handled':True,'reply':'; '.join(rules.describe(item) for item in pace)+('. Auto follows this schedule.' if auto_on() else '. Saved. Auto is currently off.')}
 plan=manual_commands.parse(text)
 if not plan:return {'handled':False}
 with LOCK:OWNER_REVISION+=1
 OWNER_GUARD.revision=OWNER_REVISION
 kind=plan['kind'];out={'handled':True}
 if kind=='refuse_target':raise ValueError('That group is excluded. Nothing was sent.')
 if kind=='stop_dms':
  CAMPAIGN['stop']=True;ENGINE.set_dms(False,ENGINE.s.get('dm_daily',30));out['reply']='DMs stopped. Automatic DMs stay off until you turn them on.'
 elif kind=='hold':out['reply']=set_hold(True)
 elif kind=='resume':out['reply']=set_hold(False)
 elif kind=='donation_order':out['reply']=edit_donation_order()
 elif kind=='remove_arrival_line':out['reply']=remove_arrival_line()
 elif kind=='dm_name':out['reply']=edit_dm_name(plan['name'],plan.get('to',''))
 elif kind=='status':out['reply']=send_status_text(plan.get('freelance',False))
 elif kind=='money':
  if plan['amount']>read_left():raise ValueError('That donation is larger than the amount remaining. Tell me the correct remaining amount.')
  set_left(read_left()-plan['amount']);out['reply']=f"Recorded Rs. {plan['amount']:,} received. Rs. {read_left():,} left."
 elif kind=='amount':
  set_left(plan['amount']);out['reply']=f"Rs. {plan['amount']:,} left. Captions updated."
 elif kind=='delete':out['reply']=delete_last_group(plan.get('target'))
 elif kind=='select':
  remember_manual({'kind':'appeal','target':plan['target']});out['reply']='Selected '+('GiveLife main' if plan['target']=='main' else plan['target'])+'.'
 elif kind=='repeat':
  if not LAST_MANUAL:raise ValueError('Who should receive it? Name a group or contact.')
  if LAST_MANUAL.get('kind')=='appeals':out.update(send_selected_groups(LAST_MANUAL['targets'],request_id))
  elif LAST_MANUAL.get('kind')=='appeal':out.update(send_appeal(LAST_MANUAL['target'],request_id))
  elif LAST_MANUAL.get('kind')=='dm_appeal':out['reply']=send_dm_appeal(LAST_MANUAL['to'],LAST_MANUAL.get('name',''),LAST_MANUAL.get('gender','Brother'))
  elif LAST_MANUAL.get('kind')=='text':
   send_free(LAST_MANUAL['to'],LAST_MANUAL['text'],LAST_MANUAL.get('with_picture',False),literal=True);out['reply']='WhatsApp confirmed the repeated message.'
  else:raise ValueError('There is no previous manual send to repeat.')
 elif kind=='appeals':
  if plan.get('amount') is not None:set_left(plan['amount'])
  out.update(send_selected_groups(plan['targets'],request_id))
 elif kind=='appeal':
  if plan.get('amount') is not None:set_left(plan['amount'])
  out.update(send_appeal(plan['target'],request_id))
 elif kind=='appeal_to':
  target=resolve_person(plan['to'])
  if target in GROUPS or target in ('all','free','test'):out.update(send_appeal(target,request_id))
  else:out['reply']=send_dm_appeal(target)
 elif kind=='text':
  target=resolve_person(plan['to']) if plan.get('to') else (LAST_MANUAL.get('to') if LAST_MANUAL.get('kind')=='text' else LAST_MANUAL.get('target') if LAST_MANUAL.get('kind')=='appeal' else None)
  if not target:raise ValueError('Who should receive this text? Give a name, number or group.')
  send_free(target,plan['text'],False,literal=True);out['reply']='WhatsApp confirmed the message.'
 drafts=json.loads(DRAFT.read_text(encoding='utf-8'));out.update(group=drafts['group'],dm=drafts['dm'],left=read_left())
 return out

def manual_command(text,request_id=None):
 previous=getattr(OWNER_GUARD,'revision',None)
 try:
  pending=KNOWLEDGE.data.get('pending',{})
  if pending.get('created',0)<time.time()-600:pending={};KNOWLEDGE.data['pending']={}
  if pending and str(text).strip().casefold() in ('cancel','forget it','stop','no'):
   KNOWLEDGE.data['pending']={};KNOWLEDGE.save();return {'handled':True,'reply':'Cancelled the pending recipient selection. Nothing was sent.'}
  matches=[x for x in pending.get('candidates',[]) if str(text).strip().casefold() in (x['name'].casefold(),x['id'].split('@')[0],x['id'].split('@')[0][-4:])]
  if len(matches)==1 and pending.get('action'):
   target=matches[0]['id'];action=pending['action'];KNOWLEDGE.data['pending']={};KNOWLEDGE.save()
   with LOCK:
    global OWNER_REVISION
    OWNER_REVISION+=1;OWNER_GUARD.revision=OWNER_REVISION
   send_free(target,action['text'],False,literal=True)
   return {'handled':True,'reply':'WhatsApp confirmed your earlier message to '+matches[0]['name']+'.'}
  if pending.get('action'):
   fresh=manual_commands.parse(text) or {}
   if fresh.get('kind') not in (None,'status'):
    KNOWLEDGE.data['pending']={};KNOWLEDGE.save()
  try:result=execute_manual_command(text,request_id)
  except ValueError:
   plan=manual_commands.parse(text) or {}
   if plan.get('kind')=='text' and KNOWLEDGE.data.get('pending',{}).get('kind')=='recipient':
    KNOWLEDGE.data['pending']['action']={'text':plan['text'],'to_query':plan.get('to')};KNOWLEDGE.save()
   raise
  if result.get('handled'):result['dm_identity']=dm_identity()
  return result
 finally:OWNER_GUARD.revision=previous

def dm_identity():
 if LAST_MANUAL.get('kind')=='dm_appeal':return {'name':LAST_MANUAL.get('name',''),'phone':LAST_MANUAL.get('to','').split('@')[0],'gender':LAST_MANUAL.get('gender','Brother')}
 return None

def fast_command_eligible(text):
 text=str(text).strip()
 if not text or len(text)>10000:return False
 if re.match(r'(?i)^(summarize|analyse|analyze|explain|review|read|check)\b',text):return False
 if text.startswith(('"','“',"'",'```','>')) or re.search(r'(?i)\b(transcript|message says|text says|summarize|analyse|analyze|see fn remove)\s*:',text):return False
 if re.search(r'(?i);|\band then\b|\n(?:you|assistant|app):',text):return False
 if re.search(r'(?i)\band\s+(?:set|change|write|delete|remove|remember|pause|enable|disable)\b',text):return False
 return True

def set_group_pace(target,minutes):
 if target not in (*GROUPS,'free','all'):raise ValueError('Choose a known group or freelance/all.')
 minutes=max(15,min(1440,int(minutes)))
 ENGINE.add_rule({'kind':'gap','group':target,'minutes':minutes})
 return f'Automatic posts in {target}: every {minutes} minutes. Other groups keep their settings.'

def send_status_text(freelance=False):
 summary=ENGINE.summary();last=last_sent_by_key();keys=FREELANCE if freelance else list(GROUPS)
 lines=['Auto is '+('on' if auto_on() else 'off')+'.']
 current=get_job(ACTIVE) if ACTIVE else None
 if current:lines.append(current.get('message','A send is running.'))
 for key in keys:
  every=summary['group_intervals'][key];stamp=last.get(key)
  elapsed=max(0,(time.time()-stamp)/60) if stamp else None
  state='paused' if ENGINE.blocked(key) else ('due now' if elapsed is None or elapsed>=every else f'next in {math.ceil(every-elapsed)} min')
  lines.append(f'{GROUPS[key][0]}: every {every} min, '+(f'last confirmed {int(elapsed)} min ago' if elapsed is not None else 'no confirmed send recorded')+', '+state+'.')
 if auto_on():lines.append('Due groups send automatically while WhatsApp is connected and sending is not on hold; batch recipients stay 60 seconds apart.')
 return '\n'.join(lines)

class Handler(BaseHTTPRequestHandler):
 def remote_config(self):
  return {'key':os.environ.get('UI_ACCESS_KEY',''),'origins':[x for x in os.environ.get('ALLOWED_ORIGINS','').split(',') if x]}
 def authorized(self):
  key=self.remote_config().get('key','')
  return bool(key) and secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+key)
 def do_OPTIONS(self):
  self.reply({})
 def reply(self,data,kind='application/json',status=200):
  self.response_sent=True
  if not isinstance(data,(str,bytes)):data=json.dumps(data,ensure_ascii=False)
  self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Cache-Control','no-store')
  origin=self.headers.get('Origin')
  if origin in self.remote_config().get('origins',[]):
   self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin');self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type');self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
  self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data if isinstance(data,bytes) else data.encode())
 def do_GET(self):
  if self.path=='/health':return self.reply({'ok':True})
  if self.path in ('/','/app.js','/format.js','/connection.js'):
   name='index.html' if self.path=='/' else self.path[1:]
   return self.reply((ROOT/name).read_bytes(),'text/html' if self.path=='/' else 'application/javascript')
  if not self.authorized():return self.reply({'error':'Access key required'},status=401)
  if self.path=='/wa-status':
   try:return self.reply(api('/devices/'+DEVICE+'/status'))
   except Exception:return self.reply({'error':'WhatsApp is restarting. Try again shortly.'},status=502)
  if self.path=='/drafts':self.reply(DRAFT.read_bytes())
  elif self.path=='/poster':self.reply((DATA/'poster.jpg').read_bytes(),'image/jpeg')
  elif self.path=='/format.js':self.reply((ROOT/'format.js').read_bytes(),'application/javascript')
  elif self.path=='/app.js':self.reply((ROOT/'app.js').read_bytes(),'application/javascript')
  elif self.path=='/left':self.reply({'left':read_left()})
  elif self.path.startswith('/autopilot'):self.reply({'on':auto_on(),'ai':bool(assistant.client()),'log':AUTOLOG[-20:],'summary':ENGINE.summary(),'status':ENGINE.status() if auto_on() else None,'hold':on_hold()})
  elif self.path=='/memory':self.reply(mem_get())
  elif self.path=='/knowledge':mem_get();self.reply(KNOWLEDGE.summary())
  elif self.path.startswith('/assistant-evaluate/'):
   result=EVAL_TASKS.get(self.path.split('/')[-1]);self.reply(result or {'error':'Unknown evaluation.'},status=200 if result else 404)
  elif self.path=='/campaign':self.reply({**{k:v for k,v in CAMPAIGN.items() if k!='stop'},'log':CAMPAIGN['log'][-8:],'wait':max(0,round(CAMPAIGN['next_at']-time.time()))})
  elif self.path=='/rules':self.reply({'items':ENGINE.rule_list(),'autopilot':auto_on()})
  elif self.path=='/ai-test':self.reply(ai_test())
  elif self.path=='/wa-check':
   c=check_groups(True);self.reply({'checked':c.get('checked'),'missing':c.get('missing',[]),'fixed':c.get('fixed',[]),'whatsapp':wa_ok()})
  elif self.path=='/chat':self.reply({'items':chat_get(200)})
  elif self.path=='/suggestions':self.reply({'items':ENGINE.suggestions(),'autopilot':auto_on(),'summary':ENGINE.summary()})
  elif self.path=='/groups':self.reply([{'key':k,'name':v[0]} for k,v in GROUPS.items()])
  elif self.path.startswith('/assistant-status/'):
   ident=self.path.split('/')[-1];task=ASSIST_TASKS.get(ident)
   if task is None and STORE:
    task=mapping(STORE.get('assistant_task_'+ident)) or None
    if task and not task.get('done'):task={'done':True,'error':'The service restarted before completion. Check recent activity; this action will not repeat automatically.'}
   self.reply(task or {'error':'This request is no longer tracked after a service restart. Check recent activity before trying again.'},status=200 if task else 404)
  elif self.path.startswith('/send-status/'):
   job=get_job(self.path.split('/')[-1]);self.reply(job or {'error':'Unknown job'},status=200 if job else 404)
  elif self.path=='/':self.reply((ROOT/'index.html').read_bytes(),'text/html')
  else:self.reply({},status=404)
 def do_POST(self):
  self.response_sent=False
  try:self._post()
  except (ValueError,TypeError,KeyError):
   if not self.response_sent:self.reply({'error':'The request data is invalid. Correct the fields and try again.'},status=400)
  except Exception:
   if not self.response_sent:self.reply({'error':'This request did not complete reliably. Check confirmed activity before repeating any send.'},status=502)
 def _post(self):
  global ACTIVE,OWNER_REVISION
  if not self.authorized():return self.reply({'error':'Access key required'},status=401)
  ENGINE.touch_owner()
  if self.path not in ('/chat-log','/rule-text','/assistant','/command','/feedback','/knowledge','/assistant-evaluate'):
   with LOCK:OWNER_REVISION+=1
   OWNER_GUARD.revision=OWNER_REVISION
  origin=self.headers.get('Origin');same_origin=origin and urllib.parse.urlparse(origin).netloc==self.headers.get('Host')
  if origin and not same_origin and origin not in self.remote_config().get('origins',[]):return self.reply({},status=403)
  try:
   length=int(self.headers.get('Content-Length',0))
   if not 0<length<=12_000_000:return self.reply({'error':'Request is empty or too large.'},status=400)
   body=json.loads(self.rfile.read(length))
  except Exception:return self.reply({'error':'Invalid request'},status=400)
  if not isinstance(body,dict):return self.reply({'error':'Request must be a JSON object.'},status=400)
  if self.path=='/drafts':
   if any(not isinstance(body.get(k),str) or len(body[k])>10000 for k in ('group','dm')):return self.reply({'error':'Both captions must be text, at most 10,000 characters each.'},status=400)
   with LOCK:
    DRAFT.write_text(json.dumps({k:str(body[k]) for k in ('group','dm')},ensure_ascii=False),encoding='utf-8');persist_file('drafts',DRAFT)
   self.reply({'saved':True})
  elif self.path=='/wa-reconnect':
   try:
    api('/app/reconnect')
    self.reply({'ok':True})
   except Exception:self.reply({'error':'Could not restore the connection. Try linking with a QR code.'},status=502)
  elif self.path=='/wa-logout':
   if body.get('confirm') is not True:return self.reply({'error':'Confirm disconnect first.'},status=400)
   if not SEND_LOCK.acquire(blocking=False):return self.reply({'error':'A send is running. Wait before disconnecting.'},status=409)
   try:
    api('/app/logout');self.reply({'ok':True})
   except Exception:self.reply({'error':'Disconnect was not confirmed. Check the connection status.'},status=502)
   finally:SEND_LOCK.release()
  elif self.path=='/send-custom':
   try:self.reply(send_custom(body))
   except ValueError as e:self.reply({'error':str(e)},status=400)
   except Exception:self.reply({'error':'Could not prepare this send. No automatic retry will occur.'},status=502)
  elif self.path=='/wa-login':
   try:
    data=api('/devices/'+DEVICE+'/login');url=data.get('results',{}).get('qr_link','');path=urllib.parse.urlparse(url).path
    if not path.startswith('/statics/qrcode/'):return self.reply({'error':'QR not available; check connection.'},status=400)
    with urllib.request.urlopen(GOWA_URL+path,timeout=10) as qr:encoded=base64.b64encode(qr.read()).decode()
    self.reply({'qr':'data:image/png;base64,'+encoded,'duration':data['results'].get('qr_duration',30)})
   except Exception as e:self.reply({'error':'Could not get QR: '+str(e)},status=502)
  elif self.path=='/next-message':self.reply({'message':next_message()})
  elif self.path=='/next-dm':self.reply({'message':next_dm()})
  elif self.path=='/memory':self.reply({'reply':mem_add(body.get('rule',''))})
  elif self.path=='/hold':self.reply({'reply':set_hold(body.get('on',True)),'hold':on_hold()})
  elif self.path=='/dm-batch':
   try:self.reply({'reply':dm_batch_now(body.get('kind','donors'),body.get('count',10),body.get('group','main'))})
   except ValueError as e:self.reply({'error':str(e)},status=400)
  elif self.path=='/chat-log':self.reply({'ok':True,'turn_id':chat_add(body.get('who'),body.get('text',''),body.get('err'),body.get('turn_id'))})
  elif self.path=='/knowledge':
   self.reply({'removed':KNOWLEDGE.forget(str(body.get('forget',''))),'memory':KNOWLEDGE.summary()})
  elif self.path=='/feedback':
   try:self.reply({'saved':KNOWLEDGE.feedback(str(body.get('turn_id','')),body.get('correction',''),body.get('remember') is True),'warning':KNOWLEDGE.sync_error})
   except ValueError as e:self.reply({'error':str(e)},status=400)
  elif self.path=='/assistant-evaluate':
   import chat_eval
   cases=body.get('cases',list(chat_eval.CASES))
   if not isinstance(cases,list) or not 1<=len(cases)<=8 or any(x not in chat_eval.CASES for x in cases):return self.reply({'error':'Choose 1 to 8 known test cases.'},status=400)
   running=next((k for k,v in EVAL_TASKS.items() if not v.get('done')),None)
   if running:return self.reply({'eval_id':running})
   ident=uuid.uuid4().hex;EVAL_TASKS[ident]={'done':False,'results':[],'total':len(cases)}
   def evaluate():
    for key in cases:
     try:result=chat_eval.run_case(key)
     except Exception as e:result={'case':key,'passed':False,'error':str(e)[:160],'sandbox':True}
     EVAL_TASKS[ident]['results'].append(result)
    EVAL_TASKS[ident]['done']=True
    KNOWLEDGE.trace({'evaluation':ident,'passed':sum(x['passed'] for x in EVAL_TASKS[ident]['results']),'total':len(cases),'sandbox':True})
   threading.Thread(target=evaluate,daemon=True).start();self.reply({'eval_id':ident})
  elif self.path=='/autopilot':self.reply({'reply':set_auto(bool(body.get('on'))),'on':auto_on()})
  elif self.path=='/upload-image':
   try:self.reply({'id':save_upload(str(body.get('data','')),body.get('use','attachment'))})
   except Exception as e:self.reply({'error':str(e)[:120]},status=400)
  elif self.path=='/campaign':
   if body.get('stop'):CAMPAIGN['stop']=True;return self.reply({'reply':'Stopping the DM list.'})
   try:self.reply({'reply':start_campaign(body)})
   except Exception as e:self.reply({'error':str(e)[:160]},status=400)
  elif self.path=='/find':
   out,checked=find_data(str(body.get('query','')));self.reply({'items':out,'checked':checked})
  elif self.path=='/command':
   if not isinstance(body.get('text',''),str) or len(body.get('text',''))>10000:return self.reply({'error':'Command must be text of at most 10,000 characters.'},status=400)
   try:self.reply(manual_command(str(body.get('text','')),body.get('request_id')))
   except ValueError as e:self.reply({'error':str(e)},status=400)
  elif self.path=='/send-now':
   if not isinstance(body.get('text'),str) or not isinstance(body.get('to',''),str):return self.reply({'error':'Recipient and message must be text.'},status=400)
   to=str(body.get('to','')).strip() or LAST_RECIPIENT.get('id','')
   if not to:return self.reply({'error':'Who should I send it to? Say: send hi to <name or number>.'},status=400)
   try:send_free(to,body.get('text',''),bool(body.get('with_picture')),literal=body.get('literal') is True);self.reply({'ok':True,'to':LAST_RECIPIENT.get('name','')})
   except ValueError as e:self.reply({'error':str(e)},status=400)
   except Exception as e:self.reply({'error':'Could not send: '+str(e)[:100]},status=502)
  elif self.path=='/rule-text':
   rule,msg=rule_from_text(str(body.get('text','')))
   if not rule:return self.reply({'rule':False})
   if not auto_on():return self.reply({'rule':True,'saved':False,'summary':msg})
   ENGINE.add_rule(rule);self.reply({'rule':True,'saved':True,'summary':msg})
  elif self.path=='/rules':
   self.reply({'removed':ENGINE.delete_rule(body.get('delete')),'items':ENGINE.rule_list()})
  elif self.path=='/suggestion':
   msg=ENGINE.run_suggestion(str(body.get('action','')))
   if msg is None:return self.reply({'error':'This one is done from the screen or by you.'},status=400)
   self.reply({'reply':msg})
  elif self.path=='/autopilot-settings':
   a=str(body.get('action',''));key=str(body.get('key',''))
   if a in ('pause','resume') and key not in GROUPS:return self.reply({'error':'Unknown group. Use: '+', '.join(GROUPS)},status=400)
   try:
    msg=ENGINE.pause(key,float(body.get('hours',24))) if a=='pause' else ENGINE.resume(key) if a=='resume' else ENGINE.set_quiet(int(body.get('start',0)),int(body.get('end',0))) if a=='quiet' else ENGINE.set_dms(bool(body.get('enabled',True)),int(body.get('daily',30)),body.get('new_people')) if a=='dms' else ENGINE.set_pace(body.get('main'),body.get('freelance')) if a=='pace' else None
   except Exception as e:return self.reply({'error':str(e)[:120]},status=400)
   if msg is None:return self.reply({'error':'Unknown setting'},status=400)
   self.reply({'reply':msg,'summary':ENGINE.summary()})
  elif self.path=='/assistant':
   text=body.get('text','')
   if not isinstance(text,str) or len(text)>10000:return self.reply({'error':'Use a text message of at most 10,000 characters.'},status=400)
   if not text.strip():return self.reply({'error':'Type something first.'},status=400)
   try:
    direct=manual_command(text,body.get('request_id'))
    if direct.get('handled'):return self.reply(direct)
    ident=assistant_task(body);self.reply({'task_id':ident})
   except ValueError as e:self.reply({'error':str(e)},status=400)
  elif self.path=='/left':
   if isinstance(body.get('left'),bool):return self.reply({'error':'Amount must be a number.'},status=400)
   try:left=int(body.get('left'))
   except Exception:return self.reply({'error':'Enter the amount as a number, like 34000.'},status=400)
   if not 0<=left<=10000000:return self.reply({'error':'Amount looks wrong.'},status=400)
   g,d=set_left(left);self.reply({'left':left,'group':g,'dm':d})
  elif self.path=='/send-group':
   if not isinstance(body.get('group'),str) or not isinstance(body.get('message'),str):return self.reply({'error':'Group and caption must be text.'},status=400)
   key=body.get('group');caption=str(body.get('message',''))
   if key not in GROUPS and key not in ('all','free'):return self.reply({'error':'Unknown group'},status=400)
   try:
    OWNER_REVISION+=1
    remember_manual({'kind':'appeal','target':key})
    ident=start_send_job(list(GROUPS) if key=='all' else FREELANCE if key=='free' else [key],caption,True,body.get('request_id'))
    self.reply({'job_id':ident})
   except ValueError as e:self.reply({'error':str(e)},status=400)
  elif self.path=='/test':
   caption=str(body.get('message',''))
   if not caption.strip():return self.reply({'error':'Message is empty'},status=400)
   try:
    with SEND_LOCK:result=send_image('120363431210327603@g.us',caption)
    self.reply(result)
   except Exception as e:self.reply({'code':'ERROR','message':str(e)})
  else:self.reply({},status=404)
 def log_message(self,*args):pass
if __name__=='__main__':
 PILOT.start()
 ENGINE.start()
 threading.Thread(target=timed_loop,daemon=True).start()
 ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()
