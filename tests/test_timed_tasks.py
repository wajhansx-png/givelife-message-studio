import copy,datetime,json,tempfile,threading,unittest
from pathlib import Path
import timed_tasks as tt,chat_policy

class Store:
 def __init__(self):self.data={};self.lock=threading.RLock()
 def get(self,k,d=None):return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def claim(self,k,v):
  with self.lock:
   if k in self.data:return False
   self.data[k]=copy.deepcopy(v);return True

class TimedTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=Store();self.now=datetime.datetime(2026,10,27,10,0,tzinfo=tt.PKT).timestamp();self.dispatched=[];self.jobs={};self.allowed=True
  def dispatch(task):
   self.dispatched.append(task)
   if task['action']!='send':return {'message':'Auto changed'}
   self.jobs[task['id']]={'done':False};return {'job_id':task['id'],'expected':1}
  self.s=tt.Scheduler(Path(self.temp.name)/'tasks.json',self.store,dispatch,lambda id:self.jobs.get(id),lambda task:self.allowed,clock=lambda:self.now)
 def create(self,text='send to givelife in 10 minutes'):
  self.s.command(text);return self.s.tasks[-1]
 def test_clock_pkt_today_tomorrow_and_dates(self):
  for text,date in [('send to main at 9pm',(27,21)),('send to main at 9am',(28,9)),('send to main tomorrow at 8am',(28,8)),('send to main on 2026-10-29 at 14:30',(29,14))]:
   d=datetime.datetime.fromtimestamp(tt.parse(text,self.now)['due'],tt.PKT);self.assertEqual((d.day,d.hour),date)
 def test_invalid_time_and_missing_fields(self):
  for text in ['send main at 25:99','send main at 13pm','send main today at 8am','schedule main','send at 9pm','send main in 0 minutes','send main at 9pm UTC','start auto on and off at 9pm','send exclusive upwork at 9pm']:
   with self.subTest(text=text),self.assertRaises(ValueError):tt.parse(text,self.now)
 def test_queries_negative_and_quoted_injection_are_not_actions(self):
  for text in ['what will send to main at 9pm','do not send main at 9pm','"send to main at 9pm"','send "meet at 9pm" to main']:
   self.assertIsNone(tt.parse(text,self.now))
  p=tt.parse('send "hello givelife at 7pm" to fiverr at 9pm',self.now);self.assertEqual(p['targets'],['fiverr']);self.assertEqual(p['clock'],'21:00');self.assertEqual(p['text'],'hello givelife at 7pm')
 def test_interval_rules_and_immediate_today_preserved(self):
  self.assertIsNone(tt.parse('post freelance every 30 minutes daily',self.now));self.assertIsNone(tt.parse('send main now today',self.now))
 def test_no_early_dispatch_and_once_with_receipt(self):
  t=self.create();self.s.tick();self.assertEqual(self.dispatched,[]);self.now+=600;self.s.tick();self.s.tick();self.assertEqual(len(self.dispatched),1);self.assertEqual(t['state'],'running')
  self.jobs[t['id']]={'done':True,'results':[{'code':'SUCCESS'}],'message':'Confirmed sent'};self.s.tick();self.assertEqual(t['state'],'completed');self.s.tick();self.assertEqual(len(self.dispatched),1)
 def test_hold_waits_then_runs_without_enabling_auto(self):
  t=self.create();self.allowed=False;self.now+=600;self.s.tick();self.assertEqual(t['state'],'pending');self.allowed=True;self.s.tick();self.assertEqual(t['state'],'running')
 def test_failure_is_not_retried(self):
  t=self.create();self.now+=600;self.s.dispatch=lambda task:(_ for _ in ()).throw(TimeoutError());self.s.tick();self.assertEqual(t['state'],'uncertain');self.s.tick();self.assertEqual(t['state'],'uncertain')
 def test_partial_receipt_not_claimed_success(self):
  t=self.create();self.now+=600;self.s.tick();self.jobs[t['id']]={'done':True,'results':[{'code':'UNCERTAIN'}],'message':'Not confirmed'};self.s.tick();self.assertEqual(t['state'],'failed')
 def test_restart_during_dispatch_is_uncertain_not_replayed(self):
  t=self.create();t['state']='dispatching';self.s.save();s=tt.Scheduler(self.s.path,self.store,self.s.dispatch,self.s.receipt,self.s.ready,clock=lambda:self.now+700);s.tick();self.assertEqual(s.tasks[0]['state'],'uncertain');self.assertEqual(self.dispatched,[])
 def test_pending_survives_restart(self):
  t=self.create();s=tt.Scheduler(self.s.path,self.store,self.s.dispatch,self.s.receipt,self.s.ready,clock=lambda:self.now+600);s.tick();self.assertEqual(len(self.dispatched),1)
 def test_cancel_and_duplicate_creation(self):
  t=self.create();self.s.command('send to givelife in 10 minutes');self.assertEqual(len(self.s.tasks),1);self.s.command('cancel schedule '+t['id']);self.now+=600;self.s.tick();self.assertEqual(self.dispatched,[]);self.assertEqual(t['state'],'cancelled')
 def test_daily_auto_and_missed_tasks(self):
  t=self.create('start auto daily at 11am');self.now+=3600;self.s.tick();self.assertEqual(t['state'],'pending');self.assertGreater(t['due'],self.now);self.assertEqual(self.dispatched[0]['action'],'auto_on')
  late=self.create('send main in 1 minute');self.now+=1000;self.s.tick();self.assertEqual(late['state'],'missed')
 def test_model_cannot_send_future_action_now(self):
  text='send main tomorrow at 9pm';self.assertTrue(chat_policy.permitted('schedule_task',text));self.assertFalse(chat_policy.permitted('send_appeal',text));self.assertFalse(chat_policy.permitted('autopilot','start auto at 9pm'));self.assertTrue(chat_policy.permitted('send_appeal','send main now today'))
 def test_resume_parsing_does_not_unpause_unspecified_groups(self):
  self.assertEqual(tt.parse('resume freelance at 11am',self.now)['targets'],['free']);self.assertEqual(tt.parse('resume at 11am',self.now)['targets'],[]);self.assertEqual(tt.parse('start sending in givelife at 11am',self.now)['action'],'resume');self.assertFalse(chat_policy.permitted('hold','resume auto at 11am'))
 def test_file_fallback_and_concurrent_ticks(self):
  s=tt.Scheduler(self.s.path,None,self.s.dispatch,self.s.receipt,self.s.ready,clock=lambda:self.now);s.command('send main in 1 minute');self.now+=60
  threads=[threading.Thread(target=s.tick) for _ in range(5)]
  for th in threads:th.start()
  for th in threads:th.join()
  self.assertEqual(len(self.dispatched),1);self.assertTrue(json.loads(s.path.read_text()))
 def test_overlapping_deploy_workers_do_not_dispatch_twice(self):
  task=self.create();other=tt.Scheduler(self.s.path,self.store,self.s.dispatch,self.s.receipt,self.s.ready,clock=lambda:self.now);self.now+=600
  threads=[threading.Thread(target=s.tick) for s in (self.s,other)]
  for th in threads:th.start()
  for th in threads:th.join()
  self.assertEqual(len(self.dispatched),1)
 def test_cancel_tombstone_stops_a_stale_worker(self):
  task=self.create();other=tt.Scheduler(self.s.path,self.store,self.s.dispatch,self.s.receipt,self.s.ready,clock=lambda:self.now);self.s.command('cancel schedule '+task['id']);self.now+=600;other.tick();self.assertEqual(self.dispatched,[]);self.assertEqual(other.tasks[0]['state'],'cancelled')
 def test_overlapping_daily_completion_keeps_next_occurrence(self):
  task=self.create('start auto daily at 11am');other=tt.Scheduler(self.s.path,self.store,self.s.dispatch,self.s.receipt,self.s.ready,clock=lambda:self.now);self.now+=3600;self.s.tick();other.tick();self.assertEqual(len(self.dispatched),1);self.assertEqual(other.tasks[0]['due'],task['due']);self.assertEqual(other.tasks[0]['state'],'pending')
 def test_live_reservation_waits_for_receipt_without_repeating(self):
  task=self.create();self.now+=600;self.store.claim(self.s.claim_key(task),{'state':'dispatching','claimed_at':self.now});self.s.tick();self.assertEqual(task['state'],'pending');self.assertEqual(self.dispatched,[])

