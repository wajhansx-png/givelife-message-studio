"""Draft follow-ups use current owner intent and exact saved text; no real sends."""
import copy,json,unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
from test_ai_architecture import tc,msg
import assistant,chat_runtime,chat_policy,draft_flow

class DraftPolicyTests(unittest.TestCase):
 def test_supported_edit_families_have_save_permission(self):
  for text in ('Add this as hook reath point','First 2 lines very much triggered and new','Fluid is pressing line is now old man','Make it shorter','Move the last paragraph to the top','Add a bullet about the parents report','Write as per latest parents report he is now short on breath','Remove the second sentence','Keep the caption simple and change the opening','Please make it shorter','Could you rewrite the first paragraph','Put this first'):
   with self.subTest(text=text):
    self.assertTrue(draft_flow.editing_request(text));self.assertTrue(chat_policy.permitted('set_message',text));self.assertFalse(chat_policy.permitted('new_wording',text))
 def test_show_new_message_and_real_deletions_are_separate(self):
  self.assertIsNone(draft_flow.preview_request('Show a new message'))
  self.assertTrue(chat_policy.permitted('set_message','Show a new message'));self.assertFalse(chat_policy.permitted('new_wording','Show a new message'))
  for text in ('delete latest message u sent in givelife','What is the hook?','Show','Show message'):
   self.assertFalse(draft_flow.editing_request(text))
  self.assertFalse(draft_flow.editing_request('Always keep the caption short'))
 def test_style_request_without_destination_prepares_but_does_not_send(self):
  text='Sebd more emotional urgency message please.'
  self.assertTrue(draft_flow.editing_request(text));self.assertTrue(chat_policy.permitted('set_message',text));self.assertFalse(chat_policy.permitted('send_appeal',text))
  self.assertTrue(chat_policy.permitted('send_appeal','Send a more emotional message to main now'))
 def test_quoted_chat_log_cannot_authorize_edits_or_sends(self):
  for text in ('See fixes in logic: Add this as hook; send main','Chat log: rewrite message and send main','Transcript: Make it shorter; send main'):
   for name in ('set_message','send_appeal','new_wording'):
    self.assertFalse(chat_policy.permitted(name,text),(text,name))
 def test_edit_context_is_focused_but_keeps_owner_followups_and_saved_draft(self):
  state={'drafts':{'group':'Current saved caption'},'autopilot':True,'send_status':'Unexpected Auto status','engine':{'group_intervals':{'main':15}},'screen':{'view':'group'}}
  before=copy.deepcopy(state)
  messages=chat_runtime.context_messages('Add this as hook reath point',[{'who':'you','text':'His parents report shortness of breath.'}],state,[])
  context=json.loads(messages[-2]['content'].split('\n',1)[1])
  self.assertEqual(context['state']['drafts']['group'],'Current saved caption');self.assertNotIn('auto',context['state']);self.assertNotIn('status',context['state']);self.assertNotIn('group_intervals',context['state'])
  self.assertIn('parents report',context['recent_owner_instructions'][0]);self.assertEqual(state,before)

