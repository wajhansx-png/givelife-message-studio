"""Volunteer batch start delays; synthetic recipients and fake transport only."""
import unittest
from unittest.mock import patch
import test_volunteers as fixture
from volunteers import Volunteers

class VolunteerTimingTests(unittest.TestCase):
 setUp=fixture.VolunteerTests.setUp
 tearDown=fixture.VolunteerTests.tearDown
 send=fixture.VolunteerTests.send
 def prepare(self):
  self.v.mutate({'action':'add','name':'Sara','phone':'03001234567'})
  self.v.set_message('Please share this case, {name}.')
 def queue(self,delay):
  with patch('donor_delivery.threading.Thread'),patch('volunteers.time.time',return_value=self.clock):
   return self.v.mutate({'action':'send_all','delay_seconds':delay,'poster':False,'request_id':'timing-test'})
 def test_presets_save_start_time_and_preserve_message_poster_and_gap(self):
  for delay in (300,600,900,1800,3600,7200):
   with self.subTest(delay=delay):
    self.prepare();self.queue(delay)
    job=self.v.jobs.export_jobs()['jobs'][-1]
    self.assertEqual(job['hold_until'],self.clock+delay);self.assertEqual(job['gap_seconds'],180)
    self.assertFalse(job['poster']);self.assertEqual(job['caption'],'Please share this case, {name}.');self.assertEqual(self.sent,[])
    self.v.jobs.import_jobs({'jobs':[]});self.v.jobs.active=None
 def test_send_now_has_no_future_wait(self):
  self.prepare();self.queue(0);self.assertFalse(self.v.jobs.export_jobs()['jobs'][-1].get('hold_until'))
 def test_repeated_schedule_request_keeps_one_job_and_the_original_time(self):
  self.prepare();first=self.queue(600)['job'];self.clock+=30
  second=self.queue(600)['job']
  self.assertEqual(first['id'],second['id']);self.assertEqual(first['hold_until'],second['hold_until']);self.assertEqual(len(self.v.jobs.export_jobs()['jobs']),1)
 def test_invalid_delay_does_not_create_a_batch(self):
  self.prepare()
  for delay in (-1,1,True,301,'300',None,float('nan')):
   with self.subTest(delay=delay),self.assertRaises(ValueError):self.queue(delay)
  self.assertEqual(self.v.jobs.status()['state'],'Idle')
 def test_first_send_waits_until_selected_time(self):
  self.prepare();self.queue(600);job=self.v.jobs.export_jobs()['jobs'][-1];sent_at=[]
  original_send=self.v.jobs.send
  self.v.jobs.send=lambda body:sent_at.append(self.clock) or original_send(body)
  def wait_until(due):
   self.assertEqual(self.sent,[]);self.assertEqual(due,job['created_at']+600);self.clock=due;return False
  with patch('donor_delivery.time.time',side_effect=lambda:self.clock),patch.object(self.v.jobs,'_sleep_until',side_effect=wait_until):self.v.jobs._run(job)
  self.assertEqual(sent_at,[job['created_at']+600]);self.assertEqual(self.v.jobs.status()['sent'],1)
 def test_restart_preserves_the_original_scheduled_time(self):
  self.prepare();self.queue(3600);before=self.v.jobs.export_jobs()['jobs'][-1]
  restored=Volunteers(self.v.app,lambda phone:True)
  with patch('donor_delivery.threading.Thread'),patch('donor_delivery.time.time',return_value=self.clock+60):restored.jobs.recover()
  after=restored.jobs.export_jobs()['jobs'][-1]
  self.assertEqual(after['hold_until'],before['hold_until']);self.assertEqual(self.sent,[])
 def test_stop_during_the_wait_prevents_all_sends_and_recovery(self):
  self.prepare();self.queue(300);job=self.v.jobs.export_jobs()['jobs'][-1]
  self.v.mutate({'action':'stop'})
  with patch('donor_delivery.time.time',return_value=self.clock):self.v.jobs._run(job)
  self.assertEqual(self.sent,[]);self.assertEqual(self.v.jobs.status()['state'],'Stopped');self.assertIsNone(self.v.jobs.recover())

if __name__=='__main__':unittest.main()
