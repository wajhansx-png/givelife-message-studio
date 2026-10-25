import json, subprocess, urllib.request, urllib.parse, threading, time, uuid, datetime, math, re, secrets, os, base64, hashlib
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from persist import configured_store
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('DATA_DIR','/data/studio'))
DATA.mkdir(parents=True,exist_ok=True)
DRAFT=DATA/'drafts.json'
DEVICE=os.environ.get('WHATSAPP_DEVICE_ID','')
GROUPS={'main':('GiveLife Foundation','120363423121755785@g.us'),'community':('Upwork Community 2026','120363398623589385@g.us'),'fiverr':('Fiverr Course 2026','120363411617215937@g.us'),'upwork':('Upwork Course 2026','120363430624868021@g.us'),'uet':('Fiverr Course UET','120363412286860707@g.us'),'toprated':('Top Rated Upworkers','120363427826119453@g.us')}
FREELANCE=['community','fiverr','upwork','uet','toprated']
LAST_LOCAL={}
JOBS={};LOCK=threading.Lock();SEND_LOCK=threading.Lock();ACTIVE=None
STORE=configured_store()
BLOCKED=set(json.loads((ROOT/'campaign-blocks.json').read_text())) if (ROOT/'campaign-blocks.json').exists() else set()
def persist_file(key,path):
 if STORE:STORE.put(key,path.read_text(encoding='utf-8'))