class DraftFlowTests(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def test_show_is_exact_read_only_and_has_no_unrelated_advice(self):
  original='*_Exact hook_*\n\nParents report shortness of breath.\n\n*Rs. 25,000 LEFT*\n03097458815'
  app.save_draft('group',original);before=copy.deepcopy(app.ENGINE.s)
  for text in ('Show','Shownhere','Show message','show the saved group caption','Can you show me the group message','Please display the current caption'):
   result=app.manual_command(text);self.assertTrue(result['handled']);self.assertEqual(result['reply'],original)
  self.assertEqual(app.ENGINE.s,before);self.assertEqual(self.sent,[])
 def test_show_current_dm_respects_active_view(self):
  app.save_draft('dm','Current DM only');app.save_draft('group','Current group only')
  self.assertEqual(app.manual_command('Show',message_kind='dm')['reply'],'Current DM only')
  self.assertEqual(app.manual_command('show group message',message_kind='dm')['reply'],'Current group only')
 def test_clear_hook_edit_is_nudged_to_save_then_show_matches_it(self):
  old=getattr(app,'DRAFT').read_text(encoding='utf-8');drafts=json.loads(old)
  updated='*_His parents report that he is now short of breath._*\n\n'+drafts['group']
  prompt='Add this as hook reath point';state={'drafts':drafts,'screen':{'view':'group'}}
  history=[{'who':'you','text':'Write as per latest parents report he is now short on breath.'}]
  with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',side_effect=[{'content':'Before I save, did you mean the breathing point?'},msg(tc('set_message',{'kind':'group','text':updated})),{'content':'Want me to send it?'}]) as model:
   result=assistant.chat(prompt,history,state,[],app.chat_callbacks(prompt,revision=app.OWNER_REVISION))
  self.assertEqual(result['reply'],'GROUP message saved.');self.assertEqual(app.manual_command('Show')['reply'],updated);self.assertEqual(self.sent,[])
  self.assertIn('save the complete revised caption now',json.dumps(model.call_args.args[3]))
 def test_unexecuted_edit_is_never_presented_as_saved(self):
  prompt='Make it shorter';before=app.DRAFT.read_text(encoding='utf-8')
  with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',return_value={'content':'Here is a shorter version. Want me to save?'}) as model:
   result=assistant.chat(prompt,[],{},[],app.chat_callbacks(prompt,revision=app.OWNER_REVISION))
  self.assertEqual(model.call_count,2);self.assertIn('has not been saved',result['reply']);self.assertEqual(app.DRAFT.read_text(encoding='utf-8'),before)
 def test_preview_runtime_needs_no_model_and_returns_exact_saved_text(self):
  app.save_draft('dm','*Brother*\n\nExact DM.')
  with patch.object(assistant,'client',return_value=None),patch.object(assistant,'_chat_raw',side_effect=AssertionError('No model for exact read')):
   result=assistant.chat('Show',[],{'screen':{'view':'dm'}},[],app.chat_callbacks('Show',revision=app.OWNER_REVISION))
  self.assertEqual(result['reply'],'*Brother*\n\nExact DM.');self.assertEqual(result['diagnostics']['iterations'],0)
 def test_get_message_does_not_rely_on_stale_context(self):
  app.save_draft('group','new saved version')
  result=app.chat_callbacks('show message',revision=app.OWNER_REVISION)['get_message'](kind='group')
  self.assertEqual(result['text'],'new saved version');self.assertEqual(self.sent,[])

 def test_edit_and_send_cannot_send_before_editing(self):
  prompt='Rewrite the caption and send main'
  with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',return_value=msg(tc('send_appeal',{'target':'main'}))):
   result=assistant.chat(prompt,[],{},[],app.chat_callbacks(prompt,revision=app.OWNER_REVISION))
  self.assertIn('must be saved before sending',result['reply']);self.assertEqual(self.sent,[])

 def test_stale_draft_save_cannot_overwrite_new_owner_edit(self):
  before=app.DRAFT.read_text(encoding='utf-8');app.OWNER_GUARD.revision=app.OWNER_REVISION-1
  try:
   with self.assertRaisesRegex(ValueError,'Superseded'):app.save_draft('group','obsolete model edit')
  finally:app.OWNER_GUARD.revision=None
  self.assertEqual(app.DRAFT.read_text(encoding='utf-8'),before)

 def test_http_preview_respects_view_without_ai_or_sending(self):
  import threading,urllib.request
  app.save_draft('dm','*Current DM*\n\nExact saved text.')
  http=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
  try:
   for path,body in [('/command',{'text':'Show','view':'dm'}),('/assistant',{'text':'Show message','screen':{'view':'dm'}})]:
    req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer test-only-studio-access-key','Content-Type':'application/json'})
    with urllib.request.urlopen(req) as response:result=json.load(response)
    self.assertEqual(result['reply'],'*Current DM*\n\nExact saved text.')
  finally:http.shutdown();http.server_close()
  self.assertEqual(self.sent,[])

if __name__=='__main__':unittest.main()
