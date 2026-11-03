"""Isolated research preview: synthetic websites/search and no real WhatsApp or database access."""

import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name in ("DB_URI", "DEEPSEEK_API_KEY", "RENDER_EXTERNAL_URL"):
    os.environ.pop(name, None)
folder = tempfile.TemporaryDirectory()
os.environ.update(
    DATA_DIR=folder.name, UI_ACCESS_KEY="group-finder-preview-only", GOWA_URL="http://127.0.0.1:1"
)
for name in ("drafts.json", "state.md"):
    shutil.copyfile(ROOT / name, Path(folder.name) / name)
(Path(folder.name) / "poster.jpg").write_bytes(b"fake-poster")
import server
from group_finder import GroupBook
from group_finder_integration import GroupFinder
from group_research import Document

LINK = "https://chat.whatsapp.com/AbCdEfGhIjKlMnOpQrStUv"


class Search:
    name = "Synthetic test search (no external requests)"

    def search(self, query):
        return [
            {
                "url": "https://example.edu/welfare",
                "title": "Demo University welfare",
                "excerpt": "Public society page",
            }
        ]


class Reader:
    def fetch(self, url, **kwargs):
        return Document(
            url,
            '<title>Demo University welfare</title><a href="'
            + LINK
            + '">Join</a><script>window.injected=true</script>',
        )


book = GroupBook(Path(folder.name))
uni = book.add_university("Demo University", ["example.edu"], city="Lahore")
integration = GroupFinder(server, book=book, seed=False)
integration.service.search, integration.service.reader = Search(), Reader()
server.GROUP_RESEARCH = integration
server.api = lambda path: {
    "code": "SUCCESS",
    "results": [
        {
            "JID": "120363123456789@g.us",
            "GroupName": {"Name": "Demo University welfare"},
            "GroupAnnounce": {"IsAnnounce": False},
        }
    ],
}
server.Handler.log_message = lambda *args: None


class Handler(server.Handler):
    def do_POST(self):
        if self.path == "/__test/shutdown":
            if not self.authorized():
                return self.reply({"error": "Access key required"}, status=401)
            self.reply({"stopped": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        return super().do_POST()


class HTTP(server.ThreadingHTTPServer):
    request_queue_size = 128


port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 3041
http = HTTP(("127.0.0.1", port), Handler)
print("Synthetic group finder preview: http://127.0.0.1:" + str(port) + "/group-finder", flush=True)
try:
    http.serve_forever()
finally:
    integration.service.stop_event.set()
    integration.service.wake.set()
    if integration.service.thread:
        integration.service.thread.join(3)
    http.server_close()
    folder.cleanup()
