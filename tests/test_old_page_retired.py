"""The previous design (/old) is retired (owner, 2026-11-27): an old /old link opens the main page."""

import http.client
import threading
import unittest

from test_manual_sends import app


class OldPageRetired(unittest.TestCase):
    def test_old_redirects_to_the_main_page(self):
        http_server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=http_server.serve_forever, daemon=True).start()
        self.addCleanup(http_server.server_close)
        self.addCleanup(http_server.shutdown)
        conn = http.client.HTTPConnection("127.0.0.1", http_server.server_port, timeout=5)
        conn.request("GET", "/old")
        res = conn.getresponse()
        res.read()
        self.assertEqual(res.status, 302)
        self.assertEqual(res.getheader("Location"), "/")


if __name__ == "__main__":
    unittest.main()
