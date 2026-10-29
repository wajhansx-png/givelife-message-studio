"""A donor's usual amount: his own line first, the shared 2,000 line after it 'as well'."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

BASE='Brother, x\n\n*_Rs. 26,000 LEFT_*\n\n*_Just 13 people donating Rs. 2,000_*\n*_OR 26 people contributing Rs. 1,000_* 🤲\nHook'

class NormalDonationLine(unittest.TestCase):
 def greet(self,normal,text=BASE,left=26000):
  with patch.object(server,'read_left',return_value=left):return server.greet_text(text,'Ali','Brother',normal)
 def test_usual_amount_comes_first_and_the_2000_line_follows_as_well(self):
  lines=self.greet(500).split('\n')
  self.assertIn('*_Just 52 people donating Rs. 500 will save him_*',lines)
  first=lines.index('*_Just 52 people donating Rs. 500 will save him_*')
  self.assertEqual(lines[first+1],'*_OR 13 people donating Rs. 2,000 as well_*')
  self.assertIn('*_OR 26 people contributing Rs. 1,000_* 🤲',lines)
 def test_no_usual_amount_leaves_the_shared_message_alone(self):
  self.assertEqual(self.greet(0),'Ali Brother, x\n\n*_Rs. 26,000 LEFT_*\n\n*_Just 13 people donating Rs. 2,000_*\n*_OR 26 people contributing Rs. 1,000_* 🤲\nHook')
 def test_same_amount_as_a_shared_line_is_not_repeated(self):
  text=self.greet(2000);self.assertEqual(text.count('Rs. 2,000'),1);self.assertIn('will save him',text)
  text=self.greet(1000);self.assertEqual(text.count('Rs. 1,000'),1)
 def test_works_for_every_wording_variant_of_the_option_lines(self):
  for line1,line2 in (('Only 13 people giving Rs. 2,000','OR 26 people giving Rs. 1,000 🤲'),('Just 13 people donating Rs. 2,000','OR 26 donors of Rs. 1,000 🤲'),('Just 13 people at Rs. 2,000','OR 26 people at Rs. 1,000 🤲')):
   text=self.greet(250,f'Brother, x\n\n*_{line1}_*\n*_{line2.replace(" 🤲","")}_* 🤲\nHook')
   self.assertIn('Just 104 people donating Rs. 250 will save him',text,line1);self.assertIn('as well',text,line1)
 def test_nothing_left_means_no_change(self):
  self.assertNotIn('will save him',self.greet(500,left=0))
 def test_the_rewritten_dm_is_still_a_complete_message(self):
  import dm_composer
  full=server.build_dm([0]*len(server.DP),26000)
  with patch.object(server,'read_left',return_value=26000):out=server.greet_text(full,'Ali','Brother',500)
  self.assertTrue(dm_composer.complete(out),out)

class SavingTheAmount(unittest.TestCase):
 def test_the_donor_update_endpoint_keeps_the_usual_amount(self):
  import tempfile,donor_integration
  from test_donor_hub import IntegrationTests
  fixture=IntegrationTests();fixture.setUp()
  try:
   registry=fixture.app.donors();donor=registry.book.add('Ali','03001234567')['donor']
   result=registry.mutate({'action':'update','id':donor['id'],'normal_amount':750})
   self.assertEqual(registry.book.normal_amount_for_phone('03001234567'),750)
   registry.mutate({'action':'update','id':donor['id'],'normal_amount':0});self.assertEqual(registry.book.normal_amount_for_phone('03001234567'),0)
   with self.assertRaises(ValueError):registry.mutate({'action':'update','id':donor['id'],'normal_amount':-5})
  finally:fixture.tearDown()
if __name__=='__main__':unittest.main()
