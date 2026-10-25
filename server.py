import json, subprocess, urllib.request, urllib.parse, threading, time, uuid, datetime, math, re, secrets, os, base64
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from persist import configured_store
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('DATA_DIR','/data/studio'))
DATA.mkdir(parents=True,exist_ok=True)
DRAFT=DATA/'drafts.json'
DEVICE=os.environ.get('WHATSAPP_DEVICE_ID','')
GROUPS={'community':('Upwork Community 2026','120363398623589385@g.us'),'fiverr':('Fiverr Course 2026','120363411617215937@g.us'),'upwork':('Upwork Course 2026','120363430624868021@g.us'),'uet':('Fiverr Course UET','120363412286860707@g.us'),'toprated':('Top Rated Upworkers','120363427826119453@g.us')}
JOBS={};LOCK=threading.Lock();SEND_LOCK=threading.Lock();ACTIVE=None
STORE=configured_store()
def persist_file(key,path):
 if STORE:STORE.put(key,path.read_text(encoding='utf-8'))

def api(path):
 req=urllib.request.Request('http://127.0.0.1:3000'+path,headers={'X-Device-Id':DEVICE})
 with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)

def next_message():
 with LOCK:
  file=DATA/'variant-state.json';n=json.loads(file.read_text()).get('index',0) if file.exists() else 0
  file.write_text(json.dumps({'index':n+1}));persist_file('variants',file)
  state=(DATA/'state.md').read_text(encoding='utf-8-sig');match=re.search(r'^LEFT:\s*(\d+)',state,re.M);left=int(match[1]) if match else 39000
  openings=['💔 *Yousuf is only 2. His treatment needs our support.*','🤲 *A small contribution can help close a serious treatment gap.*','⚠️ *Yousuf faces the risk of paralysis and damage to his eyesight.*','💔 *At 2 years old, Yousuf needs help getting treatment.*','🤲 *Can we come together for Yousuf today?*','⚠️ *The risks to Yousuf are serious. Every contribution matters.*','💔 *One donation brings Yousuf closer to the treatment he needs.*']
  facts=["_Fluid in his brain can paralyse his body and damage his eyesight. Both kidneys are badly swollen, and he also has a hernia._","_Fluid in Yousuf’s brain can cause paralysis and damage his eyesight. Both kidneys are badly swollen, and he has a hernia._","_Yousuf has fluid in his brain, swelling in both kidneys, and a hernia. The brain fluid can paralyse his body and damage his eyesight._"]
  asks=['*Could you give Rs. 1,000 or Rs. 2,000 today?* Even a smaller amount helps. 🤲','*Will you be one of the people who helps cover his treatment?* Your contribution matters. 🤲','*Please help with whatever you can today.* Together, small donations can cover the gap. 🤲','*If you can contribute, please take that step today.* Thank you for helping Yousuf. 🤲','*Can you help bring the remaining amount down?* Rs. 1,000 or Rs. 2,000 would make a difference. 🤲']
  text=f'{openings[n%7]}\n\n{facts[(n//7)%3]}\n\n💰 *_Rs. {left:,} LEFT_*\n\n* *_{math.ceil(left/2000)} people giving Rs. 2,000 or {math.ceil(left/1000)} giving Rs. 1,000 can cover what remains._*\n\n{asks[(n//3)%5]}\n\n📲 *03097458815*\nEasypaisa / JazzCash: Wajdan Khan\nFor GiveLife Foundation\n\nReply *Done* after donating.'
  draft=json.loads(DRAFT.read_text(encoding='utf-8'));draft['group']=text;DRAFT.write_text(json.dumps(draft,ensure_ascii=False),encoding='utf-8');persist_file('drafts',DRAFT);return text

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
  elif self.path=='/wa-login':
   try:
    data=api('/devices/'+DEVICE+'/login');url=data.get('results',{}).get('qr_link','');path=urllib.parse.urlparse(url).path
    if not path.startswith('/statics/qrcode/'):return self.reply({'error':'QR not available; check connection.'},status=400)
    with urllib.request.urlopen('http://127.0.0.1:3000'+path,timeout=10) as qr:encoded=base64.b64encode(qr.read()).decode()
    self.reply({'qr':'data:image/png;base64,'+encoded,'duration':data['results'].get('qr_duration',30)})
   except Exception as e:self.reply({'error':'Could not get QR: '+str(e)},status=502)
  elif self.path=='/next-message':self.reply({'message':next_message()})
  elif self.path=='/send-group':
   key=body.get('group');caption=str(body.get('message',''))
   if key not in GROUPS and key!='all':return self.reply({'error':'Unknown group'},status=400)
   if not caption.strip():return self.reply({'error':'Message is empty'},status=400)
   with LOCK:
    if ACTIVE:return self.reply({'error':'A group send is already running.'},status=409)
    job_id=uuid.uuid4().hex;ACTIVE=job_id;JOBS[job_id]={'done':False,'results':[],'message':'Starting…'}
   threading.Thread(target=run_job,args=(job_id,list(GROUPS) if key=='all' else [key],caption),daemon=True).start();self.reply({'job_id':job_id})
  elif self.path=='/test':
   caption=str(body.get('message',''))
   if not caption.strip():return self.reply({'error':'Message is empty'},status=400)
   try:
    with SEND_LOCK:result=send_image('120363431210327603@g.us',caption)
    self.reply(result)
   except Exception as e:self.reply({'code':'ERROR','message':str(e)})
  else:self.reply({},status=404)
 def log_message(self,*args):pass
if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()

