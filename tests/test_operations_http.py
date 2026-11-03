"""Real local HTTP execution with a synthetic store and no outbound transports."""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from test_manual_sends import app
from test_operations_review import Store, snapshot


class ReviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.patches = [patch.object(app, 'STORE', self.store),
                        patch.dict(os.environ, {'OPERATIONS_REVIEW_KEY': 'synthetic-review-only-key-1234567890'}),
                        patch('operations_review.collect_app', return_value=snapshot()),
                        patch.object(app.ENGINE, 'touch_owner', side_effect=AssertionError('Machine poll must not touch owner activity'))]
        for p in self.patches: p.start()
        class QuietHandler(app.Handler):
            def log_message(self, *args): pass
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.http.server_port)

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join()
        for p in reversed(self.patches): p.stop()

    def request(self, path='/operations/review', body=None, key='synthetic-review-only-key-1234567890', origin=None):
        headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
        if origin: headers['Origin'] = origin
        req = urllib.request.Request(self.url + path, data=json.dumps({} if body is None else body).encode(), headers=headers)
        try: response = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as e: response = e
        with response: return response.status, json.load(response)

    def test_real_endpoint_saves_once_without_owner_side_effect(self):
        revision = app.OWNER_REVISION
        status, result = self.request()
        self.assertEqual(status, 200); self.assertFalse(result['duplicate'])
        self.assertEqual(result['report']['outbound_messages'], 0)
        self.assertTrue(self.request()[1]['duplicate'])
        self.assertEqual(app.OWNER_REVISION, revision)

    def test_machine_credential_cannot_send_or_edit_donors(self):
        for path in ('/donor-delivery', '/donor-send', '/team', '/cases', '/command'):
            self.assertEqual(self.request(path, {'action': 'send'})[0], 401)
        self.assertEqual(self.store.data, {})

    def test_unauthenticated_malformed_and_foreign_origins_rejected(self):
        self.assertEqual(self.request(key='wrong')[0], 401)
        for body in ('send now', [], {'send': True}, {'date': 'tomorrow'}):
            self.assertEqual(self.request(body=body)[0], 400)
        self.assertEqual(self.request(origin='https://untrusted.invalid')[0], 403)
        self.assertEqual(self.store.data, {})

    def test_database_failure_is_actionable_and_redacts_details(self):
        with patch.object(self.store, 'claim', side_effect=RuntimeError('private DB URI')):
            status, result = self.request()
        self.assertEqual(status, 503); self.assertNotIn('private DB URI', str(result))
        self.assertIn('Nothing was sent', result['error'])


if __name__ == '__main__': unittest.main()
