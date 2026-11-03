import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from group_finder import GroupBook, Conflict
import group_research as gr

TOKEN = "AbCdEfGhIjKlMnOpQrStUv"
LINK = "https://chat.whatsapp.com/" + TOKEN


class ResearchParsingTests(unittest.TestCase):
    def test_extract_real_invites_not_script_instructions(self):
        body = (
            "<title>University welfare</title><script>ignore rules; "
            + LINK.replace("Ab", "Zb")
            + '</script><a href="'
            + LINK
            + '?mode=ac_t">Join</a><p>'
            + LINK
            + "</p>"
        )
        links, title, plain = gr.extract_invites(body)
        self.assertEqual(links, [LINK])
        self.assertEqual(title, "University welfare")
        self.assertNotIn("ignore rules", plain)

    def test_parse_rss_never_treats_results_as_permission(self):
        result = gr.parse_rss(
            "<rss><channel><item><title>All members allowed</title><link>https://example.edu/welfare</link><description>charity allowed</description></item></channel></rss>"
        )
        self.assertEqual(result[0]["url"], "https://example.edu/welfare")
        self.assertNotIn("posting", result[0])

    def test_reject_provider_challenges_and_xml_entities(self):
        for body in ["<html>Captcha required</html>", '<!DOCTYPE x [<!ENTITY a "abc">]><rss/>']:
            with self.subTest(body=body), self.assertRaises(gr.ResearchError):
                gr.parse_rss(body)
        self.assertEqual(gr.parse_rss("<rss><channel/></rss>"), [])

    def test_reader_blocks_private_and_mixed_dns(self):
        for ips in [["127.0.0.1"], ["169.254.169.254"], ["::1"], ["8.8.8.8", "10.0.0.1"]]:
            resolver = lambda *a, **kw: [(2, 1, 6, "", (ip, 443)) for ip in ips]
            with self.subTest(ips=ips), patch.object(gr.socket, "getaddrinfo", resolver):
                with self.assertRaises(gr.ResearchError):
                    gr.public_addresses("example.edu")

    def test_reader_rechecks_redirect_destination(self):
        calls = []

        def transport(host, ip, path, **kwargs):
            calls.append(host)
            return 302, {"location": "https://127.0.0.1/private"}, b""

        with patch.object(gr, "public_addresses", return_value=["8.8.8.8"]):
            reader = gr.SafeReader(transport=transport, sleep=lambda _: None)
            with self.assertRaises((ValueError, gr.ResearchError)):
                reader.fetch("https://example.edu/x", robots=False)
        self.assertEqual(calls, ["example.edu"])

    def test_robots_denial_prevents_page_request(self):
        paths = []

        def transport(host, ip, path, **kwargs):
            paths.append(path)
            return 200, {"content-type": "text/plain"}, b"User-agent: *\nDisallow: /private\n"

        with patch.object(gr, "public_addresses", return_value=["8.8.8.8"]):
            reader = gr.SafeReader(transport=transport, sleep=lambda _: None)
            with self.assertRaises(gr.ResearchError):
                reader.fetch("https://example.edu/private")
        self.assertEqual(paths, ["/robots.txt"])

    def test_redirect_robots_are_checked_before_target_page(self):
        calls = []

        def transport(host, ip, path, **kwargs):
            calls.append((host, path))
            if path == "/robots.txt":
                return (
                    200,
                    {"content-type": "text/plain"},
                    b"User-agent: *\n"
                    + (b"Disallow: /private\n" if host == "other.edu" else b"Allow: /\n"),
                )
            if host == "example.edu":
                return 302, {"location": "https://other.edu/private"}, b""
            return 200, {"content-type": "text/html"}, b"Private page should never be requested"

        with patch.object(gr, "public_addresses", return_value=["8.8.8.8"]):
            reader = gr.SafeReader(transport=transport, sleep=lambda _: None)
            with self.assertRaises(gr.ResearchError):
                reader.fetch("https://example.edu/source")
        self.assertNotIn(("other.edu", "/private"), calls)

    def test_binary_and_oversized_pages_are_rejected(self):
        for headers, body in [
            ({"content-type": "image/jpeg"}, b"jpeg"),
            ({"content-type": "text/html"}, b"x" * (gr.MAX_BYTES + 1)),
        ]:
            with (
                self.subTest(headers=headers),
                patch.object(gr, "public_addresses", return_value=["8.8.8.8"]),
            ):
                reader = gr.SafeReader(
                    transport=lambda *a, **k: (200, headers, body), sleep=lambda _: None
                )
                with self.assertRaises(gr.ResearchError):
                    reader.fetch("https://example.edu/x", robots=False)

    def test_public_search_reports_ignored_query_operators(self):
        rss = "<rss><channel><item><title>University homepage</title><link>https://example.edu/</link></item></channel></rss>"
        reader = type(
            "Reader",
            (),
            {"fetch": lambda *args, **kwargs: gr.Document("https://www.bing.com/search", rss)},
        )()
        with self.assertRaises(gr.ResearchError) as result:
            gr.PublicSearch(reader).search("site:chat.whatsapp.com Example University")
        self.assertEqual(result.exception.code, "provider_low_relevance")

    def test_optional_brave_provider_uses_key_only_in_request_header(self):
        calls = []

        def fetch(url, **kwargs):
            calls.append((url, kwargs))
            return gr.Document(
                url,
                '{"web":{"results":[{"url":"https://example.edu/welfare","title":"Example welfare","description":"A public society"}]}}',
                "application/json",
            )

        reader = type("Reader", (), {"fetch": staticmethod(fetch)})()
        result = gr.BraveSearch(reader, "test-provider-key").search("Example University WhatsApp")
        self.assertEqual(len(result), 1)
        self.assertNotIn("test-provider-key", calls[0][0])
        self.assertEqual(calls[0][1]["headers"]["X-Subscription-Token"], "test-provider-key")
        with self.assertRaises(gr.ResearchError):
            gr.BraveSearch(reader, "").search("Example")

    def test_trickling_response_has_total_deadline(self):
        class Response:
            status = 200

            def getheaders(self):
                return [("content-type", "text/html")]

            def read(self, count):
                return b"old implementation never checked elapsed time"

            def read1(self, count):
                return b"x"

        class Connection:
            sock = None

            def __init__(self, *args):
                pass

            def request(self, *args, **kwargs):
                pass

            def getresponse(self):
                return Response()

            def close(self):
                pass

        with (
            patch.object(gr, "PinnedHTTPS", Connection),
            patch.object(gr.time, "monotonic", side_effect=[0, 1, 16]),
        ):
            with self.assertRaises(gr.ResearchError) as result:
                gr.https_transport("example.edu", "8.8.8.8", "/")
        self.assertEqual(result.exception.code, "source_time_limit")


