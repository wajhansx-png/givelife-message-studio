"""Failure lessons, habit tips, and owner shortcuts."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chat_memory import Knowledge
import chat_policy

class Learning(unittest.TestCase):
 def setUp(self):
  self.d=tempfile.TemporaryDirectory();self.k=Knowledge(self.d.name)
 def tearDown(self):self.d.cleanup()
 def test_a_failure_is_remembered_once_and_counted(self):
  self.k.learn_failure('send_message','No contact named Ali was found.','send hi to ali');self.k.learn_failure('send_message','No contact named Ali was found.','send hi to ali')
  self.assertEqual(len(self.k.data['lessons']),1);self.assertEqual(self.k.data['lessons'][0]['count'],2)
 def test_lessons_come_back_only_for_related_requests(self):
  self.k.learn_failure('send_message','No contact named Ali was found.','send hi to ali')
  self.assertTrue(self.k.lessons_for('send a message to ali'));self.assertEqual(self.k.lessons_for('how much is left'),[])
 def test_owner_decisions_and_outages_are_not_lessons(self):
  for e in ('Superseded by your newer instruction.','The current instruction does not ask for this.','The AI is not connected.'):self.assertIsNone(self.k.learn_failure('x',e))
  self.assertEqual(self.k.data['lessons'],[])
 def test_lessons_survive_a_restart(self):
  self.k.learn_failure('dm_list','Phone number is invalid.','dm these');again=Knowledge(self.d.name);self.assertEqual(len(again.data['lessons']),1)
 def test_habit_tip_comes_once_on_the_third_time(self):
  t='send dms to important donors now';self.assertEqual(self.k.count_habit(t),'');self.assertEqual(self.k.count_habit(t),'')
  tip=self.k.count_habit(t);self.assertIn('3 times',tip);self.assertEqual(self.k.count_habit(t),'')
 def test_short_chatter_is_not_a_habit(self):
  for _ in range(5):self.assertEqual(self.k.count_habit('ok'),'')
 def test_shortcut_runs_only_on_the_exact_name(self):
  self.k.shortcut_save('Morning Run','post in main group then dm 10 donors')
  self.assertEqual(self.k.expand('morning run'),'post in main group then dm 10 donors');self.assertEqual(self.k.expand(' Morning   Run! '),'post in main group then dm 10 donors')
  self.assertEqual(self.k.expand('do the morning run please'),'do the morning run please')
 def test_shortcut_save_replace_delete_and_limits(self):
  self.k.shortcut_save('a','one');self.k.shortcut_save('a','two');self.assertEqual(self.k.shortcut_list()[0]['steps'],'two');self.assertEqual(len(self.k.shortcut_list()),1)
  self.assertTrue(self.k.shortcut_delete('a'));self.assertFalse(self.k.shortcut_delete('a'))
  with self.assertRaises(ValueError):self.k.shortcut_save('','x')
  with self.assertRaises(ValueError):self.k.shortcut_save('one two three four five','x')
 def test_shortcuts_need_the_owner_to_ask_and_status_is_a_read(self):
  self.assertTrue(chat_policy.permitted('shortcut_action','save shortcut morning: post'));self.assertFalse(chat_policy.permitted('shortcut_action','send hi to ali'))
  self.assertTrue(chat_policy.permitted('app_status','what is going on'))
if __name__=='__main__':unittest.main()
