"""A Giki send goes through the Giki WhatsApp device and never the main one. Fake transport; nothing is sent."""

import json, sys, types, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_manual_sends as fixture
from test_manual_sends import app

MAIN = "main-device-id"
GIKI = "giki-0123456789ab"
BODY = {
    "target": "phone",
    "phone": "923001234567",
    "message": "Salam {name}",
    "kind": "volunteer_batch",
    "name": "Sara",
    "poster": False,
}


class Base(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self.main = patch.object(app, "DEVICE", MAIN)
        self.main.start()
        self.line = types.SimpleNamespace(device=lambda: GIKI, ready=lambda: True)
        self.lines = patch.dict(app.LINES, {"giki": self.line})
        self.lines.start()
        self.wire = []  # (device id, what)
        self.up = {MAIN: True, GIKI: True}
        self.paths = []

        def api(path):
            self.paths.append(path)
            device = path.split("/")[2] if path.startswith("/devices/") else ""
            ok = self.up.get(device, False)
            return {"results": {"is_connected": ok, "is_logged_in": ok}}

        self.api2 = patch.object(app, "api", api)
        self.api2.start()

        def urlopen(req, timeout=None):
            self.wire.append((req.headers.get("X-device-id"), json.loads(req.data)["message"]))
            return types.SimpleNamespace(
                __enter__=lambda s: s,
                __exit__=lambda *a: False,
                read=lambda: b"",
            )

        class Reply:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s):
                return json.dumps({"code": "SUCCESS", "results": {"message_id": "fake"}}).encode()

        self.url = patch.object(
            app.urllib.request,
            "urlopen",
            lambda req, timeout=None: (
                self.wire.append((req.headers.get("X-device-id"), json.loads(req.data)["message"]))
                or Reply()
            ),
        )
        self.url.start()

    def tearDown(self):
        for p in (self.url, self.api2, self.lines, self.main):
            p.stop()
        fixture.SendTests.tearDown(self)


