"""Notes: permanent storage, password/session controls, safe HTML and conflict protection."""
import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from foundation_notes import NotesVault, clean_html, cookie_header, cookie_token

class FakeStore:
 def __init__(self):
  self.data={}
 def get(self,k,d=None):
  return copy.deepcopy(self.data.get(k,d))
 def put(self,k,v):
  self.data[k]=copy.deepcopy(v)

class NotesModelTests(unittest.TestCase):
 def setUp(self):
  self.store=FakeStore()
  self.vault=NotesVault(self.store)

 def test_password_not_saved_anywhere_and_device_token_is_random_and_hashed(self):
  with patch('foundation_notes.check_pin',side_effect=lambda x:x=='correct-test-password'):
   self.assertRaises(ValueError,self.vault.unlock,'wrong','desktop')
   token=self.vault.unlock('correct-test-password','desktop')
  self.assertEqual(len(token),64)
  self.assertNotIn(token,str(self.store.data))
  self.assertNotIn('correct-test-password',str(self.store.data))
  self.assertFalse(self.vault.can_access(''))
  self.assertTrue(self.vault.can_access(cookie_header(token).split(';')[0]))
  self.assertEqual(cookie_token(cookie_header(token)),token)
  self.assertIn('HttpOnly; Secure; SameSite=Strict',cookie_header(token))
  self.vault.forget(cookie_header(token))
  self.assertFalse(self.vault.can_access(cookie_header(token)))

 def test_bad_password_rate_limited(self):
  with patch('foundation_notes.check_pin',return_value=False):
   for _ in range(8):self.assertRaisesRegex(ValueError,'Incorrect',self.vault.unlock,'wrong','desktop')
   self.assertRaisesRegex(ValueError,'Too many',self.vault.unlock,'wrong','desktop')

 def test_restarts_read_same_permanent_document_without_resaving(self):
  saved=self.vault.save('<h2>Fundraising ideas</h2><ul data-list="check"><li data-checked="true">Contact alumni</li></ul>',0)
  self.assertEqual(saved['version'],1)
  again=NotesVault(self.store)
  self.assertEqual(again.read()['html'],saved['html'])
  self.assertEqual(again.read()['version'],1)
  self.assertIn('data-checked="true"',again.read()['html'])

 def test_second_tab_cannot_silently_overwrite_newer_changes(self):
  self.vault.save('<p>First idea</p>',0)
  self.assertRaisesRegex(ValueError,'another tab',self.vault.save,'<p>Old draft</p>',0)
  self.assertIn('First idea',self.vault.read()['html'])

 def test_sanitizer_keeps_formatting_lists_and_palette_colors(self):
  source='<h1>Plans</h1><p><strong>Bold</strong> and <em>italic</em></p><ol><li>First</li></ol><ul data-list="check"><li data-checked="false">Task</li></ul><span style="color: rgb(59, 130, 246);">Blue</span>'
  rendered=clean_html(source)
  for part in ('<h1>Plans</h1>','<strong>Bold</strong>','<em>italic</em>','<ol><li>First</li></ol>','data-checked="false"','style="color:#3b82f6"'):
   self.assertIn(part,rendered)

 def test_xss_scripts_events_links_and_unapproved_colors_removed(self):
  source='<img src="x" onerror="alert(1)"><script>alert(1)</script><svg onload="alert(1)"><path/></svg><a href="javascript:alert(1)">hello</a><span style="color:red;position:absolute">red</span><ul data-list="check" onclick="bad()"><li data-checked="true" onmouseover="bad()">safe</li></ul>'
  cleaned=clean_html(source)
  for bad in ('<img','script','<svg','<a','javascript:','onerror','onclick','onmouseover','absolute','alert(1)'):
   self.assertNotIn(bad,cleaned)
  self.assertIn('hello',cleaned)
  self.assertIn('data-checked="true"',cleaned)
  self.assertIn('safe',cleaned)

 def test_invalid_or_huge_html_does_not_overwrite(self):
  self.vault.save('safe',0)
  for value in (None,123,'x'*150001):
   with self.assertRaises(ValueError):self.vault.save(value,1)
  self.assertEqual(self.vault.read()['html'],'safe')

class NotesHttpTests(unittest.TestCase):
 def setUp(self):
  from test_manual_sends import app
  self.app=app
  self.old_vault=app.NOTES_VAULT
  self.vault=NotesVault(FakeStore())
  app.NOTES_VAULT=self.vault
  self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
  self.thread.start()
  self.url='http://127.0.0.1:'+str(self.server.server_port)+'/foundation-notes'

 def tearDown(self):
  self.server.shutdown()
  self.server.server_close()
  self.app.NOTES_VAULT=self.old_vault

 def call(self,body=None,cookie=None,key='test-only-studio-access-key'):
  headers={'Authorization':'Bearer '+key}
  if cookie:headers['Cookie']=cookie
  if body is not None:headers['Content-Type']='application/json'
  req=urllib.request.Request(self.url,data=json.dumps(body).encode() if body is not None else None,headers=headers)
  try:
   with urllib.request.urlopen(req,timeout=6) as response:
    return response.status,json.load(response),response.headers
  except urllib.error.HTTPError as error:
   return error.code,json.load(error),error.headers

 def test_http_separate_lock_password_only_once_cookie_is_remembered(self):
  status,_,_=self.call(key='not-studio-password')
  self.assertEqual(status,401)
  self.assertEqual(self.call()[1],{'locked':True})
  self.assertEqual(self.call({'action':'save','html':'bad','version':0})[0],403)
  self.assertEqual(self.call({'action':'unlock','password':'wrong'})[0],401)
  with patch('foundation_notes.check_pin',side_effect=lambda p:p=='test-secret'):
   status,data,headers=self.call({'action':'unlock','password':'test-secret'})
  self.assertEqual(status,200)
  self.assertFalse(data['locked'])
  cookie=headers.get('Set-Cookie').split(';')[0]
  self.assertIn('HttpOnly',headers.get('Set-Cookie'))
  self.assertTrue(self.call(cookie=cookie)[1]['locked'] is False)
  self.assertEqual(self.call({'action':'save','html':'<h2>Ideas</h2>','version':0},cookie)[1]['version'],1)
  self.assertEqual(self.call(cookie=cookie)[1]['html'],'<h2>Ideas</h2>')
  self.assertEqual(self.call({'action':'save','html':'stale','version':0},cookie)[0],409)
  self.assertEqual(self.call({'action':'forget'},cookie)[0],200)
  self.assertTrue(self.call(cookie=cookie)[1]['locked'])

if __name__=='__main__':unittest.main()
