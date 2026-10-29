import json, unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app, commands
import dm_composer, assistant

class CompositionTests(unittest.TestCase):
 def test_labels_and_unclear_names_use_only_brother(self):
  for name in ('Jr Accounts','jr acccount','JrAccounts','Web Developer','03001234567','Unknown','Name','A','xqz','Ali_123','GiveLife Foundation'):
   with self.subTest(name=name):self.assertEqual(dm_composer.greeting(name,'Sister'),'Brother')
  self.assertEqual(dm_composer.greeting('Wajdan Khan'),'Wajdan Brother')
  self.assertEqual(dm_composer.greeting('Ayesha Khan','Sister'),'Ayesha Sister')
 def test_greeting_preserves_formatted_paragraphs(self):
  for opening in ('Brother, doctors can treat it.','*Brother, doctors can treat it.*','*_Name Brother doctors can treat it._*','Jr Accounts Brother, doctors can treat it.'):
   body='\n\n_Italic case details_\n\n*Rs. 25,000 left*\n\n*_13 people at Rs. 2,000_*\n\n📲 03097458815'
   changed=dm_composer.personalize(opening+body,'Wajdan')
   self.assertIn('Wajdan Brother',changed);self.assertTrue(changed.endswith(body));self.assertIn('doctors can treat it.',changed)
   self.assertEqual(dm_composer.personalize(changed,'Wajdan'),changed)
 def test_correction_parser(self):
  for prompt in ('his name is wadjdan','jr account name is wajdan just in msg change name','change name to Wajdan'):
   self.assertEqual(commands.parse(prompt)['kind'],'dm_name')
  self.assertIsNone(commands.parse('send to jr account'))
  self.assertEqual(commands.parse('send full dm to jr account')['kind'],'appeal_to')
 def test_model_gets_complete_caption_and_context(self):
  state={'drafts':{'dm':'Full\n\ncaption'},'last_recipient':{'id':'923001234567@s.whatsapp.net','name':'Jr Accounts'},'screen':{'dm':{'name':'Wajdan'}}}
  slim=assistant._slim(state)
  self.assertEqual(slim['drafts'],state['drafts']);self.assertEqual(slim['to'],state['last_recipient']);self.assertEqual(slim['dm_form']['name'],'Wajdan')

