import copy, importlib, json, os, sys, tempfile, threading, time, types, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BOOT=tempfile.TemporaryDirectory()
os.environ.pop('DB_URI',None);os.environ.pop('DEEPSEEK_API_KEY',None)
os.environ['DATA_DIR']=BOOT.name;os.environ['UI_ACCESS_KEY']='test-only-studio-access-key'
for name in ('drafts.json','state.md'):(Path(BOOT.name)/name).write_bytes((ROOT/name).read_bytes())
(Path(BOOT.name)/'poster.jpg').write_bytes(b'fake-poster')
import server as app, manual_commands as commands

class Store:
 def __init__(self):self.data={};self.lock=threading.RLock()
 def get(self,k,d=None):
  with self.lock:return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):
  with self.lock:self.data[k]=copy.deepcopy(v)

class CommandTests(unittest.TestCase):
 def test_transcript_commands(self):
  cases={'resend now to givelife with 25k':'appeal','send now':'repeat','in givelife froup send':'appeal','man send now':'repeat','send and restart gap':'repeat','in givelife send message now poster + message with updated amount':'appeal','now send':'repeat','dont send dm':'stop_dms','send message in givelife now':'appeal','25000':'amount','25k is remaining':'amount','updated amount is 25k':'amount','send now to givelife main':'appeal','delete message from gruo':'delete'}
  for text,kind in cases.items():
   with self.subTest(text=text):self.assertEqual(commands.parse(text)['kind'],kind)
 def test_specific_group_wins(self):
  self.assertEqual(commands.group('fiverr course uet'),'uet')
  self.assertEqual(commands.group('Upwork Community 2026'),'community')
  self.assertEqual(commands.group('give life foundation'),'main')
 def test_literals_and_negative_commands(self):
  self.assertEqual(commands.parse('send hi to Ali')['text'],'hi')
  self.assertEqual(commands.parse('send "now" to Ali')['text'],'now')
  self.assertIsNone(commands.parse('do not send to givelife'))
  self.assertIsNone(commands.parse('did you send it to givelife?'))
  self.assertIsNone(commands.parse('send to givelife at 6pm'))
 def test_command_parser_under_one_second(self):
  start=time.perf_counter()
  for _ in range(1000):commands.parse('in givelife send message now poster + message with updated amount')
  elapsed=time.perf_counter()-start
  self.assertLess(elapsed/1000,.01)

