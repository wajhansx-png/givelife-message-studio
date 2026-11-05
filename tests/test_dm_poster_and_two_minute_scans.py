"""Offline regressions for donor poster, greeting, and Auto scan cadence."""

import io, json, time, unittest
from unittest.mock import patch, Mock
import test_manual_sends as fixture
from test_manual_sends import app
import dm_composer, autopilot


class DMPosterAndGreeting(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_direct_poster_is_one_media_send_with_full_personalized_caption(self):
        text = app.get_message("dm")["text"]
        r = app.send_custom(
            {
                "target": "phone",
                "phone": "03001234567",
                "message": text,
                "poster": True,
                "kind": "dm_appeal",
                "name": "Ali",
                "gender": "Brother",
            }
        )
        self.assertEqual(r["code"], "SUCCESS")
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.sent[0]["text"].startswith("Ali Bhai, "))
        self.assertTrue(dm_composer.complete(self.sent[0]["text"]))

    def test_female_and_unknown_greeting_without_duplicate_salutation(self):
        body = app.get_message("dm")["text"]
        self.assertEqual(dm_composer.greeting("Ayesha Khan", "Sister"), "Ayesha Sister")
        self.assertEqual(dm_composer.greeting("Unknown", "Sister"), "Bhai")
        self.assertEqual(dm_composer.greeting("", "Sister"), "Bhai")
        original = dm_composer.personalize(body, "Ayesha", "Sister")
        self.assertEqual(dm_composer.personalize(original, "Ayesha", "Sister"), original)
        self.assertTrue(original.startswith("Ayesha Sister, "))

    def test_direct_text_only_checkbox_payload_sends_no_poster(self):
        body = app.get_message("dm")["text"]
        capture = []

        def fake_open(request, **kwargs):
            capture.append(json.loads(request.data))
            return io.BytesIO(
                json.dumps({"code": "SUCCESS", "results": {"message_id": "fake-text"}}).encode()
            )

        with patch.object(app.urllib.request, "urlopen", side_effect=fake_open):
            r = app.send_custom(
                {
                    "target": "phone",
                    "phone": "03001234567",
                    "message": body,
                    "poster": False,
                    "kind": "dm_appeal",
                    "name": "Ali",
                    "gender": "Brother",
                }
            )
        self.assertEqual(r["code"], "SUCCESS")
        self.assertEqual(len(capture), 1)
        self.assertTrue(capture[0]["message"].startswith("Ali Bhai, "))
        self.assertNotIn("attachment", capture[0])
        self.assertEqual(self.sent, [])

    def test_donor_batch_respects_poster_setting(self):
        donor = app.donors()
        donor.book.add("Ayesha", "03001234567")
        job = donor.start_batch(
            scope="all", gap_seconds=120, poster=False, run=False, request_id="test-no-poster-2026"
        )
        self.assertFalse(job["job"]["poster"])
        self.assertFalse(donor.jobs._load()["jobs"][-1]["poster"])

    def test_owner_written_donor_batch_still_has_personal_greeting(self):
        with patch.object(app, "send_image", return_value={"code": "SUCCESS"}) as send:
            result = app.send_custom(
                {
                    "target": "phone",
                    "phone": "03001234567",
                    "message": "Hello, thank you for volunteering.",
                    "poster": True,
                    "kind": "owner_text",
                    "name": "Sara",
                    "gender": "Sister",
                }
            )
        self.assertEqual(result["code"], "SUCCESS")
        self.assertTrue(send.call_args.args[1].startswith("Sara Sister, "))


class AutoScanCadence(unittest.TestCase):
    def test_auto_scans_group_donor_and_saved_chats_every_120_seconds(self):
        engine = autopilot.Engine.__new__(autopilot.Engine)
        timestamp = time.time()
        engine.s = {
            "day": autopilot.pkt().date().isoformat(),
            "left_seen": 25000,
            "last_money": timestamp,
            "started": timestamp,
            "l4_told": False,
            "wa_down_since": 0,
            "d1_done": False,
            "last_scan": 0,
            "last_dm_scan": 0,
            "last_chat_scan": 0,
        }
        engine.h = {"on_hold": lambda: False, "read_left": lambda: 25000, "wa_ok": lambda: True}
        engine.activity = None
        engine.worker_errors = {}
        engine.level = lambda: ("L1", 20, 30, 0)
        scans = {
            name: Mock() for name in ("scan_group_replies", "scan_dm_replies", "scan_saved_chats")
        }
        for name, fn in scans.items():
            setattr(engine, name, fn)
        for name in (
            "run_scheduled",
            "run_followups",
            "milestone_if_due",
            "update_if_due",
            "post_if_due",
            "share_if_due",
            "dm_if_due",
            "_owner_todo",
            "daily_report",
        ):
            setattr(engine, name, Mock())
        with patch.object(autopilot, "now", return_value=timestamp):
            engine.tick()
        self.assertTrue(all(fn.call_count == 1 for fn in scans.values()))
        with patch.object(autopilot, "now", return_value=timestamp + 119):
            engine.tick()
        self.assertTrue(all(fn.call_count == 1 for fn in scans.values()))
        with patch.object(autopilot, "now", return_value=timestamp + 120):
            engine.tick()
        self.assertTrue(all(fn.call_count == 2 for fn in scans.values()))


if __name__ == "__main__":
    unittest.main()
