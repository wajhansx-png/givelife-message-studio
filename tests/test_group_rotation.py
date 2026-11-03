"""Group-tab rotation is shared by manual, Auto, direct, and test sends.

All tests run against synthetic data and fake transports. No real WhatsApp calls.
"""

import unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
from focus_bank import FocusBank, wording_key


class GroupRotationTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown
    wait = fixture.SendTests.wait

    def test_manual_and_auto_reuse_only_saved_versions(self):
        source = app.get_message("group")["text"]
        manual = app.start_send_job(["main"], "UNTRUSTED LEGACY MESSAGE", manual=True)
        self.wait(manual)
        self.assertEqual(app.JOBS[manual]["caption"], source)
        self.assertTrue(app.start_auto_group_job(["community"], "UNTRUSTED AUTO MESSAGE"))
        auto = app.LAST_JOB["id"]
        self.wait(auto)
        again = app.start_send_job(["main"], "DIFFERENT INPUT", manual=True)
        self.wait(again)
        self.assertEqual(len(self.sent), 3)
        delivered = [s["text"] for s in self.sent]
        self.assertEqual(len(set(delivered)), 3)
        self.assertTrue(
            all(t in app.STORE.get("focus_wording")["group"]["items"] for t in delivered)
        )
        self.assertFalse(any("UNTRUSTED" in t or "DIFFERENT INPUT" in t for t in delivered))

    def test_cycle_through_ten_then_restart_and_repeat_without_adjacent_duplicate(self):
        src = app.get_message("group")["text"]
        items = app.STORE.get("focus_wording")["group"]["items"]
        bank = app.focus_bank()
        first = bank.reserve_groups(src, 6)
        self.assertEqual(first, items[:6])
        restarted = FocusBank(app)
        second = restarted.reserve_groups(src, 4)
        self.assertEqual(second, items[6:])
        third = restarted.reserve_groups(src, 3)
        self.assertEqual(third, items[:3])
        self.assertEqual(len({wording_key(t) for t in first + second}), 10)
        self.assertNotEqual(second[-1], third[0])

    def test_multi_group_batch_uses_distinct_versions_and_persists_position(self):
        with patch.object(app.threading.Thread, "start"):
            job_id = app.start_send_job(["main", "community", "fiverr"], "any caption", manual=True)
        job = app.JOBS[job_id]
        self.assertEqual(len(set(job["captions"])), 3)
        with patch.object(app.JOB_CANCEL[job_id], "wait", return_value=False):
            app.run_job(job_id, job["keys"], job["caption"])
        self.assertEqual([x["text"] for x in self.sent], job["captions"])
        follow = app.focus_bank().reserve_groups(job["caption"], 1)
        self.assertNotIn(follow[0], job["captions"])

    def test_missing_ten_version_bank_auto_recovers_before_manual_send(self):
        app.STORE.put("focus_wording", {})
        with patch.object(app.threading.Thread, "start"):
            ident = app.start_send_job(["main"], "legacy template", manual=True)
        job = app.JOBS[ident]
        self.assertEqual(len(app.focus_bank().get("group")["items"]), 10)
        self.assertEqual(len(job["captions"]), 1)
        self.assertNotIn("legacy template", job["captions"][0])
        self.assertEqual(self.sent, [])
        self.assertIn(app.get_message("group")["text"], job["captions"][0])

    def test_uncertain_delivery_consumes_version_without_retrying_it(self):
        with patch.object(app, "send_image", return_value={"code": "UNCERTAIN"}):
            first = app.start_send_job(["main"], "anything", manual=True)
            self.wait(first)
        self.assertEqual(app.JOBS[first]["results"][0]["code"], "UNCERTAIN")
        second = app.start_send_job(["main"], "anything", manual=True)
        self.wait(second)
        self.assertEqual(self.sent[0]["text"], app.STORE.get("focus_wording")["group"]["items"][1])

    def test_direct_group_send_uses_same_rotation(self):
        jid = app.GROUPS["main"][1]
        with patch.object(
            app,
            "send_with_image",
            return_value={"code": "SUCCESS", "results": {"message_id": "fake"}},
        ) as wire:
            app.send_free(jid, "one-off text outside Group bank", False, literal=True)
            app.send_free(jid, "different one-off text", False, literal=True)
        sent = [c.args[1] for c in wire.call_args_list]
        self.assertEqual(len(set(sent)), 2)
        self.assertEqual(sent, app.STORE.get("focus_wording")["group"]["items"][:2])

    def test_custom_group_send_uses_shared_group_bank(self):
        body = {
            "target": "main",
            "message": "Unapproved one-off text",
            "poster": True,
            "kind": "owner_text",
        }
        result = app.send_custom(body)
        self.assertEqual(result["code"], "SUCCESS")
        self.assertEqual(self.sent[0]["text"], app.STORE.get("focus_wording")["group"]["items"][0])


if __name__ == "__main__":
    unittest.main()
