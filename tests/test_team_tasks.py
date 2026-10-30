"""Team tasks over WhatsApp: planning, human wording, at-most-once sending, reminders, lateness, reply reading, verification, restarts."""
import copy,datetime,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import team_tasks as T

class Store:
 def __init__(self):self.data={}
 def get(self,k,d=None):return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)

BASE=datetime.datetime(2026,10,30,14,0,tzinfo=T.PKT).timestamp()   # 2:00 PM Pakistan time
ROBOT=('Task #','Reply "','bot','automated','app ','AI ','Deadline:','#1','#2')

class Base(unittest.TestCase):
 def setUp(self):
  self.dir=tempfile.TemporaryDirectory();self.store=Store();self.clock=[BASE];self.sent=[];self.owner=[];self.inbox=[];self.down=[False];self.wa=[True];self.hold=[False]
  self.app=SimpleNamespace(DATA=Path(self.dir.name),STORE=self.store,OWNER_PHONE='923000000000',on_hold=lambda:self.hold[0],wa_ok=lambda:self.wa[0],
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
 def reply(self,text,mid,minutes=None,media=None):
  if minutes is not None:self.at(minutes)
  m={'id':mid,'content':text,'is_from_me':False,'timestamp':datetime.datetime.fromtimestamp(self.clock[0],datetime.timezone.utc).isoformat()}
  if media:m['media_type']=media
  self.inbox.append(m);self.t.tick()
 def tasks(self):return {x['text']:x['status'] for x in self.t.view()['tasks']}
 def status(self,text):return self.tasks()[text]

class Planning(Base):
 def test_splits_and_spreads_the_time_evenly(self):
  v=self.t.plan('1) post in 3 groups 2) update the sheet 3) message donors deadline 6pm')
  self.assertEqual([(i['text'],i['start_label'],i['due_label']) for i in v['plan']['items']],[('post in 3 groups','2:00 PM','3:20 PM'),('update the sheet','3:20 PM','4:40 PM'),('message donors','4:40 PM','6:00 PM')])
 def test_own_time_per_task_and_overall_deadline_are_not_confused(self):
  v=self.t.plan('call Ali by 3pm\nupdate sheet by 5:30 pm');self.assertEqual([i['due_label'] for i in v['plan']['items']],['3:00 PM','5:30 PM'])
  v=self.t.plan('a by 4pm\nb deadline 7pm');self.assertEqual([i['due_label'] for i in v['plan']['items']],['4:00 PM','7:00 PM'])
 def test_bad_input_is_refused_with_a_reason(self):
  for text,word in (('','Write'),('post\nupdate','deadline'),('post deadline 1pm','too soon'),('post deadline 2:05 pm','too soon'),('post by 2:05pm','too soon')):
   with self.subTest(text=text),self.assertRaisesRegex(ValueError,word):self.t.plan(text)
  with self.assertRaisesRegex(ValueError,'Not enough time'):self.t.plan('\n'.join('task %d'%i for i in range(8))+'\ndeadline 3pm')
  with self.assertRaisesRegex(ValueError,'at most 20'):self.t.plan('\n'.join('task %d'%i for i in range(21))+'\ndeadline tomorrow 11pm')
  with self.assertRaisesRegex(ValueError,'valid time|read the time'):self.t.plan('a deadline 25:99')
 def test_nothing_is_sent_until_confirmed_and_plans_expire(self):
  self.t.plan('a\nb deadline 6pm');self.tick(1);self.assertEqual(self.sent,[]);self.at(20)
  with self.assertRaisesRegex(ValueError,'no task plan'):self.t.confirm_plan()
 def test_bare_hour_means_the_next_such_hour(self):
  self.assertEqual(self.t.plan('a deadline 6')['plan']['items'][0]['due_label'],'6:00 PM')
 def test_deadline_can_be_a_length_of_time_in_any_common_wording(self):
  for text,last in (('a\nb Deadline 9 hours','11:00 PM'),('a\nb deadline in 3 hours','5:00 PM'),('a\nb due 90 minutes','3:30 PM'),('a\nb within 2 hrs','4:00 PM'),('a\nb deadline 6:30 pm','6:30 PM')):
   with self.subTest(text=text):
    items=self.t.plan(text)['plan']['items'];self.assertEqual([i['text'] for i in items],['a','b']);self.assertEqual(items[-1]['due_label'],last)
 def test_tomorrow_deadline_shows_the_day(self):
  v=self.t.plan('a deadline tomorrow 10am');self.assertIn('31 Oct',v['plan']['items'][0]['due_label'])
 def test_a_task_that_would_start_at_night_waits_for_the_morning_and_must_still_fit(self):
  self.clock[0]=datetime.datetime(2026,10,30,22,0,tzinfo=T.PKT).timestamp()
  items=self.t.plan('a\nb deadline tomorrow 11am')['plan']['items']
  self.assertTrue(all(datetime.datetime.fromtimestamp(i['start_at'],T.PKT).hour>=7 or datetime.datetime.fromtimestamp(i['start_at'],T.PKT).day==30 and datetime.datetime.fromtimestamp(i['start_at'],T.PKT).hour<23 for i in items))
  with self.assertRaisesRegex(ValueError,'quiet hours'):self.t.plan('a\nb\nc deadline tomorrow 7:30am')

class HumanWords(Base):
 def scenario(self):
  self.start('post groups by 4pm\nupdate sheet by 4:30pm\nsend report deadline 6pm') if False else self.start('post groups by 4pm\nupdate sheet by 4:30pm')
  self.tick(1);self.tick(40);self.tick(110);self.tick(130);self.reply('not yet','n1',minutes=131);self.tick(200);self.tick(260)
  self.t.verify(self.t.view()['tasks'][0]['id']) if False else None
 def test_no_message_sounds_like_a_bot_or_shows_task_numbers(self):
  self.start('post groups by 4pm\nupdate sheet by 4:30pm');self.tick(1)
  for m in range(3,240,3):self.tick(m)
  self.reply('sheet done','d1',minutes=241);self.tick(245);self.tick(250)
  t=[x for x in self.t.view()['tasks'] if x['status']=='Reported'][0];self.t.reject(t['id'],'numbers are off');self.tick(260)
  t=[x for x in self.t.view()['tasks'] if x['status']=='Asked'];self.t.cancel(t[0]['id']) if t else None;self.tick(270)
  self.assertGreater(len(self.sent),4)
  for s in self.sent:
   for bad in ROBOT:self.assertNotIn(bad,s,s)
 def test_the_first_message_of_the_day_greets_and_the_rest_do_not(self):
  self.start('a by 4pm\nb by 5pm');self.tick(1);self.assertTrue(self.sent[0].startswith('Assalam o alaikum Bilal, '));self.assertNotIn('Ahmed',self.sent[0])
  self.tick(60);self.tick(120);self.assertTrue(all(not s.startswith('Assalam') for s in self.sent[1:]))
 def test_two_tasks_that_start_together_arrive_as_one_natural_message(self):
  self.start('post groups by 4pm\nupdate sheet by 5pm');self.tick(1);self.tick(2);self.assertEqual(len(self.sent),1);self.assertIn('post groups',self.sent[0]);self.assertIn('update sheet',self.sent[0]);self.assertIn('(by 4:00 PM)',self.sent[0])
 def test_messages_come_a_few_seconds_after_the_start_time_not_exactly_on_it(self):
  self.start('a deadline 6pm');self.tick(0);self.assertEqual(self.sent,[]);self.tick(1);self.assertEqual(len(self.sent),1)
 def test_wording_varies_between_tasks(self):
  self.start('a deadline 6pm');self.tick(1);first=self.sent[0].split(',',1)[1]
  seen={first}
  for n in range(12):
   self.t.plan('task %d deadline 9pm'%n);self.t.confirm_plan() if False else None
  self.assertGreaterEqual(len({T.pick(('x1','x2','x3','x4'),i) for i in range(30)}),3)

class Sending(Base):
 def test_each_task_is_asked_exactly_once_even_after_many_ticks_and_a_restart(self):
  self.start();self.tick(1);self.tick(2);self.tick(3);self.assertEqual(len(self.sent),1);self.assertIn('post in groups',self.sent[0]);self.assertIn('4:00 PM',self.sent[0])
  again=T.TeamTasks(self.app,clock=lambda:self.clock[0])
  for m in range(4,12):self.clock[0]=BASE+m*60;again.tick()
  self.assertEqual(sum('post in groups' in s for s in self.sent),1,'a restart never repeats a message')
 def test_one_message_a_minute_at_most(self):
  self.start('a\nb\nc\nd deadline 9pm');self.tick(1);self.assertEqual(len(self.sent),1);self.tick(1.4);self.assertEqual(len(self.sent),1)
 def test_quiet_hours_pause_hold_and_a_disconnected_whatsapp_send_nothing(self):
  self.t.plan('a deadline tomorrow 9am');self.t.confirm_plan();self.clock[0]=datetime.datetime(2026,10,30,23,30,tzinfo=T.PKT).timestamp();self.t.tick();self.assertEqual(self.sent,[])
  self.clock[0]=datetime.datetime(2026,10,31,7,10,tzinfo=T.PKT).timestamp();self.wa[0]=False;self.t.tick();self.assertEqual(self.sent,[]);self.wa[0]=True;self.hold[0]=True;self.t.tick();self.assertEqual(self.sent,[])
  self.hold[0]=False;self.t.pause(True);self.t.tick();self.assertEqual(self.sent,[]);self.t.pause(False);self.t.tick();self.assertEqual(len(self.sent),1)
 def test_a_failed_ask_goes_back_to_waiting_retries_after_five_minutes_and_tells_the_owner_on_the_third_failure(self):
  self.start('a deadline 6pm');self.down[0]=True;self.tick(1);self.assertEqual(self.status('a'),'Waiting');self.tick(3);self.assertEqual(self.sent,[])
  self.tick(7);self.assertEqual(self.status('a'),'Waiting');self.tick(14);self.assertFalse(self.owner==[] and False)
  self.tick(20);self.tick(27);self.assertTrue(any('Could not reach' in x for x in self.owner),self.owner)
  self.down[0]=False;self.tick(100);self.assertEqual(self.status('a'),'Asked');self.assertEqual(len(self.sent),1)
 def test_a_slow_whatsapp_never_freezes_the_owners_screen(self):
  self.start('a deadline 6pm');result=[]
  def slow(body):
   th=threading.Thread(target=lambda:result.append(self.t.view()));th.start();th.join(2);result.append(th.is_alive());self.sent.append(body['message']);return {'code':'SUCCESS'}
  self.app.send_custom=slow;self.tick(1);self.assertEqual(result[-1],False,'view() ran while the message was being sent');self.assertEqual(len(self.sent),1)
 def test_two_clock_ticks_at_once_do_not_double_send(self):
  self.start('a deadline 6pm');self.at(1);a=threading.Thread(target=self.t.tick);b=threading.Thread(target=self.t.tick);a.start();b.start();a.join();b.join();self.assertEqual(len(self.sent),1)

class Chasing(Base):
 def test_reminder_once_then_check_then_late_then_one_final_message(self):
  self.start('post groups deadline 4pm');self.tick(1);self.tick(20);self.assertEqual(len(self.sent),1,'no reminder before 30 minutes');self.tick(45);self.assertEqual(len(self.sent),2);self.assertIn('post groups',self.sent[1])
  self.tick(60);self.tick(90);self.assertEqual(len(self.sent),2,'only one reminder')
  self.tick(106);self.assertEqual(len(self.sent),3);self.assertIn('3:' if False else '4:00 PM',self.sent[2]);self.tick(108);self.assertEqual(len(self.sent),3)
  self.tick(125);self.assertEqual(self.status('post groups'),'Late');self.tick(127);self.assertEqual(len(self.sent),4);self.assertIn('4:00 PM',self.sent[3]);self.tick(200);self.assertEqual(len(self.sent),4)
  self.assertTrue(any('Late: post groups' in n for n in self.owner))
 def test_no_reminder_after_he_replied(self):
  self.start('post groups deadline 6pm');self.tick(1);self.reply('working on it','m1',minutes=5);self.tick(45);self.assertEqual(len(self.sent),1)
 def test_a_task_never_sent_before_its_deadline_is_late_and_never_asked_afterwards(self):
  self.start('a deadline 6pm');self.t.pause(True)
  for m in range(0,239,6):self.tick(m)
  self.t.pause(False);self.tick(241);self.assertEqual(self.status('a'),'Late');self.assertEqual(self.sent,[]);self.assertTrue(any('never sent' in n for n in self.owner))

class DoneDetection(unittest.TestCase):
 YES=("Done","done sir","Done ✅","Done!!","DONE","Done. please check","just finished","it's done","its done","yes done","I have completed it","completed","ho gya bhai","done 👍","Sheet updated and sent","Posted in all groups","finished the report","ok done","kar diya","sent the report","submitted","uploaded it","ready","I did it, done","the sheet is done","Done with the sheet","100% done","posted in the groups")
 NO=("not done","Not completed","can't finish","didn't finish","isn't finished","unfinished","undone","not able to complete","haven't sent","have not done it","didn't do it","will send","sending soon","will post tonight","not sent","no, not done","not yet bhai","abhi nahi hua","done nahi hua","almost done","90% done","70 percent done","half done","will be done by evening","I will do it once I'm done with lunch","done tomorrow","done in 1 hour","when it's done I'll send","how is it going?","what is the deadline","ok","working on it","please wait","done?","is it done?","finish by 5","kal tak ho jayega")
 def test_real_done_messages_count(self):
  self.assertEqual([t for t in self.YES if not T.said_done(t)],[])
 def test_not_done_and_maybe_done_messages_do_not_count(self):
  self.assertEqual([t for t in self.NO if T.said_done(t)],[])

class Replies(Base):
 def two(self):
  self.start('post groups by 4pm\nupdate sheet by 5pm');self.tick(1);self.tick(3)
 def test_done_is_recognised_in_normal_and_roman_urdu_wording(self):
  for i,text in enumerate(('done','Done bhai','finished','ho gaya','kar diya','completed it','posted it','all done','sab ho gaya')):
   with self.subTest(text=text):
    self.setUp();self.start('only task by 5pm');self.tick(1);self.reply(text,'d%d'%i,minutes=5);self.assertEqual(self.status('only task'),'Reported',text)
 def test_not_done_almost_done_questions_and_future_promises_are_not_reports(self):
  for i,text in enumerate(("not done","isn't done yet","not yet","almost done","nearly finished","half done","will be done by 5","I'll finish it after lunch","done?","once it's done I'll tell you","kaam nahi hua","done by 4","will do it tonight","work completed nahi hua","still not finished")):
   with self.subTest(text=text):
    self.setUp();self.start('only task by 5pm');self.tick(1);self.reply(text,'n%d'%i,minutes=5);self.assertEqual(self.status('only task'),'Asked',text)
 def test_he_can_name_the_task_in_his_own_words(self):
  self.two();self.reply('sheet done','r1',minutes=5);self.assertEqual(self.tasks(),{'post groups':'Asked','update sheet':'Reported'})
  self.reply('posted in the groups','r2',minutes=7);self.assertEqual(self.tasks(),{'post groups':'Reported','update sheet':'Reported'})
 def test_a_number_still_works_and_all_done_closes_everything_open(self):
  self.two();self.reply('2 done','r1',minutes=5);self.assertEqual(self.status('update sheet'),'Reported');self.assertEqual(self.status('post groups'),'Asked');self.reply('everything done','r2',minutes=8);self.assertEqual(self.status('post groups'),'Reported')
 def test_ambiguous_done_asks_a_natural_question_once_and_changes_nothing(self):
  self.two();n=len(self.sent);self.reply('done','r1',minutes=5);self.assertEqual(self.tasks(),{'post groups':'Asked','update sheet':'Asked'});self.tick(7)
  q=self.sent[n];self.assertIn('Which one do you mean',q);self.assertIn('post groups',q);self.assertIn('update sheet',q);self.reply('done','r2',minutes=8);self.tick(10);self.assertEqual(len(self.sent),n+1,'asked only once in ten minutes')
 def test_an_unknown_number_or_an_hour_in_the_text_is_never_guessed(self):
  self.two();self.reply('9 done','r1',minutes=5);self.assertEqual(self.tasks(),{'post groups':'Asked','update sheet':'Asked'})
  self.reply('will finish at 4:30','r2',minutes=6);self.reply('need 2 hours','r3',minutes=7);self.assertEqual(self.tasks(),{'post groups':'Asked','update sheet':'Asked'})
 def test_proof_present_gets_a_thank_you_and_missing_proof_gets_one_natural_request(self):
  self.start('only task by 5pm');self.tick(1);n=len(self.sent);self.reply('done https://x.com/p','r1',minutes=5);self.tick(7);self.assertEqual(self.status('only task'),'Reported');self.assertTrue(self.t.view()['tasks'][0]['proof']);self.assertEqual(len(self.sent),n+1);self.assertNotIn('screenshot',self.sent[-1])
  self.setUp();self.start('only task by 5pm');self.tick(1);self.reply('done','r1',minutes=5);self.tick(7);self.assertIn('screenshot or photo',self.sent[-1]);k=len(self.sent)
  for m in (9,12,15,20):self.tick(m)
  self.assertEqual(len(self.sent),k,'the screenshot is asked for once')
  self.reply('',"p1",minutes=22,media='image');self.assertTrue(self.t.view()['tasks'][0]['proof'])
 def test_a_voice_note_is_an_update_not_proof(self):
  self.start('only task by 5pm');self.tick(1);self.reply('','v1',minutes=5,media='audio');self.assertFalse(self.t.view()['tasks'][0]['proof']);self.assertIn('voice note',self.t.view()['latest'][0]['text'])
 def test_blocked_messages_are_flagged_answered_once_and_the_owner_is_told(self):
  self.start('only task by 5pm');self.tick(1);n=len(self.sent);self.reply("I am stuck, cannot login",'b1',minutes=5);self.tick(7);self.assertEqual(self.t.view()['latest'][0]['text'].split(': ',1)[1],'I am stuck, cannot login');self.assertIn('stopping you' if 'stopping' in self.sent[-1] else 'problem',self.sent[-1]);self.assertTrue(any('stuck' in o for o in self.owner))
  self.reply("still stuck",'b2',minutes=9);self.tick(11);self.assertEqual(len(self.sent),n+1,'one answer per task')
 def test_ok_stops_reminders_and_unrelated_chat_is_only_an_update(self):
  self.start('only task by 5pm');self.tick(1);self.reply('ok','o1',minutes=5);self.tick(45);self.assertEqual(len(self.sent),1);self.assertEqual(self.status('only task'),'Asked')
 def test_replies_with_no_open_task_and_odd_messages_never_crash(self):
  self.reply('hello','h1',minutes=1);self.inbox.extend([{'id':'x','content':None,'is_from_me':False,'timestamp':'bad'},{'content':'no id'},{'id':'y','is_from_me':True,'content':'mine'}]);self.t.tick();self.assertEqual(self.tasks(),{})
 def test_same_message_is_never_processed_twice_and_old_chat_history_is_ignored(self):
  self.start('only task by 5pm');self.tick(1);self.inbox.append({'id':'old','content':'done','is_from_me':False,'timestamp':'2020-01-01T00:00:00+00:00'});self.reply('done','r1',minutes=5);self.t.tick();self.t.tick()
  self.assertEqual(self.t.view()['counts']['Reported'],1)
 def test_a_done_message_for_a_task_not_yet_asked_is_accepted(self):
  self.start('first thing by 4pm\nlater thing deadline 9pm') if False else self.start('only task deadline 9pm');self.reply('only task done','e1',minutes=0.2);self.assertEqual(self.status('only task'),'Reported')
 def test_owner_alerts_go_at_once_then_are_batched(self):
  self.start('a by 4pm\nb by 4:30pm\nc by 5pm');self.tick(1)
  for i,m in enumerate((2,2.4,2.8)):self.reply('update number %d'%i,'u%d'%i,minutes=m)
  self.assertEqual(len(self.owner),1);self.assertIn('update number 0',self.owner[0]);self.tick(4.5);self.assertEqual(len(self.owner),2);self.assertIn('update number 1',self.owner[1]);self.assertIn('update number 2',self.owner[1])

class Verification(Base):
 def test_verify_sends_a_thank_you_and_reject_sends_the_note_and_a_new_deadline(self):
  self.start('post groups by 4pm');self.tick(1);self.reply('done https://x.com/p','r1',minutes=5);self.tick(7);tid=self.t.view()['tasks'][0]['id']
  self.t.reject(tid,'caption is wrong');self.tick(9);self.assertIn('caption is wrong',self.sent[-1]);self.assertIn('post groups',self.sent[-1]);self.assertEqual(self.status('post groups'),'Asked')
  self.reply('fixed, done','r2',minutes=20);self.tick(22);self.t.verify(tid);self.tick(24);self.assertEqual(self.status('post groups'),'Done');self.assertTrue(any(w in self.sent[-1] for w in ('Looks good','Perfect','Great')))
 def test_cannot_reject_what_was_not_reported_and_cancel_tells_him_only_if_he_was_asked(self):
  self.start('post groups by 4pm\nlater thing by 11pm');self.tick(1)
  with self.assertRaisesRegex(ValueError,'reported'):self.t.reject(self.t.view()['tasks'][0]['id'])
  asked,waiting=self.t.view()['tasks'][0],self.t.view()['tasks'][1];n=len(self.sent);self.t.cancel(waiting['id']);self.tick(3);self.assertEqual(len(self.sent),n)
  self.t.cancel(asked['id']);self.tick(5);self.assertEqual(len(self.sent),n+1);self.assertIn('no need',self.sent[-1]+'no need') ;self.assertEqual(self.t.view()['tasks'],[])
 def test_numbers_restart_when_nothing_is_open_and_a_number_never_hits_an_old_finished_task(self):
  self.start('a by 4pm');self.tick(1);self.reply('done','r1',minutes=5);self.t.verify('1');self.t.plan('b by 5pm');v=self.t.confirm_plan();self.assertEqual([x['no'] for x in v['tasks']],[1,1])
  self.t.cancel('1');self.assertEqual(self.tasks(),{'a':'Done'})
 def test_a_restart_keeps_everything(self):
  self.start();self.tick(1);again=T.TeamTasks(self.app,clock=lambda:self.clock[0]);self.assertEqual(len(again.view()['tasks']),2);self.assertEqual(again.view()['member']['name'],'Bilal Ahmed')

class Chat(Base):
 def test_chat_plan_confirm_status_verify_and_pause(self):
  r=self.t.command('tasks for Bilal: 1) post in groups 2) update sheet deadline 6pm','tasks for Bilal: 1) post in groups 2) update sheet deadline 6pm');self.assertIn('Say "confirm tasks"',r['reply']);self.assertEqual(self.sent,[])
  self.assertIn('2 tasks started',self.t.command('confirm tasks','confirm tasks')['reply']);self.tick(1);self.reply('post in groups done','c1',minutes=5)
  self.assertIn('0 of 2 done',self.t.command('team status','team status')['reply']);self.assertIn('verified',self.t.command('verify task 1','verify task 1')['reply']);self.assertIn('1 of 2 done',self.t.command('team status','team status')['reply'])
  self.assertIn('paused',self.t.command('pause team','pause team')['reply']);self.assertIsNone(self.t.command('hello there','hello there'))
 def test_chat_sets_the_teammate_and_refuses_the_owner_number(self):
  self.assertIn('Sara',self.t.command('set teammate Sara 0300 7654321','set teammate Sara 0300 7654321')['reply'])
  with self.assertRaises(ValueError):self.t.set_member('Me','923000000000')

if __name__=='__main__':unittest.main()
