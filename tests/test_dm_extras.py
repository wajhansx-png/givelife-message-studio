"""DM PDF and video: after each DM (poster + caption) the ticked ones follow, PDF then video. Stubbed transport."""

import base64, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import group_extras  # noqa: E402
import test_manual_sends as fixture  # noqa: E402
from test_manual_sends import app  # noqa: E402

OK = {"code": "SUCCESS"}
PDF = b"%PDF-1.4\n" + b"x" * 200
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200


def url(raw, mime):
    return "data:" + mime + ";base64," + base64.b64encode(raw).decode()


class Store(dict):
    def __bool__(self):
        return True

    def put(self, k, v):
        self[k] = v


class Batch(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        self.h = app.donors()
        self.h.jobs.import_jobs({"jobs": []})
        self.h.book._save({"version": 1, "records": []})

    tearDown = fixture.SendTests.tearDown

    def run_batch(self, replies=(), people=2, **options):
        h = self.h
        for i in range(people):
            h.book.add("Synthetic " + str(i), "92300123000" + str(i))
        calls, replies = [], list(replies)

        def send(body):
            calls.append((body["phone"][-1], body.get("kind"), body.get("extra")))
            return replies.pop(0) if replies else OK

        with patch.object(h.jobs, "connected", return_value=True):
            h.start_batch(scope="all", limit=people, run=False, **options)
            with (
                patch.object(h.jobs, "send", side_effect=send),
                patch.object(h.jobs, "_gap", return_value=0),
                patch.object(h.jobs.stop, "wait", new=lambda timeout=None: False),
            ):
                h.jobs._run(h.jobs._load()["jobs"][-1])
        return h.jobs.status(), calls

    def test_nothing_ticked_sends_only_the_dm(self):
        st, calls = self.run_batch()
        self.assertEqual([c[2] for c in calls], [None, None])
        self.assertEqual(st["sent"], 2)

    def test_both_ticked_video_then_pdf_after_each_dm(self):
        st, calls = self.run_batch(pdf=True, video=True)
        self.assertEqual(
            [(c[0], c[2]) for c in calls],
            [("0", None), ("0", "video"), ("0", "pdf"), ("1", None), ("1", "video"), ("1", "pdf")],
        )
        self.assertEqual(st["sent"], 2)  # the attachments are not counted as extra DMs
        self.assertTrue(all(c[1] == "dm_extra" for c in calls if c[2]))

    def test_only_one_ticked_sends_only_that_one(self):
        _, calls = self.run_batch(video=True)
        self.assertEqual([c[2] for c in calls], [None, "video", None, "video"])
        _, calls = self.run_batch(pdf=True)
        self.assertEqual([c[2] for c in calls][:2], [None, "pdf"])

    def test_a_video_that_is_not_confirmed_stops_the_pdf_and_the_batch_and_is_never_retried(self):
        st, calls = self.run_batch(replies=[OK, {"code": "UNCERTAIN"}], pdf=True, video=True)
        self.assertEqual([c[2] for c in calls], [None, "video"])  # no PDF, no second donor
        self.assertEqual(st["state"], "Stopped")
        self.assertIn("video was not confirmed", st["error"])

    def test_the_choice_is_part_of_the_job_and_can_be_changed_while_it_runs(self):
        self.h.book.add("Synthetic 0", "923001230000")
        with patch.object(self.h.jobs, "connected", return_value=True):
            self.h.start_batch(scope="all", limit=1, run=False, pdf=True)
        job = self.h.jobs._load()["jobs"][-1]
        self.assertTrue(job.get("pdf"))
        self.assertFalse(job.get("video"))
        self.h.jobs.configure(job["id"], {"video": True, "pdf": False})
        job = self.h.jobs._load()["jobs"][-1]
        self.assertTrue(job.get("video"))
        self.assertFalse(job.get("pdf"))
        with self.assertRaises(ValueError):
            self.h.jobs.configure(job["id"], {"pdf": "yes"})


class Sender(unittest.TestCase):
    def setUp(self):
        self.sent = []

        def fake(jid, caption, ident):
            self.sent.append((jid, caption, ident))
            return OK

        for p in (patch.object(app, "STORE", Store()), patch.object(app, "send_batch_attachment", fake)):
            p.start()
            self.addCleanup(p.stop)
        group_extras.add(app.STORE, "pdf", url(PDF, "application/pdf"), "r.pdf")
        group_extras.add(app.STORE, "video", url(MP4, "video/mp4"), "v.mp4")
        # The DM choice is independent of the group switch: switching the PDF off for groups does not stop DMs.
        group_extras.set_on(app.STORE, "pdf", False)

    def test_a_dm_extra_sends_the_saved_file_with_no_caption_even_if_off_for_groups(self):
        body = {"target": "phone", "phone": "923001234567", "kind": "dm_extra", "extra": "pdf", "message": ""}
        with patch.object(app, "check_hold", lambda: None), patch.object(app, "read_left", lambda: 20000):
            out = app.send_custom(body)
        self.assertEqual(out["code"], "SUCCESS")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][1], "")
        self.assertEqual(self.sent[0][2], group_extras.saved(app.STORE, "pdf"))

    def test_nothing_saved_a_group_target_and_a_finished_case_are_all_refused(self):
        app.STORE["group_extras"] = {}
        with self.assertRaises(ValueError):
            app.dm_extras_check(True, False)
        app.dm_extras_check(False, False)  # nothing ticked: fine
        with patch.object(app, "check_hold", lambda: None), patch.object(app, "read_left", lambda: 20000):
            with self.assertRaises(ValueError):
                app.send_custom({"target": "phone", "phone": "923001234567", "kind": "dm_extra", "extra": "video"})
        group_extras.add(app.STORE, "video", url(MP4, "video/mp4"), "v.mp4")
        with patch.object(app, "check_hold", lambda: None), patch.object(app, "read_left", lambda: 0):
            with self.assertRaises(ValueError):
                app.send_custom({"target": "phone", "phone": "923001234567", "kind": "dm_extra", "extra": "video"})
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