def api(path):
 req=urllib.request.Request('http://127.0.0.1:3000'+path,headers={'X-Device-Id':DEVICE})
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
 jid,is_group=custom_recipient(body);message=str(body.get('message',''))
 if not message.strip() or len(message)>10000:raise ValueError('Write a message of 1 to 10,000 characters.')
 if not STORE:raise ValueError('Persistent send records are unavailable. Try again later.')
 if not SEND_LOCK.acquire(blocking=False):raise ValueError('Another send is running. Please wait for it to finish.')
 try:
  status=api('/devices/'+DEVICE+'/status').get('results',{})
  if not status.get('is_connected') or not status.get('is_logged_in'):raise ValueError('WhatsApp is disconnected. Tap WhatsApp to reconnect.')
  now=time.time();saved=STORE.get('last_sent',{})
  if is_group and now-saved.get(jid,0)<900:raise ValueError('This group was posted to recently. Wait 15 minutes between posts.')
  if not is_group:
   digest=hashlib.sha256(jid.encode()).hexdigest()
   if digest in BLOCKED or STORE.get('dm_recipient_'+digest):raise ValueError('This recipient was already contacted or has an uncertain send. Check WhatsApp before sending again.')
   ledger=STORE.get('dm_daily',{});day=datetime.datetime.fromtimestamp(now,datetime.timezone(datetime.timedelta(hours=5))).date().isoformat()
   if ledger.get('day')!=day:ledger={'day':day,'count':0,'last':ledger.get('last',0)}
   if ledger['count']>=50:raise ValueError('The 50-DM daily limit has been reached.')
   if now-ledger.get('last',0)<60:raise ValueError('Wait at least 60 seconds between DMs.')
   ledger.update(count=ledger['count']+1,last=now);STORE.put('dm_daily',ledger);STORE.put('dm_recipient_'+digest,{'state':'uncertain','time':now})
  # Reserve before dispatch. A network failure must not silently allow duplicates.
  if is_group:saved[jid]=now;STORE.put('last_sent',saved)
  try:
   if body.get('poster') is True:result=send_image(jid,message)
   else:
    req=urllib.request.Request('http://127.0.0.1:3000/send/message',data=json.dumps({'phone':jid,'message':message}).encode(),headers={'X-Device-Id':DEVICE,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=40) as response:result=json.load(response)
  except Exception:result={'code':'UNCERTAIN','message':'Send not confirmed. Check WhatsApp before retrying.'}
  STORE.put('custom_receipt_'+uuid.uuid4().hex,{'time':now,'jid':jid,'code':result.get('code'),'message_id':result.get('results',{}).get('message_id')})
  if not is_group:STORE.put('dm_recipient_'+digest,{'state':result.get('code','UNCERTAIN'),'time':now})
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

def build_group(n,left):
 p2,p1=math.ceil(left/2000),math.ceil(left/1000)
 hook=HOOKS[n%8][0].replace('{P2}',str(p2));push=HOOKS[(n*3+1)%8][1].replace('{P2}',str(p2))
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
  write_left(left)
  try:ENGINE.amount_updated()
  except NameError:pass
  g=build_group(variant(False),left);d=build_dm(dm_selection(False),left)
  save_draft('group',g);save_draft('dm',d);return g,d

def send_image(jid,caption,check_gap=False):
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
 r=subprocess.run(['curl','-s','--max-time','40','-X','POST','http://127.0.0.1:3000/send/image','-H',f'X-Device-Id: {DEVICE}','-F',f'phone={jid}','-F',f'image=@{DATA / "poster.jpg"};type=image/jpeg','-F',f'caption=<{cap}','-F','compress=false'],capture_output=True)
 try:result=json.loads(r.stdout)
 except Exception:result={'code':'ERROR','message':'Send not confirmed. Check WhatsApp before retrying.'}
 if STORE:
  receipt={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'jid':jid,'code':result.get('code'),'message_id':result.get('results',{}).get('message_id')}
  STORE.put('receipt_'+uuid.uuid4().hex,receipt)
  if result.get('code')=='SUCCESS':
   saved=STORE.get('last_sent',{});saved[jid]=time.time();STORE.put('last_sent',saved)
 if result.get('code')=='SUCCESS':LAST_LOCAL[jid]=time.time()
 with (DATA/'group-send-log.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'jid':jid,'caption':caption,'response':result},ensure_ascii=False)+'\n')
 return result

def run_job(job_id,keys,caption):
 global ACTIVE
 job=JOBS[job_id];last_send=None
 try:
  with SEND_LOCK:
   for key in keys:
    name,jid=GROUPS[key]
    if last_send is not None:
     job['message']='Waiting 60 seconds before '+name;time.sleep(max(0,60-(time.monotonic()-last_send)))
    job['message']='Sending to '+name;result=send_image(jid,caption,True);job['results'].append({'group':name,**result})
    if result.get('code')=='SUCCESS':last_send=time.monotonic()
    elif result.get('code')!='COOLDOWN':break
   sent=sum(r.get('code')=='SUCCESS' for r in job['results'])
   if sent:job['next_caption']=next_message()
   job['message']=f'Sent to {sent}/{len(keys)} groups.';job['done']=True
 except Exception as e:job.update(done=True,message='Could not send: '+str(e))
 finally:
  with LOCK:ACTIVE=None


import assistant
MEMORY=DATA/'memory.json';AUTO=DATA/'autopilot.json';AUTOLOG=[]
if STORE:
 for key,f in (('memory',MEMORY),('autopilot',AUTO)):
  v=STORE.get(key)
  if v:f.write_text(v if isinstance(v,str) else json.dumps(v),encoding='utf-8')

def mem_get():
 return json.loads(MEMORY.read_text(encoding='utf-8')) if MEMORY.exists() else []

def mem_add(rule):
 rule=str(rule).strip()[:300]
 if not rule:return 'Nothing to save.'
 m=mem_get();m.append({'rule':rule,'time':time.time()});MEMORY.write_text(json.dumps(m,ensure_ascii=False),encoding='utf-8');persist_file('memory',MEMORY)
 return 'Saved for the future: '+rule

def auto_on():
 return bool(json.loads(AUTO.read_text()).get('on')) if AUTO.exists() else False

def set_auto(on):
 AUTO.write_text(json.dumps({'on':bool(on),'since':time.time()}));persist_file('autopilot',AUTO)
 auto_log('Autopilot turned '+('ON' if on else 'OFF')+'.');return ('Autopilot is on. I will post on schedule, watch replies, DM donor contacts carefully and message you on WhatsApp when I need you.'+('' if assistant.client() else ' (AI key not set yet, so I follow the fixed playbook only.)')) if on else 'Autopilot is off.'

def auto_log(text):
 AUTOLOG.append({'time':time.time(),'text':text});del AUTOLOG[:-50]

def wa_ok():
 try:
  s=api('/devices/'+DEVICE+'/status').get('results',{});return bool(s.get('is_connected') and s.get('is_logged_in'))
 except Exception:return False

def studio_state():
 saved=STORE.get('last_sent',{}) if STORE else {}
 since={k:(round((time.time()-saved[v[1]])/60) if v[1] in saved else None) for k,v in GROUPS.items()}
 return {'left':read_left(),'whatsapp':wa_ok(),'minutes_since_post':since,'autopilot':auto_on()}

def start_group_job(key,caption):
 global ACTIVE
 with LOCK:
  if ACTIVE:return None
  job_id=uuid.uuid4().hex;ACTIVE=job_id;JOBS[job_id]={'done':False,'results':[],'message':'Starting…'}
 threading.Thread(target=run_job,args=(job_id,list(GROUPS) if key=='all' else FREELANCE if key=='free' else [key],caption),daemon=True).start()
 return job_id

def auto_post(target):
 caption=json.loads(DRAFT.read_text(encoding='utf-8')).get('group','')
 if not caption.strip() or not start_group_job(target,caption):auto_log('Autopilot skipped: another send is running.')

CHAT_IMAGE={}
def chat_callbacks():
 def came(amount):
  nl=max(0,read_left()-int(amount));set_left(nl);return f'Rs. {int(amount):,} came. Rs. {nl:,} left.'
 return {'set_left':lambda left:(set_left(int(left)),f'Rs. {int(left):,} left. Messages updated.')[1],
  'money_came':came,
  'new_wording':lambda kind:(next_message() if kind=='group' else next_dm(),'New '+kind+' wording ready.')[1],
  'set_message':lambda kind,text:(save_draft(kind,text),'Message replaced.')[1],
  'remember':mem_add,'autopilot':set_auto,**engine_do(),
  'dm_list':lambda people,gap_minutes,vary,start_after_minutes:start_campaign({'people':people,'gap_seconds':float(gap_minutes)*60,'vary':vary,'start_after_seconds':float(start_after_minutes)*60,'image':CHAT_IMAGE.get('id') or 'poster'})}


import autopilot, random as _random
OWNER_PHONE=os.environ.get('OWNER_PHONE','923205069925')

def send_text(jid,text):
 req=urllib.request.Request('http://127.0.0.1:3000/send/message',data=json.dumps({'phone':jid,'message':text}).encode(),headers={'X-Device-Id':DEVICE,'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)

def last_sent_by_key():
 saved=dict(LAST_LOCAL)
 if STORE:saved.update(STORE.get('last_sent',{}))
 return {k:saved.get(v[1]) for k,v in GROUPS.items()}

def start_keys_job(keys,caption):
 global ACTIVE
 if not caption.strip():return False
 with LOCK:
  if ACTIVE:return False
  job_id=uuid.uuid4().hex;ACTIVE=job_id;JOBS[job_id]={'done':False,'results':[],'message':'Autopilot…'}
 threading.Thread(target=run_job,args=(job_id,[k for k in GROUPS if k in keys],caption),daemon=True).start();return True

def group_messages(jid):
 return api('/chat/'+urllib.parse.quote(jid,safe='')+'/messages?limit=20').get('results',{}).get('data',[]) or []

def donor_contacts():
 data=api('/group/participants?group_id='+urllib.parse.quote(GROUPS['main'][1],safe='')).get('results',{})
 people=data.get('participants',[]) if isinstance(data,dict) else []
 out=[]
 for p in people:
  name=str(p.get('display_name') or '');phone=str(p.get('phone_number') or '')
  if 'donor' not in name.lower() or not phone.isdigit() or phone==OWNER_PHONE:continue
  first=re.sub(r'(?i)\bdonor\b|member|\d+','',name).strip().split(' ')[0] if name else ''
  out.append((phone,first if re.fullmatch(r'[A-Za-z]{2,20}',first or '') else ''))
 _random.shuffle(out);return out

def already_dmed(digest):
 return digest in BLOCKED or bool(STORE and STORE.get('dm_recipient_'+digest))

def dm_text(name):
 sel=[_random.randrange(len(a)) for a in DP];t=build_dm(sel,read_left())
 return t.replace('Brother, ',(name+' Brother, ') if name else 'Brother, ',1)

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

def send_with_image(jid,caption,img):
 if img is None:
  req=urllib.request.Request('http://127.0.0.1:3000/send/message',data=json.dumps({'phone':jid,'message':caption}).encode(),headers={'X-Device-Id':DEVICE,'Content-Type':'application/json'},method='POST')
  with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)
 cap=DATA/('caption-'+uuid.uuid4().hex+'.txt');cap.write_text(caption,encoding='utf-8')
 r=subprocess.run(['curl','-s','--max-time','60','-X','POST','http://127.0.0.1:3000/send/image','-H',f'X-Device-Id: {DEVICE}','-F',f'phone={jid}','-F',f'image=@{img};type=image/jpeg','-F',f'caption=<{cap}','-F','compress=false'],capture_output=True)
 try:return json.loads(r.stdout)
 except Exception:return {'code':'ERROR','message':'Send not confirmed. Check WhatsApp before retrying.'}

def norm_phone(p):
 p=re.sub(r'[\s()+-]','',str(p))
 if p.startswith('00'):p=p[2:]
 if re.fullmatch(r'03\d{9}',p):p='92'+p[1:]
 return p if re.fullmatch(r'[1-9]\d{7,14}',p) else ''

def greet_text(text,name,gender):
 g=((name+' ') if name else '')+(gender if gender in ('Brother','Sister') else 'Brother')+', '
 return re.sub(r'^(?:[^\n,]{0,40}\s)?(?:Brother|Sister),\s',g,text,count=1) if re.match(r'^(?:[^\n,]{0,40}\s)?(?:Brother|Sister),\s',text) else g+text

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
   if STORE and STORE.get('dm_recipient_'+digest) and not p.get('again'):c['skipped']+=1;c['log'].append(f'Skipped …{phone[-4:]} (already messaged)');continue
   if not wa_ok():c['log'].append('WhatsApp disconnected. Stopped.');return
   base=build_dm([_random.randrange(len(a)) for a in DP],read_left()) if (vary or not message) else message
   text=greet_text(base,name,gender);c['current']=f'Sending to {(name+" ") if name else ""}{gender} …{phone[-4:]}'
   if STORE:STORE.put('dm_recipient_'+digest,{'state':'uncertain','time':time.time()})
   r=send_with_image(phone,text,img)
   if STORE:STORE.put('dm_recipient_'+digest,{'state':r.get('code','UNCERTAIN'),'time':time.time()})
   if r.get('code')!='SUCCESS':
    c['failed']+=1;c['log'].append(f'Failed …{phone[-4:]}: {str(r.get("message",""))[:80]}. Stopped to protect your number.');return
   c['sent']+=1;c['log'].append(f'✓ {(name+" ") if name else ""}{gender} …{phone[-4:]}')
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

ENGINE=autopilot.Engine({'DATA':DATA,'store_get':lambda k:STORE.get(k) if STORE else None,'persist':persist_file,'log':auto_log,
 'send_text':send_text,'owner_jid':lambda:OWNER_PHONE+'@s.whatsapp.net','enabled':auto_on,'read_left':read_left,'wa_ok':wa_ok,
 'busy':lambda:ACTIVE is not None,'last_sent':last_sent_by_key,'groups':lambda:list(GROUPS),'group_jids':lambda:{k:v[1] for k,v in GROUPS.items()},
 'caption':lambda:json.loads(DRAFT.read_text(encoding='utf-8')).get('group',''),'start_job':start_keys_job,'messages':group_messages,
 'donor_contacts':donor_contacts,'poster_left':poster_left,'already_dmed':already_dmed,'dm_text':dm_text,'send_dm':send_dm})

def engine_do():
 return {'pause_group':lambda key,hours:ENGINE.pause(key,hours),'resume_group':lambda key:ENGINE.resume(key),
  'set_quiet_hours':lambda start,end:ENGINE.set_quiet(start,end),'set_dms':lambda enabled,daily:ENGINE.set_dms(enabled,daily),
  'notify_owner':lambda text:(ENGINE.notify('ai-'+str(int(time.time())),text,0),'Owner told.')[1]}

PILOT=assistant.Autopilot(lambda:{**studio_state(),'autopilot':ENGINE.summary()},mem_get,engine_do,auto_log,auto_on)

class Handler(BaseHTTPRequestHandler):
 def remote_config(self):
  return {'key':os.environ.get('UI_ACCESS_KEY',''),'origins':[x for x in os.environ.get('ALLOWED_ORIGINS','').split(',') if x]}
 def authorized(self):
  key=self.remote_config().get('key','')
  return bool(key) and secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+key)
 def do_OPTIONS(self):
  self.reply({})
 def reply(self,data,kind='application/json',status=200):
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
  elif self.path.startswith('/autopilot'):self.reply({'on':auto_on(),'ai':bool(assistant.client()),'log':AUTOLOG[-20:],'summary':ENGINE.summary()})
  elif self.path=='/memory':self.reply(mem_get())
  elif self.path=='/campaign':self.reply({**{k:v for k,v in CAMPAIGN.items() if k!='stop'},'log':CAMPAIGN['log'][-8:],'wait':max(0,round(CAMPAIGN['next_at']-time.time()))})
  elif self.path=='/suggestions':self.reply({'items':ENGINE.suggestions(),'autopilot':auto_on(),'summary':ENGINE.summary()})
  elif self.path=='/groups':self.reply([{'key':k,'name':v[0]} for k,v in GROUPS.items()])
  elif self.path.startswith('/send-status/'):
   job=JOBS.get(self.path.split('/')[-1]);self.reply(job or {'error':'Unknown job'},status=200 if job else 404)
  elif self.path=='/':self.reply((ROOT/'index.html').read_bytes(),'text/html')
  else:self.reply({},status=404)
 def do_POST(self):
  global ACTIVE
  if not self.authorized():return self.reply({'error':'Access key required'},status=401)
  origin=self.headers.get('Origin');same_origin=origin and urllib.parse.urlparse(origin).netloc==self.headers.get('Host')
  if origin and not same_origin and origin not in self.remote_config().get('origins',[]):return self.reply({},status=403)
  try:body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
  except Exception:return self.reply({'error':'Invalid request'},status=400)
  if self.path=='/drafts':
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
    with urllib.request.urlopen('http://127.0.0.1:3000'+path,timeout=10) as qr:encoded=base64.b64encode(qr.read()).decode()
    self.reply({'qr':'data:image/png;base64,'+encoded,'duration':data['results'].get('qr_duration',30)})
   except Exception as e:self.reply({'error':'Could not get QR: '+str(e)},status=502)
  elif self.path=='/next-message':self.reply({'message':next_message()})
  elif self.path=='/next-dm':self.reply({'message':next_dm()})
  elif self.path=='/memory':self.reply({'reply':mem_add(body.get('rule',''))})
  elif self.path=='/autopilot':self.reply({'reply':set_auto(bool(body.get('on'))),'on':auto_on()})
  elif self.path=='/upload-image':
   try:self.reply({'id':save_upload(str(body.get('data','')),body.get('use','attachment'))})
   except Exception as e:self.reply({'error':str(e)[:120]},status=400)
  elif self.path=='/campaign':
   if body.get('stop'):CAMPAIGN['stop']=True;return self.reply({'reply':'Stopping the DM list.'})
   try:self.reply({'reply':start_campaign(body)})
   except Exception as e:self.reply({'error':str(e)[:160]},status=400)
  elif self.path=='/suggestion':
   msg=ENGINE.run_suggestion(str(body.get('action','')))
   if msg is None:return self.reply({'error':'This one is done from the screen or by you.'},status=400)
   self.reply({'reply':msg})
  elif self.path=='/autopilot-settings':
   a=str(body.get('action',''));key=str(body.get('key',''))
   if a in ('pause','resume') and key not in GROUPS:return self.reply({'error':'Unknown group. Use: '+', '.join(GROUPS)},status=400)
   try:
    msg=ENGINE.pause(key,float(body.get('hours',24))) if a=='pause' else ENGINE.resume(key) if a=='resume' else ENGINE.set_quiet(int(body.get('start',0)),int(body.get('end',0))) if a=='quiet' else ENGINE.set_dms(bool(body.get('enabled',True)),int(body.get('daily',30))) if a=='dms' else None
   except Exception as e:return self.reply({'error':str(e)[:120]},status=400)
   if msg is None:return self.reply({'error':'Unknown setting'},status=400)
   self.reply({'reply':msg,'summary':ENGINE.summary()})
  elif self.path=='/assistant':
   text=str(body.get('text',''))[:4000];CHAT_IMAGE['id']=body.get('image')
   if not text.strip():return self.reply({'error':'Type something first.'},status=400)
   try:out=assistant.chat(text,body.get('history',[]),{**studio_state(),'engine':ENGINE.summary(),'suggestions':[x['text'] for x in ENGINE.suggestions()],'screen':body.get('screen',{})},mem_get(),chat_callbacks())
   except Exception as e:return self.reply({'error':'The assistant could not answer: '+str(e)[:160]},status=502)
   if out is None:return self.reply({'error':'ai-off'},status=503)
   d=json.loads(DRAFT.read_text(encoding='utf-8'));out.update(group=d.get('group',''),dm=d.get('dm',''),left=read_left(),autopilot=auto_on());self.reply(out)
  elif self.path=='/left':
   try:left=int(body.get('left'))
   except Exception:return self.reply({'error':'Enter the amount as a number, like 34000.'},status=400)
   if not 0<=left<=10000000:return self.reply({'error':'Amount looks wrong.'},status=400)
   g,d=set_left(left);self.reply({'left':left,'group':g,'dm':d})
  elif self.path=='/send-group':
   key=body.get('group');caption=str(body.get('message',''))
   if key not in GROUPS and key not in ('all','free'):return self.reply({'error':'Unknown group'},status=400)
   if not caption.strip():return self.reply({'error':'Message is empty'},status=400)
   with LOCK:
    if ACTIVE:return self.reply({'error':'A group send is already running.'},status=409)
    job_id=uuid.uuid4().hex;ACTIVE=job_id;JOBS[job_id]={'done':False,'results':[],'message':'Starting…'}
   threading.Thread(target=run_job,args=(job_id,list(GROUPS) if key=='all' else FREELANCE if key=='free' else [key],caption),daemon=True).start();self.reply({'job_id':job_id})
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
 ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()