class DMFlowTests(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def test_saved_dm_screen_has_canonical_bold_italic_structure(self):
  text=app.get_message('dm')['text']
  self.assertIn('Brother, you can close this chat. Yousuf cannot close his pain.',text)
  self.assertIn('💔 Days have passed. He is still at home.\n_Yousuf is 2.',text)
  self.assertIn('⚠️ *The paralysing has started in his fingers.',text)
  self.assertIn('💰 *_Rs. 25,000 still needed for treatment._*',text)
  self.assertIn('*_Just 13 people donating Rs. 2,000_*',text)
  self.assertIn('*_OR 25 people contributing Rs. 1,000 🤲_*',text)
  self.assertIn("_If you are reading this, it's you._ Don't wait for someone else.",text)
  self.assertIn('📲 *03097458815*',text)
  self.assertIn('Reply *Done* after donating.',text)
  self.assertTrue(dm_composer.complete(text));self.assertNotIn('Name Brother',text)
 def test_full_dm_name_edit_then_resend_same_person(self):
  jid='923001234567@s.whatsapp.net'
  with patch.object(app,'find_data',return_value=([{'id':jid,'name':'Jr Accounts','group':False}],1)):
   first=app.send_dm_appeal('jr account')
   original=self.sent[-1]['text'];self.assertTrue(original.startswith('Brother, '));self.assertTrue(dm_composer.complete(original))
   before=len(self.sent);result=app.manual_command('jr account name is wajdan just in msg change name')
   self.assertEqual(len(self.sent),before);self.assertIn('Nothing was sent',result['reply']);self.assertEqual(result['dm_identity']['name'],'Wajdan')
   self.assertEqual(app.LAST_MANUAL['to'],jid)
   app.manual_command('send now')
  text=self.sent[-1]['text'];self.assertEqual(self.sent[-1]['phone'],jid)
  self.assertEqual(text,'Wajdan '+original);self.assertIn('25,000',text)
  self.assertLess(text.index('2,000'),text.index('1,000'))
 def test_ai_salutation_only_or_flat_caption_uses_full_saved_dm(self):
  for faulty in ('Wajdan Brother,','Jr Accounts Brother, Yousuf is 2. Rs. 25,000 left. Account 03097458815.'):
   callbacks=app.chat_callbacks('send the dm to 923001234567',revision=app.OWNER_REVISION)
   callbacks['send_message'](to='923001234567',text=faulty,with_picture=True)
   self.assertTrue(dm_composer.complete(self.sent[-1]['text']));self.assertNotEqual(self.sent[-1]['text'],faulty)
 def test_caption_only_correction_cannot_send(self):
  callbacks=app.chat_callbacks('jr account name is wajdan just in msg change name',revision=app.OWNER_REVISION)
  with self.assertRaisesRegex(ValueError,'does not ask to send'):callbacks['send_dm_appeal'](to='923001234567',name='Wajdan')
  with self.assertRaises(ValueError):callbacks['send_message'](to='923001234567',text='Wajdan Brother,',with_picture=True)
  with self.assertRaises(ValueError):callbacks['set_message'](kind='dm',text='Wajdan Brother,')
  self.assertEqual(self.sent,[])
 def test_incomplete_saved_draft_repaired_before_appeal(self):
  app.save_draft('dm','Wajdan Brother,')
  app.send_dm_appeal('923001234567',name='Wajdan')
  self.assertTrue(dm_composer.complete(self.sent[-1]['text']));self.assertTrue(self.sent[-1]['text'].startswith('Wajdan Brother, '))
 def test_form_rejects_incomplete_dm(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):app.send_custom({'target':'phone','phone':'923001234567','message':'Wajdan Brother,','kind':'dm_appeal','poster':True})
  self.assertEqual(self.sent,[])
 def test_name_edit_never_looks_for_new_person(self):
  jid='923001234567@s.whatsapp.net';app.send_dm_appeal(jid)
  with patch.object(app,'find_data',side_effect=AssertionError('Must keep current recipient')):
   app.manual_command('his name is Wajdan')
  self.assertEqual(app.LAST_MANUAL['to'],jid);self.assertEqual(app.LAST_MANUAL['name'],'Wajdan');self.assertEqual(len(self.sent),1)
 def test_greeting_does_not_leak_between_people(self):
  app.send_dm_appeal('923001234567');app.edit_dm_name('Wajdan')
  app.send_dm_appeal('923009876543')
  self.assertTrue(self.sent[-1]['text'].startswith('Brother, '));self.assertNotIn('Wajdan Brother',self.sent[-1]['text'])
 def test_ai_lookup_then_full_dm_preserves_contact_name_rules(self):
  jid='923001234567@s.whatsapp.net';messages=[
   {'tool_calls':[{'id':'lookup','function':{'name':'find_contact','arguments':json.dumps({'query':'jr account'})}}]},
   {'tool_calls':[{'id':'send','function':{'name':'send_dm_appeal','arguments':json.dumps({'to':jid,'name':'Jr Accounts'})}}]}]
  with patch.object(app,'find_data',return_value=([{'id':jid,'name':'Jr Accounts','group':False}],1)),patch.object(assistant,'client',return_value='fake-key'),patch.object(assistant,'_chat_raw',side_effect=messages):
   result=assistant.chat('send to jr account',[],{'drafts':json.loads(app.DRAFT.read_text(encoding='utf-8'))},[],app.chat_callbacks('send to jr account',revision=0))
  self.assertEqual(len(self.sent),1);self.assertTrue(self.sent[0]['text'].startswith('Brother, '));self.assertTrue(dm_composer.complete(self.sent[0]['text']));self.assertIn('confirmed',result['reply'])
 def test_logical_saved_name_used_for_dm(self):
  jid='923001234567@s.whatsapp.net'
  with patch.object(app,'find_data',return_value=([{'id':jid,'name':'Ayesha Khan','group':False}],1)):
   app.send_dm_appeal('Ayesha')
  self.assertTrue(self.sent[-1]['text'].startswith('Ayesha Sister, '))
 def test_exact_custom_caption_is_not_replaced(self):
  callbacks=app.chat_callbacks('send "Hello Wajdan" with poster to 923001234567',revision=0)
  callbacks['send_message'](to='923001234567',text='Hello Wajdan',with_picture=True)
  self.assertEqual(self.sent[-1]['text'],'Hello Wajdan')

if __name__=='__main__':unittest.main()
