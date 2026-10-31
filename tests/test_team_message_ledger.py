"""Team notifications are not donor campaigns. Use the fake WhatsApp transport only."""
import hashlib
import unittest
from unittest.mock import patch
from test_donor_hub import IntegrationTests

class TeamMessageLedger(unittest.TestCase):
    def setUp(self):
        self.fixture = IntegrationTests()
        self.fixture.setUp()
        self.app = self.fixture.app

    def tearDown(self):
        self.fixture.tearDown()

    def test_team_updates_leave_donor_quota_and_recipient_state_untouched(self):
        app = self.app
        app.STORE.put('dm_daily', {'day':'2026-10-31','count':49,'last':123})
        fake = {'code':'SUCCESS','results':{'message_id':'team-test'}}
        with patch.object(app, 'send_image', return_value=fake) as wire:
            for i in range(2):
                result = app.send_custom({
                    'kind':'team_msg','target':'phone','phone':'03001234567',
                    'message':'Test teammate task update '+str(i),'poster':True
                })
                self.assertEqual(result['code'],'SUCCESS')
            self.assertEqual(wire.call_count,2)
        self.assertEqual(app.STORE.get('dm_daily')['count'],49)
        digest = hashlib.sha256(b'923001234567').hexdigest()
        self.assertIsNone(app.STORE.get('dm_recipient_'+digest))

    def test_team_message_still_respects_a_saved_optout(self):
        app = self.app
        digest = hashlib.sha256(b'923001234567').hexdigest()
        app.STORE.put('optout_'+digest,True)
        with patch.object(app,'send_image') as wire:
            with self.assertRaisesRegex(ValueError,'opted out'):
                app.send_custom({
                    'kind':'team_msg','target':'phone','phone':'03001234567',
                    'message':'Please send an update','poster':True
                })
            wire.assert_not_called()

if __name__=='__main__':
    unittest.main()
