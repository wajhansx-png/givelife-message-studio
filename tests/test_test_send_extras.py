"""The Test button (Message screen) must send what a real group post sends: the poster with the text, then the saved
PDF and video that are switched on. Stubbed transport: nothing real is sent."""

import base64, json, sys, threading, types, unittest, urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import group_extras  # noqa: E402
import test_manual_sends as fixture  # noqa: E402

app = fixture.app
PDF = b"%PDF-1.4\n" + b"x" * 200
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200
TEST_GROUP = "120363431210327603@g.us"


def url(raw, mime):
    return "data:" + mime + ";base64," + base64.b64encode(raw).decode()


class TestSendExtras(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def run_test_button(self, options=None, poster_ok=True):
        group_extras.add(app.STORE, "pdf", url(PDF, "application/pdf"), "r.pdf")
        group_extras.add(app.STORE, "video", url(MP4, "video/mp4"), "v.mp4")
        group_extras.set_text_on(app.STORE, "poster")
        files = []
        first = []

        def attach(jid, caption, ident):
            files.append((jid, caption, ident))
            return {"code": "SUCCESS"}

        def post_media(jid, cap, poster):
            first.append(jid)
            return types.SimpleNamespace(
                stdout=json.dumps({"code": "SUCCESS", "results": {}}).encode()
            )

        http = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with (
                patch.object(app.workflow(), "options", return_value=options),
                patch.object(app, "send_batch_attachment", attach),
                patch.object(app, "post_media", post_media),
                patch.object(app, "check_hold", lambda: None),
            ):
                req = urllib.request.Request(
                    "http://127.0.0.1:" + str(http.server_port) + "/test",
                    data=json.dumps(
                        {"message": "Hello\nRs. 25,000 LEFT", "stop_id": "stop-test-9999"}
                    ).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer test-only-studio-access-key",
                    },
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    return json.load(r), first, files
        finally:
            http.shutdown()
            http.server_close()

    def test_test_sends_the_poster_then_the_pdf_and_the_video_that_are_on(self):
        out, first, files = self.run_test_button()
        self.assertEqual(out["code"], "SUCCESS", out)
        self.assertEqual(first, [TEST_GROUP])
        kinds = [group_extras.saved(app.STORE, k) for k in ("video", "pdf")]
        self.assertEqual([f[2] for f in files], kinds)  # the video, then the PDF
        self.assertEqual([e["kind"] for e in out.get("extras", [])], ["video", "pdf"])

    def test_a_text_only_test_says_that_no_files_went(self):
        with patch.object(app, "send_text", return_value={"code": "SUCCESS"}):
            out, first, files = self.run_test_button(options={"poster": False})
        self.assertEqual(out["code"], "SUCCESS", out)
        self.assertEqual(files, [])
        self.assertFalse(out["files_ok"])
        self.assertIn("Text only", out["files_note"])

    def test_the_reply_names_every_file_that_went(self):
        out, _, _ = self.run_test_button()
        self.assertEqual(out["files_note"], "Video ✓, PDF ✓")
        self.assertTrue(out["files_ok"])

    def test_a_file_that_failed_is_named_with_the_reason(self):
        self.assertEqual(
            app.files_note(
                [
                    {"kind": "video", "code": "SUCCESS"},
                    {"kind": "pdf", "code": "SKIPPED", "message": "File is gone"},
                ]
            ),
            "Video ✓, PDF NOT sent: File is gone",
        )
        self.assertEqual(app.files_note([]), "")


class TestDmFiles(unittest.TestCase):
    """The donor DM Test sends the video and PDF that are ticked for DMs, after the test message."""

    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def run_dm_test(self, **ticks):
        group_extras.add(app.STORE, "pdf", url(PDF, "application/pdf"), "r.pdf")
        group_extras.add(app.STORE, "video", url(MP4, "video/mp4"), "v.mp4")
        group_extras.set_text_on(app.STORE, "poster")
        for kind, on in ticks.items():
            group_extras.set_setup(app.STORE, "dm", kind, on)
        order = []

        def attach(jid, caption, ident):
            order.append(("file", ident))
            return {"code": "SUCCESS"}

        def first(jid, text):
            order.append(("first", None))
            return {"code": "SUCCESS"}

        with (
            patch.object(app, "wa_ok", lambda: True),
            patch.object(app, "TEST_DM_PHONE", "923001234567"),
            patch.object(app, "send_image", first),
            patch.object(app, "send_batch_attachment", attach),
            patch.object(app, "check_hold", lambda: None),
        ):
            return app.send_dm_test("Hello", True), order

    def test_it_sends_the_ticked_video_then_pdf_after_the_message(self):
        out, order = self.run_dm_test(video=True, pdf=True)
        self.assertEqual(
            order,
            [
                ("first", None),
                ("file", group_extras.saved(app.STORE, "video")),
                ("file", group_extras.saved(app.STORE, "pdf")),
            ],
        )
        self.assertEqual(out["files_note"], "Video ✓, PDF ✓")
        self.assertIn("Video ✓, PDF ✓", out["reply"])

    def test_it_sends_only_what_is_ticked(self):
        out, order = self.run_dm_test(video=False, pdf=True)
        self.assertEqual(order, [("first", None), ("file", group_extras.saved(app.STORE, "pdf"))])
        self.assertEqual(out["files_note"], "PDF ✓")

    def test_nothing_ticked_sends_no_file(self):
        out, order = self.run_dm_test(video=False, pdf=False)
        self.assertEqual(order, [("first", None)])
        self.assertEqual(out["files_note"], "")

    def test_a_ticked_file_that_is_not_saved_is_reported_not_hidden(self):
        group_extras.remove(app.STORE, "pdf")
        group_extras.set_setup(app.STORE, "dm", "pdf", True)
        with (
            patch.object(app, "wa_ok", lambda: True),
            patch.object(app, "TEST_DM_PHONE", "923001234567"),
            patch.object(app, "send_image", lambda jid, text: {"code": "SUCCESS"}),
            patch.object(app, "check_hold", lambda: None),
        ):
            out = app.send_dm_test("Hello", True)
        self.assertFalse(out["files_ok"])
        self.assertIn("PDF NOT sent", out["files_note"])

    def test_files_can_be_left_out(self):
        group_extras.add(app.STORE, "pdf", url(PDF, "application/pdf"), "r.pdf")
        group_extras.set_setup(app.STORE, "dm", "pdf", True)
        with (
            patch.object(app, "wa_ok", lambda: True),
            patch.object(app, "TEST_DM_PHONE", "923001234567"),
            patch.object(app, "send_image", lambda jid, text: {"code": "SUCCESS"}),
            patch.object(app, "send_batch_attachment") as wire,
            patch.object(app, "check_hold", lambda: None),
        ):
            out = app.send_dm_test("Hello", True, files=False)
        wire.assert_not_called()
        self.assertEqual(out["files_note"], "")


if __name__ == "__main__":
    unittest.main()
