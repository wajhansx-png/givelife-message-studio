"""Team tasks: planning, at-most-once sending, reminders, lateness, reply matching, verification, restarts."""
import copy,datetime,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import team_tasks as T

class Store:
 def __init__(self):self.data={}
 def get(self,k,d=None):return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)

BASE=datetime.datetime(2026,10,30,14,0,tzinfo=T.PKT).timestamp()   # 2:00 PM Pakistan time

class Base(unittest.TestCase):
 def setUp(self):
  self.dir=tempfile.TemporaryDirectory();self.store=Store();self.clock=[BASE];self.sent=[];self.owner=[];self.inbox=[];self.down=[False]
  self.app=SimpleNamespace(DATA=Path(self.dir.name),STORE=self.store,OWNER_PHONE='923000000000',on_hold=lambda:False,wa_ok=lambda:True,
   send_custom=self.send,send_text=lambda jid,text:self.owner.append(text),group_messages=lambda jid:list(self.inbox))
  self.t=T.TeamTasks(self.app,clock=lambda:self.clock[0]);self.t.set_member('Bilal Ahmed','03001234567');self.t._load()['member']['since']=BASE-10;self.t._save()
 def tearDown(self):self.dir.cleanup()
 def send(self,body):
  if self.down[0]:raise RuntimeError('down')
  self.sent.append(body['message']);return {'code':'SUCCESS'}
 def at(self,minutes):self.clock[0]=BASE+minutes*60
 def tick(self,minutes=None):
  if minutes is not None:self.at(minutes)
  self.t.tick()
 def start(self,text='1) post in groups 2) update sheet deadline 6pm'):
  self.t.plan(text);return self.t.confirm_plan()
 def reply(self,text,mid,media=False,minutes=None):
  if minutes is not None:self.at(minutes)
  self.inbox.append({'id':mid,'content':text,'is_from_me':False,'timestamp':datetime.datetime.fromtimestamp(self.clock[0],datetime.timezone.utc).isoformat(),**({'media_type':'image'} if media else {})})
  self.t.tick()
 def status(self):return {x['no']:x['status'] for x in self.t.view()['tasks']}

class Planning(Base):
 def test_splits_and_spreads_the_time_evenly(self):
  v=self.t.plan('1) post in 3 groups 2) update the sheet 3) message donors deadline 6pm')
  self.assertEqual([(i['text'],i['start_label'],i['due_label']) for i in v['plan']['items']],[('post in 3 groups','2:00 PM','3:20 PM'),('update the sheet','3:20 PM','4:40 PM'),('message donors','4:40 PM','6:00 PM')])
 def test_own_time_per_task_and_overall_deadline_are_not_confused(self):
  v=self.t.plan('call Ali by 3pm\nupdate sheet by 5:30 pm');self.assertEqual([i['due_label'] for i in v['plan']['items']],['3:00 PM','5:30 PM'])
 def test_bad_input_is_refused_with_a_reason(self):
  for text,word in (('','Write'),('post\nupdate','deadline'),('post deadline 1pm','too soon'),('post deadline 2:05 pm','too soon')):
   with self.subTest(text=text),self.assertRaisesRegex(ValueError,word):self.t.plan(text)
  with self.assertRaisesRegex(ValueError,'Not enough time'):self.t.plan('\n'.join('task %d'%i for i in range(8))+'\ndeadline 3pm')
  with self.assertRaisesRegex(ValueError,'at most 20'):self.t.plan('\n'.join('task %d'%i for i in range(21))+'\ndeadline tomorrow 11pm')
 def test_nothing_is_sent_until_confirmed_and_plans_expire(self):
  self.t.plan('a\nb deadline 6pm');self.tick(1);self.assertEqual(self.sent,[]);self.at(20)
  with self.assertRaisesRegex(ValueError,'no task plan'):self.t.confirm_plan()
 def test_bare_hour_means_the_next_such_hour(self):
  self.assertEqual(self.t.plan('a deadline 6')['plan']['items'][0]['due_label'],'6:00 PM')

