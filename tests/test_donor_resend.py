"""DM sent is never forgotten, favourites stay favourites, repeats are allowed, bulk paste is forgiving."""
import copy,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from donor_book import DonorBook
from donor_paste import PastedDonors

class Store:
 def __init__(self):self.data={}
 def get(self,k,d=None):return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)

class SentState(unittest.TestCase):
 def setUp(self):
  self.f=tempfile.TemporaryDirectory();self.addCleanup(self.f.cleanup);self.book=DonorBook(self.f.name,Store())
  self.d=self.book.add('Ali','03001234567')['donor'];self.book.update(self.d['id'],important=True)
 def row(self):return next(r for r in self.book.list('important')['items'] if r['id']==self.d['id'])
 def test_sent_marks_dm_sent_and_keeps_important(self):
  self.book.delivery(self.d['id'],'Sent');r=self.row()
  self.assertTrue(r['dm_sent']);self.assertTrue(r['important']);self.assertEqual(r['sent_count'],1)
  self.assertEqual(len(self.book.list('important')['items']),1,'still listed in the Important tab')
 def test_later_failure_or_pending_never_erases_dm_sent(self):
  self.book.delivery(self.d['id'],'Sent')
  for state in ('Sending','Uncertain','Not sent'):
   self.book.delivery(self.d['id'],state);self.assertTrue(self.row()['dm_sent'],state)
 def test_every_confirmed_repeat_is_counted(self):
  for _ in range(3):self.book.delivery(self.d['id'],'Sent')
  self.assertEqual(self.row()['sent_count'],3)
 def test_a_donor_never_sent_is_not_marked(self):
  self.assertFalse(self.row()['dm_sent']);self.assertEqual(self.row()['sent_count'],0)
 def test_old_records_that_were_sent_before_this_change_still_show_sent(self):
  data=self.book._load();rec=data['records'][0];rec.update(delivery='Sent',last_sent_at=1000.0);rec.pop('dm_sent',None);self.book._save(data)
  self.assertTrue(self.row()['dm_sent'])
 def test_toggling_importance_does_not_touch_sent_state(self):
  self.book.delivery(self.d['id'],'Sent');self.book.update(self.d['id'],important=False);self.book.update(self.d['id'],important=True)
  self.assertTrue(self.row()['dm_sent'])

class QueueOrder(unittest.TestCase):
 def setUp(self):
  self.f=tempfile.TemporaryDirectory();self.addCleanup(self.f.cleanup);self.book=DonorBook(self.f.name,Store())
  self.ids={}
  for name,phone in (('Ali','03001111111'),('Bilal','03002222222'),('Chand','03003333333'),('Danish','03004444444')):
   d=self.book.add(name,phone)['donor'];self.ids[name]=d['id'];self.book.update(d['id'],important=True)
 def names(self,tab='important'):return [r['name'] for r in self.book.list(tab)['items']]
 def test_important_positions_do_not_change_after_delivery(self):
  self.assertEqual(self.names(),['Ali','Bilal','Chand','Danish'])
  self.book.delivery(self.ids['Ali'],'Sent',100.0);self.assertEqual(self.names(),['Ali','Bilal','Chand','Danish'])
  self.book.delivery(self.ids['Bilal'],'Sent',200.0);self.assertEqual(self.names(),['Ali','Bilal','Chand','Danish'])
 def test_repeat_sends_never_reorder_important_donors(self):
  for name,t in (('Danish',100.0),('Ali',200.0),('Chand',300.0)):self.book.delivery(self.ids[name],'Sent',t)
  self.assertEqual(self.names(),['Ali','Bilal','Chand','Danish'])
  self.book.delivery(self.ids['Danish'],'Sent',400.0);self.assertEqual(self.names(),['Ali','Bilal','Chand','Danish'])
 def test_a_batch_takes_people_in_the_same_order_as_the_screen(self):
  self.book.delivery(self.ids['Ali'],'Sent',100.0)
  self.assertEqual([r['name'] for r in self.book.recipients('important',None,2)],['Ali','Bilal'])
 def test_important_still_comes_before_everyone_else(self):
  x=self.book.add('Aaa','03005555555')['donor'];self.assertEqual(self.names('all')[-1],'Aaa')

class RoughPaste(unittest.TestCase):
 def setUp(self):
  self.f=tempfile.TemporaryDirectory();self.addCleanup(self.f.cleanup);self.book=DonorBook(self.f.name,Store())
  self.p=PastedDonors(self.book,None,lambda:'923205069925',lambda label:(label.split()[0],'Brother'))
 def names(self,text):return self.p.preview(text)['names']
 def test_bare_numbers_one_per_line_or_on_one_line(self):
  self.assertEqual(self.names('03001234567\n03011234567'),['Donor 1','Donor 2'])
  self.assertEqual(self.names('03001234567 03011234567, 0302-1234567'),['Donor 1','Donor 2','Donor 3'])
 def test_names_in_any_order_with_bullets_and_labels(self):
  self.assertEqual(self.names('1. Ali 0300 1234567\n- 0301-1234567 Sara\nName: Zaid, Number: 03021234567'),['Ali','Sara','Zaid'])
 def test_several_named_numbers_on_one_line(self):
  self.assertEqual(self.names('Ali 03001234567, Sara 03011234567'),['Ali','Sara'])
 def test_mixed_named_and_unnamed_on_one_line_is_rejected_not_guessed(self):
  with self.assertRaises(ValueError):self.p.preview('Ali 03001234567 03011234567')
 def test_schedule_is_planned_for_everyone_at_once(self):
  r=self.p.preview('Ali 03001234567\nSara 03011234567\n03021234567',gap_seconds=180)
  self.assertEqual([x['after_seconds'] for x in r['plan']],[0,180,360]);self.assertEqual(r['total_seconds'],360);self.assertEqual(r['gap_seconds'],180.0)
  self.assertEqual([x['name'] for x in r['plan']],['Ali','Sara','Donor 3'])
  self.assertNotIn('0300',str(r['plan']));self.assertNotIn('1234567',str(r['plan']))
 def test_gap_is_validated(self):
  for gap in (0,59,601,True,float('nan'),'4'):
   with self.subTest(gap=gap),self.assertRaises(ValueError):self.p.preview('03001234567',gap_seconds=gap)
 def test_more_than_twenty_different_people_is_refused_clearly(self):
  with self.assertRaisesRegex(ValueError,'20'):self.p.preview(' '.join('92300%07d'%i for i in range(21)))
 def test_own_number_and_invalid_numbers_still_refused(self):
  for text in ('Me 03205069925','Ali 0300123','no number here'):
   with self.subTest(text=text),self.assertRaises(ValueError):self.p.preview(text)

if __name__=='__main__':unittest.main()
