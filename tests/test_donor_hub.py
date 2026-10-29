import copy,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from donor_book import DonorBook,normalize_phone,parse_contact,send_request
from donor_delivery import DonorDelivery

class Store:
 def __init__(self):self.data={}
 def get(self,k,d=None):return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)

class RegistryTests(unittest.TestCase):
 def setUp(self):self.folder=tempfile.TemporaryDirectory();self.store=Store();self.book=DonorBook(self.folder.name,self.store)
 def tearDown(self):self.folder.cleanup()
 def add(self,name='Ali',phone='03001234567'):return self.book.add(name,phone)['donor']
 def test_numbers_never_leave_public_views(self):
  d=self.add();self.book.update(d['id'],notes='call +92 300 1234567');raw=json.dumps(self.book.list(query='1234567'))
  self.assertNotIn('923001234567',raw);self.assertNotIn('1234567',raw);self.assertNotIn('phone',raw);self.assertIn('number_hidden',raw)
 def test_duplicates_normalize_and_do_not_replace_status(self):
  d=self.add();self.book.update(d['id'],important=True,donated=True,amount=2000)
  result=self.book.add('Other label','+92 (300) 123-4567');self.assertTrue(result['duplicate']);self.assertTrue(result['donor']['important']);self.assertEqual(self.book.list()['counts']['all'],1)
 def test_soft_delete_restore_and_persistence(self):
  d=self.add();self.book.delete(d['id']);self.assertEqual(self.book.list()['counts']['all'],0)
  self.book=DonorBook(self.folder.name,self.store);self.book.restore(d['id']);self.assertEqual(self.book.list()['items'][0]['name'],'Ali')
 def test_import_atomic_and_excludes_self(self):
  rows=[{'name':'Me','phone':'+923205069925'},{'name':'D99','phone':'+923001234567'}]
  self.assertEqual(self.book.import_contacts(rows,'923205069925')['added'],1)
  with self.assertRaises(ValueError):self.book.import_contacts([{'phone':'+923331234567'},{'phone':'bad'}],'923205069925')
  self.assertEqual(self.book.list()['counts']['all'],1)
 def test_status_tabs_and_important_sort(self):
  a=self.add('Zaid');b=self.add('Amina','03011234567');self.book.update(a['id'],important=True);self.book.update(b['id'],donated=True,amount=2000)
  self.assertEqual(self.book.list()['items'][0]['id'],a['id']);self.assertEqual(len(self.book.list('donated')['items']),1);self.assertEqual(self.book.list('not_donated')['items'][0]['id'],a['id'])
  self.assertEqual(self.book.list('important','Zaid')['counts']['donated_amount'],2000)
  self.book.delete(b['id']);self.assertEqual(self.book.list()['counts']['donated_amount'],0)
 def test_random_names_and_mixed_paste(self):
  for text in ('D25 / new label, 0300 1234567','+92 300 1234567\nD25 / new label'):
   name,phone=parse_contact(text);self.assertIn('D25',name);self.assertEqual(phone,'923001234567')
  self.assertEqual(self.add('Random 23')['name'],'Random 23')
 def test_ambiguous_names_rejected(self):
  self.add('Ali','03001234567');self.add('Ali','03011234567')
  with self.assertRaises(ValueError):self.book.resolve('Ali')
 def test_validation(self):
  for phone in ('abc','0300','123<script>','+0000000000'):
   with self.assertRaises(ValueError):normalize_phone(phone)
  d=self.add()
  for change in ({'important':'true'},{'amount':float('nan')},{'amount':-1},{'phone':'923331234567'}):
   with self.assertRaises(ValueError):self.book.update(d['id'],**change)
 def test_send_command_gaps_and_scope(self):
  for text,scope,gap in [('send to important donors with 2 minutes gap','important',120),('DM all donors 90 sec gap','all',90),('send to not donated donors 1 hour gap','not_donated',3600)]:
   r=send_request(text);self.assertEqual(r['scope'],scope);self.assertEqual(r['gap_seconds'],gap)
  self.assertFalse(send_request('send to important donors without poster')['poster'])
  for text in ('do not send donors','show donors','send donors tomorrow','send a more emotional caption to donors'):
   self.assertIsNone(send_request(text))

