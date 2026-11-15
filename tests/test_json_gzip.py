import gzip, io, json, sys, unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_manual_sends import app as server  # sets the test data folder before the server is imported


def call(data, accept="", kind="application/json"):
    sent = {}
    fake = SimpleNamespace(
        headers={"Accept-Encoding": accept} if accept else {},
        remote_config=lambda: {"origins": []},
        send_response=lambda status: None,
        send_header=lambda name, value: sent.setdefault(name, value),
        end_headers=lambda: None,
        wfile=io.BytesIO(),
        command="GET",
    )
    server.Handler.reply(fake, data, kind=kind)
    return sent, fake.wfile.getvalue()


class JsonGzip(unittest.TestCase):
    BIG = {"items": [{"id": "x" * 20, "name": "Name %d" % i, "state": "Sent"} for i in range(200)]}

    def test_a_big_json_list_is_sent_compressed_when_the_browser_accepts_it(self):
        sent, body = call(self.BIG, "gzip, deflate, br")
        self.assertEqual(sent["Content-Encoding"], "gzip")
        self.assertEqual(sent["Vary"], "Accept-Encoding")
        self.assertEqual(int(sent["Content-Length"]), len(body))
        self.assertEqual(json.loads(gzip.decompress(body)), self.BIG)
        self.assertLess(len(body), len(json.dumps(self.BIG)) / 4)

    def test_nothing_changes_without_gzip_or_for_small_or_other_replies(self):
        for sent, body in (
            call(self.BIG),  # a client that did not ask
            call({"ok": True}, "gzip"),  # tiny
            call("<html>" + "x" * 5000, "gzip", kind="text/html"),  # not JSON
        ):
            self.assertNotIn("Content-Encoding", sent)
            self.assertEqual(int(sent["Content-Length"]), len(body))


if __name__ == "__main__":
    unittest.main()
