"""Regression for the owner's real chat: "resume group dm's by 11 am" resumed DMs immediately and
"Givelife main today by 11am" was not understood as a time. Synthetic data; no WhatsApp."""
import datetime as dt
import unittest
import test_manual_sends as fixture
from test_manual_sends import app
import timed_tasks,chat_policy

NOW=dt.datetime(2026,11,3,9,0,tzinfo=timed_tasks.PKT).timestamp()

class ClockWording(unittest.TestCase):
 def due(self,text):
  value=timed_tasks.due_time(text,NOW)
  return None if value is None else dt.datetime.fromtimestamp(value,timed_tasks.PKT).strftime('%d %H:%M')
 def test_by_at_till_and_bare_clock_forms(self):
  for text,expected in (("resume group dm's by 11 am",'03 11:00'),('Givelife main today by 11am','03 11:00'),('by 11:30pm','03 23:30'),
    ('till 10 pm','03 22:00'),('at 9','04 09:00'),('tomorrow 8am','04 08:00'),('in 2 hours','03 11:00'),('after 30 min','03 09:30')):
   with self.subTest(text=text):self.assertEqual(self.due(text),expected)
 def test_no_time_is_none_and_conflicting_times_are_refused(self):
  self.assertIsNone(self.due('resume the dms'))
  with self.assertRaises(ValueError):self.due('send at 9am and 11am')
  self.assertEqual(self.due('at 11am and again by 11 am'),'03 11:00')
 def test_a_passed_time_is_never_guessed(self):
  with self.assertRaises(ValueError):self.due('by 8am today')

 def test_schedule_with_by_is_a_real_task(self):
  plan=timed_tasks.parse('schedule send to GiveLife main by 11am',NOW)
  self.assertEqual((plan['command'],plan['action'],plan['clock']),('create','send','11:00'))
  self.assertEqual(plan['targets'],['main'])

 def test_group_answer_after_a_schedule_question_keeps_the_time(self):
  history=[{'who':'you','text':'Schedule send by 11 am'},{'who':'app','text':'Which group should I schedule? For example: send to GiveLife main tomorrow at 9pm.'}]
  follow=chat_policy.followup('Givelife main today by 11am',history)
  self.assertTrue(follow['inherited'])
  plan=timed_tasks.parse(follow['text'],NOW)
  self.assertEqual((plan['action'],plan['targets'],plan['clock']),('send',['main'],'11:00'))

class ResumeDmsAtATime(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def test_resume_dms_by_11am_is_scheduled_not_immediate(self):
  hub=app.donors();hub.pause_personal()
  out=hub.command("Hi resume group dm's by 11 am",'transcript-1')
  self.assertTrue(hub.paused)
  self.assertEqual(hub.resume_status().get('state'),'Pending')
  self.assertNotIn('available again',str(out))
  self.assertIn('11:00',str(out))

 def test_resume_dms_without_a_time_still_resumes_now(self):
  hub=app.donors();hub.pause_personal()
  hub.command('resume dms','transcript-2')
  self.assertFalse(hub.paused)

 def test_timed_resume_when_not_paused_changes_nothing(self):
  hub=app.donors();hub.resume_personal()
  out=hub.command('resume dms at 11am','transcript-3')
  self.assertIn('not stopped',str(out))
  self.assertFalse(hub.paused)

if __name__=='__main__':unittest.main()
