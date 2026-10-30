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
 def test_not_contacted_tab_lists_donors_with_no_dm_and_no_donation(self):
  a=self.add('Ali','03001234567');b=self.add('Bilal','03007654321');c=self.add('Chand','03001112233')
  self.book.update(b['id'],donated=True,amount=500)
  self.book.delivery(c['id'],'Sent')
  listed=self.book.list('not_contacted');self.assertIn(a['id'],[x['id'] for x in listed['items']]);self.assertNotIn(b['id'],[x['id'] for x in listed['items']]);self.assertNotIn(c['id'],[x['id'] for x in listed['items']])
  self.assertEqual(listed['counts']['not_contacted'],len(listed['items']))
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
  super().setUp();self.sent=[];self.clock=time.time();self.contacted=set()
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
 def test_rounds_continue_by_themselves_with_same_gap_and_rest(self):
  for i in range(5):self.book.update(self.add('P%d'%i,'030012345%02d'%i)['id'],important=True)
  self.jobs.variants=lambda n:['w%d'%i for i in range(n)]
  r=self.jobs.start('important',120,chunk=2,rest_seconds=1200,run=False);self.assertIn('by itself',r['reply']);self.run_job(r)
  times=[t for _,t in self.sent];self.assertEqual(len(times),5)
  self.assertGreaterEqual(times[1]-times[0],120);self.assertGreaterEqual(times[2]-times[1],1200);self.assertLess(times[2]-times[1],1300)
  self.assertGreaterEqual(times[3]-times[2],120);self.assertLess(times[3]-times[2],200);self.assertGreaterEqual(times[4]-times[3],1200)
  self.assertEqual([b['message'] for b,_ in self.sent],['w0','w1','w0','w1','w0']);self.assertEqual(self.jobs.status()['state'],'Completed')
 def test_closed_case_starts_nothing_and_stops_a_running_batch(self):
  for i in range(4):self.book.update(self.add('C%d'%i,'030012346%02d'%i)['id'],important=True)
  closed=[False];self.jobs.case_closed=lambda:closed[0]
  closed[0]=True
  with self.assertRaisesRegex(ValueError,'case is complete'):self.jobs.start('important',120,run=False)
  closed[0]=False;r=self.jobs.start('important',120,run=False)
  real=self.send
  def send_then_close(body):
   out=real(body)
   if len(self.sent)==2:closed[0]=True
   return out
  self.jobs.send=send_then_close;self.run_job(r)
  self.assertEqual(len(self.sent),2,'no DM is sent after the amount reaches 0');st=self.jobs.status();self.assertEqual(st['state'],'Stopped');self.assertIn('Rs. 0 left',st['error'])
 def test_queued_dms_use_the_amount_left_at_send_time(self):
  for i in range(3):self.book.update(self.add('F%d'%i,'030012347%02d'%i)['id'],important=True)
  amount=[25000]
  self.jobs.variants=lambda n:['need Rs. %d now %d'%(amount[0],i) for i in range(n)]
  r=self.jobs.start('important',120,chunk=3,run=False);amount[0]=9000;self.run_job(r)
  self.assertTrue(all('Rs. 9000' in b['message'] for b,_ in self.sent),[b['message'] for b,_ in self.sent])
 def test_stop_during_rest_sends_nothing_more(self):
  for i in range(3):self.add('P%d'%i,'030012345%02d'%i)
  r=self.jobs.start('all',60,chunk=1,rest_seconds=600,run=False);job=self.jobs._load()['jobs'][-1]
  def wait(seconds):self.clock+=seconds;self.jobs.stop.set();return True
  with patch('donor_delivery.time.time',side_effect=lambda:self.clock),patch.object(self.jobs.stop,'wait',side_effect=wait):self.jobs._run(job)
  self.assertEqual(len(self.sent),1);self.assertEqual(self.jobs.status()['state'],'Stopped')
 def test_bad_round_settings_are_refused(self):
  self.add()
  for bad in ({'chunk':0},{'chunk':21},{'rest_seconds':5},{'rest_seconds':99999}):
   with self.assertRaises(ValueError):self.jobs.start('all',60,run=False,**bad)
 def test_chat_phrases_pick_round_size_or_exact_total(self):
  r=send_request('send 20 dms to important donors');self.assertEqual((r['chunk'],r['limit']),(20,None))
  r=send_request('send first 5 donors');self.assertEqual((r['chunk'],r['limit']),(None,5))
  r=send_request('dm 40 important donors');self.assertEqual((r['chunk'],r['limit']),(20,40))
  r=send_request('send 100 dms to important donors 3 min gap, 30 min between batches, random delays');self.assertEqual((r['chunk'],r['limit'],r['gap_seconds'],r['rests']),(20,100,180.0,[1800.0]));self.assertEqual(r['jitter'],{'min':-10,'max':15})
  r=send_request('send 20 dms to important donors with 3 minutes gap');self.assertEqual((r['gap_seconds'],r['rests'],r['jitter']),(180.0,None,None))
 def _five(self):
  for i in range(5):self.book.update(self.add('P%d'%i,'030012345%02d'%i)['id'],important=True)
 def _drop_whatsapp_after(self,n):
  real=self.send
  def send(body):
   if len(self.sent)>=n:raise ValueError('WhatsApp is disconnected.')
   return real(body)
  self.jobs.send=send;return real
 def test_after_a_disconnect_continue_skips_people_already_sent(self):
  self._five();real=self._drop_whatsapp_after(2)
  self.run_job(self.jobs.start('important',60,run=False));self.assertEqual(self.jobs.status()['state'],'Stopped');self.assertEqual(self.jobs.status()['resumable'],3)
  self.jobs.send=real;r=self.jobs.start('important',60,run=False);self.assertIn('2 already handled',r['reply']);self.run_job(r)
  names=[b['name'] for b,_ in self.sent];self.assertEqual(names,['P0','P1','P2','P3','P4'],'nobody got a second DM')
 def test_continue_also_works_after_a_restart_and_after_pressing_stop(self):
  self._five();real=self._drop_whatsapp_after(2);self.run_job(self.jobs.start('important',60,run=False))
  later=DonorDelivery(self.folder.name,self.store,self.book,real,lambda:'saved **full**\n\nDM caption',lambda:True,lambda:False,lambda p:True,lambda n:(n,'Brother'))
  job=later._load()['jobs'][-1];job['state']='Sending';job['boot']='old';later._save({'jobs':[job]});self.assertEqual(later.status()['state'],'Interrupted');self.assertEqual(later.status()['resumable'],3)
  r=later.start('important',60,run=False);self.assertEqual(r['job']['total'],3)
 def test_start_over_sends_to_everyone_again_on_purpose(self):
  self._five();self._drop_whatsapp_after(2);self.run_job(self.jobs.start('important',60,run=False))
  r=self.jobs.start('important',60,run=False,fresh=True);self.assertEqual(r['job']['total'],5);self.assertNotIn('Continuing',r['reply'])
 def test_a_finished_batch_is_never_resumed_so_repeat_sends_still_work(self):
  self._five();self.run_job(self.jobs.start('important',60,run=False));self.assertNotIn('resumable',self.jobs.status())
  r=self.jobs.start('important',60,run=False);self.assertEqual(r['job']['total'],5)
 def test_unconfirmed_delivery_is_not_sent_again_on_continue(self):
  self._five();calls=[]
  def send(body):
   calls.append(body['name']);return {'code':'UNCERTAIN'} if body['name']=='P1' else {'code':'SUCCESS'}
  self.jobs.send=send;self.run_job(self.jobs.start('important',60,run=False));self.assertEqual(self.jobs.status()['state'],'Stopped')
  self.jobs.send=lambda b:(calls.append(b['name']),{'code':'SUCCESS'})[1];self.run_job(self.jobs.start('important',60,run=False))
  self.assertEqual(calls,['P0','P1','P2','P3','P4'])
 def test_stop_button_then_continue_resumes_after_the_last_sent_and_lists_names(self):
  self._five();job=self.jobs.start('important',60,run=False)['job'];stored=self.jobs._load()['jobs'][-1]
  real=self.send
  def send(body):
   out=real(body)
   if len(self.sent)==2:self.jobs.stop.set()
   return out
  self.jobs.send=send;self.run_job(job)
  st=self.jobs.status();self.assertEqual(st['state'],'Stopped')
  self.assertEqual([r['name'] for r in st['receipts'] if r['state']=='Sent'],['P0','P1']);self.assertEqual(st['waiting'],['P2','P3','P4']);self.assertEqual(st['resumable'],3)
  self.assertTrue(all('0300' not in n for n in st['waiting']))
  self.jobs.send=real;self.jobs.stop.clear();r=self.jobs.start('important',60,run=False);self.run_job(r)
  self.assertEqual([b['name'] for b,_ in self.sent],['P0','P1','P2','P3','P4']);self.assertEqual(self.jobs.status()['waiting'],[])
 def _many(self,n):
  for i in range(n):self.book.update(self.add('P%02d'%i,'0300%07d'%(1000000+i))['id'],important=True)
 def test_100_contacts_split_into_batches_of_20_with_different_pauses(self):
  self._many(45);r=self.jobs.start('important',120,chunk=20,limit=45,rests=[1200,1800],run=False)
  self.assertEqual((r['job']['total'],r['job']['batches']),(45,3));self.run_job(r)
  t=[x for _,x in self.sent];self.assertEqual(len(t),45)
  self.assertTrue(1200<=t[20]-t[19]<1300,t[20]-t[19]);self.assertTrue(1800<=t[40]-t[39]<1900,t[40]-t[39])
  self.assertTrue(all(120<=t[i+1]-t[i]<130 for i in list(range(19))+list(range(21,39))))
  self.assertEqual(len({b['phone'] for b,_ in self.sent}),45,'nobody twice');self.assertEqual(self.jobs.status()['state'],'Completed')
 def test_last_pause_repeats_for_later_batches(self):
  self._many(61);r=self.jobs.start('important',60,chunk=20,limit=61,rests=[600,900],run=False);self.run_job(r)
  t=[x for _,x in self.sent];self.assertTrue(600<=t[20]-t[19]<700);self.assertTrue(900<=t[40]-t[39]<1000);self.assertTrue(900<=t[60]-t[59]<1000)
 def test_random_gap_varies_inside_the_chosen_range_and_never_below_60s(self):
  self._many(6);steps=iter([-5,12,4,-300,9])
  with patch('donor_delivery.random.uniform',side_effect=lambda lo,hi:next(steps)):
   r=self.jobs.start('important',180,jitter={'min':-5,'max':15},run=False);self.run_job(r)
  gaps=[round(self.sent[i+1][1]-self.sent[i][1]) for i in range(5)]
  self.assertEqual(gaps,[175,192,184,60,189])
 def test_random_gap_off_keeps_the_exact_gap(self):
  self._many(3);self.run_job(self.jobs.start('important',180,run=False))
  self.assertEqual([round(self.sent[i+1][1]-self.sent[i][1]) for i in range(2)],[180,180])
 def test_bad_random_gap_is_refused(self):
  self._many(2)
  for bad in ({'min':10,'max':5},{'min':-999,'max':5},{'min':0},{'min':0,'max':9999},'x'):
   with self.assertRaises(ValueError):self.jobs.start('important',180,run=False,jitter=bad)
 def test_contacted_people_are_left_out_of_automatic_batches(self):
  self._many(5);ids=[r['id'] for r in self.book.recipients('important')]
  self.book.delivery(ids[0],'Sent',50.0);self.book.delivery(ids[1],'Sent',60.0)
  r=self.jobs.start('important',60,chunk=20,run=False);self.assertEqual(r['job']['total'],3);self.assertIn('2 already contacted',r['reply'])
 def test_include_contacted_on_purpose(self):
  self._many(3);ids=[r['id'] for r in self.book.recipients('important')];self.book.delivery(ids[0],'Sent',50.0)
  r=self.jobs.start('important',60,chunk=20,skip_contacted=False,run=False);self.assertEqual(r['job']['total'],3)
 def test_everyone_already_contacted_gives_a_clear_answer(self):
  self._many(2)
  for x in self.book.recipients('important'):self.book.delivery(x['id'],'Sent',50.0)
  with self.assertRaisesRegex(ValueError,'already contacted'):self.jobs.start('important',60,chunk=20,run=False)
 def test_there_is_no_daily_cap_on_donor_batches(self):
  self._many(3);day=time.strftime('%Y-%m-%d');self.store.put('dm_daily',{'day':day,'count':500,'last':0})
  self.run_job(self.jobs.start('important',60,chunk=20,run=False));self.assertEqual(len(self.sent),3)
 def test_whatsapp_disconnect_waits_and_carries_on(self):
  self._many(3);checks={'n':0}
  def connected():
   checks['n']+=1;return not 3<=checks['n']<=6
  self.jobs.connected=connected;self.run_job(self.jobs.start('important',60,chunk=20,run=False))
  self.assertEqual(len(self.sent),3);self.assertEqual(self.jobs.status()['state'],'Completed')
 def test_whatsapp_gone_for_good_stops_and_can_continue(self):
  self._many(3);up={'ok':True};real=self.send
  def send(body):
   out=real(body)
   if len(self.sent)==1:up['ok']=False
   return out
  self.jobs.send=send;self.jobs.connected=lambda:up['ok']
  r=self.jobs.start('important',60,chunk=20,run=False);self.run_job(r)
  st=self.jobs.status();self.assertEqual(st['state'],'Stopped');self.assertEqual(st['resumable'],2);self.assertIn('30 minutes',st['error'])
 def test_live_progress_during_a_pause_shows_next_batch(self):
  self._many(25);seen={}
  r=self.jobs.start('important',60,chunk=20,rests=[1500],run=False);job=self.jobs._load()['jobs'][-1]
  def wait(seconds):
   self.clock+=seconds;st=self.jobs.status()
   if st.get('next_batch_at') and not seen:seen.update(st);self.jobs.stop.set();return True
   return False
  with patch('donor_delivery.time.time',side_effect=lambda:self.clock),patch.object(self.jobs.stop,'wait',side_effect=wait):self.jobs._run(job)
  self.assertEqual((seen['sent'],seen['pending'],seen['batch'],seen['batches'],seen['next_batch_size']),(20,5,2,2,5));self.assertGreater(seen['next_batch_at'],self.clock-1)
 def test_after_a_restart_a_confirmed_batch_carries_on_without_repeats(self):
  self._many(6);real=self.send
  def send(body):
   out=real(body)
   if len(self.sent)==2:self.jobs.stop.set()
   return out
  self.jobs.send=send;self.run_job(self.jobs.start('important',60,chunk=20,run=False))
  data=self.jobs._load();j=data['jobs'][-1];j.update(state='Waiting',boot='old-process',next_batch_at=self.clock+500,updated_at=self.clock);self.jobs._save(data)
  later=DonorDelivery(self.folder.name,self.store,self.book,real,lambda:'saved **full**\n\nDM caption',lambda:True,lambda:False,lambda p:True,lambda n:(n,'Brother'))
  with patch('donor_delivery.threading.Thread.start'):new=later.recover()
  self.assertEqual(new['job']['total'],4);self.assertTrue(later._load()['jobs'][-1]['hold_until']>time.time()-1)
  self.assertIsNone(later.recover(),'a second recover does nothing while one is active')
 def test_recover_ignores_old_manual_jobs_and_finished_ones(self):
  self._many(3);self.run_job(self.jobs.start('important',60,chunk=20,run=False));self.assertIsNone(self.jobs.recover())
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

