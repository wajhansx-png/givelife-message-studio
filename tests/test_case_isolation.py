"""Regression: one GiveLife case must never inherit another patient's facts.
Uses the existing fake WhatsApp fixture; no donor receives messages.
"""
import unittest
from pathlib import Path
from unittest.mock import patch
import test_donor_hub as hub

class CaseIsolation(unittest.TestCase):
 def setUp(self):
  self.fixture=hub.IntegrationTests()
  self.fixture.setUp()
  self.app=self.fixture.app
  # Case creation rewrites captions. Keep this test's drafts isolated so it
  # cannot corrupt other tests or the fixture's saved baseline messages.
  original=self.app.DRAFT
  draft=Path(self.fixture.scope.name)/'isolated-drafts.json'
  draft.write_bytes(original.read_bytes())
  self.draft_patch=patch.object(self.app,'DRAFT',draft)
  self.draft_patch.start()
 def tearDown(self):
  self.draft_patch.stop()
  self.fixture.tearDown()
 def drafts(self):
  return self.app.get_message('group')['text'],self.app.get_message('dm')['text']
 def test_new_case_uses_name_and_current_amount_without_old_medical_claims(self):
  self.app.donors().cases.new('Affan family',42000)
  for text in self.drafts():
   self.assertIn('Affan family',text)
   self.assertIn('42,000',text)
   self.assertNotIn('Yousuf',text)
   self.assertNotIn('brain',text.lower())
   self.assertNotIn('kidneys',text.lower())
  self.assertEqual(self.app.studio_state()['case_name'],'Affan family')
 def test_all_regeneration_paths_remain_inside_current_case(self):
  self.app.donors().cases.new('Food aid family',18000)
  self.app.next_message();self.app.next_dm()
  self.app.set_left(12000)
  for text in self.drafts():
   self.assertIn('Food aid family',text)
   self.assertNotIn('Yousuf',text)
   self.assertNotIn('brain',text.lower())
   self.assertIn('12,000',text)
 def test_new_case_has_twenty_distinct_complete_dms_without_old_facts(self):
  import dm_composer
  self.app.donors().cases.new('Another child',28000)
  bank=self.app.donors().messages.get()
  texts=[row['text'] for row in bank['items']]
  self.assertEqual(len(texts),20)
  self.assertEqual(len(set(texts)),20)
  self.assertEqual(len(self.app.donors().messages.captions(20)),20)
  for text in texts:
   self.assertTrue(dm_composer.complete(text))
   self.assertIn('Another child',text)
   self.assertIn('28,000',text)
   self.assertNotIn('Yousuf',text)
   self.assertNotIn('brain',text.lower())

 def test_completed_case_does_not_solicit_new_donations(self):
  self.app.donors().cases.new('Food aid family',12000)
  self.app.set_left(0)
  for text in self.drafts():
   self.assertIn('complete',text.lower())
   self.assertNotIn('people donating',text.lower())
   self.assertNotIn('12,000 left',text.lower())
  self.assertTrue(self.app.studio_state()['case_closed'])
 def test_closing_custom_appeal_replaces_zero_people_with_completion(self):
  self.app.donors().cases.new('Another family',24000)
  self.app.save_draft('group','Urgent family case\n\n*Rs. 24,000 LEFT*\n\n12 people donating Rs. 2,000\n\nGiveLife Foundation')
  self.app.save_draft('dm','Brother,\n\nNeed urgent help.\n\nRs. 24,000 left\n\n12 people donating Rs. 2,000\n\n03097458815')
  self.app.set_left(0)
  for text in self.drafts():
   self.assertIn('complete',text.lower())
   self.assertNotIn('0 people',text.lower())
   self.assertNotIn('Rs. 0 still needed',text)
  self.assertFalse(self.app.auto_on())
 def test_completed_case_rejects_new_mixed_fundraising_caption(self):
  self.app.donors().cases.new('Yousuf',20000)
  self.app.set_left(0)
  bad=('The case for Yousuf has been completed. Thank you everyone.\\n\\n'
       '*_Rs. 0 LEFT_*\\n*_0 people donating Rs. 2,000_*\\n'
       'Reply Done after you donate. - GiveLife Foundation')
  for kind in ('group','dm'):
   with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'completed'):
    self.app.save_draft(kind,bad)
   text=self.app.get_message(kind)['text']
   self.assertNotIn('people donating',text)
   self.assertIn('complete',text.lower())
  self.assertEqual(self.app.get_message('group')['text'],self.app.build_group(0,0))
 def test_get_drafts_repairs_persisted_legacy_mixed_completion_appeal(self):
  import json
  self.app.donors().cases.new('Yousuf',20000)
  self.app.set_left(0)
  stored=json.loads(self.app.DRAFT.read_text(encoding='utf-8'))
  stored['group']='*The case for Yousuf has been completed.*\\n\\n*_Rs. 0 LEFT_*\\n*_0 people donating Rs. 2,000_*'
  stored['dm']='Thanks everyone!\\n\\nOR 0 people donating Rs. 1,000. Reply Done after you donate.'
  self.app.DRAFT.write_text(json.dumps(stored),encoding='utf-8')
  group=self.app.get_message('group')['text']
  dm=self.app.get_message('dm')['text']
  self.assertIn('Case complete',group)
  self.assertIn('completed',dm)
  for text in (group,dm):
   self.assertNotIn('0 people',text)
   self.assertNotIn('Rs. 0 LEFT',text)
  repaired=json.loads(self.app.DRAFT.read_text(encoding='utf-8'))
  self.assertEqual(repaired['group'],group)
  self.assertEqual(repaired['dm'],dm)
 def test_completed_case_cannot_dispatch_old_fundraising_caption_even_by_manual_route(self):
  self.app.donors().cases.new('Yousuf',15000)
  self.app.set_left(0)
  caption='Case completed, but 0 people donating Rs. 2,000; donate today.'
  with self.assertRaisesRegex(ValueError,'completed case'):
   self.app.start_send_job(['main'],caption,manual=True)
  with self.assertRaisesRegex(ValueError,'completed case'):
   self.app.send_custom({'target':'main','message':caption})
 def test_new_case_never_inherits_old_patient_poster_or_medical_documents(self):
  import base64
  cases=self.app.donors().cases
  original=cases.view()['current']
  picture=b'old-case-image'
  paper=b'old-case-medical-paper'
  self.app.STORE.put('poster_b64',base64.b64encode(picture).decode())
  self.app.STORE.put('papers_b64',[base64.b64encode(paper).decode()])
  (self.app.DATA/'poster.jpg').write_bytes(picture)
  papers=self.app.DATA/'papers';papers.mkdir(exist_ok=True)
  (papers/'paper-0.jpg').write_bytes(paper)
  cases.new('Another child',28000)
  self.assertFalse((self.app.DATA/'poster.jpg').exists())
  self.assertEqual(list(papers.glob('*.jpg')),[])
  self.assertEqual(self.app.STORE.get('papers_b64'),[])
  cases.switch(original)
  self.assertEqual((self.app.DATA/'poster.jpg').read_bytes(),picture)
  self.assertEqual((papers/'paper-0.jpg').read_bytes(),paper)
 def test_donor_bank_and_auto_messages_never_contain_old_patient_name(self):
  self.app.donors().cases.new('Another child',32000)
  bank=self.app.donors().messages.get()
  self.assertEqual(len(bank['items']),20)
  for row in bank['items']:
   self.assertIn('Another child',row['text'])
   self.assertNotIn('Yousuf',row['text'])
  for text in (self.app.caption_variant(0),self.app.dm_text('Ali','repeat'),
               self.app.dm_text('Ali','reminder'),self.app.update_text(2000,30000),
               self.app.milestone_text(2000,30000),self.app.thank_text(),
               self.app.share_text(),self.app.done_text()):
   self.assertNotIn('Yousuf',text)
 def test_templates_never_invent_medical_outcomes(self):
  import dm_templates
  for index in range(dm_templates.COUNT):
   caption=dm_templates.build(index,25000)
   self.assertIn('family reported',caption)
   self.assertNotRegex(caption.lower(),r'(?:will|can|may|threatening to)\\s+paraly[sz]e|paralys')
  self.assertNotRegex(self.app.build_group(0,25000,'Yousuf').lower(),r'paraly[sz]|damage his eyesight')

 def test_legacy_case_name_does_not_come_from_saved_medical_caption(self):
  import json
  self.app.STORE.put('cases',{'current':'legacy','cases':[{'id':'legacy','name':'Current case','created_at':0,'snapshot':None}]})
  existing=json.loads(self.app.DRAFT.read_text(encoding='utf-8'))
  existing['group']='Yousuf has a brain condition; please help.'
  self.app.DRAFT.write_text(json.dumps(existing),encoding='utf-8')
  self.assertEqual(self.app.active_case_name(),'Current case')
  self.assertNotIn('Yousuf',self.app.build_group(0,25000))

 def test_unnamed_case_does_not_assume_yousuf_story(self):
  for caption in (self.app.build_group(0,25000,'Current case'),self.app.build_dm(0,25000,'Current case')):
   self.assertIn('Current case',caption)
   self.assertNotIn('Yousuf',caption)
   self.assertNotIn('brain',caption.lower())

 def test_corrupt_balance_never_uses_a_guessed_amount_or_sends(self):
  (self.app.DATA/'state.md').write_text('LEFT: unknown\\n',encoding='utf-8')
  with self.assertRaisesRegex(ValueError,'balance is missing or invalid'):
   self.app.read_left()
  with self.assertRaisesRegex(ValueError,'balance is missing or invalid'):
   self.app.start_send_job(['main'],'Test appeal',manual=True)
  with self.assertRaisesRegex(ValueError,'balance is missing or invalid'):
   self.app.send_custom({'target':'main','message':'Test appeal','poster':False})

 def test_switch_back_restores_original_drafts_and_case_identity(self):
  cases=self.app.donors().cases
  previous=cases.view()['current']
  original=self.drafts()
  cases.new('New child',30000)
  cases.switch(previous)
  self.assertEqual(self.drafts(),original)
  self.assertNotEqual(self.app.studio_state()['case_name'],'New child')

if __name__=='__main__':
 unittest.main()
