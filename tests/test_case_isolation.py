"""Regression: one GiveLife case must never inherit another patient's facts.
Uses the existing fake WhatsApp fixture; no donor receives messages.
"""
import unittest
from pathlib import Path
import test_donor_hub as hub

class CaseIsolation(unittest.TestCase):
 def setUp(self):
  self.fixture=hub.IntegrationTests()
  self.fixture.setUp()
  self.app=self.fixture.app
 def tearDown(self):
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
 def test_completed_case_does_not_solicit_new_donations(self):
  self.app.donors().cases.new('Food aid family',12000)
  self.app.set_left(0)
  for text in self.drafts():
   self.assertIn('complete',text.lower())
   self.assertNotIn('people donating',text.lower())
   self.assertNotIn('12,000 left',text.lower())
  self.assertTrue(self.app.studio_state()['case_closed'])
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
