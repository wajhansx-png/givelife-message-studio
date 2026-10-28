"""Local full-stack preview. Every WhatsApp request goes to a fake server."""
import os,sys,tempfile,json,threading,shutil,time
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
EVENTS=ROOT.parent/'manual-preview-events.json';events=[]
def record(item):
 events.append(item);EVENTS.write_text(json.dumps(events,ensure_ascii=False),encoding='utf-8')
class FakeWhatsApp(BaseHTTPRequestHandler):
 def response(self,data):
  body=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if '/status' in self.path:return self.response({'code':'SUCCESS','results':{'is_connected':True,'is_logged_in':True}})
  if '/messages' in self.path:return self.response({'results':{'data':[]}})
  if '/chats' in self.path or '/contacts' in self.path:return self.response({'results':{'data':[{'id':'923001234567@s.whatsapp.net','name':'Jr Accounts','is_group':False}]}})
  return self.response({'results':[]})
 def do_POST(self):
  raw=self.rfile.read(int(self.headers.get('Content-Length',0)));fields={}
  if 'multipart/form-data' in self.headers.get('Content-Type',''):
   msg=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
   for part in msg.iter_parts():
    name=part.get_param('name',header='content-disposition')
    if name!='image':fields[name]=part.get_payload(decode=True).decode('utf-8')
  else:
   try:fields=json.loads(raw)
   except Exception:fields={}
  record({'path':self.path,'fields':fields,'time':time.time()})
  self.response({'code':'SUCCESS','results':{'message_id':'fake-message-'+str(len(events))}})
 def log_message(self,*args):pass
fake=ThreadingHTTPServer(('127.0.0.1',0),FakeWhatsApp);threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ.pop('DB_URI',None);os.environ.pop('RENDER_EXTERNAL_URL',None);os.environ.pop('DEEPSEEK_API_KEY',None)
os.environ.update(GOWA_URL='http://127.0.0.1:'+str(fake.server_port),UI_ACCESS_KEY='manual-fix-preview-key',WHATSAPP_DEVICE_ID='fake-device')
folder=tempfile.TemporaryDirectory();os.environ['DATA_DIR']=folder.name
for name in ('drafts.json','state.md'):shutil.copyfile(ROOT/name,Path(folder.name)/name)
poster=ROOT.parent/'cloud-service/poster.jpg'
(Path(folder.name)/'poster.jpg').write_bytes(poster.read_bytes() if poster.exists() else b'fake-poster')
import server
class Store:
 def __init__(self):self.data={};self.lock=threading.RLock()
 def get(self,k,d=None):
  import copy
  with self.lock:return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):
  import copy
  with self.lock:self.data[k]=copy.deepcopy(v)
server.STORE=Store();server.set_left(25000);server.ENGINE.s['dm_enabled']=False
if '--donors' in sys.argv:
 for i in range(20):
  row=server.donors().book.add('Demo donor '+str(i+1),'1555'+str(1230000+i))['donor']
  if i<3:server.donors().book.update(row['id'],important=True)
if '--draft-task' in sys.argv:
 text='*A short charity reminder.*\nYousuf needs treatment. *Rs. 25,000 left.* 💔\n*03097458815* Easypaisa / JazzCash (Wajdan Khan)'
 server.chat_callbacks('Make a message for givelife without poster only 3 lines',revision=server.OWNER_REVISION)['set_message'](kind='group',text=text)
# No engine/background AI loops are started. The only sends are explicit preview actions.
server.Handler.log_message=lambda *a:None
original_get=server.Handler.do_GET
def preview_get(self):
 if self.path=='/mobile-preview':return self.reply((ROOT/'tests/mobile_preview.html').read_bytes(),'text/html')
 return original_get(self)
server.Handler.do_GET=preview_get
http=ThreadingHTTPServer(('127.0.0.1',3003),server.Handler)
print('Local fake-WhatsApp preview: http://127.0.0.1:3003/ (no real messages possible)',flush=True)
http.serve_forever()

