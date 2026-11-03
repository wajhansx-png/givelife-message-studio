import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_manual_sends import app
from group_finder import GroupBook
from group_research import ResearchService
from group_finder_integration import GroupFinder

LINK = "https://chat.whatsapp.com/AbCdEfGhIjKlMnOpQrStUv"


class GroupFinderAPITests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = patch.object(app, "STORE", None)
        self.store.start()
        self.addCleanup(self.store.stop)
        book = GroupBook(Path(self.folder.name))
        self.integration = GroupFinder(app, book=book, seed=False)
        self.uni = book.add_university("Example University", ["example.edu"])
        self.service = patch.object(app, "GROUP_RESEARCH", self.integration, create=True)
        self.service.start()
        self.addCleanup(self.service.stop)
        self.integration.service.start_worker = lambda: None
        self.http = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)

    def request(self, path="/api/group-finder", body=None, auth=True, origin=None):
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer test-only-studio-access-key"
        if origin:
            headers["Origin"] = origin
        req = urllib.request.Request(
            "http://127.0.0.1:" + str(self.http.server_port) + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)

    def test_all_research_data_requires_authentication(self):
        self.assertEqual(self.request(auth=False)[0], 401)
        self.assertEqual(self.request(body={"action": "search"}, auth=False)[0], 401)

    def test_import_deduplicates_and_cannot_claim_verified_source(self):
        status, data = self.request(
            body={
                "action": "import",
                "university_id": self.uni["id"],
                "text": LINK + "\n" + LINK + "?mode=ac_t",
                "source_url": "https://example.edu/welfare",
                "source_verified": True,
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["added"], 1)
        result = self.request()[1]
        self.assertEqual(result["counts"]["all"], 1)
        self.assertEqual(result["items"][0]["checks"]["affiliation"]["value"], "unknown")

    def test_search_request_does_not_change_sending_or_owner_revision(self):
        before = app.OWNER_REVISION
        with (
            patch.object(app.ENGINE, "touch_owner") as touch,
            patch.object(app, "send_image") as send,
        ):
            status, job = self.request(
                body={
                    "action": "search",
                    "university_ids": [self.uni["id"]],
                    "request_id": "api-test-request-001",
                }
            )
        self.assertEqual(status, 200)
        self.assertEqual(job["state"], "queued")
        self.assertEqual(app.OWNER_REVISION, before)
        touch.assert_not_called()
        send.assert_not_called()

    def test_untrusted_origin_is_rejected(self):
        self.assertEqual(
            self.request(
                body={"action": "import", "text": LINK}, origin="https://attacker.invalid"
            )[0],
            403,
        )

    def test_posting_permission_check_uses_exact_bound_joined_group(self):
        row = self.integration.book.discover(LINK, self.uni["id"], "https://example.edu/welfare")
        row = self.integration.book.review(
            row["id"],
            {"jid": "120363123456789@g.us"},
            {
                "kind": "owner_observation",
                "reference": "Mapped this invite to its exact joined group.",
            },
            row["version"],
        )
        with patch.object(
            app,
            "api",
            return_value={"results": [{"JID": row["jid"], "GroupAnnounce": {"IsAnnounce": False}}]},
        ):
            status, checked = self.request(
                body={"action": "check_account", "id": row["id"], "version": row["version"]}
            )
        self.assertEqual(status, 200)
        self.assertEqual(checked["checks"]["posting"]["value"], "all_members")
        self.assertEqual(checked["checks"]["member"]["value"], "yes")
        self.assertEqual(checked["checks"]["charity"]["value"], "unknown")

    def test_uncertain_joined_group_response_is_not_no_membership(self):
        row = self.integration.book.discover(LINK, self.uni["id"], "https://example.edu/welfare")
        row = self.integration.book.review(
            row["id"],
            {"jid": "120363123456789@g.us"},
            {"kind": "owner_observation", "reference": "Mapped the exact joined group."},
            row["version"],
        )
        with patch.object(app, "api", return_value={"code": "ERROR", "message": "Disconnected"}):
            status, data = self.request(
                body={"action": "check_account", "id": row["id"], "version": row["version"]}
            )
        self.assertEqual(status, 502)
        self.assertEqual(self.integration.book.get(row["id"])["version"], row["version"])

    def test_stale_review_returns_conflict(self):
        row = self.integration.book.discover(LINK, self.uni["id"], "https://example.edu/welfare")
        payload = {
            "action": "review",
            "id": row["id"],
            "version": row["version"],
            "changes": {"charity": "allowed"},
            "evidence": {"kind": "owner_observation", "reference": "Admin approved case sharing."},
            "confirm_observed": True,
        }
        self.assertEqual(self.request(body=payload)[0], 200)
        self.assertEqual(self.request(body=payload)[0], 409)

    def test_review_cannot_impersonate_connected_account_check(self):
        row = self.integration.book.discover(LINK, self.uni["id"], "https://example.edu/welfare")
        status, _ = self.request(
            body={
                "action": "review",
                "id": row["id"],
                "version": row["version"],
                "changes": {"posting": "all_members"},
                "evidence": {
                    "kind": "account_observation",
                    "reference": "Pretend an API check happened",
                },
                "confirm_observed": True,
            }
        )
        self.assertEqual(status, 400)

    def test_unknown_actions_cannot_join_or_send(self):
        for action in ["send", "join", "scrape_members", "auto_dm"]:
            with self.subTest(action=action):
                self.assertEqual(self.request(body={"action": action})[0], 400)


if __name__ == "__main__":
    unittest.main()
