"""The case's PDF and video that follow the poster message in every group post. Fake gateway: nothing is ever sent."""

import base64, json, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import group_extras  # noqa: E402
import test_manual_sends  # noqa: E402,F401  (temporary data folder and import path)
from test_manual_sends import app  # noqa: E402

PDF = b"%PDF-1.4\n" + b"x" * 200
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200
GROUP = "120363431210327603@g.us"


def url(raw, mime):
    return "data:" + mime + ";base64," + base64.b64encode(raw).decode()


class Store(dict):
    def __bool__(self):  # an empty store is still a store
        return True

    def put(self, k, v):
        self[k] = v


class Rules(unittest.TestCase):
    def setUp(self):
        self.s = Store()

    def test_nothing_saved_means_nothing_is_sent(self):
        self.assertEqual(group_extras.to_send(self.s), [])
        v = group_extras.view(self.s)
        self.assertFalse(v["pdf"]["has"] or v["video"]["has"])

    def test_pdf_then_video_in_that_order_each_switched_on_when_added(self):
        group_extras.add(self.s, "video", url(MP4, "video/mp4"), "oxygen.mp4")
        group_extras.add(self.s, "pdf", url(PDF, "application/pdf"), "report.pdf")
        order = [k for k, _ in group_extras.to_send(self.s)]
        self.assertEqual(order, ["pdf", "video"])  # always the PDF first, then the video
        v = group_extras.view(self.s)
        self.assertEqual((v["pdf"]["name"], v["pdf"]["on"]), ("report.pdf", True))

    def test_each_can_be_deselected_without_being_removed(self):
        group_extras.add(self.s, "pdf", url(PDF, "application/pdf"))
        group_extras.add(self.s, "video", url(MP4, "video/mp4"))
        group_extras.set_on(self.s, "pdf", False)
        self.assertEqual([k for k, _ in group_extras.to_send(self.s)], ["video"])
        self.assertTrue(group_extras.view(self.s)["pdf"]["has"])  # still saved
        group_extras.set_on(self.s, "pdf", True)
        self.assertEqual([k for k, _ in group_extras.to_send(self.s)], ["pdf", "video"])

    def test_remove_and_replace(self):
        group_extras.add(self.s, "pdf", url(PDF, "application/pdf"), "a.pdf")
        group_extras.add(self.s, "pdf", url(PDF + b"y", "application/pdf"), "b.pdf")
        self.assertEqual(group_extras.view(self.s)["pdf"]["name"], "b.pdf")
        group_extras.remove(self.s, "pdf")
        self.assertFalse(group_extras.view(self.s)["pdf"]["has"])

    def test_wrong_files_are_refused_with_a_plain_reason(self):
        with self.assertRaises(ValueError):
            group_extras.add(self.s, "pdf", url(MP4, "video/mp4"))  # a video offered as the PDF
        with self.assertRaises(ValueError):
            group_extras.add(self.s, "video", url(PDF, "application/pdf"))
        with self.assertRaises(ValueError):
            group_extras.add(self.s, "pdf", url(b"not a pdf at all", "application/pdf"))  # contents do not match
        with self.assertRaises(ValueError):
            group_extras.add(self.s, "audio", url(PDF, "application/pdf"))
        with self.assertRaises(ValueError):
            group_extras.set_on(self.s, "pdf", True)  # nothing saved yet


