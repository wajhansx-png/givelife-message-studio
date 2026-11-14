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

    def test_video_then_pdf_in_that_order_each_switched_on_when_added(self):
        group_extras.add(self.s, "video", url(MP4, "video/mp4"), "oxygen.mp4")
        group_extras.add(self.s, "pdf", url(PDF, "application/pdf"), "report.pdf")
        group_extras.set_text_on(self.s, "poster")  # the poster carries the text: both files follow it
        order = [k for k, _ in group_extras.to_send(self.s)]
        self.assertEqual(order, ["video", "pdf"])  # the video first, then the PDF
        v = group_extras.view(self.s)
        self.assertEqual((v["pdf"]["name"], v["pdf"]["on"]), ("report.pdf", True))

    def test_each_can_be_deselected_without_being_removed(self):
        group_extras.add(self.s, "pdf", url(PDF, "application/pdf"))
        group_extras.add(self.s, "video", url(MP4, "video/mp4"))
        group_extras.set_text_on(self.s, "poster")
        group_extras.set_on(self.s, "pdf", False)
        self.assertEqual([k for k, _ in group_extras.to_send(self.s)], ["video"])
        self.assertTrue(group_extras.view(self.s)["pdf"]["has"])  # still saved
        group_extras.set_on(self.s, "pdf", True)
        self.assertEqual([k for k, _ in group_extras.to_send(self.s)], ["video", "pdf"])

    def test_text_goes_with_the_video_by_default_and_the_setting_survives_changes(self):
        group_extras.add(self.s, "video", url(MP4, "video/mp4"))
        group_extras.add(self.s, "pdf", url(PDF, "application/pdf"))
        self.assertEqual(group_extras.view(self.s)["text_on"], "video")
        self.assertEqual(group_extras.lead(self.s), group_extras.saved(self.s, "video"))
        self.assertEqual([k for k, _ in group_extras.to_send(self.s)], ["pdf"])  # the video went first
        group_extras.set_text_on(self.s, "poster")
        group_extras.set_on(self.s, "pdf", False)  # a later change keeps the choice
        self.assertEqual(group_extras.view(self.s)["text_on"], "poster")
        self.assertIsNone(group_extras.lead(self.s))
        group_extras.set_text_on(self.s, "video")
        group_extras.set_on(self.s, "video", False)  # a switched-off video never carries the text
        self.assertIsNone(group_extras.lead(self.s))
        with self.assertRaises(ValueError):
            group_extras.set_text_on(self.s, "pdf")

    def test_groups_dms_and_giki_each_keep_their_own_choices_and_share_the_files(self):
        group_extras.add(self.s, "video", url(MP4, "video/mp4"))
        group_extras.add(self.s, "pdf", url(PDF, "application/pdf"))
        video = group_extras.saved(self.s, "video")
        group_extras.set_setup(self.s, "dm", "text_on", "poster")
        group_extras.set_setup(self.s, "giki", "poster", False)
        group_extras.set_setup(self.s, "giki", "pdf", True)
        self.assertEqual(group_extras.lead(self.s, "group"), video)  # groups: unchanged (text on the video)
        self.assertIsNone(group_extras.lead(self.s, "dm"))  # DMs: the poster carries the text
        self.assertEqual(group_extras.lead(self.s, "giki"), video)
        self.assertIsNone(group_extras.after_poster(self.s, "group"))  # no after poster added yet
        group_extras.add(self.s, "poster", url(b"\xff\xd8\xff" + b"0" * 200, "image/jpeg"), "after.jpg")
        after = group_extras.saved(self.s, "poster")
        self.assertEqual(group_extras.after_poster(self.s, "group"), after)  # groups: on when added
        self.assertIsNone(group_extras.after_poster(self.s, "giki"))  # Giki: only when ticked
        self.assertIsNone(group_extras.after_poster(self.s, "dm"))
        group_extras.set_setup(self.s, "dm", "poster", True)
        self.assertEqual(group_extras.after_poster(self.s, "dm"), after)
        # Giki's PDF goes as its 2nd / 3rd message, never again with the batch
        self.assertEqual(group_extras.extras_for(self.s, "giki"), {"pdf": False, "video": False})
        self.assertEqual([k for k, _ in group_extras.after_items(self.s, "giki")], ["pdf"])
        self.assertEqual(group_extras.extras_for(self.s, "dm"), {"pdf": False, "video": False})
        v = group_extras.view(self.s)["setup"]
        self.assertEqual((v["dm"]["text_on"], v["giki"]["poster"], v["giki"]["pdf"]), ("poster", False, True))
        group_extras.set_on(self.s, "pdf", False)  # a group switch never changes the others
        self.assertTrue(group_extras.view(self.s)["setup"]["giki"]["pdf"])
        group_extras.remove(self.s, "pdf")  # no file: nothing to send, the tick is kept for later
        self.assertEqual(group_extras.extras_for(self.s, "giki"), {"pdf": False, "video": False})
        with self.assertRaises(ValueError):
            group_extras.set_setup(self.s, "other", "pdf", True)
        with self.assertRaises(ValueError):
            group_extras.set_setup(self.s, "dm", "pdf", "yes")

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
        group_extras.set_text_on(app.STORE, "poster")  # these tests: the poster carries the text
        group_extras.set_setup(app.STORE, "dm", "text_on", "poster")
        self.pdf_id = group_extras.saved(app.STORE, "pdf")
        self.video_id = group_extras.saved(app.STORE, "video")

    def test_video_goes_first_then_the_pdf_with_no_caption(self):
        out = app.send_group_extras(GROUP)
        self.assertEqual([c[2] for c in self.calls], [self.video_id, self.pdf_id])
        self.assertTrue(all(c[0] == GROUP and c[1] == "" for c in self.calls))
        self.assertEqual([o["kind"] for o in out], ["video", "pdf"])

    def test_a_deselected_one_is_not_sent(self):
        group_extras.set_on(app.STORE, "pdf", False)
        app.send_group_extras(GROUP)
        self.assertEqual([c[2] for c in self.calls], [self.video_id])

    def test_a_video_that_is_not_confirmed_stops_the_pdf_and_is_never_retried(self):
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
        self.assertEqual([e["kind"] for e in group["extras"]], ["video", "pdf"])
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


    def test_the_after_poster_is_its_own_picture_sent_after_the_message_when_ticked(self):
        group_extras.set_text_on(app.STORE, "video")
        group_extras.set_setup(app.STORE, "dm", "text_on", "video")
        group_extras.add(app.STORE, "poster", url(b"\xff\xd8\xff" + b"1" * 200, "image/jpeg"), "after.jpg")
        after = group_extras.saved(app.STORE, "poster")
        media = []
        ok = type("R", (), {"stdout": json.dumps({"code": "SUCCESS", "results": {"message_id": "m"}})})()

        def post(jid, cap, path):
            media.append((jid, Path(cap).read_text(), str(path)))
            return ok

        statuses = {"is_connected": True, "is_logged_in": True}
        with patch.object(app, "api_result", lambda *a, **k: statuses), patch.object(
            app, "post_media", post
        ), patch.object(app, "poster_media", lambda *a, **k: Path("/x/poster.jpg")), patch.object(
            app, "record_delivery", lambda *a, **k: None
        ), patch.object(app, "check_stop", lambda: None), patch.object(app, "check_hold", lambda: None):
            group = app.send_image(GROUP, "the case text")
            dm_off = app.send_image("923001234567@s.whatsapp.net", "the case text")
            group_extras.set_setup(app.STORE, "dm", "poster", True)
            dm_on = app.send_image("923001234567@s.whatsapp.net", "the case text")
        # group: the video with the text, then the after poster, then the PDF; the main poster is not resent
        self.assertEqual(self.calls[0], (GROUP, "the case text", self.video_id))
        self.assertEqual([e["kind"] for e in group["extras"]], ["poster", "pdf"])
        self.assertEqual(self.calls[1], (GROUP, "", after))
        self.assertEqual(media, [])  # the main poster never goes twice
        # DM, poster not ticked: only the video with the text
        self.assertEqual(dm_off["code"], "SUCCESS")
        self.assertNotIn("after", dm_off)
        # DM, poster ticked: the video with the text, then the after poster
        self.assertEqual(self.calls[-2], ("923001234567@s.whatsapp.net", "the case text", self.video_id))
        self.assertEqual(self.calls[-1], ("923001234567@s.whatsapp.net", "", after))
        self.assertEqual(dm_on["after"], [{"kind": "poster", "code": "SUCCESS"}])

    def test_a_group_can_switch_the_after_poster_off(self):
        group_extras.add(app.STORE, "poster", url(b"\xff\xd8\xff" + b"2" * 200, "image/jpeg"), "after.jpg")
        group_extras.set_setup(app.STORE, "group", "poster", False)
        self.assertNotIn("poster", [k for k, _ in group_extras.to_send(app.STORE)])

    def test_giki_2nd_and_3rd_messages_follow_the_case_in_the_chosen_order_each_only_when_ticked(self):
        group_extras.set_setup(app.STORE, "giki", "text_on", "poster")
        group_extras.add(app.STORE, "poster", url(b"\xff\xd8\xff" + b"4" * 200, "image/jpeg"), "after.jpg")
        after = group_extras.saved(app.STORE, "poster")

        def run():
            self.calls.clear()
            ok = type("R", (), {"stdout": json.dumps({"code": "SUCCESS", "results": {"message_id": "m"}})})()
            statuses = {"is_connected": True, "is_logged_in": True}
            with app.on_line("giki"), patch.dict(app.LINES, {"giki": type("L", (), {"device": lambda s: "giki-x"})()}), patch.object(
                app, "api_result", lambda *a, **k: statuses
            ), patch.object(app, "post_media", lambda *a: ok), patch.object(
                app, "poster_media", lambda *a, **k: Path("/x/poster.jpg")
            ), patch.object(app, "record_delivery", lambda *a, **k: None), patch.object(
                app, "check_stop", lambda: None
            ), patch.object(app, "check_hold", lambda: None):
                r = app.send_image("923001234567@s.whatsapp.net", "case")
            return [c[2] for c in self.calls], r

        self.assertEqual(run()[0], [])  # nothing ticked: only the case
        group_extras.set_setup(app.STORE, "giki", "poster", True)
        group_extras.set_setup(app.STORE, "giki", "pdf", True)
        self.assertEqual(run()[0], [after, self.pdf_id])  # 2nd: poster pic, 3rd: PDF
        group_extras.set_setup(app.STORE, "giki", "order", "pdf_poster")
        sent, r = run()
        self.assertEqual(sent, [self.pdf_id, after])  # 2nd: PDF, 3rd: poster pic
        self.assertEqual([d["kind"] for d in r["after"]], ["pdf", "poster"])
        group_extras.set_setup(app.STORE, "giki", "poster", False)
        self.assertEqual(run()[0], [self.pdf_id])  # each tick on its own
        # Giki's PDF is never also sent by the batch (no double), and no video alone
        self.assertEqual(group_extras.extras_for(app.STORE, "giki"), {"pdf": False, "video": False})
        with self.assertRaises(ValueError):
            group_extras.set_setup(app.STORE, "giki", "order", "video_first")

    def test_giki_2nd_message_can_be_the_video_and_picking_the_other_rows_item_swaps_them(self):
        s = app.STORE
        self.assertEqual((group_extras.setup(s, "giki")["second"], group_extras.setup(s, "giki")["third"]), ("poster", "pdf"))
        group_extras.set_setup(s, "giki", "second", "video")
        self.assertEqual((group_extras.setup(s, "giki")["second"], group_extras.setup(s, "giki")["third"]), ("video", "pdf"))
        group_extras.set_setup(s, "giki", "third", "video")  # the 2nd had the video: they swap
        self.assertEqual((group_extras.setup(s, "giki")["second"], group_extras.setup(s, "giki")["third"]), ("pdf", "video"))
        group_extras.set_setup(s, "giki", "text_on", "poster")
        group_extras.set_setup(s, "giki", "video", True)
        group_extras.set_setup(s, "giki", "pdf", True)
        self.assertEqual([k for k, _ in group_extras.after_items(s, "giki")], ["pdf", "video"])
        group_extras.set_setup(s, "giki", "text_on", "video")  # the video already carried the case: not twice
        self.assertEqual([k for k, _ in group_extras.after_items(s, "giki")], ["pdf"])
        with self.assertRaises(ValueError):
            group_extras.set_setup(s, "giki", "second", "audio")
        with self.assertRaises(ValueError):
            group_extras.set_setup(s, "dm", "second", "pdf")

    def test_the_after_poster_must_be_a_picture(self):
        with self.assertRaises(ValueError):
            group_extras.add(app.STORE, "poster", url(PDF, "application/pdf"))
        with self.assertRaises(ValueError):
            group_extras.add(app.STORE, "poster", url(b"not a picture", "image/png"))
        group_extras.add(app.STORE, "poster", url(b"\x89PNG\r\n\x1a\n" + b"3" * 100, "image/png"), "p.png")
        self.assertTrue(group_extras.view(app.STORE)["poster"]["has"])

    def test_a_dm_whose_text_is_on_the_poster_sends_the_poster_with_the_text_while_groups_use_the_video(self):
        group_extras.set_text_on(app.STORE, "video")
        group_extras.set_setup(app.STORE, "dm", "text_on", "poster")
        media = []
        ok = type("R", (), {"stdout": json.dumps({"code": "SUCCESS", "results": {"message_id": "m"}})})()

        def post(jid, cap, path):
            media.append((jid, Path(cap).read_text()))
            return ok

        statuses = {"is_connected": True, "is_logged_in": True}
        with patch.object(app, "api_result", lambda *a, **k: statuses), patch.object(
            app, "post_media", post
        ), patch.object(app, "poster_media", lambda *a, **k: Path("/x/poster.jpg")), patch.object(
            app, "record_delivery", lambda *a, **k: None
        ), patch.object(app, "check_stop", lambda: None), patch.object(app, "check_hold", lambda: None):
            app.send_image("923001234567@s.whatsapp.net", "dm text")
            app.send_image(GROUP, "group text")
        self.assertEqual(media[0], ("923001234567@s.whatsapp.net", "dm text"))  # poster carries the DM text
        self.assertEqual(self.calls[0], (GROUP, "group text", self.video_id))  # video carries the group text

    def test_a_dm_ticked_video_is_not_sent_twice_when_it_carried_the_text(self):
        group_extras.set_text_on(app.STORE, "video")
        group_extras.set_setup(app.STORE, "dm", "text_on", "video")
        with patch.object(app, "read_left", lambda: 5000):
            r = app.send_dm_extra("923001234567", False, "video")
        self.assertEqual(r["code"], "SUCCESS")
        self.assertEqual(self.calls, [])


class PdfName(unittest.TestCase):
    def test_a_pdf_is_named_after_the_case(self):
        with patch.object(app, "active_case_name", lambda: "Mirha oxygen cylinders"):
            self.assertEqual(app.pdf_title(), "Mirha Medical Documents.pdf")
        with patch.object(app, "active_case_name", lambda: "Current case"):
            self.assertEqual(app.pdf_title(), "Medical Documents.pdf")
        store = Store()
        with patch.object(app, "STORE", store):
            group_extras.add(store, "pdf", url(PDF, "application/pdf"), "scan.pdf")
            args = []
            with patch.object(app, "active_case_name", lambda: "Mirha"), patch.object(
                app.subprocess,
                "run",
                lambda a, **k: args.append(a) or type("R", (), {"stdout": b'{"code":"SUCCESS"}'})(),
            ), patch.object(app, "check_stop", lambda: None), patch.object(app, "check_hold", lambda: None):
                r = app.send_batch_attachment("923001234567", "", group_extras.saved(store, "pdf"))
        self.assertEqual(r["code"], "SUCCESS")
        self.assertTrue(any("filename=Mirha Medical Documents.pdf" in x for x in args[0]))


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
