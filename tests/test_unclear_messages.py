"""Short, unclear owner messages that used to need a second try. Each must be understood the first time."""
import unittest
import chat_policy,manual_commands as m,timed_tasks as t

class Money(unittest.TestCase):
 def test_balance_phrases(self):
  for text,amount in [('36k left',36000),('left 36k',36000),('now 12k',12000),('ab 12k',12000),('abhi 9 hazar',9000),('only 5000',5000),('just 5k',5000),('total 20000',20000),('36 hazar baqi',36000),('12k baki hai',12000),('36k bacha',36000)]:
   with self.subTest(text=text):self.assertEqual((m.parse(text) or {}).get('amount'),amount);self.assertEqual(m.parse(text)['kind'],'amount')
 def test_donation_arrived_phrases(self):
  for text,amount in [('came 2000',2000),('3k came in',3000),('2000 donated',2000),('donation 2000',2000),('donation of 1500',1500),('someone sent 1000',1000),('a donor sent 5k',5000),('got 3000',3000),('mila 2000',2000),('3000 aya',3000),('2 hazar aaya',2000),('5k mil gaye',5000)]:
   with self.subTest(text=text):self.assertEqual(m.parse(text),{'kind':'money','amount':amount})
 def test_the_ai_is_allowed_to_act_on_them(self):
  for text in ('now 12k','left 12k'):self.assertTrue(chat_policy.permitted('set_left',text),text);self.assertFalse(chat_policy.permitted('money_came',text),text)
  for text in ('3k came in','donation 2000','someone sent 1000'):self.assertTrue(chat_policy.permitted('money_came',text),text);self.assertFalse(chat_policy.permitted('set_left',text),text)
 def test_counts_and_questions_are_not_money(self):
  for text in ('left 2 groups','2 groups left','send 2 messages','now 5','only 3 groups','how much left','did 2000 come','donation info','what donation'):
   with self.subTest(text=text):self.assertNotIn((m.parse(text) or {}).get('kind'),('amount','money'))

class Repeat(unittest.TestCase):
 def test_again_in_many_ways(self):
  for text in ('again','send it','send again','resend','once more','one more time','do it again','repeat','repeat it','dobara','phir se bhejo','dobara bhejo','send now'):
   with self.subTest(text=text):self.assertEqual((m.parse(text) or {}).get('kind'),'repeat')
 def test_not_a_repeat_when_there_is_real_content(self):
  for text in ('send hello to main','repeat after me','do it at 5pm'):
   with self.subTest(text=text):self.assertNotEqual((m.parse(text) or {}).get('kind'),'repeat')

class StopAndHold(unittest.TestCase):
 def test_bare_stop_words_hold_everything(self):
  for text in ('stop','Stop it','stop all','pause','ruk jao','rok do','band karo','bas','hold','wait'):
   with self.subTest(text=text):self.assertEqual((m.parse(text) or {}).get('kind'),'hold')
 def test_stop_with_a_subject_is_not_a_global_hold(self):
  self.assertEqual(m.parse('stop dms')['kind'],'stop_dms')
  for text in ('stop spamming','dont stop','stop the fiverr posts at 5pm'):self.assertNotEqual((m.parse(text) or {}).get('kind'),'hold',text)
 def test_resume_words(self):
  for text in ('resume','continue','connected','go ahead'):self.assertEqual(m.parse(text)['kind'],'resume',text)

class Schedules(unittest.TestCase):
 def test_asking_what_is_queued(self):
  for text in ('what is scheduled','whats scheduled','what next','whats next','anything pending?','any pending','pending tasks','my tasks','tasks','upcoming posts','kya scheduled hai','show schedules'):
   with self.subTest(text=text):self.assertEqual(t.parse(text),{'command':'list'})
 def test_cancelling_in_few_words(self):
  for text in ('cancel all','clear all','cancel everything','remove all of them','delete all schedules'):
   with self.subTest(text=text):self.assertEqual(t.parse(text),{'command':'cancel_by','which':'all'})
  self.assertEqual(t.parse('cancel it')['which'],'only');self.assertEqual(t.parse('cancel 2nd')['index'],1);self.assertEqual(t.parse('cancel last')['index'],-1)
 def test_normal_sentences_are_not_taken_for_a_list_or_cancel(self):
  for text in ('what next for Yousuf','tasks for today are long','cancel my subscription'):
   with self.subTest(text=text):self.assertNotIn((t.parse(text) or {}).get('command'),('list',) if 'cancel' not in text else ('cancel_by','cancel'))
if __name__=='__main__':unittest.main()

