"""Short owner replies ("yes", "kar do", "all groups", "shorter") must be understood from the
conversation: they continue the request just discussed, finish it, and never widen what may be sent."""
import json,unittest
from unittest.mock import patch
import assistant,chat_runtime,chat_policy,draft_flow,manual_commands
import test_manual_sends as fixture
from test_manual_sends import app

def call(name,args,ident='c1'):
 return {'content':'','tool_calls':[{'id':ident,'function':{'name':name,'arguments':json.dumps(args)}}]}
def chat(owner,app):return [{'who':'you','text':owner},{'who':'app','text':app}]

class Replay:
 """Run the real runtime with a scripted model and record which tools the model was offered."""
 def play(self,text,history,responses,do,state=None):
  with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',side_effect=responses) as model:
   result=chat_runtime.run_chat(text,history,state or {'case_name':'Yousuf','left':25000},[],do)
  self.offered=[t['function']['name'] for t in model.call_args_list[0].args[2]]
  self.model=model
  return result

class ConfirmationReplies(Replay,unittest.TestCase):
 def test_yes_finishes_the_edit_the_assistant_offered(self):
  saved=[]
  history=chat('make the dm shorter','Here is a 3-line version: "Brother, Yousuf needs Rs 25,000." Shall I save it?')
  state={'case_name':'Yousuf','left':25000,'draft_task':{'kind':'dm','state':'editing'},'screen':{'view':'dm'}}
  result=self.play('yes',history,[call('set_message',{'kind':'dm','text':'Brother, Yousuf needs Rs 25,000.'}),{'content':'Done.'}],
   {'set_message':lambda **kw:(saved.append(kw) or 'Saved the DM.')},state)
  self.assertIn('set_message',self.offered)
  self.assertEqual(len(saved),1)
  self.assertIn('Saved the DM',result['reply'])

 def test_urdu_kar_do_confirms_a_pending_send_the_assistant_asked_about(self):
  sent=[]
  history=chat('send the caption to all groups','Send the saved caption to every group now?')
  result=self.play('kar do',history,[call('send_appeal',{'target':'all'}),{'content':'ok'}],
   {'send_appeal':lambda **kw:(sent.append(kw) or 'WhatsApp confirmed the post.')})
  self.assertIn('send_appeal',self.offered)
  self.assertEqual(len(sent),1)
  self.assertIn('WhatsApp confirmed',result['reply'])

 def test_model_is_told_what_the_short_reply_answers(self):
  history=chat('send the caption to all groups','Send the saved caption to every group now?')
  self.play('haan kar do',history,[{'content':'Sent? no'}],{})
  context=next(m['content'] for m in self.model.call_args_list[0].args[3] if m['content'].startswith('APP_CONTEXT_JSON'))
  self.assertIn('continues_owner_request',context)
  self.assertIn('send the caption to all groups',context)

 def test_yes_alone_gives_no_permission_when_nothing_was_asked(self):
  history=chat('send the caption to all groups','Sent to 12 groups.')
  self.play('yes',history,[{'content':'Anything else?'}],{})
  self.assertEqual([n for n in self.offered if n not in chat_policy.READ],[])

 def test_yes_cannot_send_when_the_question_was_about_something_else(self):
  history=chat('send the caption to all groups','Saved. Want me to slow the pace afterwards?')
  self.play('yes',history,[{'content':'Pace slowed.'}],{})
  self.assertNotIn('send_appeal',self.offered)
  self.assertNotIn('send_message',self.offered)

 def test_old_do_not_send_still_wins_over_yes(self):
  history=chat("don't send it yet, just shorten the dm",'Shortened. Shall I save this?')
  followed=chat_policy.followup('yes',history)
  self.assertFalse(chat_policy.permitted('send_appeal',followed['text']))
  self.assertTrue(chat_policy.permitted('set_message',followed['text']))

 def test_yes_after_a_question_is_not_a_command(self):
  history=chat('what is the balance','Rs 25,000. Want me to change it?')
  self.assertFalse(chat_policy.followup('yes',history)['inherited'])

 def test_greeting_and_unrelated_yes_do_nothing(self):
  self.assertFalse(chat_policy.followup('yes',[])['inherited'])
  self.assertFalse(chat_policy.followup('yes',chat('hi','Hello! How can I help?'))['inherited'])

