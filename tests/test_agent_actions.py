"""The chat agent's newer actions: own-text to a list of numbers, team tasks, volunteers, cases. Each must match the owner's own words."""
import sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_donor_hub as hub

class Agent(unittest.TestCase):
 def setUp(self):
  self.fx=hub.IntegrationTests();self.said=[];self.fx.setUp();self.app=self.fx.app;self.sent=[]
  self.p1=patch.object(self.app,'send_custom',side_effect=lambda b:(self.sent.append(b),{'code':'SUCCESS'})[1]);self.p1.start()
  self.p2=patch('time.sleep',lambda s:None);self.p2.start();self.p3=patch.object(self.app,'chat_add',side_effect=lambda who,text,**k:self.said.append(text));self.p3.start()
 def tearDown(self):self.p1.stop();self.p2.stop();self.p3.stop();self.fx.tearDown()
 def cb(self,prompt):return self.app.chat_callbacks(prompt,revision=self.app.OWNER_REVISION)
 def wait(self):
  import threading
  for th in threading.enumerate():
   if th.name.startswith('text-list-'):th.join(5)
 def test_own_text_goes_to_every_number_written_and_the_result_is_reported(self):
  prompt='send "Meeting at 5 pm today" to 03001234567, 03007654321 and 0333 1112223'
  r=self.cb(prompt)['send_text_list'](text='Meeting at 5 pm today',phones=['03001234567','03007654321','03331112223']);self.wait()
  self.assertIn('3 numbers',r);self.assertEqual([b['message'] for b in self.sent],['Meeting at 5 pm today']*3);self.assertEqual({b['kind'] for b in self.sent},{'owner_text'})
  self.assertEqual(self.said,['Your message went to 3 of 3 numbers. All delivered.'])
 def test_reworded_text_unknown_numbers_and_no_send_request_are_refused(self):
  prompt='send "Meeting at 5" to 03001234567'
  with self.assertRaisesRegex(ValueError,'exact words'):self.cb(prompt)['send_text_list'](text='Our meeting is at 5',phones=['03001234567'])
  with self.assertRaisesRegex(ValueError,'written in your message'):self.cb(prompt)['send_text_list'](text='Meeting at 5',phones=['03009999999'])
  with self.assertRaises(ValueError):self.cb('what does "Meeting at 5" to 03001234567 mean?')['send_text_list'](text='Meeting at 5',phones=['03001234567'])
  self.wait();self.assertEqual(self.sent,[])
 def test_team_plan_needs_a_clear_confirm_before_anything_starts(self):
  self.app.donors().team.set_member('Bilal','03001112222')
  out=self.cb('team tasks: update the sheet deadline 11pm')['team_action'](action='plan',text='update the sheet deadline 11pm');self.assertIn('nothing sent',out)
  with self.assertRaisesRegex(ValueError,'confirm'):self.cb('what about the team tasks')['team_action'](action='confirm')
  self.assertIn('started',self.cb('confirm the team tasks')['team_action'](action='confirm'))
  self.assertIn('sheet',self.cb('team status')['team_action'](action='status'))
  self.assertEqual(self.cb('cancel the sheet task')['team_action'](action='cancel',task='sheet'),'Cancelled.')
 def test_volunteers_and_cases_follow_the_owner_words(self):
  with self.assertRaisesRegex(ValueError,'number'):self.cb('add volunteer Sara')['volunteer_action'](action='add',name='Sara',phone='03001234567')
  self.assertEqual(self.cb('add volunteer Sara 03001234567')['volunteer_action'](action='add',name='Sara',phone='03001234567'),'Volunteer added.')
  with self.assertRaisesRegex(ValueError,'exact words'):self.cb('volunteer message: please share')['volunteer_action'](action='set_message',text='Kindly share the case')
  with self.assertRaisesRegex(ValueError,'amount'):self.cb('start a new case for Maria')['case_action'](action='new',name='Maria',left=30000)
  self.assertIn('Maria',self.cb('start a new case for Maria, 30k needed')['case_action'](action='new',name='Maria',left=30000))
  with self.assertRaises(ValueError):self.cb('tell me a joke')['case_action'](action='list')

if __name__=='__main__':unittest.main()
