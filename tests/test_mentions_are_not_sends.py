"""Sentences that merely mention a post/message/send must never send, resend or reach a send tool."""
import unittest
import assistant,chat_policy,manual_commands

SEND_TOOLS={'send_message','send_appeal','send_dm_appeal','dm_list','dm_donors','dm_group','send_text_list'}
NOT_SENDS=["the post was good","I shared it yesterday","my message looks bad","post is empty","the message is too long","share the update with me","message from donor said thanks","why is the post late","did the message go","good post","nice message","the dm looks wrong","i posted it already","post again later","send me the status","send me a summary","text me when done","post to me the report","can you send","could you post","should I send now","do not send until I say","dont post yet","wait before sending","hold the send","message me","dm me","post mortem","share price","what message did you send to main","was it sent","has it been posted","check if posted","not sent yet","nothing sent yet man","sent already","already posted in main","this message needs more emotion","the post in main is old","group post failed","main post status","message limit","post count","how many posts today","how many messages did you send","send count","messages sent today","list sent messages","show last post","show me what was posted","preview the post","draft the post","write a post","prepare a message","see the dm"]

REAL_SENDS={'send main':'appeal','post in main':'appeal','send to all groups':'appeal','post to fiverr and upwork':'appeals','send the post to main':'appeal',
 'send hi to Ali':'text','post the message in all groups':'appeal','share in test group':'appeal','send it again':'repeat','send poster to 03001234567':'appeal_to',
 'hi send main':'appeal','post main now please':'appeal','send new post to main':'appeal','send the saved post in uet':'appeal','send the saved caption to fiverr':'appeal'}

class MentionsAreNotSends(unittest.TestCase):
 def test_no_send_tool_and_no_direct_send(self):
  names=[t['function']['name'] for t in assistant.CHAT_TOOLS]
  for phrase in NOT_SENDS:
   with self.subTest(phrase=phrase):
    self.assertEqual([n for n in names if n in SEND_TOOLS and chat_policy.permitted(n,phrase)],[])
    self.assertNotIn((manual_commands.parse(phrase) or {}).get('kind'),('appeal','appeals','text','repeat','appeal_to'))

 def test_real_send_commands_still_send(self):
  for phrase,kind in REAL_SENDS.items():
   with self.subTest(phrase=phrase):
    self.assertEqual((manual_commands.parse(phrase) or {}).get('kind'),kind)
    self.assertTrue(chat_policy.intent(phrase)['send'])

class RefusalsNeverSend(unittest.TestCase):
 PHRASES=('main me mat bhejo','mat bhejo','abhi nahi bhejo','send mat karo','post mat karo main me','main me abhi post nahi karna','no send to main','no need to send',
  'send nahi karna','dm mat karo','dms mat bhejo','kisi ko mat bhejo','pehle show karo phir bhejo','send only after I confirm','send after I confirm')
 def test_urdu_and_english_refusals_never_send(self):
  names=[t['function']['name'] for t in assistant.CHAT_TOOLS]
  for phrase in self.PHRASES:
   with self.subTest(phrase=phrase):
    self.assertNotIn((manual_commands.parse(phrase) or {}).get('kind'),('appeal','appeals','text','repeat','appeal_to'))
    self.assertEqual([n for n in names if n in SEND_TOOLS and chat_policy.permitted(n,phrase)],[])
 def test_polite_requests_with_na_still_send(self):
  self.assertTrue(chat_policy.intent('bhej do na')['send'])
  self.assertEqual(manual_commands.parse('dobara bhejo')['kind'],'repeat')

class ComplaintsAreNotAmounts(unittest.TestCase):
 def test_a_complaint_about_a_number_never_sets_it(self):
  for phrase in ('remaining 5000 is wrong','5000 left is wrong','balance 5000 galat hai','5000 old'):
   with self.subTest(phrase=phrase):self.assertIsNone(manual_commands.parse(phrase))
  self.assertEqual(manual_commands.parse('that was wrong, 4000 left')['amount'],4000)

if __name__=='__main__':unittest.main()