class TimedIntegrationTests(unittest.TestCase):
 def test_scheduled_resume_releases_hold_only_when_due(self):
  from test_manual_sends import SendTests,app
  from unittest.mock import patch
  fixture=SendTests();fixture.setUp()
  try:
   app.set_hold(True)
   with patch.object(app.ENGINE,'resume') as resume:
    out=app.manual_command('resume freelance in 10 minutes','resume-test-123');scheduler=app.timed_scheduler();task=scheduler.tasks[-1]
    self.assertIn('Scheduled',out['reply']);self.assertTrue(app.on_hold());self.assertFalse(app.auto_on());resume.assert_not_called()
    scheduler.clock=lambda:task['due'];scheduler.tick();self.assertFalse(app.on_hold());self.assertTrue(app.auto_on());self.assertEqual({x.args[0] for x in resume.call_args_list},set(app.FREELANCE));self.assertEqual(fixture.sent,[])
  finally:fixture.tearDown()
 def test_chat_commands_persist_without_sending_then_dispatch_full_caption(self):
  from test_manual_sends import SendTests,app
  fixture=SendTests();fixture.setUp()
  try:
   out=app.manual_command('send to givelife in 10 minutes','schedule-test-123');self.assertTrue(out['handled']);self.assertIn('PKT',out['reply']);self.assertEqual(fixture.sent,[])
   scheduler=app.timed_scheduler();task=scheduler.tasks[-1];scheduler.clock=lambda:task['due'];scheduler.tick();fixture.wait(task['job_id']);scheduler.tick();self.assertEqual(task['state'],'completed');self.assertEqual(len(fixture.sent),1);self.assertIn('03097458815',fixture.sent[0]['text']);self.assertFalse(app.auto_on());self.assertIn(task['id'],app.manual_command('show schedules')['reply'])
  finally:fixture.tearDown()

if __name__=='__main__':unittest.main()
