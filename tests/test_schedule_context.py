"""The owner's real failures: duplicate schedules and 'cancel 2nd' that the app could not do."""
import copy,datetime,tempfile,threading,unittest
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

class ScheduleContext(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.now=datetime.datetime(2026,10,29,8,0,tzinfo=tt.PKT).timestamp()
  self.s=tt.Scheduler(Path(self.temp.name)/'t.json',Store(),lambda t:{'message':'ok'},lambda i:None,lambda t:True,clock=lambda:self.now)
 def add(self,text,request_id=None):return self.s.command(text,request_id)
 def pending(self):return [x for x in self.s.tasks if x['state']=='pending']

 def test_same_task_twice_is_not_added_twice_even_minutes_apart(self):
  self.add('Resume givelife main sending auto on by 10am today',request_id='a')
  self.now+=300
  reply=self.add('resume main at 10am today',request_id='b')
  self.assertEqual(len(self.pending()),1);self.assertIn('already have this exact task',reply)

 def test_different_times_or_targets_are_separate(self):
  self.add('send to main at 9pm');self.add('send to fiverr at 9pm');self.add('send to main at 10pm')
  self.assertEqual(len(self.pending()),3)

 def test_cancel_second_keeps_first_exactly_as_the_owner_asked(self):
  self.add('send to main at 9pm');self.add('send to fiverr at 9pm')
  first,second=self.pending()
  reply=self.add('Only 1 please cancel 2nd')
  self.assertEqual(second['state'],'cancelled');self.assertEqual(first['state'],'pending')
  self.assertIn(first['id'],reply);self.assertIn('Cancelled',reply)

 def test_cancel_first_last_and_by_id(self):
  for g in ('main','fiverr','upwork'):self.add(f'send to {g} at 9pm')
  a,b,c=self.pending()
  self.add('cancel last schedule');self.assertEqual(c['state'],'cancelled')
  self.add('cancel 1st');self.assertEqual(a['state'],'cancelled')
  self.add('cancel schedule '+b['id']);self.assertEqual(b['state'],'cancelled')
  self.assertEqual(self.add('cancel schedule'),'There is nothing to cancel. No schedule is pending.')

 def test_cancel_duplicate_removes_only_extra_copies(self):
  # Simulate an older duplicate already saved before the guard existed.
  self.add('send to main at 9pm');one=self.pending()[0]
  twin=dict(one,id='deadbeef',signature='x',request_id='r');self.s.tasks.append(twin)
  self.add('send to fiverr at 9pm')
  reply=self.add('cancel the duplicate')
  self.assertEqual(one['state'],'pending');self.assertEqual(twin['state'],'cancelled');self.assertEqual(len(self.pending()),2);self.assertIn('Cancelled',reply)
  self.assertIn('no duplicate',self.add('cancel the duplicate'))

 def test_cancel_all_and_ambiguous_asks_which(self):
  self.add('send to main at 9pm');self.add('send to fiverr at 9pm')
  with self.assertRaises(ValueError) as e:self.add('cancel schedule')
  self.assertIn('Which one?',str(e.exception));self.assertEqual(len(self.pending()),2)
  self.add('cancel all schedules');self.assertEqual(len(self.pending()),0)

 def test_one_pending_cancel_needs_no_question(self):
  self.add('send to main at 9pm');self.add('cancel the schedule');self.assertEqual(len(self.pending()),0)

 def test_out_of_range_position_is_explained(self):
  self.add('send to main at 9pm');self.assertIn('only 1 pending',self.add('cancel 3rd schedule').replace('There are only 1 pending schedule(s).','only 1 pending'))

 def test_listing_is_numbered_and_matches_positions(self):
  self.add('send to main at 9pm');self.add('send to fiverr at 9pm')
  lines=self.s.list().split('\n');self.assertTrue(lines[0].startswith('1. #'));self.assertTrue(lines[1].startswith('2. #'))
  summary=self.s.summary();self.assertEqual([x['position'] for x in summary],[1,2])

 def test_phrases_that_are_not_schedule_cancels(self):
  for text in ['delete the last message in main','delete last message','do not cancel anything','what happens if I cancel schedule','remove the bold from the caption']:
   with self.subTest(text=text):self.assertFalse(tt.cancel_request(text))

 def test_assistant_may_use_the_schedule_tool_for_cancel_words(self):
  for text in ['Only 1 please cancel 2nd','cancel schedule 30cdc6cc','remove the duplicate schedule','cancel all schedules']:
   with self.subTest(text=text):self.assertTrue(chat_policy.permitted('schedule_task',text))
  self.assertFalse(chat_policy.permitted('schedule_task','what is my schedule?'))

 def test_state_for_the_ai_reports_real_schedules(self):
  import assistant
  self.add('send to main at 9pm')
  slim=assistant._slim({'schedules':self.s.summary(),'left':15000})
  self.assertEqual(slim['schedules'][0]['position'],1);self.assertIn('ALL pending',slim['schedules_note'])

if __name__=='__main__':unittest.main()
