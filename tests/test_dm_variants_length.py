"""Generated DM versions stay about as long as the message the owner gave."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dm_templates,dm_variants

class LengthRule(unittest.TestCase):
 def setUp(self):self.src=dm_templates.build(0,25000)
 def test_range_is_a_few_percent(self):
  low,high=dm_variants.length_range(self.src);n=len(self.src.strip());self.assertLessEqual(high-low,int(n*0.17)+2);self.assertLess(low,n);self.assertGreater(high,n)
 def test_a_version_of_nearly_the_same_length_is_accepted(self):
  self.assertEqual(dm_variants.validate(self.src,self.src.replace('Days have passed.','Time has passed.')),'')
 def test_a_much_longer_or_shorter_version_is_rejected(self):
  longer=self.src.replace('He is still at home.','He is still at home and the family keeps waiting for help every single hour of the day and night with no answer at all.')
  self.assertIn('length',dm_variants.validate(self.src,longer))
  shorter=self.src.replace('Fluid is filling his brain, which will paralyze his body. Both kidneys are badly swollen. He also has a hernia.','Fluid is filling his brain.')
  self.assertIn('length',dm_variants.validate(self.src,shorter))
 def test_the_prompt_states_the_length_and_asks_for_urgency(self):
  p=dm_variants._prompt(self.src,10,[]);low,high=dm_variants.length_range(self.src)
  self.assertIn(f'between {low} and {high} characters',p);self.assertIn('Strong urgency',p);self.assertIn('Never write "will die"',p)
if __name__=='__main__':unittest.main()
