"""DM PDF and video: the selected video comes before the PDF. Stubbed transport."""

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

    def test_a_single_dm_also_sends_the_video_before_the_pdf(self):
        calls = []
        with (
            patch.object(self.h, "exclusion_reason", return_value=""),
            patch.object(app, "send_custom", side_effect=lambda body: calls.append(body["extra"]) or OK),
        ):
            self.assertEqual(self.h._single_extras({"phone": "923001230000"}, True, True), "Sent")
        self.assertEqual(calls, ["video", "pdf"])

    def test_a_long_attachment_uses_the_gap_and_edits_apply_to_the_next_chat(self):
        h = self.h
        for i in range(2):
            h.book.add(f"Synthetic {i}", f"92300123000{i}")
        with patch.object(h.jobs, "connected", return_value=True):
            h.start_batch(scope="all", limit=2, run=False, video=True, pdf=True)
            job = h.jobs._load()["jobs"][-1]
            stamp, calls = [job["created_at"]], []

            def send(body):
                calls.append((body["phone"][-1], body.get("extra")))
                if calls == [("0", None)]:
                    h.jobs.configure(job["id"], {"pdf": False})
                if body.get("extra") == "video":
                    stamp[0] += 20
                return OK

            with (
                patch.object(h.jobs, "send", side_effect=send),
                patch.object(h.jobs, "_gap", return_value=10),
                patch.object(h.jobs.stop, "wait") as wait,
                patch("donor_delivery.time.time", side_effect=lambda: stamp[0]),
            ):
                h.jobs._run(job)
            wait.assert_not_called()
        self.assertEqual(calls, [("0", None), ("0", "video"), ("0", "pdf"), ("1", None), ("1", "video")])

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


class SavedTicks(unittest.TestCase):
    """The DM PDF / video ticks are saved on the server, so a start that does not say (an Auto card, the chat's
    "send dms") sends the files that are ticked, the same as the screen, and the Test button does too."""

    def setUp(self):
        fixture.SendTests.setUp(self)
        self.h = app.donors()
        self.h.jobs.import_jobs({"jobs": []})
        self.h.book._save({"version": 1, "records": []})
        self.h.book.add("Synthetic 0", "923001230000")
        group_extras.add(app.STORE, "pdf", url(PDF, "application/pdf"), "r.pdf")
        group_extras.add(app.STORE, "video", url(MP4, "video/mp4"), "v.mp4")

    tearDown = fixture.SendTests.tearDown

    def start(self, scope="all", **body):
        with patch.object(self.h.jobs, "connected", return_value=True):
            self.h.start_batch(scope=scope, limit=1, run=False, **body)
        return self.h.jobs._load()["jobs"][-1]

    def tick(self, kind, on=True):
        group_extras.set_setup(app.STORE, "dm", kind, on)

    def test_a_start_that_does_not_say_sends_the_ticked_files(self):
        self.tick("pdf")
        self.tick("video")
        job = self.start()
        self.assertTrue(job.get("pdf"))
        self.assertTrue(job.get("video"))

    def test_only_the_ticked_one_goes(self):
        self.tick("pdf")
        job = self.start()
        self.assertTrue(job.get("pdf"))
        self.assertFalse(job.get("video"))

    def test_a_start_that_says_keeps_its_own_choice(self):
        self.tick("pdf")
        self.tick("video")
        job = self.start(pdf=False, video=False)
        self.assertFalse(job.get("pdf"))
        self.assertFalse(job.get("video"))

    def test_nothing_ticked_sends_no_file(self):
        job = self.start()
        self.assertFalse(job.get("pdf"))
        self.assertFalse(job.get("video"))

    def test_a_ticked_file_that_is_not_saved_is_left_out_not_an_error(self):
        self.tick("pdf")
        group_extras.remove(app.STORE, "pdf")
        job = self.start()
        self.assertFalse(job.get("pdf"))

    def test_a_list_with_its_own_text_keeps_no_file_unless_it_says(self):
        self.tick("pdf")
        ident = self.h.book.recipients("all")[0]["id"]
        job = self.start(scope="selected", ids=[ident], custom_template="Hello {name}")
        self.assertFalse(job.get("pdf"))

    def test_the_test_button_uses_what_the_screen_says_then_the_saved_ticks(self):
        self.tick("pdf")  # saved: PDF only
        self.assertEqual(app.dm_ticks(), {"pdf": True, "video": False})
        self.assertEqual(app.dm_ticks(video=True), {"pdf": True, "video": True})  # the screen says video too
        self.assertEqual(app.dm_ticks(pdf=False, video=False), {"pdf": False, "video": False})