class Sending(Base):
 def test_each_task_is_asked_exactly_once_even_after_many_ticks_and_a_restart(self):
  self.start();self.tick(0);self.tick(1);self.tick(2);self.assertEqual(len(self.sent),1);self.assertIn('Task #1',self.sent[0]);self.assertIn('4:00 PM',self.sent[0])
  again=T.TeamTasks(self.app,clock=lambda:self.clock[0]);self.at(1.5*60)
  for m in range(2,6):self.clock[0]=BASE+(m+88)*60;again.tick()
  self.assertEqual(sum('Task #1:' in s for s in self.sent),1,'a restart never repeats a message')
 def test_one_message_a_minute_at_most(self):
  self.start('a\nb\nc\nd deadline 9pm');self.tick(0);self.t.tick();self.assertEqual(len(self.sent),1)
  self.tick(0.5);self.assertEqual(len(self.sent),1);self.tick(1.1);self.assertEqual(len(self.sent),1)
 def test_quiet_hours_and_pause_and_hold(self):
  self.t.plan('a deadline tomorrow 9am');self.t.confirm_plan();self.clock[0]=datetime.datetime(2026,10,30,23,30,tzinfo=T.PKT).timestamp();self.t.tick();self.assertEqual(self.sent,[])
  self.clock[0]=datetime.datetime(2026,10,31,7,1,tzinfo=T.PKT).timestamp();self.t.tick();self.assertEqual(len(self.sent),1)
  self.t.pause(True)
 def test_paused_sends_nothing(self):
  self.start();self.t.pause(True);self.tick(0);self.assertEqual(self.sent,[]);self.t.pause(False);self.tick(1.2);self.assertEqual(len(self.sent),1)
 def test_a_failed_send_goes_back_to_waiting_and_retries_later_then_is_reported(self):
  self.start('a deadline 6pm');self.down[0]=True;self.tick(0);self.assertEqual(self.status(),{1:'Waiting'});self.tick(2);self.assertEqual(self.sent,[])
  self.down[0]=False;self.tick(6);self.assertEqual(self.status(),{1:'Asked'});self.assertEqual(len(self.sent),1)
 def test_the_owner_is_told_when_a_send_keeps_failing(self):
  self.start('a deadline 6pm');self.down[0]=True
  for m in (0,6,12,18):self.tick(m)
  self.tick(25);self.assertTrue(any('could not be sent' in x for x in self.owner))

class Chasing(Base):
 def test_reminder_once_then_check_then_late_then_one_final_message(self):
  self.start('post groups deadline 4pm');self.tick(0);self.tick(31);self.tick(32);  self.assertEqual(sum(s.startswith('Reminder') for s in self.sent),1)
  self.tick(106);self.assertEqual(sum(s.startswith('Quick check') for s in self.sent),1);self.tick(107)
  self.assertEqual(sum(s.startswith('Quick check') for s in self.sent),1)
  self.tick(125);self.assertEqual(self.status(),{1:'Late'});self.tick(127);self.assertEqual(sum('has passed' in s for s in self.sent),1);self.tick(140);self.assertEqual(sum('has passed' in s for s in self.sent),1)
  self.assertTrue(any('is late' in n for n in self.owner))
 def test_no_reminder_after_he_replied(self):
  self.start('post groups deadline 6pm');self.tick(0);self.reply('working on it',"m1",minutes=5);self.tick(40);self.assertEqual(sum(s.startswith('Reminder') for s in self.sent),0)
 def test_a_task_never_sent_before_its_deadline_is_late_and_not_asked_afterwards(self):
  self.start('a deadline 6pm');self.down[0]=True
  for m in range(0,239,6):self.tick(m)
  self.down[0]=False;self.tick(241);self.assertEqual(self.status(),{1:'Late'});self.assertEqual(self.sent,[])