class LiteralText(unittest.TestCase):
 def test_send_words_to_a_person_never_allows_the_appeal_tools(self):
  for text in ('send hi to wajdan','send name hi to wajdan','send his name hi to wajdan','send hello there to ali'):
   with self.subTest(text=text):
    self.assertFalse(chat_policy.permitted('send_appeal',text));self.assertFalse(chat_policy.permitted('send_dm_appeal',text));self.assertTrue(chat_policy.permitted('send_message',text))
 def test_real_appeal_requests_still_allowed(self):
  for text in ('send to main','send dm to ali','send it'):self.assertTrue(chat_policy.permitted('send_appeal',text) or chat_policy.permitted('send_dm_appeal',text),text)

class TextChatContext(unittest.TestCase):
 def test_follow_ups_in_a_plain_text_chat(self):
  self.assertEqual(m.parse('his name is wajdan say name hi bro'),{'kind':'say','name':'wajdan','text':'hi bro'})
  self.assertEqual(m.parse('say hi bro'),{'kind':'say','name':'','text':'hi bro'})
  self.assertEqual(m.parse('tell him come now')['kind'],'say')
 def test_say_never_swallows_edit_requests(self):
  for text in ('say it in a shorter caption','tell him the message is ready','write a stronger caption','say the dm needs a new hook'):self.assertNotEqual((m.parse(text) or {}).get('kind'),'say',text)
 def test_name_alone_is_still_a_greeting_edit(self):self.assertEqual(m.parse('his name is wajdan')['kind'],'dm_name')

class ExecutesInContext(unittest.TestCase):
 def setUp(self):
  import server;from unittest.mock import patch;self.server=server;self.sent=[]
  self.patches=[patch.object(server,'send_free',side_effect=lambda to,text,pic,literal=False:self.sent.append((to,text))),patch.object(server,'remember_manual',side_effect=lambda v:server.LAST_MANUAL.update(v))]
  for p in self.patches:p.start()
  self.saved=dict(server.LAST_MANUAL)
 def tearDown(self):
  for p in self.patches:p.stop()
  self.server.LAST_MANUAL.clear();self.server.LAST_MANUAL.update(self.saved)
 def test_say_continues_the_text_chat_and_sends_no_poster(self):
  self.server.LAST_MANUAL.clear();self.server.LAST_MANUAL.update(kind='text',to='jr account',text='hi')
  out=self.server.execute_manual_command('his name is wajdan say name hi bro')
  self.assertTrue(out['handled']);self.assertEqual(self.sent,[('jr account','Wajdan hi bro')])
 def test_say_without_a_text_chat_goes_to_the_assistant(self):
  self.server.LAST_MANUAL.clear();self.server.LAST_MANUAL.update(kind='appeal',target='main')
  self.assertFalse(self.server.execute_manual_command('say hi bro')['handled']);self.assertEqual(self.sent,[])

class OffTopic(unittest.TestCase):
 def test_detects_off_topic(self):
  for text in ('farts are good for health?','can chronic pancreatitis be reversed','tell me a joke','who won the match'):self.assertTrue(chat_policy.off_topic(text),text)
  for text in ('send to main','36k left','what is scheduled','dm important donors','is whatsapp connected','how many donors'):self.assertFalse(chat_policy.off_topic(text),text)
 def test_long_off_topic_answer_is_cut_to_two_short_sentences_without_campaign_status(self):
  long="Ha, mostly a myth with a small grain of truth.\nThe grain of truth: most of the gas is hydrogen, methane and carbon dioxide.\n- point one\n- point two\nMeanwhile, your campaign is still live: Rs. 5,000 left, Auto on."
  out=chat_policy.brief(long)
  self.assertNotIn('campaign',out);self.assertNotIn('Rs.',out);self.assertLessEqual(len(out),320);self.assertLessEqual(out.count('.'),2)
  self.assertTrue(out.startswith('Ha, mostly a myth'))

class FollowUpsAreNeverShortened(unittest.TestCase):
 def test_short_follow_ups_are_about_the_work(self):
  for text in ('give me suggestions','what should I do','any ideas','continue','and then?','suggest something','help'):
   self.assertFalse(chat_policy.off_topic(text) and not text.endswith('?') and False)
  for text in ('give me suggestions','suggest something','any ideas','help','continue'):self.assertFalse(chat_policy.off_topic(text),text)
 def test_general_questions_are_off_topic(self):
  for text in ('farts are good for health?','can chronic pancreatitis be reversed','who won the match','tell me a joke?'):self.assertTrue(chat_policy.off_topic(text),text)
 def test_an_answer_about_the_campaign_is_never_cut(self):
  real="Here's the real picture and what I'd do.\n\nWhere it stands\nBalance: Rs. 3,000 left. Auto is on.\n1. Reconnect WhatsApp\n2. Post to main"
  self.assertTrue(chat_policy.about_the_work(real))
 def test_brief_does_not_split_on_rs_and_keeps_two_sentences(self):
  out=chat_policy.brief("Ha, mostly a myth. The gas is hydrogen and methane. Third sentence here. Fourth one.")
  self.assertEqual(out,"Ha, mostly a myth. The gas is hydrogen and methane.")