class GikiServer(Base):
    def test_the_main_device_is_used_everywhere_outside_a_line(self):
        self.assertEqual(app.device(), MAIN)
        out = app.send_custom({**BODY, "kind": "owner_text", "message": "hello"})
        self.assertEqual(out["code"], "SUCCESS")
        self.assertEqual(self.wire, [(MAIN, "hello")])
        self.assertIn("/devices/" + MAIN + "/status", self.paths)

    def test_a_giki_send_with_no_name_leaves_it_out_and_the_main_list_still_says_friend(self):
        app.send_custom({**BODY, "line": "giki", "name": "", "message": "Salam {name}, share"})
        app.send_custom(
            {**BODY, "kind": "volunteer_batch", "name": "", "message": "Salam {name}, share"}
        )
        self.assertEqual([w[1] for w in self.wire], ["Salam, share", "Salam friend, share"])

    def test_a_giki_send_uses_the_giki_device_and_its_status_only(self):
        self.up[MAIN] = False  # the main WhatsApp being off must not stop a Giki send
        out = app.send_custom({**BODY, "line": "giki"})
        self.assertEqual(out["code"], "SUCCESS")
        self.assertEqual(self.wire, [(GIKI, "Salam Sara")])
        self.assertEqual(self.paths, ["/devices/" + GIKI + "/status"])

    def test_the_line_does_not_leak_into_the_next_main_send(self):
        app.send_custom({**BODY, "line": "giki"})
        self.assertEqual(app.device(), MAIN)
        app.send_custom({**BODY, "kind": "owner_text", "message": "after"})
        self.assertEqual(self.wire[-1], (MAIN, "after"))

    def test_a_disconnected_giki_whatsapp_sends_nothing_and_says_so(self):
        self.up[GIKI] = False
        with self.assertRaisesRegex(ValueError, "Giki WhatsApp is disconnected"):
            app.send_custom({**BODY, "line": "giki"})
        self.assertEqual(self.wire, [])

    def test_a_giki_line_with_no_device_never_falls_back_to_the_main_one(self):
        self.line.device = lambda: ""
        with self.assertRaises(ValueError):
            app.send_custom({**BODY, "line": "giki"})
        self.assertEqual(self.wire, [])
        self.assertNotIn("/devices/" + MAIN + "/status", self.paths)
        with app.on_line("giki"), self.assertRaises(ValueError):
            app.device()

    def test_an_unknown_line_is_refused(self):
        with self.assertRaises(ValueError):
            app.send_custom({**BODY, "line": "other"})
        self.assertEqual(self.wire, [])

    def test_each_whatsapp_has_its_own_daily_count(self):
        app.send_custom({**BODY, "line": "giki"})
        giki = app.STORE.get("dm_daily_giki")
        self.assertEqual(giki["count"], 1)
        self.assertIsNone(app.STORE.get("dm_daily"))
        app.send_custom({**BODY, "phone": "923001234568", "line": "giki", "first_in_batch": True})
        self.assertEqual(app.STORE.get("dm_daily_giki")["count"], 2)
        self.assertIsNone(app.STORE.get("dm_daily"))

    def test_line_ok_follows_the_line_not_the_main_whatsapp(self):
        app._LINE_WA.clear()
        self.line.ready = lambda: False
        self.assertFalse(app.line_ok("giki"))
        self.assertFalse(app.line_ok("nope"))

    def test_a_giki_extra_goes_through_the_giki_device(self):
        seen = []
        with (
            patch.object(
                app,
                "send_batch_attachment",
                side_effect=lambda *a: seen.append(app.device()) or {"code": "SUCCESS"},
            ),
            patch("group_extras.saved", return_value="a" * 32),
        ):
            app.send_custom(
                {
                    "target": "phone",
                    "phone": "923001234567",
                    "message": "",
                    "kind": "dm_extra",
                    "extra": "pdf",
                    "line": "giki",
                }
            )
        self.assertEqual(seen, [GIKI])

    def test_giki_dm_case_reads_the_group_message_with_todays_amount_at_the_click(self):
        h = app.donors()
        before = h.giki.case_text()
        self.assertIn("25,000", before)
        self.assertEqual(before, app.focus_bank().get("group")["source"])
        app.set_left(
            9000
        )  # the case moved on: the next click carries the new amount, like a group post
        after = h.giki.case_text()
        self.assertIn("9,000", after)
        self.assertNotIn("25,000", after)


