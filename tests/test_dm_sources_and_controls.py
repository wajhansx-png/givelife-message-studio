"""Where DMs come from, Test DM, Stop/Resume DMs, auto replies and the separate DM poster."""

import copy, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
import autopilot, reply_setup


class SourceAndControlTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_saving_a_group_message_never_replaces_the_20_donor_messages(self):
        hub = app.donors()
        before = [r["text"] for r in hub.messages.get()["items"]]
        self.assertEqual(len(before), 20)
        fb = app.focus_bank()
        with patch.object(fb, "start"):
            fb.save("group", app.get_message("group")["text"] + " EDITED")
        self.assertEqual([r["text"] for r in hub.messages.get()["items"]], before)

    def test_auto_dms_use_the_saved_donor_messages_not_built_in_templates(self):
        hub = app.donors()
        texts = [r["text"] for r in hub.messages.get()["items"]]
        sent = app.dm_text("Ali Donor", "member")
        self.assertTrue(sent.startswith("Ali Bhai, "))
        self.assertIn(
            sent.split(", ", 1)[1], [t.split(", ", 1)[1] if ", " in t else t for t in texts]
        )

    def test_a_short_bank_still_sends_what_is_saved(self):
        hub = app.donors()
        bank = hub.messages.get()
        bank["items"] = bank["items"][:1]
        with patch.object(hub.messages, "get", return_value=bank):
            self.assertEqual(hub.messages.reserve_one(), bank["items"][0]["text"])

    def test_main_screen_dm_rotates_through_its_own_saved_versions(self):
        fb = app.focus_bank()
        items = ["Brother, version %d. Rs. 5 left." % i for i in range(4)]
        app.save_draft("dm", items[0])
        app.STORE.put(
            "focus_wording",
            {"dm": {"source": items[0], "revision": "r1", "items": items, "state": "Ready"}},
        )
        got = [fb.next_dm_version() for _ in range(5)]
        self.assertEqual(got, items + [items[0]])

    def test_test_dm_goes_only_to_the_owner_and_uses_no_rotation(self):
        hub = app.donors()
        seen = []
        # test_dm now sends to TEST_DM_PHONE (not regular rotation); donor_single_rotation must stay untouched
        with (
            patch.object(app, "wa_ok", return_value=True),
            patch.object(app, "TEST_DM_PHONE", "923001112223"),
            patch.object(
                app,
                "send_image",
                side_effect=lambda j, t: seen.append((j, t)) or {"code": "SUCCESS"},
            ),
        ):
            out = hub.test_dm(True)
        self.assertEqual(out["code"], "SUCCESS")
        self.assertEqual(seen[0][0], "923001112223")
        self.assertTrue(seen[0][1].startswith("🧪 TEST DM"))
        self.assertIsNone(app.STORE.get("donor_single_rotation"))

    def test_stop_dms_then_stop_again_resumes_the_whole_automation(self):
        hub = app.donors()
        app.ENGINE.s["dm_enabled"] = True
        app.ENGINE.s["dm_daily"] = 25
        first = hub.toggle()
        self.assertTrue(first["paused"])
        self.assertTrue(hub.paused)
        self.assertFalse(app.ENGINE.s["dm_enabled"])
        second = hub.toggle()
        self.assertFalse(second["paused"])
        self.assertFalse(hub.paused)
        self.assertTrue(app.ENGINE.s["dm_enabled"])
        self.assertEqual(app.ENGINE.s["dm_daily"], 25)

    def test_poster_for_dms_is_separate_from_the_group_poster(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app, "DATA", Path(folder)):
            (Path(folder) / "poster.jpg").write_bytes(b"group")
            self.assertEqual(
                app.poster_media("dm").name, "poster.jpg"
            )  # no DM poster yet: shared one
            (Path(folder) / "dm-poster.jpg").write_bytes(b"dm")
            self.assertEqual(app.poster_media("dm").name, "dm-poster.jpg")
            self.assertEqual(app.poster_media("group").name, "poster.jpg")

    def test_poster_dialog_replaces_the_poster_for_groups_and_dms(self):
        import base64

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(app, "DATA", Path(folder)),
            patch.object(app, "STORE", None),
            patch.object(app, "CAMPAIGN", {}),
            patch.object(app, "ACTIVE", None),
            patch.object(app, "DONORS", None),
        ):
            (Path(folder) / "poster.jpg").write_bytes(b"\xff\xd8\xffold")
            (Path(folder) / "dm-poster.jpg").write_bytes(b"\xff\xd8\xffolddm")
            new = b"\xff\xd8\xffnew"
            self.assertEqual(
                app.save_upload(
                    "data:image/jpeg;base64," + base64.b64encode(new).decode(), "dm_poster"
                ),
                "poster",
            )
            self.assertEqual(app.poster_media("group").read_bytes(), new)
            self.assertEqual(app.poster_media("dm").read_bytes(), new)


class AutoReplyTests(unittest.TestCase):
    def engine(self, store, messages):
        e = autopilot.Engine.__new__(autopilot.Engine)
        e.s = {}
        e.log = lambda *a, **k: None
        sent = []
        e.h = {
            "reply_setup": lambda: reply_setup.get(store),
            "reply_take": lambda: reply_setup.take(store),
            "recent_chats": lambda: [("923001234567", "Ali")],
            "messages": lambda jid: messages,
            "send_text": lambda jid, text: sent.append((jid, text)),
            "on_hold": lambda: False,
        }
        return e, sent

    def store(self):
        class S:
            def __init__(self):
                self.d = {}

            def get(self, k, d=None):
                return copy.deepcopy(self.d.get(k, d))

            def put(self, k, v):
                self.d[k] = copy.deepcopy(v)

        return S()

    def test_validation_and_rotation(self):
        s = self.store()
        with self.assertRaises(ValueError):
            reply_setup.save(s, True, [])
        reply_setup.save(s, True, ["one", "two", "one", " "])
        self.assertEqual([reply_setup.take(s) for _ in range(3)], ["one", "two", "one"])

    def test_replies_once_to_done_or_picture_and_ignores_other_chat(self):
        s = self.store()
        reply_setup.save(s, True, ["Thank you", "JazakAllah"])
        s.d["reply_setup"]["since"] = 0
        msgs = [
            {"id": "a", "content": "done", "timestamp": "2026-11-03T10:00:00Z"},
            {"id": "b", "content": "hello", "timestamp": "2026-11-03T10:01:00Z"},
            {"id": "c", "content": "", "media_type": "image", "timestamp": "2026-11-03T10:02:00Z"},
        ]
        e, sent = self.engine(s, msgs)
        e.scan_reply_setup()
        e.scan_reply_setup()
        self.assertEqual(
            len(sent), 1
        )  # the second scan adds nothing; same person only once per 6 hours
        self.assertEqual(sent[0], ("923001234567@s.whatsapp.net", "Thank you"))

    def test_off_or_on_hold_sends_nothing(self):
        s = self.store()
        reply_setup.save(s, False, ["x"])
        e, sent = self.engine(
            s, [{"id": "a", "content": "done", "timestamp": "2026-11-03T10:00:00Z"}]
        )
        e.scan_reply_setup()
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
