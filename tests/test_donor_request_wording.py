"""Owner wording for donor DM rounds: gap, rest and poster must land in the right setting."""
import unittest
import donor_book

class DonorRequestWording(unittest.TestCase):
 def parse(self,text):return donor_book.send_request(text)
 def test_rest_is_not_the_gap(self):
  plan=self.parse('send 20 dms to important donors then rest 20 minutes')
  self.assertEqual((plan['gap_seconds'],plan['rests']),(240,[1200.0]))
  plan=self.parse('dm all donors 4 min gap and 30 min rest')
  self.assertEqual((plan['gap_seconds'],plan['rests']),(240.0,[1800.0]))
 def test_poster_off_wording(self):
  for text in ('dm donors with poster off','dm donors without the picture','dm donors no poster','dm donors text only'):
   with self.subTest(text=text):self.assertFalse(self.parse(text)['poster'])
  self.assertTrue(self.parse('dm important donors')['poster'])
 def test_gap_and_scope_still_read(self):
  plan=self.parse('dm first 10 donors gap 5 minutes')
  self.assertEqual((plan['gap_seconds'],plan['limit']),(300.0,10))
  self.assertEqual(self.parse('send dms to not donated donors')['scope'],'not_donated')

if __name__=='__main__':unittest.main()