class DeliveryTests(RegistryTests):
 def setUp(self):
  super().setUp();self.sent=[];self.clock=1000.;self.contacted=set()
  self.jobs=DonorDelivery(self.folder.name,self.store,self.book,self.send,lambda:'saved **full**\n\nDM caption',lambda:True,lambda:False,lambda p:p not in self.contacted,lambda n:(n,'Brother'))
 def send(self,body):self.sent.append((body,self.clock));self.contacted.add(body['phone']);return {'code':'SUCCESS'}
 def run_job(self,result):
  job=self.jobs._load()['jobs'][-1]
  def wait(seconds):self.clock+=seconds;return False
  with patch('donor_delivery.time.time',side_effect=lambda:self.clock),patch.object(self.jobs.stop,'wait',side_effect=wait):self.jobs._run(job)
 def test_saved_caption_order_and_exact_minimum_gap(self):
  a=self.add('First','03001234567');b=self.add('Important','03011234567');self.book.update(b['id'],important=True)
  result=self.jobs.start('all',120,run=False);self.run_job(result)
  self.assertEqual([b[0]['name'] for b in self.sent],['Important','First']);self.assertGreaterEqual(self.sent[1][1]-self.sent[0][1],120)
  self.assertEqual(self.sent[0][0]['message'],'saved **full**\n\nDM caption');self.assertTrue(self.sent[0][0]['poster']);self.assertEqual(self.jobs.status()['sent'],2)
 def test_double_click_idempotency(self):
  self.add();a=self.jobs.start('all',60,request_id='same',run=False);b=self.jobs.start('all',60,request_id='same',run=False);self.assertEqual(a['job']['id'],b['job']['id']);self.assertEqual(len(self.jobs._load()['jobs']),1)
 def test_already_contacted_skips_and_deletion_skips(self):
  a=self.add();self.contacted.add('923001234567');r=self.jobs.start('all',run=False);self.run_job(r);self.assertFalse(self.sent);self.assertEqual(self.jobs.status()['skipped'],1)
  self.contacted.clear();r=self.jobs.start('all',run=False);self.book.delete(a['id']);self.run_job(r);self.assertFalse(self.sent)
 def test_uncertain_result_stops_without_retry(self):
  self.add();self.add('Other','03011234567');self.jobs.send=lambda b:{'code':'UNCERTAIN'};r=self.jobs.start('all',run=False);self.run_job(r);self.assertEqual(self.jobs.status()['failed'],1);self.assertEqual(self.jobs.status()['sent'],0);self.assertEqual(self.jobs.status()['state'],'Stopped')
 def test_restart_does_not_resume(self):
  self.add();self.jobs.start('all',run=False);new=DonorDelivery(self.folder.name,self.store,self.book,self.send,lambda:'caption',lambda:True,lambda:False,lambda p:True,lambda n:(n,'Brother'));self.assertEqual(new.status()['state'],'Interrupted');self.assertFalse(self.sent)
 def test_minimum_cap_and_no_phone_in_job(self):
  self.add();r=self.jobs.start('all',20,run=False);self.assertEqual(r['job']['gap_seconds'],60);self.assertNotIn('923001234567',json.dumps(r));self.assertNotIn('caption',r['job'])
 def test_cancellation(self):
  self.add();r=self.jobs.start('all',run=False);self.jobs.cancel();self.run_job(r);self.assertFalse(self.sent);self.assertEqual(self.jobs.status()['state'],'Stopped')

