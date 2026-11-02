import unittest,re
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
import caption_facts,draft_workflow
SOURCE='💔 *Yousaf has passed away.*\n\n_His Janazah time has not been announced because the family is short of funds._\n\nRs. 25,000 urgently needed.\n\n13 kind people donating Rs. 2,000 OR 25 × Rs. 1,000 can help the family.\n\n03097458815 Easypaisa / JazzCash Wajdan Khan'
class CaptionFactsTests(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def seed(self):
  app.write_left(25000);app.save_draft('group',SOURCE);app.save_draft('dm','Brother, '+SOURCE)
  app.STORE.put('focus_wording',{k:{'source':app.get_message(k)['text'],'items':[app.get_message(k)['text'].replace('short of funds','unable to pay')],'revision':'old','state':'Ready'} for k in ('group','dm')})
 def test_amount_updates_every_saved_variant_without_rebuilding_old_case(self):
  self.seed();self.assertTrue(app.manual_command('23k left now')['handled'])
  for row in app.STORE.get('focus_wording').values():
   for text in [row['source'],*row['items']]:
    self.assertIn('23,000 urgently needed',text);self.assertIn('12 kind people donating Rs. 2,000',text);self.assertIn('23 × Rs. 1,000',text);self.assertIn('passed away',text);self.assertNotIn('fluid',text)
  self.assertIn('passed away',app.get_message('group')['text'])
 def test_chat_time_updates_both_banks_and_pending_caption(self):
  self.seed();result=app.manual_command('Janazah time is 5:30 pm today')
  self.assertTrue(result['handled']);self.assertIn('5:30 PM today',result['reply'])
  for row in app.STORE.get('focus_wording').values():
   for text in [row['source'],*row['items']]:self.assertIn('The Janazah is at 5:30 PM today.',text);self.assertNotIn('not been announced',text)
  self.assertIn('5:30 PM today',caption_facts.current(app,SOURCE))
 def test_unclear_questions_and_hypotheticals_do_not_set_time(self):
  for text in ('When is Janazah time?','if Janazah time is 5 pm','do not update Janazah time is 5 pm'):
   self.assertIsNone(caption_facts.parse_time(text))
  with self.assertRaises(ValueError):caption_facts.parse_time('Janazah time is 5')
 def test_supported_count_styles(self):
  for old,expected in [('25 people or Rs. 2,000','24 people or Rs. 2,000'),('50 × Rs. 1,000','48 × Rs. 1,000'),('Rs. 1000 by 50 people','Rs. 1000 by 48 people')]:self.assertEqual(draft_workflow.update_amount(old,50000,48000),expected)
