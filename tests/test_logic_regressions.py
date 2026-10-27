"""Owner-intent and model-boundary regressions; all transports are fake."""
import copy,json,unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
import assistant,chat_runtime,chat_policy
import manual_commands
from test_ai_architecture import tc,msg

class LogicTests(unittest.TestCase):
 def model(self,text,responses,callbacks):
  with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',side_effect=responses):
   return assistant.chat(text,[],{},[],callbacks)

 def test_preview_and_inspection_never_authorize_send(self):
  for text in ('show me the message to send main','please preview what to send to givelife','draft a message to send all groups','tell me when to send main','review the message then send main'):
   for tool in chat_policy.SEND:
    with self.subTest(text=text,tool=tool):self.assertFalse(chat_policy.permitted(tool,text))
  # A preview is still allowed to prepare a draft, without sending it.
  self.assertTrue(chat_policy.permitted('prepare_dm','preview the DM to Ali'))
  self.assertTrue(chat_policy.permitted('send_appeal','please send main now'))

 def test_single_quoted_commands_are_data_but_apostrophes_are_preserved(self):
  for text in ("'send main'", "Explain 'send all groups'", "message says: 'send main'"):
   self.assertFalse(chat_policy.intent(text)['send'])
  self.assertFalse(chat_policy.intent("don't send main")['send'])
  self.assertTrue(chat_policy.intent("send 'hello' to Ali")['send'])

 def test_excluded_groups_are_removed_from_aggregate_targets(self):
  self.assertEqual(manual_commands.groups('send all freelance groups except fiverr'),['community','upwork','uet','toprated'])
  self.assertEqual(manual_commands.groups('send all groups but not main'),['community','fiverr','upwork','uet','toprated'])
  self.assertEqual(manual_commands.groups('send main and fiverr not upwork'),['main','fiverr'])
  self.assertEqual(manual_commands.groups('send all except fiverr course uet'),['main','community','fiverr','upwork','toprated'])
  self.assertEqual(manual_commands.groups('send all except main and fiverr'),['community','upwork','uet','toprated'])

 def test_legacy_and_malformed_retrieval_do_not_crash_or_mutate(self):
  for value in (None,42,'broken',{'text':'wrong container'},json.dumps([{'text':'old note'}]),['bad',None,{'text':'valid'}]):
   state={'retrieved':value};before=copy.deepcopy(state)
   messages=chat_runtime.context_messages('Explain the caption',[],state,[])
   self.assertEqual(messages[-1]['content'],'Explain the caption');self.assertEqual(state,before)

 def test_context_does_not_truncate_the_original_retrieved_memory(self):
  state={'retrieved':[{'text':'x'*2000}]}
  chat_runtime.context_messages('Explain the caption',[],state,[])
  self.assertEqual(len(state['retrieved'][0]['text']),2000)

 def test_no_partial_execution_from_mixed_malformed_envelope(self):
  writes=[]
  for calls in ([tc('set_message',{'kind':'group','text':'good'}), 'broken'],[tc('set_message',{'kind':'group','text':'good'}),tc('set_message',{'kind':'group','text':'other'})]):
   result=self.model('rewrite group caption',[{'tool_calls':calls}],{'set_message':lambda **a:writes.append(a)})
   self.assertIn('No partial action',result['reply'])
  self.assertEqual(writes,[])

 def test_nonlist_tool_calls_are_not_interpreted_as_success(self):
  result=self.model('rewrite group caption',[{'content':'Saved.','tool_calls':'broken'}],{})
  self.assertIn('malformed',result['reply']);self.assertIn('No action was confirmed',result['reply'])

 def test_read_only_lookup_cannot_confirm_a_fabricated_mutation(self):
  result=self.model('find Ali',[msg(tc('find_contact',{'query':'Ali'})),{'content':'I saved the new caption.'},{'content':'Saved.'}],{'find_contact':lambda **a:'One Ali found.'})
  self.assertIn('do not have a confirmed tool result',result['reply'])

 def test_status_observation_does_not_trigger_an_unnecessary_model_retry(self):
  result=self.model('what is the update',[msg(tc('recent_activity',{})),{'content':'The last confirmed post was sent 5 minutes ago. Auto is on.'}],{'recent_activity':lambda:'Last confirmed post: 5 minutes ago; Auto ON.'})
  self.assertEqual(result['diagnostics']['iterations'],2);self.assertIn('5 minutes ago',result['reply'])

 def test_repaired_arguments_do_not_report_a_stale_error(self):
  writes=[]
  result=self.model('rewrite group caption',[msg(tc('set_message',{'kind':'group','text':42})),msg(tc('set_message',{'kind':'group','text':'correct'})),{'content':'Done.'}],{'set_message':lambda **a:(writes.append(a) or 'Draft changed.')})
  self.assertEqual(len(writes),1);self.assertEqual(result['reply'],'Draft changed.');self.assertEqual(result['diagnostics']['errors'],[])

 def test_provider_failure_is_a_structured_result_not_a_crash(self):
  result=self.model('how are you',[TimeoutError('Provider timed out')],{})
  self.assertIn('timed out',result['reply']);self.assertEqual(result['jobs'],[])

 def test_provider_failure_after_edit_preserves_actual_completion(self):
  result=self.model('rewrite group caption',[msg(tc('set_message',{'kind':'group','text':'correct'})),TimeoutError('Provider timed out')],{'set_message':lambda **a:'Draft changed.'})
  self.assertIn('Draft changed.',result['reply']);self.assertIn('timed out',result['reply'])

class ServerIntentTests(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def test_preview_cannot_take_the_fast_send_path(self):
  for text in ('show me the message to send main','preview message to send all groups','please show what to send givelife','draft a message to send main'):
   self.assertFalse(app.manual_command(text).get('handled'))
  self.assertEqual(self.sent,[]);self.assertEqual(app.LAST_MANUAL,{})

 def test_show_schedules_still_uses_fast_read_path(self):
  self.assertTrue(app.manual_command('show schedules')['handled']);self.assertEqual(self.sent,[])

 def test_excluded_group_cannot_be_reauthorized_by_contact_lookup(self):
  prompt='send all freelance groups except fiverr'
  callbacks=app.chat_callbacks(prompt,revision=0)
  with patch.object(app,'find_data',return_value=([{'id':app.GROUPS['fiverr'][1],'name':'Fiverr','group':True}],1)):
   callbacks['find_contact'](query='fiverr')
  with self.assertRaises(ValueError):callbacks['send_appeal'](target='fiverr')
  with self.assertRaises(ValueError):callbacks['send_appeal'](target='all')
  self.assertEqual(self.sent,[])

 def test_fast_path_passes_only_nonexcluded_groups_to_sender(self):
  with patch.object(app,'send_selected_groups',return_value={'reply':'Started fake job.'}) as wire:
   self.assertTrue(app.manual_command('send all freelance groups except fiverr')['handled'])
  self.assertEqual(wire.call_args.args[0],['community','upwork','uet','toprated']);self.assertEqual(self.sent,[])

 def test_empty_or_unknown_exclusion_does_not_fall_back_to_previous_group(self):
  app.LAST_MANUAL.update(kind='appeal',target='main')
  for prompt in ('send all except all','send main except main','send all except unknown group'):
   with self.subTest(prompt=prompt):
    with self.assertRaises(ValueError):app.manual_command(prompt)
    with self.assertRaises(ValueError):app.chat_callbacks(prompt,revision=app.OWNER_REVISION)['send_appeal'](target='main')
  self.assertEqual(self.sent,[])

if __name__=='__main__':unittest.main()