class AnswersToQuestions(Replay,unittest.TestCase):
 def test_group_choice_completes_the_pending_send(self):
  sent=[]
  history=chat('send the caption now','Which groups should I post to?')
  self.play('all groups',history,[call('send_appeal',{'target':'all'}),{'content':'ok'}],
   {'send_appeal':lambda **kw:(sent.append(kw) or 'WhatsApp confirmed the post.')})
  self.assertEqual(len(sent),1)

 def test_a_new_command_is_not_swallowed_as_an_answer(self):
  history=chat('send the caption now','Which groups should I post to?')
  result=chat_policy.followup('stop everything and set left 5000',history)
  self.assertFalse(result['inherited'])

class ShortEdits(unittest.TestCase):
 STATE={'draft_task':{'kind':'dm','state':'ready'},'screen':{'view':'dm'}}
 def test_refinements_are_edits_of_the_active_draft(self):
  for phrase in ('shorter','isko chota karo','chhota kar do','a bit longer','thoda lamba karo','also add jazzcash number','add the easypaisa account','remove the dua','same for group','more emotional','aur chota'):
   with self.subTest(phrase=phrase):
    self.assertTrue(draft_flow.contextual_edit(phrase,[],self.STATE))

 def test_refinements_need_an_active_draft(self):
  self.assertFalse(draft_flow.contextual_edit('shorter',[],{}))

 def test_non_draft_requests_are_not_refinements(self):
  for phrase in ('add donor Ali 03001234567','remove the last message','add a rule for quiet hours','delete the schedule','add a task for Akhtar','remove donors'):
   with self.subTest(phrase=phrase):
    self.assertFalse(draft_flow.contextual_edit(phrase,[],self.STATE))

 def test_shorter_gets_the_edit_tool(self):
  saved=[]
  with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',side_effect=[call('set_message',{'kind':'dm','text':'Short DM.'}),{'content':'ok'}]) as model:
   result=chat_runtime.run_chat('isko chota karo',chat('make dm better','Updated the DM.'),dict(self.STATE,case_name='Yousuf'),[],{'set_message':lambda **kw:(saved.append(kw) or 'Saved the DM.')})
  self.assertEqual(len(saved),1)
  self.assertIn('Saved the DM',result['reply'])

class AutopilotWording(unittest.TestCase):
 def test_natural_phrasings_reach_the_autopilot_tool(self):
  for phrase in ('turn off auto','auto off','switch auto on','autopilot band karo? stop auto','start auto','enable autopilot','turn on autopilot'):
   with self.subTest(phrase=phrase):
    self.assertTrue(chat_policy.permitted('autopilot',phrase))
  self.assertFalse(chat_policy.permitted('autopilot',"don't turn off auto"))

SUGGESTIONS=chr(10).join(['Hi! Here is where things stand and what I would do next.','1','Post main group now','The case is time-sensitive.',
 '2','Restart Auto for main only','Keeps the case visible every 15 minutes.','3','Send a fresh donor batch','187 donors are uncontacted.',
 'Tell me which one to start, e.g. "post main now".'])

class PickingASuggestion(Replay,unittest.TestCase):
 HISTORY=chat('hi there suggestions',SUGGESTIONS)
 def test_numbers_and_ordinals_pick_the_matching_suggestion(self):
  for reply,expected in (('1','Post main group now'),('do 2','Restart Auto for main only'),('first one','Post main group now'),('option 3','Send a fresh donor batch'),('pehla','Post main group now')):
   with self.subTest(reply=reply):
    follow=chat_policy.followup(reply,self.HISTORY)
    self.assertTrue(follow['inherited']);self.assertEqual(follow['text'],expected)

 def test_a_bare_yes_or_unknown_number_never_guesses_an_option(self):
  for reply in ('yes','kar do','4','2000','1 and 2'):
   with self.subTest(reply=reply):self.assertFalse(chat_policy.followup(reply,self.HISTORY)['inherited'])

 def test_picking_one_runs_that_action_only(self):
  sent=[]
  self.play('1',self.HISTORY,[call('send_appeal',{'target':'main'}),{'content':'ok'}],{'send_appeal':lambda **kw:(sent.append(kw) or 'WhatsApp confirmed the post.')})
  self.assertEqual(sent,[{'target':'main'}])
  context=next(m['content'] for m in self.model.call_args_list[0].args[3] if m['content'].startswith('APP_CONTEXT_JSON'))
  self.assertIn('Post main group now',context)

 def test_picking_the_auto_option_cannot_send(self):
  self.play('2',self.HISTORY,[{'content':'Auto restarted.'}],{})
  self.assertNotIn('send_appeal',self.offered)
  self.assertIn('autopilot',self.offered)

