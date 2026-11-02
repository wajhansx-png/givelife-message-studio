import unittest
from wording_fit import fit_length
from focus_bank import valid
class LengthRepairTests(unittest.TestCase):
 def test_near_length_rewrite_fits_without_padding_or_changing_facts(self):
  source='*Please support this family today.*\n\nThey are worried about burial expenses.\n\nRs. 50,000 needed\n\n03097458815 Easypaisa / JazzCash Wajdan Khan'
  candidate=source.replace('Please support','Kindly support').replace('They are','They\'re')
  repaired=fit_length(source,candidate)
  self.assertIsNotNone(repaired);self.assertEqual(len(source),len(repaired));self.assertTrue(valid(source,repaired));self.assertNotIn('  ',repaired)
 def test_payment_line_is_restored_verbatim(self):
  source='*Please help this family today.*\n\nThey are worried.\n\n03097458815 Easypaisa / JazzCash Wajdan Khan'
  candidate=source.replace('Please','Kindly').replace('Wajdan Khan','wrong name')
  repaired=fit_length(source,candidate);self.assertTrue(valid(source,repaired));self.assertIn('Wajdan Khan',repaired)
 def test_numbers_and_format_are_never_repaired_by_weakening_checks(self):
  source='*Please help.*\n\n50,000 needed\n\n03097458815 Easypaisa'
  for candidate in (source.replace('50,000','40,000'),source.replace('*','_'),source+'Lots of extra words that cannot fit.'):
   self.assertIsNone(fit_length(source,candidate))
