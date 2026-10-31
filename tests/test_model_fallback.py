"""Cerebras is primary; DeepSeek is used only when Cerebras is unset, errors, or is rate-limited."""
import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistant

def ok_response(text='hi'):
 class R:
  status=200
  def read(self):return json.dumps({'choices':[{'message':{'content':text},'finish_reason':'stop'}]}).encode()
  def __enter__(self):return self
  def __exit__(self,*a):return False
 return R()

class Fallback(unittest.TestCase):
 def setUp(self):
  self.env=dict(os.environ)
 def tearDown(self):
  os.environ.clear();os.environ.update(self.env)
 def test_client_prefers_cerebras_key(self):
  os.environ['CEREBRAS_API_KEY']='c-key';os.environ.pop('DEEPSEEK_API_KEY',None)
  self.assertEqual(assistant.client(),'c-key')
  os.environ.pop('CEREBRAS_API_KEY',None);os.environ['DEEPSEEK_API_KEY']='d-key'
  self.assertEqual(assistant.client(),'d-key')
 def test_cerebras_success_never_calls_deepseek(self):
  os.environ['CEREBRAS_API_KEY']='c-key';os.environ['DEEPSEEK_API_KEY']='d-key'
  with patch('urllib.request.urlopen',return_value=ok_response('from cerebras')) as opened:
   msg=assistant._chat_raw('c-key','sys',[],[{'role':'user','content':'hi'}])
  self.assertEqual(msg['content'],'from cerebras');self.assertFalse(assistant.fallback_used())
  self.assertIn('cerebras.ai',opened.call_args.args[0].full_url)
 def test_cerebras_failure_falls_back_to_deepseek_and_flags_it(self):
  os.environ['CEREBRAS_API_KEY']='c-key';os.environ['DEEPSEEK_API_KEY']='d-key'
  calls=[]
  def fake_urlopen(req,timeout=None):
   calls.append(req.full_url)
   if 'cerebras' in req.full_url:raise OSError('down')
   return ok_response('from deepseek')
  with patch('urllib.request.urlopen',side_effect=fake_urlopen):
   msg=assistant._chat_raw('c-key','sys',[],[{'role':'user','content':'hi'}])
  self.assertEqual(msg['content'],'from deepseek');self.assertTrue(assistant.fallback_used())
  self.assertTrue(any('deepseek' in c for c in calls))
 def test_fallback_flag_clears_after_one_read(self):
  os.environ['CEREBRAS_API_KEY']='c-key';os.environ['DEEPSEEK_API_KEY']='d-key'
  def fake_urlopen(req,timeout=None):
   if 'cerebras' in req.full_url:raise OSError('down')
   return ok_response('ok')
  with patch('urllib.request.urlopen',side_effect=fake_urlopen):
   assistant._chat_raw('c-key','sys',[],[{'role':'user','content':'hi'}])
  self.assertTrue(assistant.fallback_used());self.assertFalse(assistant.fallback_used())
 def test_no_deepseek_key_means_cerebras_failure_raises(self):
  os.environ['CEREBRAS_API_KEY']='c-key';os.environ.pop('DEEPSEEK_API_KEY',None)
  with patch('urllib.request.urlopen',side_effect=OSError('down')):
   with self.assertRaises(RuntimeError):assistant._chat_raw('c-key','sys',[],[{'role':'user','content':'hi'}])
  self.assertFalse(assistant.fallback_used())
 def test_only_deepseek_configured_still_works_as_before(self):
  os.environ.pop('CEREBRAS_API_KEY',None);os.environ['DEEPSEEK_API_KEY']='d-key'
  with patch('urllib.request.urlopen',return_value=ok_response('plain deepseek')):
   msg=assistant._chat_raw('d-key','sys',[],[{'role':'user','content':'hi'}])
  self.assertEqual(msg['content'],'plain deepseek');self.assertFalse(assistant.fallback_used())

if __name__=='__main__':unittest.main()
