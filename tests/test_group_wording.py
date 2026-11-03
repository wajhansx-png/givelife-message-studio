"""Group names with typos, Urdu 'all groups' wording and exclusions must resolve safely: an excluded group is never sent to."""
import unittest
import manual_commands

class GroupWording(unittest.TestCase):
 def test_typos_and_urdu_resolve(self):
  expected={'send to fiver':['fiverr'],'post upwrk':['upwork'],'sab groups me bhejo':['all'],'send to every group':['all'],'sabhi groups mein bhejo':['all'],
   'send to gruop main':['main'],'send main and fiverr':['main','fiverr']}
  for phrase,keys in expected.items():
   with self.subTest(phrase=phrase):self.assertEqual(manual_commands.groups(phrase),keys)

 def test_exclusions_remove_the_group(self):
  for phrase in ('send to all but fiverr','send to all without fiverr','send all groups except test','send all except fiverr'):
   with self.subTest(phrase=phrase):
    keys=manual_commands.groups(phrase)
    self.assertNotIn('fiverr' if 'fiverr' in phrase else 'test',keys)
    self.assertIn('main',keys)

 def test_an_exclusion_without_an_audience_sends_nowhere(self):
  for phrase in ('send except upwork','skip fiverr send all'):
   with self.subTest(phrase=phrase):
    self.assertEqual(manual_commands.groups(phrase),[])
    self.assertNotIn((manual_commands.parse(phrase) or {}).get('kind'),('appeal','appeals'))

 def test_but_without_a_group_is_not_an_exclusion(self):
  self.assertEqual(manual_commands.groups('send main but wait'),['main'])
  self.assertEqual(manual_commands.groups('send to main but first shorten it'),['main'])

if __name__=='__main__':unittest.main()
