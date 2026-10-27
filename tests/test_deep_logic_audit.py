"""Adversarial owner-intent and tool-contract regressions; no real transport."""
import copy,json,time,threading,unittest
from unittest.mock import patch
import manual_commands as commands,chat_policy,assistant,draft_flow
import test_manual_sends as fixture
from test_ai_architecture import tc,msg
app=fixture.app

class ParserAuditTests(unittest.TestCase):
 def test_group_year_or_count_is_never_the_balance(self):
  for text in ('send in Upwork Community 2026 with 25k left','send all 6 groups with 25k left','send in Fiverr Course 2026 with Rs. 25,000 remaining'):
   with self.subTest(text=text):self.assertEqual(commands.parse(text)['amount'],25000)
 def test_payload_group_words_do_not_select_a_broadcast(self):
  for payload in ('all the best','main point is ready','free today'):
   plan=commands.parse('send '+payload+' to Ali');self.assertEqual(plan['kind'],'text');self.assertEqual(plan['to'],'Ali');self.assertEqual(plan['text'],payload)
 def test_balance_control_text_is_not_a_literal_caption(self):
  self.assertEqual(commands.parse('send current message with 25k to main')['kind'],'appeal')
 def test_conflicting_balance_cannot_silently_reuse_old_amount(self):
  with self.assertRaises(ValueError):commands.parse('send main with 25k left and 30k remaining')
 def test_future_actions_and_negated_stops_do_not_run_now(self):
  for text in ('delete latest message in main tomorrow','delete latest message in main not now','send main later','stop dms in 10 minutes','do not stop dms'):
   with self.subTest(text=text):self.assertIsNone(commands.parse(text))
 def test_hypothetical_is_not_a_command(self):
  for text in ('what if I send main now','should I send main','could I send all groups now'):
   self.assertIsNone(commands.parse(text));self.assertFalse(chat_policy.intent(text)['send'])
 def test_quoted_future_word_remains_literal_text(self):
  p=commands.parse('send "tomorrow" to Ali');self.assertEqual(p['text'],'tomorrow');self.assertTrue(chat_policy.intent('send "tomorrow" to Ali')['send'])
 def test_preview_options_do_not_rotate_or_save_a_caption(self):
  for name in ('new_wording','autopilot','set_left'):
   self.assertFalse(chat_policy.permitted(name,'show me 3 new hooks'))
 def test_deferred_and_negative_tool_permissions(self):
  for tool,text in [('delete_last_message','delete main later'),('hold','do not stop everything'),('set_left','do not change amount to 25k'),('autopilot','do not stop auto')]:
   self.assertFalse(chat_policy.permitted(tool,text),(tool,text))
 def test_separate_switch_instructions(self):
  self.assertIs(chat_policy.switch_request('turn Auto off and DMs on','auto'),False)
  self.assertIs(chat_policy.switch_request('turn Auto off and DMs on','dm'),True)
 def test_editing_a_future_word_is_not_a_deferred_external_action(self):
  self.assertTrue(chat_policy.permitted('set_message','remove the tomorrow line from the caption'))
 def test_small_bare_choice_is_not_money(self):
  self.assertIsNone(commands.parse('2'));self.assertFalse(chat_policy.permitted('set_left','2'))
  self.assertEqual(commands.parse('Rs. 2')['amount'],2);self.assertEqual(commands.parse('2k')['amount'],2000)
 def test_choice_requires_recent_draft_options(self):
  history=[{'who':'you','text':'show 3 hooks'},{'who':'app','text':'**1.**\nFirst hook\n\n**2.**\nSecond hook\n\n**3.**\nThird hook'}]
  self.assertEqual(draft_flow.selected_option('2',history),2);self.assertIsNone(draft_flow.selected_option('4',history));self.assertIsNone(draft_flow.selected_option('2',[]))
  history[0]['text']='show 3 contacts';self.assertIsNone(draft_flow.selected_option('2',history))