class RepeatedNoticesDoNotEraseContext(unittest.TestCase):
 def test_thirty_identical_failures_keep_the_real_conversation_in_view(self):
  history=[{'who':'you','text':'send the caption to main at 11am'}]+[{'who':'app','text':'Test failed: Group tab has 0/10 distinct saved versions.'}]*40+[{'who':'you','text':'resume group dms by 11 am'}]
  messages=chat_runtime.context_messages('ok',history,{},[])
  texts=[m['content'] for m in messages]
  self.assertIn('send the caption to main at 11am',texts)
  self.assertIn('resume group dms by 11 am',texts)
  self.assertEqual(sum('Test failed' in t for t in texts),1)
  self.assertTrue(any('repeated 40 times' in t for t in texts))

class UrduAndHinglishCommands(unittest.TestCase):
 def test_everyday_phrasings_run_without_the_model(self):
  expected={'ab 3000 bache hain':('amount',3000),'1500 aaye hain':('money',1500),'Rs 1500 aye hain':('money',1500),
   'stop sending':('hold',None),'rukk jao':('hold',None),'resume everything':('resume',None),'continue sending':('resume',None),
   'chalu karo':('resume',None),'dobara bhej do':('repeat',None),'same again':('repeat',None)}
  for phrase,(kind,amount) in expected.items():
   with self.subTest(phrase=phrase):
    plan=manual_commands.parse(phrase) or {}
    self.assertEqual(plan.get('kind'),kind)
    if amount is not None:self.assertEqual(plan.get('amount'),amount)

class ServerGuardAgrees(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def test_yes_saves_the_dm_edit_through_the_real_server_guard(self):
  original=app.get_message('dm')['text']
  history=chat('make the dm shorter','Here is a shorter DM. Shall I save it?')
  follow=chat_policy.followup('yes',history)
  app.workflow().begin('make the dm shorter','dm',original);app.workflow().revise(original)
  callback=app.chat_callbacks(follow['text'],revision=app.OWNER_REVISION,history=history)
  self.assertTrue(callback['set_message'](kind='dm',text=original.replace('Brother,','Brother, please read.')))
  self.assertEqual(app.workflow().data['kind'],'dm')

 def test_bare_yes_without_a_question_cannot_save(self):
  original=app.get_message('dm')['text']
  follow=chat_policy.followup('yes',chat('make the dm shorter','Saved it.'))
  with self.assertRaises(ValueError):
   app.chat_callbacks(follow['text'],revision=app.OWNER_REVISION)['set_message'](kind='dm',text='Changed without being asked')
  self.assertEqual(app.get_message('dm')['text'],original)

class WholeConversationOverHttp(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def converse(self,text,script):
  import json,threading,time,urllib.request
  server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  def request(path,body=None):
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=json.dumps(body).encode() if body else None,headers={'Authorization':'Bearer test-only-studio-access-key','Content-Type':'application/json'})
   with urllib.request.urlopen(req) as r:return json.load(r)
  try:
   with patch.object(assistant,'client',return_value='fake'),patch.object(assistant,'_chat_raw',side_effect=script) as model:
    started=request('/assistant',{'text':text,'request_id':'e2e-'+str(abs(hash(text))),'screen':{'view':'dm'}})
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
     result=request('/assistant-status/'+started['task_id'])
     if result.get('done'):break
     time.sleep(.02)
   return result,model
  finally:server.shutdown();server.server_close()

 def test_yes_after_the_assistants_offer_saves_the_dm_through_the_real_server(self):
  original=app.get_message('dm')['text'];shorter=original.replace('Brother,','Brother, please read this.')
  app.workflow().begin('make the dm shorter','dm',original);app.workflow().revise(original)
  app.chat_add('you','make the dm shorter');app.chat_add('app','Here is the shorter DM. Shall I save it?')
  result,model=self.converse('yes',[{'tool_calls':[{'id':'e','function':{'name':'set_message','arguments':json.dumps({'kind':'dm','text':shorter})}}]},{'content':'Saved.'}])
  self.assertTrue(result.get('done'));self.assertNotIn('error',result)
  self.assertEqual(app.get_message('dm')['text'],shorter)

 def test_yes_with_nothing_asked_changes_nothing_over_http(self):
  original=app.get_message('dm')['text']
  app.chat_add('you','make the dm shorter');app.chat_add('app','Saved the shorter DM.')
  result,model=self.converse('yes',[{'content':'Anything else?'}])
  self.assertTrue(result.get('done'))
  self.assertEqual(app.get_message('dm')['text'],original)

if __name__=='__main__':unittest.main()