class IntegrationTests(unittest.TestCase):
 def setUp(self):
  from test_manual_sends import app,Store as AppStore
  self.app=app;app.STORE=AppStore();app.DONORS=None;app.CAMPAIGN.update(running=False,stop=False);app.HOLD.write_text('{"on":false}')
  self.scope=tempfile.TemporaryDirectory();(Path(self.scope.name)/'state.md').write_text('LEFT: 25000\n');self.data=patch.object(app,'DATA',Path(self.scope.name));self.data.start();self.api=patch.object(app,'api',return_value={'results':{'is_connected':True,'is_logged_in':True}});self.api.start()
 def tearDown(self):self.api.stop();self.data.stop();self.scope.cleanup();self.app.DONORS=None
 def test_chat_add_mark_donate_remove(self):
  app=self.app;r=app.manual_command('add donor Random23 0300 1234567','add-test');self.assertTrue(r['handled']);self.assertNotIn('1234567',json.dumps(r))
  app.manual_command('make Random23 important');self.assertEqual(app.donors().book.list('important')['counts']['important'],1)
  before=app.read_left();app.manual_command('mark Random23 donated 2000');self.assertEqual(app.read_left(),before);self.assertEqual(app.donors().book.list('donated')['items'][0]['amount'],2000)
  app.manual_command('remove donor Random23');self.assertEqual(app.donors().book.list()['counts']['all'],0)
 def test_model_cannot_invent_number_or_change_wrong_donor(self):
  app=self.app;d=app.donors().book.add('Ali','03001234567')['donor'];cb=app.chat_callbacks('add donor Ali 03001234567')
  with self.assertRaises(ValueError):cb['donor_action'](action='add',name='Ali',phone='03011234567')
  cb=app.chat_callbacks('make Zaid important')
  with self.assertRaises(ValueError):cb['donor_action'](action='update',id=d['id'],important=True)
  cb=app.chat_callbacks('show donors')
  with self.assertRaises(ValueError):cb['donor_action'](action='remove',id=d['id'],query='Ali')
  self.assertEqual(app.donors().personal_name('Random23')[0],'')
  self.assertEqual(app.donors().personal_name('Preview demo')[0],'')
  self.assertEqual(app.donors().personal_name('Ali Donor'),('Ali','Brother'))
  self.assertEqual(app.donors().personal_name('Ayesha Donor'),('Ayesha','Sister'))
 def test_http_auth_and_hidden_number_contract(self):
  import urllib.request,urllib.error
  app=self.app;http=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=http.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(http.server_port)
  try:
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/donors')
   self.assertEqual(error.exception.code,401)
   def request(path,body=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer test-only-studio-access-key'})
    with urllib.request.urlopen(req) as r:return json.load(r)
   request('/donors',{'action':'add','name':'Ali','phone':'03001234567'})
   result=request('/donors?q=1234567');self.assertEqual(len(result['items']),1);self.assertNotIn('1234567',json.dumps(result));self.assertEqual(request('/donor-delivery')['state'],'Idle')
  finally:http.shutdown();http.server_close()
 def test_registry_send_retains_daily_cap(self):
  app=self.app;day=app.datetime.datetime.fromtimestamp(time.time(),app.datetime.timezone(app.datetime.timedelta(hours=5))).date().isoformat();app.STORE.put('dm_daily',{'day':day,'count':50,'last':0})
  with self.assertRaisesRegex(ValueError,'50-DM'):app.send_custom({'target':'phone','phone':'03001234567','message':app.get_message('dm')['text'],'kind':'donor_registry','poster':True})
 def test_old_jid_receipt_blocks_new_send(self):
  import hashlib
  app=self.app;app.STORE.put('dm_recipient_'+hashlib.sha256(b'923001234567@s.whatsapp.net').hexdigest(),{'state':'uncertain'})
  # A deliberate new send is allowed even after an old uncertain receipt; automatic sends are not.
  self.assertTrue(app.donors().eligible('923001234567'))
  with self.assertRaisesRegex(ValueError,'contacted before'):app.send_custom({'target':'phone','phone':'03001234567','message':app.get_message('dm')['text'],'kind':'donor_registry','poster':True})
 def test_explicit_manual_repeats_send_now_and_same_request_does_not_repeat(self):
  app=self.app;registry=app.donors();d=registry.book.add('Ali','03001234567')['donor'];sent=[]
  def image(jid,text):sent.append((jid,text));return {'code':'SUCCESS','results':{'message_id':'fake-'+str(len(sent))}}
  with patch.object(app,'send_image',side_effect=image):
   first=registry.send_one(d['id'],'click-one-test');again=registry.send_one(d['id'],'click-two-test');duplicate=registry.send_one(d['id'],'click-two-test')
  self.assertEqual(len(sent),2);self.assertEqual(first['code'],'SUCCESS');self.assertEqual(again['code'],'SUCCESS');self.assertTrue(duplicate['repeated_request']);self.assertEqual(registry.book.resolve(d['id'])['delivery'],'Sent');self.assertEqual(sent[0][1],sent[1][1]);self.assertIn('03097458815',sent[0][1]);self.assertGreater(registry.jobs.manual_sent_at,0)
 def test_explicit_repeat_still_respects_optout_and_daily_cap(self):
  import hashlib
  app=self.app;registry=app.donors();d=registry.book.add('Ali','03001234567')['donor'];app.STORE.put('optout_'+hashlib.sha256(b'923001234567').hexdigest(),True)
  with patch.object(app,'send_image') as image:
   with self.assertRaisesRegex(ValueError,'opted out'):registry.send_one(d['id'],'blocked-click-test')
   image.assert_not_called()
 def test_failed_manual_send_does_not_show_sent(self):
  app=self.app;registry=app.donors();d=registry.book.add('Ali','03001234567')['donor']
  with patch.object(app,'send_image',return_value={'code':'UNCERTAIN'}):result=registry.send_one(d['id'],'uncertain-click-test')
  self.assertEqual(result['code'],'UNCERTAIN');self.assertEqual(registry.book.resolve(d['id'])['delivery'],'Uncertain')

if __name__=='__main__':unittest.main()