class Sending(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.results = []

        def fake(jid, caption, ident):
            self.calls.append((jid, caption, ident))
            return self.results.pop(0) if self.results else {"code": "SUCCESS"}

        for p in (
            patch.object(app, "send_batch_attachment", fake),
            patch.object(app, "STORE", Store()),
        ):
            p.start()
            self.addCleanup(p.stop)
        group_extras.add(app.STORE, "pdf", url(PDF, "application/pdf"), "r.pdf")
        group_extras.add(app.STORE, "video", url(MP4, "video/mp4"), "v.mp4")
        self.pdf_id = group_extras.to_send(app.STORE)[0][1]
        self.video_id = group_extras.to_send(app.STORE)[1][1]

    def test_pdf_goes_first_then_the_video_with_no_caption(self):
        out = app.send_group_extras(GROUP)
        self.assertEqual([c[2] for c in self.calls], [self.pdf_id, self.video_id])
        self.assertTrue(all(c[0] == GROUP and c[1] == "" for c in self.calls))
        self.assertEqual([o["kind"] for o in out], ["pdf", "video"])

    def test_a_deselected_one_is_not_sent(self):
        group_extras.set_on(app.STORE, "pdf", False)
        app.send_group_extras(GROUP)
        self.assertEqual([c[2] for c in self.calls], [self.video_id])

    def test_a_pdf_that_is_not_confirmed_stops_the_video_and_is_never_retried(self):
        self.results = [{"code": "UNCERTAIN", "message": "not confirmed"}]
        out = app.send_group_extras(GROUP)
        self.assertEqual(len(self.calls), 1)  # the video did not follow, nothing was resent
        self.assertEqual(out[0]["code"], "UNCERTAIN")

    def test_a_failure_to_start_is_reported_as_skipped_not_raised(self):
        def boom(*a):
            raise ValueError("On hold: you told me to wait.")

        with patch.object(app, "send_batch_attachment", boom):
            out = app.send_group_extras(GROUP)
        self.assertEqual(out[0]["code"], "SKIPPED")

    def test_the_group_post_adds_them_after_the_poster_and_a_dm_does_not(self):
        ok = type("R", (), {"stdout": json.dumps({"code": "SUCCESS", "results": {"message_id": "m"}})})()
        statuses = {"is_connected": True, "is_logged_in": True}
        with patch.object(app, "api_result", lambda *a, **k: statuses), patch.object(
            app, "post_media", lambda *a, **k: ok
        ), patch.object(app, "poster_media", lambda *a, **k: Path(__file__)), patch.object(
            app, "record_delivery", lambda *a, **k: None
        ), patch.object(app, "check_stop", lambda: None), patch.object(app, "check_hold", lambda: None):
            group = app.send_image(GROUP, "caption")
            dm = app.send_image("923001234567@s.whatsapp.net", "caption")
        self.assertEqual(group.get("code"), "SUCCESS")
        self.assertEqual([e["kind"] for e in group["extras"]], ["pdf", "video"])
        self.assertNotIn("extras", dm)  # DMs never get them
        self.assertEqual(len(self.calls), 2)


    def test_an_auto_group_post_goes_the_same_way_poster_then_the_ticked_files(self):
        """Auto (every 45 minutes) posts through _group_attempt exactly like this; the ticked PDF and video follow."""
        ok = type("R", (), {"stdout": json.dumps({"code": "SUCCESS", "results": {"message_id": "m"}})})()
        statuses = {"is_connected": True, "is_logged_in": True}
        group_extras.set_on(app.STORE, "video", False)  # PDF only
        with patch.object(app, "api_result", lambda *a, **k: statuses), patch.object(
            app, "post_media", lambda *a, **k: ok
        ), patch.object(app, "poster_media", lambda *a, **k: Path(__file__)), patch.object(
            app, "record_delivery", lambda *a, **k: None
        ), patch.object(app, "check_stop", lambda: None), patch.object(app, "check_hold", lambda: None):
            auto = app._group_attempt({"with_picture": True, "manual": False}, GROUP, "caption")
        self.assertEqual(auto.get("code"), "SUCCESS")
        self.assertEqual([e["kind"] for e in auto["extras"]], ["pdf"])


class CaseOwnership(unittest.TestCase):
    def test_a_new_case_starts_with_no_pdf_or_video_and_the_old_case_keeps_its_own(self):
        store = app.STORE
        if store is None:
            self.skipTest("no private storage in this fixture")
        cases = app.donors().cases
        first = cases.view()["current"]
        group_extras.add(store, "pdf", url(PDF, "application/pdf"), "old.pdf")
        # Another test may have left a batch marked running; this test is about who owns the files, not batches.
        with patch.object(cases, "_busy", lambda: None):
            cases.new("Another child", 12000)
            self.assertEqual(group_extras.to_send(store), [])
            cases.switch(first)
        self.assertEqual(group_extras.view(store)["pdf"]["name"], "old.pdf")


if __name__ == "__main__":
    unittest.main()
