"""Regeneration follows the current, saved Message 1, never an old origin.

All rewrites are synthetic and no WhatsApp API or paid AI is called.
"""
import unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
import dm_composer,dm_templates,dm_variants
from donor_messages import MessageBank

class DonorMasterTests(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown

 def fake_variants(self, source, count=10, avoid=None):
  # Only safe synthetic rewrites; keep original message facts and formatting.
  start=len(avoid or [])
  return [source.replace('Brother, ', 'Bhai, ',1).replace(
    'please read', 'kindly read' if (start+i)%2 else 'do read',1
  ).replace('the support', 'the help' if (start+i)%2 else 'the care',1)
  + (' ' * (start+i+1)) for i in range(count)]

 def test_saved_first_is_master_including_changed_angle_and_bold_italic(self):
  bank=app.donors().messages
  before=bank.get()
  first=before['items'][0]
  revised=first['text'].replace('Brother, ', 'Bhai, ',1)
  revised=revised.replace('please read about Yousuf and the support his family requested.',
    'our community can help Yousuf and his grieving family today.',1)
  revised=revised.replace('💔 ', '💔 *',1).replace('His parents reported that he was admitted to hospital for treatment.',
    'His parents reported that he was admitted for treatment.*',1)
  self.assertTrue(dm_composer.complete(revised))
  bank.update(first['id'],revised)
  calls=[]
  def fake(source,count=10,avoid=None):
   calls.append((source,count,list(avoid or [])))
   return [source.replace('our community can help', 'we can stand with' if (j%2) else 'we can support')
           + ' '* (len(avoid or [])+j+1) for j in range(count)]
  with patch('dm_variants.generate',side_effect=fake),patch('dm_templates.matches',return_value=True):
   result=bank.regenerate()
  self.assertEqual(result['mode'],'custom')
  self.assertEqual(len(result['items']),20)
  self.assertEqual(result['items'][0]['text'],revised)
  self.assertEqual(calls[0][0],revised)
  self.assertEqual(result['origin'],revised)
  self.assertTrue(all(revised.split('📲')[1] in x['text'] for x in result['items']))
  self.assertTrue(all('💔 *' in x['text'] for x in result['items']))
  self.assertEqual(len({r['text'] for r in result['items']}),20)

 def test_second_regeneration_uses_new_message_one_again(self):
  bank=app.donors().messages
  first=bank.get()['items'][0]
  with patch('dm_variants.generate',side_effect=self.fake_variants):
   bank.update(first['id'],first['text'].replace('Brother, ', 'Bhai, ',1))
   one=bank.regenerate()
   second=one['items'][0]['text'].replace('Yousuf','Yousaf')
   bank.update(first['id'],second)
   two=bank.regenerate()
  self.assertEqual(two['items'][0]['text'],second)
  self.assertEqual(two['origin'],second)
  self.assertNotEqual(two['origin'],one['origin'])

 def test_master_edit_survives_main_dm_draft_changes(self):
  bank=app.donors().messages
  master=bank.get()['items'][0]
  edited=master['text'].replace('Brother, ', 'Bhai, ', 1)
  bank.update(master['id'],edited)
  app.save_draft('dm',dm_templates.build(1,app.read_left()))
  restarted=MessageBank(app)
  self.assertEqual(restarted.get()['items'][0]['text'],edited)
  self.assertEqual(restarted.get()['mode'],'custom')

 def test_incomplete_second_batch_does_not_overwrite_old_twenty(self):
  bank=app.donors().messages
  first=bank.get()['items'][0]
  edited=first['text'].replace('Brother, ', 'Bhai, ',1)
  bank.update(first['id'],edited)
  old=bank.get()['items']
  calls=[0]
  def incomplete(source,count=10,avoid=None):
   calls[0]+=1
   if calls[0]==1:
    return self.fake_variants(source,count,avoid)
   raise ValueError('AI did not produce enough distinct body rewrites')
  with patch('dm_variants.generate',side_effect=incomplete):
   with self.assertRaisesRegex(ValueError,'Only 9 of 19'):
    bank.regenerate()
  self.assertEqual(bank.get()['items'],old)
  self.assertEqual(bank.get()['items'][0]['text'],edited)

 def test_model_failure_keeps_last_saved_master_and_previous_versions(self):
  bank=app.donors().messages
  first=bank.get()['items'][0]
  new=first['text'].replace('Brother, ', 'Bhai, ',1)
  bank.update(first['id'],new)
  before=bank.get()
  with patch('dm_variants.generate',side_effect=ValueError('AI service unavailable')):
   with self.assertRaisesRegex(ValueError,'AI service unavailable'):bank.regenerate()
  self.assertEqual(bank.get()['items'],before['items'])
  self.assertEqual(bank.get()['items'][0]['text'],new)

 def test_concurrent_first_edit_must_not_be_overwritten(self):
  bank=app.donors().messages
  original=bank.get()['items'][0]
  first=original['text'].replace('Brother, ', 'Bhai, ',1)
  later=original['text'].replace('Brother, ', 'Ayesha Sister, ',1)
  bank.update(original['id'],first)
  def rewrite(source,count=10,avoid=None):
   bank.update(original['id'],later)
   return self.fake_variants(source,count,avoid)
  with patch('dm_variants.generate',side_effect=rewrite):
   with self.assertRaisesRegex(ValueError,'Message 1 changed'):bank.regenerate()
  self.assertEqual(bank.get()['items'][0]['text'],later)

if __name__=='__main__':unittest.main()
