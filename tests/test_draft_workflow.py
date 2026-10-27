import json,unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app,commands
import draft_workflow

CAPTION='*A short charity reminder.*\nYousuf needs treatment. *Rs. 25,000 left.* 💔\n*03097458815* Easypaisa / JazzCash (Wajdan Khan)'

class WorkflowTests(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 wait=fixture.SendTests.wait
 def draft(self,prompt='Make a message for givelife without poster only 3 lines',caption=CAPTION):
  app.chat_callbacks(prompt,revision=app.OWNER_REVISION)['set_message'](kind='group',text=caption)
  return app.next_chat_actions()
 def test_followup_keeps_recipient_mode_and_line_limit(self):
  self.draft();self.draft('Add breaking heart icon')
  task=app.workflow().data;self.assertEqual(task['target'],'main');self.assertFalse(task['poster']);self.assertEqual(task['max_lines'],3)
  self.assertIn('Send to GiveLife main',[a['label'] for a in app.next_chat_actions()])
 def test_total_line_limit_rejects_blank_lines_and_keeps_draft(self):
  self.draft();before=app.DRAFT.read_text(encoding='utf-8')
  with self.assertRaisesRegex(ValueError,'3 total lines'):self.draft('Only 3 lines man',CAPTION.replace('\n','\n\n'))
  self.assertEqual(app.DRAFT.read_text(encoding='utf-8'),before);self.assertEqual(app.next_chat_actions(),[])
 def test_test_send_preserves_exact_draft_and_production_target(self):
  actions=self.draft();self.draft('Add the poster to this message')
  actions=app.next_chat_actions();test=next(a for a in actions if a['target']=='test')
  start=app.execute_chat_action(test['id']);job=self.wait(start['job_id'])
  self.assertEqual(self.sent[0]['text'],CAPTION);self.assertEqual(app.get_message('group')['text'],CAPTION)
  self.assertNotIn('next_caption',job);self.assertEqual(app.workflow().data['target'],'main')
 def test_action_is_idempotent_and_text_only_is_honored(self):
  action=next(a for a in self.draft() if a['target']=='main')
  sent=[]
  with patch.object(app,'send_text',side_effect=lambda jid,text:(sent.append((jid,text)) or {'code':'SUCCESS','results':{'message_id':'text-test'}})):
   one=app.execute_chat_action(action['id']);self.wait(one['job_id']);two=app.execute_chat_action(action['id'])
  self.assertEqual(one['job_id'],two['job_id']);self.assertEqual(sent,[(app.GROUPS['main'][1],CAPTION)]);self.assertEqual(self.sent,[])
 def test_stale_action_cannot_send_after_any_caption_edit(self):
  old=next(a for a in self.draft() if a['target']=='main');app.save_draft('group',CAPTION+' changed')
  with self.assertRaisesRegex(ValueError,'draft changed'):app.execute_chat_action(old['id'])
  self.assertEqual(self.sent,[])
 def test_generic_send_uses_current_task_not_old_toprated(self):
  app.LAST_MANUAL.update(kind='appeal',target='toprated');self.draft('Make a message for givelife with poster')
  result=app.manual_command('send now');self.wait(result['job_id'])
  self.assertEqual(self.sent[0]['phone'],app.GROUPS['main'][1]);self.assertEqual(self.sent[0]['text'],CAPTION)
 def test_unknown_task_recipient_never_falls_back(self):
  app.LAST_MANUAL.update(kind='appeal',target='toprated');self.draft('Make a short hadith message without poster')
  with self.assertRaisesRegex(ValueError,'previous recipient'):app.manual_command('send now')
  self.assertIn('Choose group',[a['label'] for a in app.next_chat_actions()]);self.assertEqual(self.sent,[])
 def test_workflow_survives_restart_and_explicit_poster_change(self):
  self.draft();old=app.workflow().data.copy();restored=draft_workflow.DraftWorkflow(app.DATA/'draft-workflow.json',app.STORE)
  self.assertEqual(restored.data['hash'],old['hash']);self.assertEqual(restored.data['target'],'main')
  result=app.manual_command('send test with poster');self.wait(result['job_id'])
  self.assertTrue(app.JOBS[result['job_id']]['with_picture']);self.assertEqual(app.get_message('group')['text'],CAPTION)
 def test_referential_hadith_instruction_never_becomes_literal_payload(self):
  self.assertEqual(commands.parse('Send this hadith message to givelife group')['kind'],'appeal')
  self.assertEqual(commands.parse('send "this hadith message" to givelife group')['kind'],'text')
 def test_hold_blocks_suggested_send(self):
  a=next(a for a in self.draft() if a['target']=='main');app.set_hold(True)
  with self.assertRaises(ValueError):app.execute_chat_action(a['id'])
  self.assertEqual(self.sent,[])
 def test_amount_update_preserves_task_caption_and_invalidates_old_buttons(self):
  caption='*Hadith reminder.*\n*_13 people donating Rs. 2,000_* OR *_25 people donating Rs. 1,000_*\n*Rs. 25,000 LEFT* · 03097458815'
  old=next(a for a in self.draft(caption=caption) if a['target']=='main');app.set_left(23000)
  text=app.get_message('group')['text'];self.assertIn('Hadith reminder',text);self.assertIn('23,000',text);self.assertIn('12 people',text);self.assertIn('23 people',text);self.assertIn('03097458815',text)
  self.assertEqual(app.workflow().data['target'],'main');self.assertFalse(app.workflow().data['poster'])
  with self.assertRaises(ValueError):app.execute_chat_action(old['id'])
 def test_unknown_or_forged_action_never_sends(self):
  self.draft()
  for ident in ('forged','b'*32,None):
   with self.assertRaises(ValueError):app.execute_chat_action(ident)
  self.assertEqual(self.sent,[])

if __name__=='__main__':unittest.main()