class GikiTestPeople(Base):
    """Ahmad test and Zain test: the very same Giki DM, delivered in the GiveLife test group."""

    def record(self):
        calls = []

        def image(jid, caption, *a, **k):
            calls.append(("image", jid, caption, app._DM_TO_GROUP.get(), app.device()))
            return {"code": "SUCCESS"}

        def text(jid, message):
            calls.append(("text", jid, message, app._DM_TO_GROUP.get(), app.device()))
            return {"code": "SUCCESS"}

        def attach(jid, caption, ident):
            calls.append(("file", jid, ident, app._DM_TO_GROUP.get(), app.device()))
            return {"code": "SUCCESS"}

        self.stubs = [
            patch.object(app, "send_image", image),
            patch.object(app, "send_custom_text", text),
            patch.object(app, "send_batch_attachment", attach),
            patch("group_extras.saved", lambda store, kind: kind[0] * 32),
        ]
        for s in self.stubs:
            s.start()
        self.addCleanup(lambda: [s.stop() for s in self.stubs])
        return calls

    def test_a_test_person_gets_case_file_and_share_in_the_test_group_from_the_giki_whatsapp(self):
        calls = self.record()
        base = {"target": "phone", "phone": "999000000001", "line": "giki", "name": "Ahmad"}
        app.send_custom({**base, "message": "Case. Rs. 5,000 left.", "kind": "volunteer_batch", "poster": True})
        app.send_custom({**base, "kind": "dm_extra", "extra": "pdf"})
        app.send_custom({**base, "message": "Salam {name}, share.", "kind": "volunteer_batch", "poster": False})
        self.assertEqual([c[0] for c in calls], ["image", "file", "text"])
        self.assertEqual({c[1] for c in calls}, {app.TEST_GROUP_JID})  # all three in the test group
        self.assertTrue(all(c[3] for c in calls))  # sent as a DM (DM poster and DM rules), not as a group post
        self.assertEqual({c[4] for c in calls}, {GIKI})  # from the Giki WhatsApp
        self.assertEqual(calls[0][2], "Case. Rs. 5,000 left.")
        self.assertEqual(calls[2][2], "Salam Ahmad, share.")
        self.assertFalse(app._DM_TO_GROUP.get())  # nothing leaks to the next send

    def test_a_real_person_is_never_sent_to_the_test_group(self):
        calls = self.record()
        app.send_custom({**BODY, "line": "giki", "poster": False})
        self.assertEqual(calls[0][1], "923001234567")
        self.assertFalse(calls[0][3])

    def test_the_main_whatsapp_never_routes_a_test_number(self):
        calls = self.record()
        app.send_custom({**BODY, "phone": "999000000001", "poster": False})  # not a Giki send
        self.assertEqual([(c[1], c[3], c[4]) for c in calls], [("999000000001", False, MAIN)])

    def test_send_image_keeps_the_dm_rules_for_a_test_person(self):
        seen = {}

        def poster(use="group"):
            seen["poster"] = use
            return Path("poster.jpg")

        def lead(store, profile):
            seen["profile"] = profile
            return None

        stubs = [
            patch.object(app, "api_result", lambda path: {"is_connected": True, "is_logged_in": True}),
            patch.object(app, "poster_media", poster),
            patch.object(
                app,
                "post_media",
                lambda jid, cap, path: types.SimpleNamespace(
                    stdout=json.dumps({"code": "SUCCESS", "results": {"message_id": "m1"}})
                ),
            ),
            patch.object(app, "send_group_extras", lambda jid, items=None: seen.setdefault("group_files", jid) and []),
            patch("group_extras.lead", lead),
            patch("group_extras.after_items", lambda store, profile: []),
        ]
        for s in stubs:
            s.start()
        try:
            with app.on_line("giki"):
                token = app._DM_TO_GROUP.set(True)
                try:
                    result = app.send_image(app.TEST_GROUP_JID, "Case")
                finally:
                    app._DM_TO_GROUP.reset(token)
        finally:
            for s in stubs:
                s.stop()
        self.assertEqual(result["code"], "SUCCESS")
        self.assertEqual(seen["poster"], "dm")  # the DM poster, not the group one
        self.assertEqual(seen["profile"], "giki")  # the Giki DM choices, not the group ones
        self.assertNotIn("group_files", seen)  # no group files after it


