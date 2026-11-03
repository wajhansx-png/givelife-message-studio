"""Generated DM versions stay within the deliberate length tolerance of the owner's message.

c719e01 widened LENGTH_TOLERANCE (0.08 -> 0.28) so meaning can be rewritten
deeply instead of matching a character count, and removed urgency/death
language from the prompt. These checks follow that design.
"""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dm_templates,dm_variants

class LengthRule(unittest.TestCase):
 def setUp(self):self.src=dm_templates.build(0,25000)
 def test_range_is_a_few_percent(self):
  low,high=dm_variants.length_range(self.src);n=len(self.src.strip())
  self.assertLessEqual(abs((high-low)-2*n*dm_variants.LENGTH_TOLERANCE),2)
  self.assertLess(low,n);self.assertGreater(high,n)
 def test_a_version_of_nearly_the_same_length_is_accepted(self):
  # A genuinely rewritten version of the same case, facts and payment lines.
  self.assertEqual(dm_variants.validate(self.src,dm_templates.build(18,25000)),'')
 def test_a_much_longer_or_shorter_version_is_rejected(self):
  longer=self.src.replace("Don't wait for someone else.","Don't wait for someone else. "+'Please read this again and think about it carefully. '*8)
  self.assertIn('length',dm_variants.validate(self.src,longer))
  shorter=self.src.replace('_Yousuf is 2. Fluid is filling his brain, which will paralyze his body. Both kidneys are badly swollen. He also has a hernia._','_Yousuf is 2._').replace('*His parents reported that he was short of breath. Please rely on verified medical information for further details.*','*He is unwell.*').replace('please read about Yousuf and the support his family requested.','please help Yousuf.')
  self.assertIn('length',dm_variants.validate(self.src,shorter))
 def test_the_prompt_states_the_length_and_forbids_invented_urgency(self):
  p=dm_variants._prompt(self.src,10,[]);low,high=dm_variants.length_range(self.src)
  self.assertIn(f'target {low} to {high} characters',p);self.assertIn('No invented time pressure',p);self.assertNotIn('will die',p)
if __name__=='__main__':unittest.main()