class SendTests(unittest.TestCase):
 def setUp(self):
  self.gowa=patch.object(app,'GOWA_URL','http://127.0.0.1:1');self.gowa.start()
  app.cancel_jobs('test reset')
  app.STORE=Store();app.KNOWLEDGE=app.Knowledge(app.DATA,app.STORE);app.KNOWLEDGE.data={'entries':[],'turns':[],'feedback':[],'traces':[],'pending':{}};app.JOBS.clear();app.JOB_CANCEL.clear();app.REQUEST_JOBS.clear();app.ACTIVE=None;app.LAST_LOCAL.clear();app.LAST_MANUAL.clear();app.DELIVERIES.clear();app.LAST_RECIPIENT.clear();app.LAST_JOB.clear();app.OWNER_REVISION=0
  app.HOLD.write_text('{"on":false}');app.AUTO.write_text('{"on":false}');app.CAMPAIGN.update(running=False,stop=False)
  app.MEMORY.write_text('[]',encoding='utf-8')
  app.DM_NAMES.clear();app.CONTACT_CONTEXT.clear();app.set_left(25000)
  # Ten synthetic saved Group-tab variants, never sent outside the fake transport.
  source=app.get_message('group')['text']
  app.STORE.put('focus_wording',{'group':{'source':source,'revision':'fixture-bank','items':[f'*Version {i:02d}*\n'+source for i in range(1,11)],'state':'Ready'}})
  self.sent=[];self.status_connected=True;self.status_recent=False
  def api(path):
   if '/status' in path:return {'results':{'is_connected':self.status_connected,'is_logged_in':self.status_connected}}
   if '/messages' in path:return {'results':{'data':[{'id':'recent','is_from_me':True,'timestamp':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}] if self.status_recent else []}}
   return {'results':[]}
  self.api=patch.object(app,'api',api);self.api.start()
  def curl(args,**kwargs):
   fields=[args[i+1] for i,x in enumerate(args) if x=='-F'];phone=next(x.split('=',1)[1] for x in fields if x.startswith('phone='));caption=next(x[len('caption=<'):] for x in fields if x.startswith('caption=<'))
   self.sent.append({'phone':phone,'text':Path(caption).read_text(encoding='utf-8')})
   return types.SimpleNamespace(stdout=json.dumps({'code':'SUCCESS','results':{'message_id':'fake-'+str(len(self.sent))}}).encode())
  self.curl=patch.object(app.subprocess,'run',curl);self.curl.start()
 def tearDown(self):
  app.cancel_jobs('test complete')
  deadline=time.monotonic()+2
  while any(not x.get('done') for x in app.JOBS.values()) and time.monotonic()<deadline:time.sleep(.005)
  self.curl.stop();self.api.stop();self.gowa.stop()
 def wait(self,ident,seconds=2):
  end=time.monotonic()+seconds
  while not app.JOBS[ident]['done'] and time.monotonic()<end:time.sleep(.005)
  self.assertTrue(app.JOBS[ident]['done'],app.JOBS[ident]);return app.JOBS[ident]
 def test_send_exact_thanks_to_registered_teammate_by_name(self):
  teammate={'member':{'name':'Akhtar','phone':'923001234567'}}
  with patch.object(app.donors().team,'_load',return_value=teammate),patch.object(app,'send_with_image',return_value={'code':'SUCCESS','results':{'message_id':'fake'}}) as wire:
   self.assertEqual(app.resolve_person('Akhtar'),'923001234567@s.whatsapp.net')
   self.assertEqual(app.manual_command('Send thanks akhtar to Akhtar fast')['reply'],'WhatsApp confirmed the message.')
  self.assertEqual(wire.call_count,1)
  self.assertEqual(wire.call_args.args[0],'923001234567@s.whatsapp.net')
  self.assertEqual(wire.call_args.args[1],'thanks akhtar')
  self.assertIsNone(wire.call_args.args[2])
 def test_emergency_hold_typo_works_without_ai(self):
  result=app.manual_command('Hold evverything')
  self.assertTrue(app.on_hold())
  self.assertIn('On hold',result['reply'])
  self.assertEqual(self.sent,[])
 def test_post_in_all_every_15_min_enables_auto_for_open_case(self):
  app.set_left(25000)
  with patch.object(app,'wa_ok',return_value=True):
   result=app.manual_command('Post in all every 15 min')
  self.assertTrue(app.auto_on(),result)
  self.assertIn('Auto ON',result['reply'])
  self.assertTrue(any(r.get('kind')=='gap' and r.get('group')=='all' and r.get('minutes')==15 for r in app.ENGINE.rules()))
  self.assertEqual(self.sent,[],'A recurring-post command must not claim a manual send')
 def test_closed_case_refuses_recurring_appeal_and_preserves_auto_state(self):
  app.set_left(0)
  before=len(app.ENGINE.rules())
  with patch.object(app,'wa_ok',return_value=True):
   with self.assertRaisesRegex(ValueError,'case is complete'):
    app.manual_command('Post in all every 15 min')
  self.assertEqual(len(app.ENGINE.rules()),before)
  self.assertFalse(app.auto_on())
  self.assertEqual(self.sent,[])
 def test_schedule_setting_only_does_not_start_auto(self):
  app.set_left(25000)
  app.manual_command('all groups every 15 min')
  self.assertFalse(app.auto_on())
  self.assertEqual(self.sent,[])
 def test_compound_explicit_commands_are_not_truncated_to_one_fast_action(self):
  text='send "Hello" to 03001234567 and then send "Thanks" to 03007654321'
  result=app.manual_command(text)
  self.assertFalse(result.get('handled'),result)
  self.assertEqual(self.sent,[])
 def test_two_separate_quoted_texts_keep_correct_phone_and_payload(self):
  text='send "Hello" to 03001234567 and then send "Thanks" to 03007654321'
  sent=[]
  with patch.object(app,'send_free',side_effect=lambda to,message,pic,literal=False:sent.append((to,message)) or 'Sent.'):
   cb=app.chat_callbacks(text,revision=app.OWNER_REVISION)
   cb['send_message'](to='03001234567',text='wrong')
   cb['send_message'](to='03007654321',text='wrong')
  self.assertEqual([x[1] for x in sent],['Hello','Thanks'])
  self.assertEqual(len(sent),2)
 def test_manual_bypasses_recent_group_and_resets_auto_timer(self):
  jid=app.GROUPS['main'][1];old=time.time()-10;app.STORE.put('last_sent',{jid:old});self.status_recent=True
  response=app.manual_command('send now to givelife main','manual-send-001');job=self.wait(response['job_id'])
  self.assertEqual(len(self.sent),1);self.assertEqual(self.sent[0]['phone'],jid);self.assertIn('25,000',self.sent[0]['text'])
  self.assertEqual(job['results'][0]['code'],'SUCCESS');self.assertGreater(app.STORE.get('last_sent')[jid],old)
  self.assertEqual(app.send_image(jid,'automatic caption',True)['code'],'COOLDOWN');self.assertEqual(len(self.sent),1)
 def test_repeat_never_uses_stale_personal_recipient(self):
  app.remember_recipient('wrong old contact','923001234567@s.whatsapp.net')
  response=app.manual_command('resend now to givelife with 25k');self.wait(response['job_id'])
  response=app.manual_command('send and restart gap');self.wait(response['job_id'])
  self.assertEqual([x['phone'] for x in self.sent],[app.GROUPS['main'][1]]*2)
  self.assertFalse(any(x['text'] in ('now','and restart gap') for x in self.sent))
 def test_command_words_cannot_be_sent_through_legacy_api(self):
  for text in ('now','and restart gap','message in givelife now'):
   with self.subTest(text=text),self.assertRaises(ValueError):app.send_free('923001234567',text,False)
  self.assertEqual(self.sent,[])
 def test_manual_interrupts_auto_sleep_without_waiting(self):
  ident=app.start_send_job(['main','community'],'auto snapshot',manual=False)
  until=time.monotonic()+1
  while len(self.sent)<1 and time.monotonic()<until:time.sleep(.005)
  start=time.monotonic();response=app.manual_command('send in givelife now','preempt-auto-001');self.wait(response['job_id']);self.wait(ident)
  self.assertLess(time.monotonic()-start,1)
  self.assertEqual([x['phone'] for x in self.sent],[app.GROUPS['main'][1]]*2)
  self.assertIsNone(app.ACTIVE)
 def test_same_request_id_never_sends_twice(self):
  one=app.manual_command('send givelife','repeat-request-001');self.wait(one['job_id'])
  two=app.manual_command('send givelife','repeat-request-001');self.assertEqual(one['job_id'],two['job_id']);self.assertEqual(len(self.sent),1)
 def test_disconnected_does_not_claim_success(self):
  self.status_connected=False
  with self.assertRaisesRegex(ValueError,'not connected'):app.manual_command('send to givelife main')
  self.assertEqual(self.sent,[])
 def test_uncertain_not_retried_and_timer_not_reset(self):
  jid=app.GROUPS['main'][1];old=time.time()-100;app.STORE.put('last_sent',{jid:old})
  with patch.object(app.subprocess,'run',return_value=types.SimpleNamespace(stdout=b'bad-json')) as wire:
   response=app.manual_command('send main');job=self.wait(response['job_id'])
   self.assertEqual(wire.call_count,1);self.assertNotEqual(job['results'][0]['code'],'SUCCESS')
  self.assertEqual(app.STORE.get('last_sent')[jid],old)
 def test_stop_dms_persists_and_cancels_campaign(self):
  app.ENGINE.s['dm_enabled']=True;app.CAMPAIGN['running']=True
  result=app.manual_command('dont send dm')
  self.assertTrue(app.CAMPAIGN['stop']);self.assertFalse(app.ENGINE.s['dm_enabled']);self.assertIn('DMs stopped',result['reply'])
  self.assertIn('remain off',app.engine_do(True)['set_dms'](enabled=True,daily=30))
 def test_new_owner_instruction_blocks_old_ai_tools(self):
  callbacks=app.chat_callbacks('send main',revision=0,task_id='stale-task-001')
  app.manual_command('dont send dm')
  with self.assertRaisesRegex(ValueError,'Superseded'):callbacks['send_appeal'](target='main')
  self.assertEqual(self.sent,[])
 def test_group_request_never_authorizes_dm_batch(self):
  callbacks=app.chat_callbacks('send in givelife now',revision=0)
  with self.assertRaisesRegex(ValueError,'does not authorize DMs'):callbacks['dm_donors'](count=5)
 def test_hold_stops_waiting_job(self):
  ident=app.start_send_job(['main','community'],'snapshot',manual=True)
  end=time.monotonic()+1
  while not self.sent and time.monotonic()<end:time.sleep(.005)
  app.manual_command('hold');job=self.wait(ident)
  self.assertEqual(len(self.sent),1);self.assertIn('Stopped by owner',job['message'])
 def test_requested_caption_is_frozen(self):
  with patch.object(app.threading.Thread,'start'):
   result=app.manual_command('resend now to givelife with 25k')
  job=app.JOBS[result['job_id']];snap=job['captions'][0];app.set_left(23000)
  self.assertIn('25,000',snap);self.assertNotIn('23,000',snap)
  app.run_job(result['job_id'],['main'],job['caption'])
  self.assertEqual(self.sent[0]['text'],app.caption_facts.current(app,snap))
  self.assertIn('23,000',self.sent[0]['text'])
  self.assertIn('23,000',json.loads(app.DRAFT.read_text(encoding='utf-8'))['group'])
 def test_donation_wording_order_never_changes_money(self):
  result=app.manual_command('in messages add 2000 by this much first, then 1000, not 1000 first')
  self.assertEqual(app.read_left(),25000)
  text=json.loads(app.DRAFT.read_text(encoding='utf-8'))['group'];self.assertLess(text.index('2,000'),text.index('1,000'))
  self.assertIn('stays Rs. 25,000',result['reply'])
 def test_current_wording_edit_not_a_future_rule(self):
  app.save_draft('group',app.update_text(3000,25000))
  before=copy.deepcopy(app.ENGINE.rule_list())
  result=app.manual_command('dont write this much came in delete')
  self.assertEqual(app.read_left(),25000);self.assertNotIn('came in',json.loads(app.DRAFT.read_text(encoding='utf-8'))['group']);self.assertEqual(app.ENGINE.rule_list(),before)
  import rules
  self.assertIsNone(rules.parse('dont write this much came in delete')[0])
 def test_received_donation_only_when_explicit(self):
  app.manual_command('came 2000');self.assertEqual(app.read_left(),23000)
  app.manual_command('25k left now not 22000');self.assertEqual(app.read_left(),25000)
  cb=app.chat_callbacks('put 2000 first then 1000 in messages',revision=app.OWNER_REVISION)
  with self.assertRaises(ValueError):cb['money_came'](amount=3000)
  with self.assertRaises(ValueError):cb['set_left'](left=22000)
  self.assertEqual(app.read_left(),25000)
 def test_restart_receipt_does_not_auto_resume(self):
  app.STORE.put('send_job_restart',{'done':False,'results':[],'message':'sending'})
  result=app.get_job('restart');self.assertTrue(result['done']);self.assertIn('will not retry',result['message'])
 def test_delete_uses_only_own_group_message_id(self):
  app.LAST_MANUAL.update(kind='appeal',target='main');jid=app.GROUPS['main'][1];app.DELIVERIES[jid]={'message_id':'my-own-message'}
  import io
  response=io.BytesIO(json.dumps({'code':'SUCCESS'}).encode());response.__enter__=lambda:response
  with patch.object(app.urllib.request,'urlopen',return_value=response) as req:
   result=app.manual_command('delete message from gruo')
  request=req.call_args.args[0];self.assertTrue(request.full_url.endswith('/my-own-message/revoke'));self.assertEqual(json.loads(request.data)['phone'],jid);self.assertIn('confirmed deletion',result['reply'])

 def test_excluded_group_never_falls_back_to_personal_text(self):
  for text in ('send Exclusive Upwork Course','send to GiveLife Foundation 37 members','send to 120363432572916292@g.us'):
   with self.subTest(text=text),self.assertRaisesRegex(ValueError,'excluded'):app.manual_command(text)
  self.assertEqual(self.sent,[])
 def test_multiple_groups_share_one_manual_batch(self):
  with patch.object(app.threading.Thread,'start'):
   result=app.manual_command('send main and fiverr now')
  job=app.JOBS[result['job_id']];event=app.JOB_CANCEL[result['job_id']]
  with patch.object(event,'wait',return_value=False) as wait:
   app.run_job(result['job_id'],job['keys'],job['caption'])
  self.assertEqual([x['phone'] for x in self.sent],[app.GROUPS['main'][1],app.GROUPS['fiverr'][1]])
  self.assertGreaterEqual(wait.call_args.args[0],59)
 def test_ai_lookup_then_send_still_works(self):
  import assistant
  calls=[{'content':'','tool_calls':[{'id':'lookup','function':{'name':'find_contact','arguments':'{"query":"Ali"}'}}]}, {'content':'','tool_calls':[{'id':'send','function':{'name':'send_message','arguments':'{"to":"923001234567","text":"hello","with_picture":false}'}}]}]
  actual=[]
  with patch.object(assistant,'client',return_value='fake-key'),patch.object(assistant,'_chat_raw',side_effect=calls) as model:
   result=assistant.chat('send hello to Ali',[],{},[],{'find_contact':lambda query:'[{"name":"Ali","id":"923001234567"}]','send_message':lambda **kw:(actual.append(kw) or 'Sent.')})
  self.assertEqual(len(actual),1);self.assertEqual(model.call_count,2);self.assertEqual(result['reply'],'Sent.')
 def test_ai_cannot_claim_success_after_tool_refuses(self):
  import assistant
  message={'content':'Sent to main.','tool_calls':[{'id':'send','function':{'name':'send_appeal','arguments':'{"target":"main"}'}}]}
  def refuse(**args):raise ValueError('WhatsApp disconnected')
  with patch.object(assistant,'client',return_value='fake-key'),patch.object(assistant,'_chat_raw',return_value=message):
   result=assistant.chat('send main',[],{},[],{'send_appeal':refuse})
  self.assertIn('WhatsApp disconnected',result['reply']);self.assertNotEqual(result['reply'],'Sent to main.')
 def test_ai_returns_job_receipt_not_fake_sent(self):
  import assistant
  message={'content':'Sent.','tool_calls':[{'id':'send','function':{'name':'send_appeal','arguments':'{"target":"main"}'}}]}
  receipt={'reply':'Sending to GiveLife main now.','job_id':'fake-job','caption':'exact'}
  with patch.object(assistant,'client',return_value='fake-key'),patch.object(assistant,'_chat_raw',return_value=message):
   result=assistant.chat('send main',[],{},[],{'send_appeal':lambda **kw:receipt})
  self.assertEqual(result['jobs'],[receipt]);self.assertEqual(result['reply'],receipt['reply'])
 def test_tools_are_not_repeated_within_one_ai_turn(self):
  actual=[];callbacks=app.chat_callbacks('send hello to 923001234567',revision=0)
  with patch.object(app,'send_free',side_effect=lambda *a,**k:(actual.append(a) or 'Sent.')):
   callbacks['send_message'](to='923001234567',text='hello',with_picture=False)
   callbacks['send_message'](to='923001234567',text='hello',with_picture=False)
  self.assertEqual(len(actual),1)
 def test_ordinary_caption_edit_does_not_start_autopilot_or_save_rule(self):
  callbacks=app.chat_callbacks('shorten this caption',revision=0)
  with self.assertRaises(ValueError):callbacks['autopilot'](on=True)
  with self.assertRaises(ValueError):callbacks['remember'](rule='shorten this caption')
  with self.assertRaises(ValueError):callbacks['send_appeal'](target='main')
 def test_existing_schedules_and_preferences_still_parse(self):
  import rules
  for text,kind in [('post in fiverr every 30 min','gap'),('no posting 2am to 7am','quiet'),('max 10 posts a day','cap'),('post in main at 9pm daily','schedule'),('always use simple words','note')]:
   with self.subTest(text=text):self.assertEqual(rules.parse(text)[0]['kind'],kind)
 def test_disabled_auto_dms_do_not_send_replies_or_followups(self):
  app.ENGINE.s['dm_enabled']=False
  with patch.dict(app.ENGINE.h,{'send_text':lambda *a:self.fail('No automatic DM was authorized')}):
   app.ENGINE._reply('923001234567@s.whatsapp.net','hello');app.ENGINE.run_followups()
 def test_http_login_and_direct_ack_under_one_second(self):
  import urllib.request,urllib.error
  http=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(http.server_port)
  def request(path,body=None,auth=True):
   headers={'Authorization':'Bearer test-only-studio-access-key'} if auth else {}
   if body is not None:headers['Content-Type']='application/json'
   req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
   try:
    with urllib.request.urlopen(req,timeout=3) as r:return r.status,json.loads(r.read())
   except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
  try:
   self.assertEqual(request('/health',auth=False)[0],200)
   self.assertEqual(request('/command',{'text':'send main'},False)[0],401)
   start=time.perf_counter();code,result=request('/command',{'text':'resend now to givelife with 25k','request_id':'http-manual-001'});elapsed=time.perf_counter()-start
   self.assertEqual(code,200);self.assertLess(elapsed,1);self.wait(result['job_id'])
   self.assertEqual(request('/send-status/'+result['job_id'])[1]['results'][0]['code'],'SUCCESS')
   self.assertEqual(request('/send-now',{'to':'923001234567','text':'now'})[0],400)
   print('Measured fake-service direct-command acknowledgement: %.1f ms'%(elapsed*1000))
  finally:http.shutdown();http.server_close()
 def test_slow_ai_is_an_async_task_and_does_not_time_out_the_post(self):
  def slow(*args,**kw):time.sleep(.2);return {'reply':'Answered.','actions':[],'jobs':[]}
  app.ASSIST_TASKS.clear()
  with patch.object(app.assistant,'chat',side_effect=slow):
   start=time.perf_counter();ident=app.assistant_task({'text':'How are you?','request_id':'async-test-001'});elapsed=time.perf_counter()-start
   self.assertLess(elapsed,.1)
   same=app.assistant_task({'text':'How are you?','request_id':'async-test-001'});self.assertEqual(ident,same)
   end=time.monotonic()+2
   while not app.ASSIST_TASKS[ident]['done'] and time.monotonic()<end:time.sleep(.005)
   self.assertEqual(app.ASSIST_TASKS[ident]['result']['reply'],'Answered.')

 def test_stale_ai_waiting_for_wire_cannot_send_after_stop(self):
  errors=[];callbacks=app.chat_callbacks('send hello to 923001234567',revision=0)
  def worker():
   try:callbacks['send_message'](to='923001234567',text='hello',with_picture=True)
   except ValueError as e:errors.append(str(e))
  with app.WIRE_LOCK:
   thread=threading.Thread(target=worker);thread.start();time.sleep(.02);app.manual_command('dont send dm')
  thread.join(1);self.assertFalse(thread.is_alive());self.assertEqual(self.sent,[]);self.assertTrue(errors)
 def test_preempted_job_waiting_for_wire_does_not_dispatch(self):
  with app.WIRE_LOCK:
   old=app.start_send_job(['main'],'old auto caption',False)
   end=time.monotonic()+1
   while app.JOBS[old]['message']!='Sending to GiveLife Foundation' and time.monotonic()<end:time.sleep(.005)
   newer=app.manual_command('send main','preempt-wire-001')['job_id']
  self.wait(newer);self.wait(old)
  self.assertEqual(len(self.sent),1);self.assertNotEqual(self.sent[0]['text'],'old auto caption')

if __name__=='__main__':unittest.main(verbosity=2)