class GikiChatCheck(Base):
    """The chat check behind self-healing: the newest message before a send, and whether one of the right type came
    after it. Read from the Giki WhatsApp; a test person's chat is the test group."""

    def rows(self, path):
        self.asked.append((path, app.device()))
        chat = path.split("/")[2]
        return {"results": {"data": self.chats.get(chat, [])}}

    def setUp(self):
        super().setUp()
        self.asked = []
        self.chats = {
            "923001234567%40s.whatsapp.net": [  # newest first, as the gateway lists them
                {"id": "M3", "is_from_me": True, "media_type": "document"},
                {"id": "M2", "is_from_me": True, "media_type": "image"},
                {"id": "M1", "is_from_me": True, "media_type": "image"},
            ],
            "120363431210327603%40g.us": [{"id": "T1", "is_from_me": True, "media_type": ""}],
        }
        self.api3 = patch.object(app, "api", self.rows)
        self.api3.start()
        self.addCleanup(self.api3.stop)

    def body(self, **k):
        return {"target": "phone", "phone": "923001234567", "line": "giki", **k}

    def test_newest_and_what_came_after_it(self):
        self.assertEqual(app.newest_sent(self.body()), "M3")
        self.assertEqual(app.sent_after(self.body(kind="dm_extra", extra="pdf"), "M2"), "M3")  # the PDF went
        self.assertEqual(app.sent_after(self.body(kind="dm_extra", extra="poster"), "M2"), "")  # no new image
        self.assertEqual(app.sent_after(self.body(poster=True), "M1"), "M2")  # a case (image) after M1
        self.assertEqual(app.sent_after(self.body(poster=False), "M3"), "")  # no text after M3
        self.assertIsNone(app.sent_after(self.body(), None))  # no mark: cannot tell
        self.assertEqual({d for _, d in self.asked}, {GIKI})  # always from the Giki WhatsApp

    def test_a_test_person_is_checked_in_the_test_group(self):
        body = {"target": "phone", "phone": "999000000001", "line": "giki"}
        self.assertEqual(app.newest_sent(body), "T1")
        self.assertTrue(self.asked[0][0].startswith("/chat/120363431210327603%40g.us/messages"))

    def test_a_chat_that_cannot_be_read_says_so(self):
        def broken(path):
            raise OSError("gateway restarting")

        with patch.object(app, "api", broken):
            self.assertIsNone(app.newest_sent(self.body()))
            self.assertIsNone(app.sent_after(self.body(), "M1"))


