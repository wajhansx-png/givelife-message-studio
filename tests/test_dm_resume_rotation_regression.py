"""Actual resume/dispatch regressions with synthetic recipients only."""
import unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app


class ResumeRotationTests(unittest.TestCase):
 def setUp(self):
  fixture.SendTests.setUp(self)
  app.donors().jobs.import_jobs({'jobs':[]})
 tearDown=fixture.SendTests.tearDown

 def test_resume_uses_saved_job_id_not_latest_unrelated_job(self):
  h=app.donors()
  for i in range(3):h.book.add('Synthetic '+str(i),'92300123000'+str(i))
  with patch.object(h.jobs,'connected',return_value=True):
   job=h.start_batch(scope='all',limit=3,run=False)['job']
   h.pause_personal();raw=h.jobs.export_jobs()['jobs'][-1];h.jobs._update(job['id'],state='Stopped',receipts=[{'id':raw['ids'][0],'state':'Sent'}]);h.jobs.active=None
   data=h.jobs.export_jobs();data['jobs'].append({'id':'later-other-job','scope':'selected','state':'Completed','ids':[],'receipts':[]});h.jobs.import_jobs(data)
   with patch('donor_delivery.threading.Thread'):
    result=h.resume_all()
   resumed=h.jobs.export_jobs()['jobs'][-1]
  self.assertFalse(result['paused']);self.assertEqual(resumed['scope'],'all')
  self.assertEqual(resumed['total'],2);self.assertEqual(resumed['original_total'],3);self.assertEqual(resumed['previous_sent'],1)

 def test_reserved_wording_survives_live_bank_peek(self):
  h=app.donors();job={'ids':['a','b'],'caption':'fallback','captions':['Assigned version 8','Assigned version 9']}
  with patch.object(h.jobs,'variants',return_value=['Version 1','Version 2']):
   self.assertEqual(h.jobs._fresh_caption(job,0),'Assigned version 8')
   self.assertEqual(h.jobs._fresh_caption(job,1),'Assigned version 9')

 def test_preserved_wording_still_updates_balance(self):
  h=app.donors();job={'ids':['a'],'caption':'fallback','captions':['Unique hook\nRs. 25,000 LEFT\n13 people donating Rs. 2,000']}
  app.set_left(23000)
  text=h.jobs._fresh_caption(job,0)
  self.assertIn('Unique hook',text);self.assertIn('23,000',text);self.assertIn('12 people',text)

 def test_every_canonical_template_updates_without_losing_its_hook(self):
  import dm_templates
  h=app.donors();app.set_left(23000)
  for i in range(20):
   source=dm_templates.build(i,25000)
   job={'ids':['a'],'caption':source,'captions':[source],'caption_balance':25000}
   text=h.jobs._fresh_caption(job,0)
   self.assertNotIn('25,000',text);self.assertIn('23,000',text)
   self.assertEqual(source.splitlines()[0],text.splitlines()[0])


if __name__=='__main__':unittest.main()
