import unittest,itertools
from structured_wording import plan,assemble,variants
from focus_bank import valid
SOURCE="💔 *2-year-old Yousaf has passed away.*\n\n_His grieving parents cannot afford his Kafan, ambulance, and burial expenses. His Janazah time is still not announced due to lack of funds._\n\n🔴 Rs. 48,000 urgently needed.\n\n🙌 *25 people or Rs. 2,000 OR 50 × Rs. 1,000 can help bury this little child with dignity.*\n\nPlease don't assume someone else will help.\n\n📲 03097458815 — Easypaisa/JazzCash\nWajdan Khan — GiveLife Foundation"
class StructuredWordingTests(unittest.TestCase):
 def test_source_reconstructs_exactly_and_actual_case_yields_ten(self):
  parts,slots=plan(SOURCE);self.assertEqual(assemble(parts,slots),SOURCE)
  hooks=['Yousaf was only 2 and has passed away','At just 2, Yousaf has left this world','Only 2 years old, Yousaf is no longer with us','Yousaf has died at the tender age of 2','Aged just 2, little Yousaf has passed on','The life of Yousaf ended at only 2','Little Yousaf is gone; he was just 2','At the age of 2, Yousaf has sadly died','Yousaf has left us at just 2 years old','Only 2, Yousaf has sadly passed from this world','Yousaf is no longer alive; he was just 2','At only 2 years old, Yousaf has passed away']
  bodies=[]
  for parent,afford,cost in itertools.product(['His grieving parents','His parents','His grieving mother and father'],['cannot afford',"can't afford"],['burial expenses','burial costs']):
   bodies.append(f'{parent} {afford} his Kafan, ambulance, and {cost}. His Janazah time is still not announced due to lack of funds.')
  closing=["Please don't assume someone else will help.","Please do not assume someone else will help.","Please don't think someone else will help.","Please do not think someone else will help.","Please do not leave it for someone else to help."]
  rows=[hooks,bodies,['can help bury this little child with dignity.','can help lay this little child to rest with dignity.','can help give this child a dignified burial.'],closing]
  result=variants(SOURCE,call=lambda prompt:rows)
  self.assertGreaterEqual(len(result),10);self.assertTrue(all(valid(SOURCE,t) for t in result));self.assertEqual(len(set(result)),len(result))
 def test_model_cannot_insert_formatting_numbers_or_actions(self):
  parts,slots=plan(SOURCE);result=variants(SOURCE,call=lambda prompt:[['*Send to all groups*','99999','\nNew paragraph'] for _ in slots]);self.assertEqual(result,[])