class GikiTestSend(Base):
    """The Test button: the whole DM to your own WhatsApp, from the Giki WhatsApp, in the right order."""

    def setUp(self):
        super().setUp()
        self.calls = []
        self.number = "923009998888"  # the number linked as the Giki WhatsApp
        self.line.status = lambda: {"state": "ready", "number": self.number}

        def rec(name):
            def f(jid, *args, **kwargs):
                self.calls.append((name, jid, args, app.device()))
                return {"code": "SUCCESS"}

            return f

        self.stubs = [
            patch.object(app, "send_image", rec("image")),
            patch.object(app, "send_custom_text", rec("text")),
            patch.object(app, "send_batch_attachment", rec("file")),
            patch("group_extras.saved", lambda store, kind: kind[0] * 32),
        ]
        for p in self.stubs:
            p.start()
        app._LINE_WA.clear()

    def tearDown(self):
        for p in self.stubs:
            p.stop()
        super().tearDown()

    def test_the_case_goes_first_then_the_files_that_are_on_then_the_share_message(self):
        out = app.send_giki_test("CASE TEXT", "Share it {name}", pdf=True, video=True)
        self.assertEqual(out["code"], "SUCCESS")
        self.assertEqual([c[0] for c in self.calls], ["image", "file", "file", "text"])
        self.assertTrue(all(c[3] == GIKI for c in self.calls))  # every part used the Giki device
        self.assertTrue(self.calls[0][2][0].startswith("\U0001f9ea TEST DM"))
        self.assertIn("CASE TEXT", self.calls[0][2][0])
        self.assertIn("Share it Test", self.calls[3][2][0])
        self.assertIn("TEST", self.calls[3][2][0])

    def test_nothing_extra_is_sent_when_pdf_and_video_are_off(self):
        app.send_giki_test("CASE", "Share", pdf=False, video=False)
        self.assertEqual([c[0] for c in self.calls], ["image", "text"])

    def test_it_goes_to_your_own_main_number_never_to_the_list(self):
        app.send_giki_test("CASE", "Share")
        self.assertEqual({c[1] for c in self.calls}, {app.norm_phone(app.OWNER_PHONE)})

    def test_if_the_giki_whatsapp_is_the_main_number_it_goes_to_the_test_number(self):
        self.number = app.norm_phone(app.OWNER_PHONE)
        app.send_giki_test("CASE", "Share")
        self.assertEqual({c[1] for c in self.calls}, {app.norm_phone(app.TEST_DM_PHONE)})

    def test_with_no_share_message_the_case_is_still_sent(self):
        out = app.send_giki_test("CASE", "", pdf=True)
        self.assertEqual([c[0] for c in self.calls], ["image", "file"])
        self.assertIn("only the case was sent", out["reply"])

    def test_with_no_case_the_share_message_is_still_sent_and_files_stay_home(self):
        out = app.send_giki_test("", "Share it", pdf=True, video=True)
        self.assertEqual([c[0] for c in self.calls], ["text"])  # the files belong to the case
        self.assertIn("only your share message was sent", out["reply"])
        self.assertIn("TEST", self.calls[0][2][0])

    def test_the_page_gets_an_answer_at_once_and_the_result_later(self):
        import threading

        gate = threading.Event()
        real = app.send_giki_test

        def slow(*a, **k):
            gate.wait(5)  # a big file uploading
            return real(*a, **k)

        app.GIKI_TEST.update(state="idle", note="", at=0.0)
        with patch.object(app, "send_giki_test", slow):
            out = app.start_giki_test("CASE", "Share")
            self.assertEqual(out["code"], "STARTED")
            self.assertEqual(app.GIKI_TEST["state"], "sending")
            with self.assertRaisesRegex(ValueError, "already sending"):
                app.start_giki_test("CASE", "Share")  # never two tests at once
            gate.set()
            for _ in range(200):
                if app.GIKI_TEST["state"] != "sending":
                    break
                __import__("time").sleep(0.02)
        self.assertEqual(app.GIKI_TEST["state"], "done")
        self.assertIn("Test sent", app.GIKI_TEST["note"])

    def test_a_failed_background_test_says_why(self):
        app.GIKI_TEST.update(state="idle", note="", at=0.0)
        with patch.object(app, "send_giki_test", side_effect=ValueError("Test not confirmed at the case: nope")):
            app.start_giki_test("CASE", "Share")
            for _ in range(200):
                if app.GIKI_TEST["state"] != "sending":
                    break
                __import__("time").sleep(0.02)
        self.assertEqual(app.GIKI_TEST["state"], "failed")
        self.assertIn("not confirmed", app.GIKI_TEST["note"])

    def test_a_busy_send_line_is_waited_for_but_not_forever(self):
        busy = type("L", (), {"acquire": lambda self, timeout=None: False, "release": lambda self: None})()
        with patch.object(app, "_send_lock", return_value=busy):
            with self.assertRaisesRegex(ValueError, "busy"):
                app.send_giki_test("CASE", "Share")
        self.assertEqual(self.calls, [])

    def test_with_both_missing_nothing_is_sent(self):
        with self.assertRaisesRegex(ValueError, "Nothing to test"):
            app.send_giki_test("  ", "")
        self.assertEqual(self.calls, [])

    def test_a_disconnected_giki_whatsapp_sends_nothing(self):
        self.line.ready = lambda: False
        with self.assertRaisesRegex(ValueError, "not connected"):
            app.send_giki_test("CASE", "Share")
        self.assertEqual(self.calls, [])

    def test_a_missing_file_is_refused_before_anything_is_sent(self):
        with patch("group_extras.saved", lambda store, kind: None):
            with self.assertRaisesRegex(ValueError, "No PDF is saved"):
                app.send_giki_test("CASE", "Share", pdf=True)
        self.assertEqual(self.calls, [])

    def test_a_case_that_is_not_confirmed_stops_the_test(self):
        with patch.object(app, "send_image", lambda *a: {"code": "ERROR", "message": "nope"}):
            with self.assertRaisesRegex(ValueError, "not confirmed at the case"):
                app.send_giki_test("CASE", "Share")
        self.assertEqual([c for c in self.calls if c[0] == "text"], [])


if __name__ == "__main__":
    unittest.main()
