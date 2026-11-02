import tempfile,unittest,threading,copy
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from focus_bank import FocusBank,valid
class Store:
 def __init__(self):self.data={}
 def get(self,k,d=None):return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
class FocusTests(unittest.TestCase):
 def make(self):
  self.drafts={'group':'*Please help this family today.*\n\nRs. 50,000 needed\n\n03097458815 Easypaisa / JazzCash Wajdan Khan','dm':'Brother, support this family.'}
  bank=SimpleNamespace(lock=threading.RLock(),_save=lambda d:None,_fingerprint=lambda t:t,_entries=lambda ts:[{'text':t} for t in ts]);self.app=SimpleNamespace(donors=lambda:SimpleNamespace(messages=bank),read_left=lambda:50000,STORE=Store(),LOCK=threading.RLock(),get_message=lambda k:{'text':self.drafts[k]},save_draft=lambda k,v:self.drafts.update({k:v}))
  return FocusBank(self.app)
 def test_saved_original_and_custom_dm_survive_group_changes(self):
  b=self.make()
  with patch.object(b,'start'):
   first=b.save('group',self.drafts['group']);dm=b.get('dm');self.assertTrue(dm['source'].startswith('Brother, '))
   b.save('dm','My personal DM',dm['revision']);b.save('group','Different case message',first['revision'])
   self.assertEqual(b.get('dm')['source'],'My personal DM');self.assertEqual(b.get('group')['history'],[first['source']])
   with self.assertRaises(ValueError):b.save('group','stale',first['revision'])
 def test_exact_length_numbers_format_and_payment_are_checked(self):
  source='*Please help*\n\n50,000 needed\n\n03097458815 Easypaisa'
  self.assertTrue(valid(source,source.replace('Please','Kindly')))
  for candidate in (source+'!',source.replace('*','_'),source.replace('50,000','40,000'),source.replace('Easypaisa','JazzCash')):self.assertFalse(valid(source,candidate))
 def test_failed_generation_keeps_source_and_can_restart_with_new_instance(self):
  b=self.make()
  with patch.object(b,'start'):row=b.save('group',self.drafts['group'])
  with patch('dm_variants.assistant.client',return_value=None):b._generate('group',row,('group',row['revision']))
  newer=FocusBank(self.app);self.assertEqual(newer.get('group')['source'],row['source']);self.assertEqual(newer.get('group')['state'],'Needs retry');self.assertEqual(self.drafts['group'],row['source'])
 def test_ten_distinct_exact_length_versions_and_stale_results(self):
  b=self.make();source='*Hook A*\n\nRs. 50,000 needed\n\n03097458815 Easypaisa / JazzCash Wajdan Khan'
  with patch.object(b,'start'):row=b.save('group',source)
  versions=[source.replace('Hook A','Hook '+chr(66+i)) for i in range(10)]
  with patch('dm_variants.assistant.client',return_value='fake'),patch('dm_variants._call',return_value=versions):b._generate('group',row,('group',row['revision']))
  self.assertEqual(b.get('group')['items'],versions);self.assertEqual(self.drafts['group'],source)
  with patch.object(b,'start'):latest=b.save('group',source+'!',row['revision'])
  with patch('dm_variants.assistant.client',return_value='fake'),patch('dm_variants._call',return_value=versions):b._generate('group',row,('group',row['revision']))
  self.assertEqual(b.get('group')['source'],latest['source']);self.assertEqual(b.get('group')['items'],[])
if __name__=='__main__':unittest.main()