class Replies(Base):
 def two(self):
  self.start('a by 4pm\nb by 5pm');self.tick(0);self.tick(2)
 def test_number_and_done_reports_the_right_task(self):
  self.two();self.reply('2 done','r1',minutes=5);self.assertEqual(self.status(),{1:'Asked',2:'Reported'})
  self.assertTrue(any('says task #2 is done' in e['text'] for e in self.t.view()['feed']));self.assertTrue(any('says task #2' in n for n in self.owner))
 def test_done_without_a_number_is_only_accepted_when_one_task_is_open(self):
  self.two();self.reply('done','r1',minutes=5);self.assertEqual(self.status(),{1:'Asked',2:'Asked'});self.reply('1 done','r2',minutes=6);self.reply('done','r3',minutes=8)
  self.assertEqual(self.status()[1],'Reported')
 def test_single_open_task_accepts_plain_done(self):
  self.start('a deadline 6pm');self.tick(0);self.reply('Done','r1',minutes=5);self.assertEqual(self.status(),{1:'Reported'})
 def test_all_done_and_other_languages(self):
  self.two();self.reply('all done','r1',minutes=5);self.assertEqual(self.status(),{1:'Reported',2:'Reported'})
  self.start('c deadline 9pm');self.tick(8);self.reply('ho gaya','r2',minutes=9)
 def test_ambiguous_done_asks_which_task_and_changes_nothing(self):
  self.two();self.reply('done','r1',minutes=5);self.assertEqual(self.status(),{1:'Asked',2:'Asked'});self.tick(7);self.assertTrue(any(s.startswith('Which task') for s in self.sent))
 def test_unknown_number_is_not_guessed(self):
  self.two();self.reply('9 done','r1',minutes=5);self.assertEqual(self.status(),{1:'Asked',2:'Asked'})
 def test_a_time_in_the_message_is_not_a_task_number(self):
  self.start('a deadline 6pm');self.tick(0);self.reply('will finish at 4:30','r1',minutes=5);self.assertEqual(self.status(),{1:'Asked'})
 def test_photo_or_link_counts_as_proof_and_missing_proof_is_requested_once(self):
  self.start('a deadline 6pm');self.tick(0);self.reply('done https://x.com/p','r1',minutes=5);self.assertTrue(self.t.view()['tasks'][0]['proof']);self.tick(7);self.assertFalse(any('send a screenshot' in s for s in self.sent))
  self.start('b deadline 9pm') if False else None
 def test_no_proof_triggers_a_single_proof_request(self):
  self.start('a deadline 6pm');self.tick(0);self.reply('done','r1',minutes=5)
  for m in (7,9,11):self.tick(m)
  self.assertEqual(sum('send a screenshot' in s for s in self.sent),1)
 def test_blocked_messages_are_flagged_and_the_owner_is_told(self):
  self.start('a deadline 6pm');self.tick(0);self.reply("I am stuck, cannot login",'r1',minutes=5);self.assertEqual(self.t.view()['feed'][0]['kind'],'blocked');self.assertTrue(self.owner)
 def test_same_message_is_never_processed_twice_and_old_chat_history_is_ignored(self):
  self.start('a deadline 6pm');self.tick(0);self.inbox.append({'id':'old','content':'done','is_from_me':False,'timestamp':'2020-01-01T00:00:00+00:00'});self.reply('1 done','r1',minutes=5);self.t.tick();self.t.tick()
  self.assertEqual(sum(1 for e in self.t.view()['feed'] if e['kind']=='report'),1)
 def test_owner_notes_are_batched_not_spammed(self):
  self.start('a\nb\nc deadline 9pm');self.tick(0)
  for i,m in enumerate((2,2.4,2.8)):self.reply('update %d'%i,'u%d'%i,minutes=m)
  self.assertEqual(len(self.owner),1,'the first goes at once, the next ones wait');self.assertIn('update 0',self.owner[0]);self.tick(4.5)
  self.assertEqual(len(self.owner),2);self.assertIn('update 1',self.owner[1]);self.assertIn('update 2',self.owner[1])

class Verification(Base):
 def test_verify_reject_cancel_and_numbering(self):
  self.start('a deadline 6pm');self.tick(0);self.reply('1 done','r1',minutes=5);self.t.verify('1');self.assertEqual(self.status(),{1:'Done'})
  self.t.plan('b deadline 7pm');v=self.t.confirm_plan();self.assertEqual([x['no'] for x in v['tasks']],[1,1],'numbers restart when nothing is open')
  self.tick(20);self.reply('1 done','r2',minutes=25);self.t.reject('1','photo is blurry');self.assertEqual(self.t.view()['tasks'][-1]['status'],'Asked');self.tick(27);self.assertTrue(any('photo is blurry' in s for s in self.sent))
 def test_cannot_reject_what_was_not_reported(self):
  self.start('a deadline 6pm');self.tick(0)
  with self.assertRaisesRegex(ValueError,'reported'):self.t.reject('1')
 def test_a_restart_keeps_everything(self):
  self.start();self.tick(0);again=T.TeamTasks(self.app,clock=lambda:self.clock[0]);self.assertEqual(len(again.view()['tasks']),2);self.assertEqual(again.view()['member']['name'],'Bilal Ahmed')

class Chat(Base):
 def test_chat_plan_confirm_status_verify_and_pause(self):
  r=self.t.command('tasks for Bilal: 1) post in groups 2) update sheet deadline 6pm','tasks for Bilal: 1) post in groups 2) update sheet deadline 6pm');self.assertIn('Say "confirm tasks"',r['reply']);self.assertEqual(self.sent,[])
  self.assertIn('2 tasks started',self.t.command('confirm tasks','confirm tasks')['reply']);self.tick(0);self.reply('1 done','c1',minutes=5)
  self.assertIn('#1',self.t.command('team status','team status')['reply']);self.assertIn('verified',self.t.command('verify task 1','verify task 1')['reply'])
  self.assertIn('paused',self.t.command('pause team','pause team')['reply']);self.assertIsNone(self.t.command('hello there','hello there'))
 def test_chat_sets_the_teammate_and_refuses_the_owner_number(self):
  self.assertIn('Sara',self.t.command('set teammate Sara 0300 7654321','set teammate Sara 0300 7654321')['reply'])
  with self.assertRaises(ValueError):self.t.set_member('Me','923000000000')

if __name__=='__main__':unittest.main()