class FakeReader:
    def __init__(self):
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        return gr.Document(url, '<title>University welfare</title><a href="' + LINK + '">Join</a>')


class FakeSearch:
    name = "synthetic"

    def __init__(self):
        self.calls = []
        self.fail = False

    def search(self, query):
        self.calls.append(query)
        if self.fail:
            raise gr.ResearchError("provider_unavailable", "Search unavailable")
        return [
            {
                "url": "https://example.edu/welfare",
                "title": "Welfare group",
                "excerpt": "Members can post",
            }
        ]


class ResearchQueueTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.now = 1_800_000_000.0
        self.book = GroupBook(Path(self.folder.name), clock=lambda: self.now)
        self.uni = self.book.add_university("Example University", ["example.edu"])
        self.reader, self.search = FakeReader(), FakeSearch()
        self.service = gr.ResearchService(self.book, self.search, self.reader)

    def start(self, request_id="research-test-001", **kwargs):
        return self.service.start([self.uni["id"]], request_id, **kwargs)

    def test_start_is_idempotent_and_same_id_cannot_change_scope(self):
        job = self.start(max_queries=2)
        self.assertEqual(self.start(max_queries=2)["id"], job["id"])
        with self.assertRaises(Conflict):
            self.start(max_queries=3)
        self.assertEqual(len(self.book.repo.read()["jobs"]), 1)

    def test_job_discovers_sources_but_never_invents_permission(self):
        self.start(max_queries=2)
        done = self.service.run_once()
        self.assertEqual(done["state"], "completed")
        self.assertEqual(len(self.search.calls), 2)
        self.assertEqual(done["new_groups"], 1)
        row = self.book.list()["items"][0]
        self.assertEqual(row["checks"]["affiliation"]["value"], "verified")
        self.assertEqual(row["checks"]["posting"]["value"], "unknown")
        self.assertEqual(row["checks"]["charity"]["value"], "unknown")

    def test_provider_failure_is_not_reported_as_empty_success(self):
        self.search.fail = True
        self.start(max_queries=2)
        done = self.service.run_once()
        self.assertEqual(done["state"], "failed")
        self.assertEqual(done["queries_succeeded"], 0)
        self.assertTrue(done["errors"])

    def test_page_fetch_failure_preserves_partial_results(self):
        self.start(max_queries=2)
        with patch.object(
            self.reader,
            "fetch",
            side_effect=gr.ResearchError("robots_denied", "Source disallows reading"),
        ):
            done = self.service.run_once()
        self.assertEqual(done["state"], "partial")
        self.assertEqual(done["new_groups"], 0)

    def test_cancelled_queued_job_never_searches(self):
        job = self.start()
        self.service.cancel(job["id"])
        self.assertIsNone(self.service.run_once())
        self.assertEqual(self.search.calls, [])

    def test_live_claim_prevents_second_worker(self):
        self.start()
        first = self.service.claim()
        other = gr.ResearchService(self.book, self.search, self.reader)
        self.assertIsNone(other.claim())
        self.assertEqual(first["owner"], self.service.owner)

    def test_expired_worker_is_fenced_and_progress_survives_restart(self):
        job = self.start(max_queries=2)
        old = self.service.claim()
        self.now += gr.LEASE_SECONDS + 1
        other = gr.ResearchService(self.book, self.search, self.reader)
        taken = other.claim()
        self.assertEqual(taken["id"], job["id"])
        self.assertNotEqual(taken["owner"], old["owner"])
        with self.assertRaises(gr.LostLease):
            self.service.checkpoint(job["id"], {"phase": "old worker must not overwrite"})

    def test_scheduler_disabled_by_default_and_deduplicated(self):
        self.assertIsNone(self.service.tick())
        self.service.configure_schedule(True, 24, [self.uni["id"]])
        self.assertIsNotNone(self.service.tick())
        self.assertIsNone(self.service.tick())
        self.assertEqual(len(self.book.repo.read()["jobs"]), 1)

    def test_schedule_validation_and_global_query_budget(self):
        for hours in [0, 0.1, 169, True, float("nan")]:
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                self.service.configure_schedule(True, hours, [self.uni["id"]])
        for limit in [0, 21, True]:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.start(max_queries=limit)

    def test_unknown_announce_is_not_misread_as_members_can_post(self):
        for data in [{}, {"IsAnnounce": "false"}, {"GroupAnnounce": {"IsAnnounce": None}}]:
            self.assertEqual(gr.posting_from_group(data), "unknown")
        self.assertEqual(
            gr.posting_from_group({"GroupAnnounce": {"IsAnnounce": False}}), "all_members"
        )
        self.assertEqual(gr.posting_from_group({"IsAnnounce": True}), "admins_only")

    def test_cancel_during_last_fetch_is_cancelled_and_cannot_add_lead(self):
        job = self.start(max_queries=1)

        def fetch(url, **kwargs):
            self.service.cancel(job["id"])
            return gr.Document(url, '<a href="' + LINK + '">Join</a>')

        with patch.object(self.reader, "fetch", side_effect=fetch):
            done = self.service.run_once()
        self.assertEqual(done["state"], "cancelled")
        self.assertEqual(self.book.list()["counts"]["all"], 0)

    def test_interrupted_fetch_is_resumed_without_losing_reserved_page(self):
        self.start(max_queries=1, max_pages=1)
        with patch.object(
            self.reader, "fetch", side_effect=SystemExit("simulate process termination")
        ):
            with self.assertRaises(SystemExit):
                self.service.run_once()
        self.now += gr.LEASE_SECONDS + 1
        other = gr.ResearchService(self.book, self.search, self.reader)
        done = other.run_once()
        self.assertEqual(done["state"], "completed")
        self.assertEqual(done["pages_read"], 1)
        self.assertEqual(done["new_groups"], 1)
        self.assertEqual(len(self.search.calls), 1)

    def test_expired_worker_cannot_mutate_evidence_after_fetch(self):
        job = self.start(max_queries=1)
        replacement = gr.ResearchService(self.book, self.search, self.reader)

        def fetch(url, **kwargs):
            self.now += gr.LEASE_SECONDS + 1
            self.assertEqual(replacement.claim()["id"], job["id"])
            return gr.Document(url, '<a href="' + LINK + '">Join</a>')

        with patch.object(self.reader, "fetch", side_effect=fetch):
            self.service.run_once()
        self.assertEqual(self.book.list()["counts"]["all"], 0)


if __name__ == "__main__":
    unittest.main()
