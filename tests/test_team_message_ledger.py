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
        previous_manual = dict(app.LAST_MANUAL)
        with patch.object(app, 'send_image', return_value=fake) as wire:
            for i in range(2):
                result = app.send_custom({
                    'kind':'team_msg','target':'phone','phone':'03001234567',
                    'message':'Test teammate task update '+str(i),'poster':True
                })
                self.assertEqual(result['code'],'SUCCESS')
            self.assertEqual(wire.call_count,2)
        self.assertEqual(app.STORE.get('dm_daily')['count'],49)
        self.assertEqual(app.LAST_MANUAL, previous_manual, 'Team messages must not replace last manual send')
        digest = hashlib.sha256(b'923001234567').hexdigest()
        self.assertIsNone(app.STORE.get('dm_recipient_'+digest))

    def test_direct_web_route_cannot_spoof_internal_team_kind(self):
        import json, threading, urllib.error, urllib.request
        app = self.app
        http = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread = threading.Thread(target=http.serve_forever,daemon=True)
        thread.start()
        try:
            payload = json.dumps({'kind':'team_msg','target':'phone',
                                  'phone':'03001234567','message':'unapproved task ping',
                                  'poster':False}).encode()
            request = urllib.request.Request(
                'http://127.0.0.1:'+str(http.server_port)+'/send-custom',
                data=payload,
                headers={'Authorization':'Bearer test-only-studio-access-key',
                         'Content-Type':'application/json'})
            with patch.object(app, 'send_image') as wire:
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(request,timeout=3)
                self.assertEqual(ctx.exception.code,403)
                wire.assert_not_called()
        finally:
            http.shutdown()
            http.server_close()

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