class ToolLoopAuditTests(unittest.TestCase):
 def model(self,text,responses,do):
  with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',side_effect=responses):return assistant.chat(text,[],{},[],do)
 def test_all_batch_arguments_checked_before_any_write(self):
  writes=[]
  result=self.model('rewrite group caption and set Fiverr pace to 45 minutes',[msg(tc('set_message',{'kind':'group','text':'good'},'a'),tc('set_group_pace',{'target':'fiverr','minutes':'wrong'},'b')),{'content':'I cannot finish.'}],{'set_message':lambda **a:writes.append(a),'set_group_pace':lambda **a:writes.append(a)})
  self.assertEqual(writes,[]);self.assertIn('wrong type',result['reply'])
 def test_repaired_batch_executes_each_write_once(self):
  writes=[]
  result=self.model('rewrite group caption and set Fiverr pace to 45 minutes',[msg(tc('set_message',{'kind':'group','text':'good'},'a'),tc('set_group_pace',{'target':'fiverr','minutes':'wrong'},'b')),msg(tc('set_message',{'kind':'group','text':'good'},'c'),tc('set_group_pace',{'target':'fiverr','minutes':45},'d')),{'content':'Done'}],{'set_message':lambda **a:(writes.append('caption') or 'Caption saved.'),'set_group_pace':lambda **a:(writes.append('pace') or '45 minutes.')})
  self.assertEqual(writes,['caption','pace']);self.assertIn('45 minutes',result['reply'])
 def test_failed_tool_result_is_not_a_completion(self):
  for value in ({'ok':False,'error':'Transport failed'},{'code':'ERROR','message':'Uncertain'},None):
   calls=[]
   result=self.model('send main',[msg(tc('send_appeal',{'target':'main'}))],{'send_appeal':lambda **a:(calls.append(a) or value)})
   self.assertEqual(len(calls),1);self.assertIn('Could not send_appeal',result['reply']);self.assertEqual(result['jobs'],[])
 def test_failed_read_blocks_a_dependent_send(self):
  sends=[]
  result=self.model('send dm to Ali',[msg(tc('find_contact',{'query':'Ali'},'a'),tc('send_dm_appeal',{'to':'923001234567'},'b'))],{'find_contact':lambda **a:{'error':'Lookup failed'},'send_dm_appeal':lambda **a:sends.append(a)})
  self.assertEqual(sends,[]);self.assertIn('failed',result['reply'])
 def test_uncertain_financial_write_is_not_retried(self):
  writes=[]
  def failed(amount):writes.append(amount);raise TimeoutError('Storage not confirmed')
  result=self.model('came 2000',[msg(tc('money_came',{'amount':2000})),msg(tc('money_came',{'amount':2000}))],{'money_came':failed})
  self.assertEqual(writes,[2000]);self.assertIn('not retried',result['reply'])
 def test_chosen_hook_has_edit_tool_but_no_money_or_send_tool(self):
  history=[{'who':'you','text':'show 2 hooks'},{'who':'app','text':'1. First hook\n2. Second hook'}];writes=[]
  with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',side_effect=[msg(tc('set_message',{'kind':'group','text':'Second hook'})),{'content':'Done'}]) as model:
   result=assistant.chat('2',history,{},[],{'set_message':lambda **a:(writes.append(a) or 'Caption saved.')})
  names={t['function']['name'] for t in model.call_args.args[2]};self.assertIn('set_message',names);self.assertNotIn('set_left',names);self.assertFalse(names & chat_policy.SEND);self.assertEqual(len(writes),1)
 def test_passive_completion_claim_without_evidence_is_rejected(self):
  result=self.model('rewrite the group caption',[{'content':'The caption is saved.'},{'content':'The caption is saved.'}],{})
  self.assertIn('not been saved',result['reply'])

