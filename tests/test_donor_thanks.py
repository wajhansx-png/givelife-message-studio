import base64
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_media
from donor_book import DonorBook
from donor_thanks import DonorThanks
from persist import SqliteStore


class ThanksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = SqliteStore(root / "studio.sqlite")
        self.store.initialize()
        self.case, self.left, self.sent = "case-one", 0, []
        self.app = SimpleNamespace(
            DATA=root,
            ATT=root,
            STORE=self.store,
            read_left=lambda: self.left,
            on_hold=lambda: False,
            wa_ok=lambda: True,
            CAMPAIGN={},
            ENGINE=SimpleNamespace(dm_running=False),
            completed_case_appeal=lambda text: "donate now" in text,
            send_custom=lambda body: self.sent.append(body) or {"code": "SUCCESS"},
        )
        self.hub = SimpleNamespace(
            book=DonorBook(root, self.store),
            cases=SimpleNamespace(lock=threading.RLock(), _load=lambda: {"current": self.case}),
            jobs=SimpleNamespace(active=False),
            volunteers=SimpleNamespace(jobs=SimpleNamespace(active=False)),
            control_lock=threading.RLock(),
            eligible=lambda phone: True,
        )
        self.thanks = DonorThanks(self.app, self.hub)
        self.hub.thanks = self.thanks
        self.first = self.add("Sara", True)
        self.other = self.add("Other", False)
        self.asset = batch_media.save(
            self.store,
            "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nproof").decode(),
        )

    def add(self, name, donated):
        ident = self.hub.book.add(
            name, "1555123" + str(len(self.hub.book.recipients("all"))).zfill(4)
        )["donor"]["id"]
        self.hub.book.update(ident, donated=donated)
        return ident

    def save(self, **changes):
        data = self.thanks.view()
        return self.thanks.save(
            {
                k: changes.get(k, data[k])
                for k in ("case_id", "revision", "attachment", "filename", "caption", "message")
            }
        )

    def start(self):
        with patch("donor_thanks.threading.Thread"):
            self.thanks.start()

    def test_media_caption_is_one_send_and_separate_message_is_second(self):
        self.save(
            attachment=self.asset,
            caption="Alhamdulillah, case complete.",
            message="Thank you {name}.",
        )
        self.start()
        self.thanks.tick()
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[0]["attachment"], self.asset)
        self.assertEqual(self.sent[0]["message"], "Alhamdulillah, case complete.")
        self.assertIsNone(self.sent[1]["attachment"])
        self.assertEqual(self.sent[1]["message"], "Thank you Sara.")
        self.assertTrue(all(x["donor_id"] == self.first for x in self.sent))
        self.assertEqual(self.thanks.view()["sent"], 1)
        self.assertFalse(self.hub.book.resolve(self.first).get("dm_sent", False))

    def test_media_alone_has_an_empty_caption_and_text_alone_has_no_attachment(self):
        self.save(attachment=self.asset)
        self.start()
        self.thanks.tick()
        self.assertEqual(self.sent[0]["message"], "")
        self.assertEqual(len(self.sent), 1)
        self.case = "case-two"
        self.save(message="Thank you for your support.")
        self.start()
        self.thanks.tick()
        self.assertEqual(len(self.sent), 2)
        self.assertIsNone(self.sent[-1]["attachment"])

    def test_active_case_must_be_finished_and_no_fundraising_caption(self):
        self.save(message="Thank you.")
        self.left = 1000
        with self.assertRaisesRegex(ValueError, "Finish this case"):
            self.start()
        self.left = 0
        with self.assertRaisesRegex(ValueError, "fundraising"):
            self.save(message="donate now")
        with self.assertRaisesRegex(ValueError, "caption needs"):
            self.save(caption="Caption without media")
        self.assertEqual(self.sent, [])

    def test_receipts_survive_restart_and_case_isolation(self):
        self.save(message="Thank you.")
        self.start()
        self.thanks.tick()
        restored = DonorThanks(self.app, self.hub)
        with self.assertRaisesRegex(ValueError, "No donors are waiting"):
            restored.start()
        self.case = "case-two"
        self.assertEqual(restored.view()["sent"], 0)
        self.assertEqual(restored.view()["message"], "")
        self.case = "case-one"
        self.assertEqual(restored.view()["sent"], 1)
        self.assertEqual(len(self.sent), 1)

    def test_uncertain_media_is_not_repeated_and_separate_text_does_not_send(self):
        self.app.send_custom = lambda body: self.sent.append(body) or {"code": "UNCERTAIN"}
        self.save(attachment=self.asset, message="Thank you.")
        self.start()
        self.thanks.tick()
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(self.thanks.view()["on"])
        with self.assertRaisesRegex(ValueError, "No donors are waiting"):
            self.start()
        self.assertEqual(self.thanks.view()["recipients"][0]["state"], "Uncertain")

    def test_crash_after_claim_never_replays_the_started_part(self):
        self.save(message="Thank you.")
        self.start()
        self.store.claim("thanks_part_case-one_" + self.first + "_message", {"at": 1})
        self.thanks.tick()
        self.assertEqual(self.sent, [])
        self.assertEqual(self.thanks.view()["recipients"][0]["state"], "Uncertain")

    def test_pause_between_media_and_message_resumes_only_remaining_message(self):
        def send(body):
            self.sent.append(body)
            self.thanks.stop()
            return {"code": "SUCCESS"}

        self.app.send_custom = send
        self.save(attachment=self.asset, message="Thank you.")
        self.start()
        self.thanks.tick()
        self.assertEqual(len(self.sent), 1)
        self.app.send_custom = lambda body: self.sent.append(body) or {"code": "SUCCESS"}
        self.start()
        self.thanks.tick()
        self.assertEqual(len(self.sent), 2)
        self.assertIsNone(self.sent[-1]["attachment"])
        self.assertEqual(self.thanks.view()["sent"], 1)

    def test_default_pace_and_batch_rest_are_measured_after_recipient_finishes(self):
        for i in range(11):
            self.add("Donor " + str(i), True)
        self.save(message="Thank you.")
        self.start()
        for i in range(10):
            now = 10000 + i * 300
            with patch("donor_thanks.time.time", return_value=now):
                data = self.thanks._load()
                data["next_at"] = now
                self.thanks._put(data)
                self.thanks.tick(now)
            self.assertEqual(self.thanks._load()["next_at"], now + (1200 if i == 9 else 300))
        self.assertEqual(len(self.sent), 10)
        self.assertEqual(self.thanks._load()["batch_count"], 0)
        due = self.thanks._load()["next_at"]
        self.thanks.tick(due - 1)
        self.assertEqual(len(self.sent), 10)
        self.thanks.configure({"rest_minutes": 30})
        self.assertEqual(self.thanks._load()["next_at"], now + 1800)

    def test_changed_case_or_donation_status_cannot_receive_update(self):
        self.save(message="Thank you.")
        self.start()
        self.case = "case-two"
        self.thanks.tick()
        self.assertEqual(self.sent, [])
        self.case = "case-one"
        self.start()
        self.hub.book.update(self.first, donated=False)
        self.thanks.tick()
        self.assertEqual(self.sent, [])

    def test_other_queues_and_hold_prevent_sending_and_edits_are_revision_checked(self):
        self.save(message="Thank you.")
        self.hub.jobs.active = True
        with self.assertRaisesRegex(ValueError, "other DM queue"):
            self.start()
        self.hub.jobs.active = False
        self.start()
        self.app.on_hold = lambda: True
        self.thanks.tick()
        self.assertEqual(self.sent, [])
        with self.assertRaisesRegex(ValueError, "Pause"):
            self.save(message="An edit")
        self.thanks.stop()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.thanks.save({"case_id": "old", "revision": 0})

    def test_two_workers_cannot_dispatch_the_same_recipient(self):
        self.save(message="Thank you.")
        self.start()
        entered, release = threading.Event(), threading.Event()

        def send(body):
            self.sent.append(body)
            entered.set()
            release.wait(3)
            return {"code": "SUCCESS"}

        self.app.send_custom = send
        second = DonorThanks(self.app, self.hub)
        thread = threading.Thread(target=self.thanks.tick)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            second.tick()
            self.assertEqual(len(self.sent), 1)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.thanks.view()["sent"], 1)

    def test_settings_validation_and_missing_storage_do_not_send(self):
        for values in ([], {"batch_size": True}, {"batch_size": 2.5}, {"gap_minutes": 0}):
            with self.assertRaises(ValueError):
                self.thanks.configure(values)
        self.save(message="Thank you.")
        self.app.STORE = None
        self.assertFalse(self.thanks.active)
        with self.assertRaisesRegex(ValueError, "storage"):
            self.start()
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
