import unittest
from unittest.mock import patch,Mock
import test_manual_sends as fixture
from test_manual_sends import app
class AutoGroupSourceTests(unittest.TestCase):
 setUp=fixture.SendTests.setUp
 tearDown=fixture.SendTests.tearDown
 def test_auto_ignores_legacy_templates_and_uses_editor_source(self):
  saved='Owner-approved group message from editor'
  bank=Mock();bank.get.return_value={'revision':'owner','source':saved,'items':['Another approved version']}
  with patch.object(app,'get_message',return_value={'text':saved}),patch.object(app,'focus_bank',return_value=bank),patch.object(app,'start_keys_job',return_value=True) as send,patch.object(app,'build_group',side_effect=AssertionError('must not use templates')):
   for old in ('old medical template','legacy milestone copy','unrelated sharing request'):
    self.assertTrue(app.start_auto_group_job(['main'],old));self.assertEqual(send.call_args.args,(['main'],saved))
   self.assertEqual(app.caption_variant(100),saved)
 def test_all_auto_paths_share_saved_source_including_completion(self):
  self.assertIs(app.ENGINE.h['start_job'],app.start_auto_group_job)
  self.assertIs(app.ENGINE.h['post_text_all'],app.auto_post_saved_to_all)
  with patch.object(app,'start_auto_group_job',return_value=True) as send:
   app.auto_post_saved_to_all('legacy text');self.assertEqual(send.call_args.args,(list(app.GROUPS),))
 def test_blank_saved_group_message_does_not_fall_back_to_templates(self):
  with patch.object(app,'get_message',return_value={'text':' '}),patch.object(app,'start_keys_job') as send:
   with self.assertRaises(ValueError):app.start_auto_group_job(['main'],'old template')
   send.assert_not_called()