class ServerAuditTests(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def test_edit_then_send_uses_ai_path(self):
  for text in ('make message in main and then send it','rewrite the caption and send main','came 2000 and send main'):
   self.assertFalse(app.fast_command_eligible(text));self.assertFalse(app.manual_command(text)['handled'])
  self.assertEqual(self.sent,[])
 def test_status_does_not_change_target_or_cancel_pending_instruction(self):
  caption=app.get_message('group')['text'];w=app.workflow();w.begin('make a message for givelife without poster','group',caption);w.commit('group',caption)
  app.OWNER_REVISION=7;before=copy.deepcopy(w.data)
  self.assertTrue(app.manual_command('freelance groups update')['handled']);self.assertEqual(app.OWNER_REVISION,7);self.assertEqual(w.data,before)
 def test_read_only_ai_request_does_not_cancel_inflight_edit(self):
  entered=threading.Event();release=threading.Event();app.OWNER_REVISION=7
  def answer(*a,**kw):entered.set();release.wait(2);return {'reply':'Fine','diagnostics':{}}
  with patch.object(app.assistant,'chat',side_effect=answer):
   ident=app.assistant_task({'text':'what is the update','request_id':'read-only-audit-01'});self.assertTrue(entered.wait(1));self.assertEqual(app.OWNER_REVISION,7);release.set()
   while not app.ASSIST_TASKS[ident].get('done'):time.sleep(.005)
 def test_read_only_request_cannot_replace_an_inflight_attachment(self):
  ready=threading.Event();release=threading.Event();seen={}
  def answer(text,*a,**kw):
   if text.startswith('rewrite'):ready.set();release.wait(2)
   seen[text]=app.current_chat_image();return {'reply':'Observed','diagnostics':{}}
  with patch.object(app.assistant,'chat',side_effect=answer):
   edit=app.assistant_task({'text':'rewrite group caption','image':'owner-picture','request_id':'image-audit-edit'});self.assertTrue(ready.wait(1))
   read=app.assistant_task({'text':'what is the update','request_id':'image-audit-read'})
   end=time.monotonic()+2
   while not app.ASSIST_TASKS[read].get('done') and time.monotonic()<end:time.sleep(.005)
   release.set()
   while not app.ASSIST_TASKS[edit].get('done') and time.monotonic()<end:time.sleep(.005)
  self.assertEqual(seen['rewrite group caption'],'owner-picture');self.assertIsNone(seen['what is the update'])
 def test_deletion_cannot_target_a_different_group(self):
  with patch.object(app,'delete_last_group') as delete:
   with self.assertRaises(ValueError):app.chat_callbacks('delete latest message in main',revision=0)['delete_last_message'](target='fiverr')
  delete.assert_not_called()
 def test_contact_message_cannot_use_a_group_word_from_the_payload(self):
  cb=app.chat_callbacks('send all the best to Ali',revision=0)
  with self.assertRaises(ValueError):cb['send_appeal'](target='all')
  self.assertEqual(self.sent,[])
  with patch.object(app,'send_with_image',return_value={'code':'SUCCESS','results':{}}) as wire:
   app.send_free('main','It was 25k left; now 23k left.',False,literal=True)
  wire.assert_called_once();self.assertEqual(app.read_left(),25000,'Quoted outgoing amounts are text, not balance edits')
 def test_auto_switch_cannot_be_reversed_by_model(self):
  with self.assertRaises(ValueError):app.chat_callbacks('turn auto off',revision=0)['autopilot'](on=True)
  self.assertFalse(app.auto_on())
 def test_group_setting_target_and_interval_match_instruction(self):
  for args in ({'target':'all','minutes':45},{'target':'fiverr','minutes':60}):
   with self.assertRaises(ValueError):app.chat_callbacks('set fiverr posts to every 45 minutes',revision=0)['set_group_pace'](**args)
 def test_oversized_donation_is_rejected_on_ai_path(self):
  with self.assertRaises(ValueError):app.chat_callbacks('came 30000',revision=0)['money_came'](amount=30000)
  self.assertEqual(app.read_left(),25000)
 def test_caption_cannot_invent_a_balance_or_be_empty(self):
  original=app.get_message('group')['text']
  for text in ('','Rs. 22,000 left. Account 03097458815'):
   with self.assertRaises(ValueError):app.chat_callbacks('rewrite group caption',revision=0)['set_message'](kind='group',text=text)
  self.assertEqual(app.get_message('group')['text'],original)
 def test_empty_lookup_cannot_authorize_a_contact(self):
  jid='923001234567@s.whatsapp.net'
  with patch.object(app,'find_data',return_value=([{'id':jid,'name':'Ali','group':False}],1)):
   cb=app.chat_callbacks('send dm to Ali',revision=0);cb['find_contact'](query='')
   with self.assertRaises(ValueError):cb['send_dm_appeal'](to=jid)
  self.assertEqual(self.sent,[])
 def test_success_with_malformed_metadata_does_not_crash(self):
  for data in ('message-sent',None,[]):
   app.record_delivery('fake', 'caption',{'code':'SUCCESS','results':data});self.assertIsNone(app.DELIVERIES['fake']['message_id'])
 def test_malformed_device_status_fails_closed(self):
  for data in ({'results':'broken'}, {'results':None},'broken'):
   with patch.object(app,'api',return_value=data):self.assertFalse(app.wa_ok())
 def test_corrupt_hold_record_stops_sending(self):
  app.HOLD.write_text('broken');self.assertTrue(app.on_hold())
 def test_direct_wording_edit_preserves_task_target_and_poster(self):
  caption='*Yousuf needs treatment. Rs. 25,000 left.*\n25 people donating Rs. 1,000 OR 13 people donating Rs. 2,000\nAccount 03097458815'
  app.save_draft('group',caption);w=app.workflow();w.begin('make message for main without poster only 3 lines','group',caption);w.commit('group',caption)
  app.manual_command('in messages add 2000 first then 1000');changed=app.get_message('group')['text']
  self.assertTrue(w.current('group',changed));self.assertEqual(w.data['target'],'main');self.assertFalse(w.data['poster']);self.assertEqual(len(changed.splitlines()),3);self.assertIn('03097458815',changed)
 def test_arrival_line_removal_keeps_task_ready(self):
  caption='Latest money came in.\nRs. 25,000 left.\nAccount 03097458815'
  app.save_draft('group',caption);w=app.workflow();w.begin('make message for main without poster','group',caption);w.commit('group',caption)
  app.manual_command('dont write this much came in delete');self.assertTrue(w.current('group',app.get_message('group')['text']));self.assertFalse(w.data['poster'])
 def test_small_choice_does_not_change_balance_and_can_save_only_same_draft(self):
  self.assertFalse(app.manual_command('2')['handled']);self.assertEqual(app.read_left(),25000)
  cb=app.chat_callbacks('2',revision=0,selection=2,selection_kind='group')
  with self.assertRaises(ValueError):cb['set_left'](left=2)
  with self.assertRaises(ValueError):cb['set_message'](kind='dm',text='Wrong draft')
  cb['set_message'](kind='group',text='Second hook. Rs. 25,000 left.');self.assertEqual(app.read_left(),25000)
