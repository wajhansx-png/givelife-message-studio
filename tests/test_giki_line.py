"""The Giki list and its own WhatsApp. Synthetic numbers only; nothing is ever sent (fake transport)."""

import os, sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wa_lines
from giki_line import Giki2Volunteers, GikiVolunteers, clean_name, first_name, parse_numbers
from volunteers import Volunteers

TABLE = """# Giki numbers
Sources: a note that is not a person +92 300 0000000 (6 Nov)

| # | Name | Number | Found on |
|---:|------|--------|----------|
| 1 | . Giki Donor 4 | +92 300 1111111 | +92 309 0000000 (7 Nov) |
| 2 | Ali Donor Giki | +92 300 2222222 | Business +92 320 0000000 (6 Nov) |
| 3 | Hassan 10k Afzal Giki | +974 5055 7391 | +92 309 0000000 (7 Nov) |
| 4 | 💫 Giki Donor 1000 | 0300 3333333 | x |
"""


class Store:
    def __init__(self):
        self.data = {}

    def get(self, k, d=None):
        return __import__("copy").deepcopy(self.data.get(k, d))

    def put(self, k, v):
        self.data[k] = __import__("copy").deepcopy(v)


class Fixture(unittest.TestCase):
    line_class = GikiVolunteers

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store()
        self.sent = []
        self.line_up = True
        self.main_up = False  # the main WhatsApp is off: a Giki batch must not care
        self.case = "Please help this family. Rs. 5,000 left."
        app = SimpleNamespace(
            DATA=Path(self.folder.name),
            STORE=self.store,
            OWNER_PHONE="923000000000",
            send_custom=self.send,
            wa_ok=lambda: self.main_up,
            line_ok=lambda name: self.line_up,
            on_hold=lambda: False,
            start_giki_test=self.fake_test,
            get_message=lambda kind: {"text": "draft text"},
            focus_bank=lambda: SimpleNamespace(get=lambda kind: {"source": self.case}),
        )
        self.g = self.line_class(app, lambda phone: True)
        self.main = Volunteers(app, lambda phone: True)
        self.tests = []
        self.patches = [
            patch.dict(os.environ, {"GIKI_SEED_FILE": ""}),
            patch("caption_facts.current", side_effect=lambda app, text: text),
            patch(
                "group_extras.extras_for",
                side_effect=lambda store, profile: {
                    "pdf": any(k == "pdf" for k, _ in self.on),
                    "video": any(k == "video" for k, _ in self.on),
                },
            ),
            # the Giki 2nd / 3rd messages, in the Timer's order
            patch("group_extras.after_items", side_effect=lambda store, profile: list(self.on)),
        ]
        self.on = []
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.folder.cleanup()

    def send(self, body):
        self.sent.append(body)
        if getattr(self, "on_send", None):
            self.on_send(body)
        return {"code": "SUCCESS"}

    def fake_test(self, case, share, pdf=False, video=False, line="giki"):
        self.tests.append((case, share, pdf, video))
        return {"code": "SUCCESS", "reply": "Test sent."}

    def go(self, vols, body):
        with patch.object(vols.jobs, "_run"):
            return vols.mutate(body)

    def run_job(self, jobs):
        job = jobs._load()["jobs"][-1]
        clock = [time.time()]

        def wait(seconds):
            clock[0] += seconds
            return False

        with (
            patch("donor_delivery.time.time", side_effect=lambda: clock[0]),
            patch.object(jobs.stop, "wait", side_effect=wait),
        ):
            jobs._run(job)
        return jobs._load()["jobs"][-1]


class GikiList(Fixture):
    def test_the_list_message_and_batches_are_separate_from_volunteers(self):
        self.main.mutate({"action": "add", "name": "Main One", "phone": "0300 1000001"})
        self.g.mutate({"action": "add", "name": "Giki One", "phone": "0300 2000002"})
        self.g.mutate({"action": "message", "text": "Giki text {name}"})
        self.assertEqual([x["name"] for x in self.main.view()["items"]], ["Main One"])
        self.assertEqual([x["name"] for x in self.g.view()["items"]], ["Giki One"])
        self.assertEqual(self.main.view()["message"], "")
        self.assertEqual(self.g.view()["message"], "Giki text {name}")
        self.assertIn("giki_book", self.store.data)
        self.assertIn("volunteer_book", self.store.data)

    def test_dm_all_sends_the_case_first_then_the_share_message_on_the_giki_line(self):
        self.g.mutate({"action": "add", "name": "Sara Giki", "phone": "0300 2000002"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})
        self.g.mutate({"action": "pace", "gap_minutes": 3, "batch_size": 4, "rest_minutes": 7})
        r = self.go(self.g, {"action": "send_all", "request_id": "r1", "poster": False})
        job = self.g.jobs._load()["jobs"][-1]
        self.assertEqual((job["gap_seconds"], job["chunk"], job["rests"]), (180, 4, [420.0]))
        self.assertEqual(job["follow_up"], "Salam {name}, please share this.")
        self.run_job(self.g.jobs)
        self.assertEqual(len(self.sent), 2)
        case, share = self.sent
        self.assertEqual(
            (case["message"], case["poster"]), (self.case, True)
        )  # the Group msgs text with the poster
        self.assertEqual(
            share["message"], "Salam Sara Sister, please share this."
        )  # then the share message
        self.assertIs(share["poster"], False)
        self.assertTrue(
            all(b["line"] == "giki" and b["kind"] == "volunteer_batch" for b in self.sent)
        )
        self.assertIn("case first", r["reply"])

    def test_dm_case_sends_one_person_the_case_then_the_share_message(self):
        self.g.mutate({"action": "add", "name": "Sara Giki", "phone": "0300 2000002"})
        self.g.mutate({"action": "add", "name": "Ali Giki", "phone": "0300 2000003"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})
        sara = next(x["id"] for x in self.g.view()["items"] if x["name"] == "Sara Giki")
        self.go(self.g, {"action": "send_case", "id": sara, "request_id": "c1", "poster": True})
        self.run_job(self.g.jobs)
        self.assertEqual(len(self.sent), 2)  # only Sara
        case, share = self.sent
        self.assertEqual((case["message"], case["poster"]), (self.case, True))
        self.assertEqual(share["message"], "Salam Sara Sister, please share this.")
        self.assertIs(share["poster"], False)

    def test_dm_case_with_no_share_message_still_sends_the_case(self):
        self.g.mutate({"action": "add", "name": "Sara Giki", "phone": "0300 2000002"})
        sara = self.g.view()["items"][0]["id"]
        self.go(self.g, {"action": "send_case", "id": sara, "request_id": "c2", "poster": True})
        self.run_job(self.g.jobs)
        self.assertEqual([(s["message"], s["poster"]) for s in self.sent], [(self.case, True)])

    def _stopped_after_first(self):
        for i in range(3):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 200000{i}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})

        def stop_after_first(body):
            out = self.send(body)
            if len(self.sent) == 2:  # the first person's case and share message went
                self.g.jobs.stop.set()
            return out

        self.g.jobs.send = stop_after_first
        self.go(self.g, {"action": "send_all", "request_id": "r-stop", "poster": False})
        job = self.run_job(self.g.jobs)
        self.assertEqual((job["state"], job["sent"]), ("Stopped", 1))
        self.g.jobs.stop.clear()
        self.g.jobs.send = self.send

    def test_stop_then_resume_goes_on_with_only_the_people_still_waiting(self):
        self._stopped_after_first()
        self.assertEqual(self.g.view()["resumable"], 2)
        self.case = "Today's case. Rs. 900 left."  # Resume sends today's case, not the one saved at the start
        with patch.object(self.g.jobs, "_run"):
            self.g.mutate({"action": "resume"})
        job = self.run_job(self.g.jobs)
        self.assertEqual((job["state"], job["sent"]), ("Completed", 2))
        self.assertEqual([s["message"] for s in self.sent[2::2]], [self.case, self.case])
        phones = [s["phone"] for s in self.sent]
        self.assertEqual(len(phones), 6)
        self.assertEqual(len(set(phones)), 3)  # each person once: case + share, nobody twice
        self.assertEqual(self.g.view()["resumable"], 0)
        with self.assertRaisesRegex(ValueError, "Nothing to resume"):
            self.g.mutate({"action": "resume"})

    def test_stop_right_after_a_case_still_sends_that_persons_share_message(self):
        for i in range(3):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 200000{i}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})

        def stop_after_case(body):
            out = self.send(body)
            if len(self.sent) == 1:  # Stop pressed the moment the first case went
                self.g.jobs.stop.set()
            return out

        self.g.jobs.send = stop_after_case
        self.go(self.g, {"action": "send_all", "request_id": "r-cut", "poster": False})
        job = self.run_job(self.g.jobs)
        self.assertEqual((job["state"], job["sent"]), ("Stopped", 1))
        self.assertEqual(len(self.sent), 2)  # the case AND its share message; nobody else started
        self.assertEqual(self.sent[1]["message"], "Salam, please share this.")
        self.assertEqual(job["receipts"][0]["follow_up"], "Sent")

    def test_resume_sends_the_share_message_to_someone_an_old_stop_cut_off(self):
        self._stopped_after_first()
        jobs = self.g.jobs._load()
        first = jobs["jobs"][-1]["receipts"][0]
        first["follow_up"] = (
            "Cancelled"  # how the old code left a person: case sent, share cut by Stop
        )
        self.g.jobs._save(jobs)
        self.g.book.follow_up(first["id"], "Cancelled")
        self.sent.clear()
        self.assertEqual(self.g.view()["resumable"], 3)  # 2 still waiting + 1 share to finish
        with patch.object(self.g.jobs, "_run"):
            self.g.mutate({"action": "resume"})
        self.assertEqual(len(self.sent), 1)  # the share message only, no second case
        self.assertIs(self.sent[0]["poster"], False)
        self.assertIn("please share this", self.sent[0]["message"])
        self.assertEqual(self.g.book.resolve(first["id"])["follow_up_state"], "Sent")
        job = self.run_job(self.g.jobs)
        self.assertEqual((job["state"], job["sent"]), ("Completed", 2))
        self.assertEqual(len(self.sent), 5)  # + case and share for the 2 still waiting
        self.assertEqual(self.g.view()["resumable"], 0)

    def test_a_restart_in_the_middle_of_a_person_sends_only_what_they_are_missing(self):
        self.on = [("video", "b" * 32), ("pdf", "a" * 32)]  # 2nd: video, 3rd: PDF
        for i in range(2):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 200000{i}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})
        self.go(self.g, {"action": "send_all", "request_id": "r-mid", "poster": False})
        self.run_job(self.g.jobs)
        self.assertEqual(len(self.sent), 8)  # 2 people x (case, video, PDF, share)
        # as a restart leaves it: person 0 got the case and the video was being uploaded; person 1 only the case
        jobs = self.g.jobs._load()
        j = jobs["jobs"][-1]
        j.update(state="Interrupted", boot="an-older-boot")
        j["receipts"][0].update(steps={"video": "Sent"}, follow_up=None)
        j["receipts"][1].update(steps={}, follow_up=None)
        self.g.jobs._save(jobs)
        for receipt in j["receipts"]:
            self.g.book.follow_up(receipt["id"], None)  # the share never went
        self.sent.clear()
        self.assertEqual(len(self.g.jobs.half_sent()), 2)
        self.assertEqual(self.g.jobs.finish_half_sent(), 2)
        got = [
            (b["phone"][-1], b.get("extra") or ("share" if not b["poster"] else "case"))
            for b in self.sent
        ]
        # person 0: the video was confirmed; only the PDF and the share go
        # person 1: the video, the PDF, then the share; nobody gets the case twice
        self.assertEqual(
            got, [("0", "pdf"), ("0", "share"), ("1", "video"), ("1", "pdf"), ("1", "share")]
        )
        self.assertEqual(self.g.jobs.half_sent(), [])  # done: nothing is sent a second time
        self.assertEqual(self.g.jobs.finish_half_sent(), 0)

    def test_a_share_already_sent_by_an_earlier_resume_is_never_sent_again(self):
        self._stopped_after_first()
        jobs = self.g.jobs._load()
        first = jobs["jobs"][-1]["receipts"][0]
        first["follow_up"] = "Cancelled"  # the old record says cut...
        self.g.jobs._save(jobs)
        self.g.book.follow_up(
            first["id"], "Sent"
        )  # ...but an earlier Resume already sent the share
        self.sent.clear()
        self.assertEqual(self.g.jobs.half_sent(), [])
        self.assertEqual(self.g.jobs.finish_half_sent(), 0)
        self.assertEqual(self.sent, [])

    def test_an_older_record_without_steps_is_never_sent_again(self):
        self._stopped_after_first()
        jobs = self.g.jobs._load()
        first = jobs["jobs"][-1]["receipts"][0]
        first.pop("seq")  # written by the code before steps were recorded
        first["follow_up"] = None
        self.g.jobs._save(jobs)
        self.g.book.follow_up(first["id"], "Cancelled")
        self.sent.clear()
        self.assertEqual(self.g.jobs.finish_half_sent(), 0)
        self.assertEqual(self.sent, [])

    def test_resume_and_the_restart_repair_at_the_same_time_send_once(self):
        import threading

        self._stopped_after_first()
        jobs = self.g.jobs._load()
        jobs["jobs"][-1]["receipts"][0]["follow_up"] = None  # the share is missing
        self.g.jobs._save(jobs)
        self.g.book.follow_up(jobs["jobs"][-1]["receipts"][0]["id"], None)
        self.sent.clear()
        go = threading.Barrier(2)

        def repair():
            go.wait()
            self.g.jobs.finish_half_sent()

        threads = [threading.Thread(target=repair) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.sent), 1)  # the share message once, never twice

    def test_the_two_test_people_come_first_in_the_list_and_in_dm_all(self):
        for name, phone in (("Aaliya Giki", "0300 2000001"), ("Bilal Giki", "0300 2000002")):
            self.g.mutate({"action": "add", "name": name, "phone": phone})
        from giki_line import SEED

        with patch.object(self.g, "seed_path", lambda: SEED):
            self.g.add_test_people()
            self.g.add_test_people()  # once only
        names = [x["name"] for x in self.g.view()["items"]]
        self.assertEqual(names, ["Ahmad test", "Zain test", "Aaliya Giki", "Bilal Giki"])
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})
        self.go(self.g, {"action": "send_all", "request_id": "r-test-people", "poster": False})
        self.run_job(self.g.jobs)
        got = [(s["phone"], s["message"]) for s in self.sent if not s["poster"]]
        self.assertEqual(
            got,
            [
                (
                    "999000000001",
                    "Salam Ahmad Bhai, please share this.",
                ),  # to the test group (server side)
                ("999000000002", "Salam Zain Bhai, please share this."),
                (
                    "923002000001",
                    "Salam Aaliya, please share this.",
                ),  # not a known name: no Bhai / Sister
                ("923002000002", "Salam Bilal Bhai, please share this."),
            ],
        )
        self.assertTrue(
            all(s["line"] == "giki" for s in self.sent)
        )  # the server routes the test numbers

    def test_a_removed_test_person_stays_removed(self):
        from giki_line import SEED

        with patch.object(self.g, "seed_path", lambda: SEED):
            self.g.add_test_people()
        ahmad = next(x for x in self.g.view()["items"] if x["name"] == "Ahmad test")
        self.g.mutate({"action": "delete", "id": ahmad["id"]})
        with patch.object(self.g, "seed_path", lambda: SEED):
            self.g.add_test_people()
        self.assertEqual([x["name"] for x in self.g.view()["items"]], ["Zain test"])

    def test_a_restart_carries_on_a_giki_batch_by_itself(self):
        self._stopped_after_first()
        jobs = self.g.jobs._load()
        jobs["jobs"][-1].update(state="Interrupted", boot="an-older-boot")  # cut by a deploy
        self.g.jobs._save(jobs)
        with patch.object(self.g.jobs, "_run"):
            self.assertTrue(self.g.jobs.recover())  # what the server runs after every restart
        job = self.run_job(self.g.jobs)
        self.assertEqual((job["state"], job["sent"]), ("Completed", 2))
        self.assertEqual(len(self.sent), 6)
        self.assertEqual(job["follow_up"], "Salam {name}, please share this.")

    def _restart_after_the_last_person(self, share_state="Sent"):
        for i in range(2):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 200000{i}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})
        self.go(self.g, {"action": "send_all", "request_id": "r-end", "poster": False})
        self.run_job(self.g.jobs)
        jobs = self.g.jobs._load()
        j = jobs["jobs"][-1]
        j["receipts"][-1]["follow_up"] = share_state
        self.g.jobs.book.follow_up(j["receipts"][-1]["id"], share_state)
        j.update(state="Interrupted", auto=True, boot="an-older-boot",
                 error="The service restarted. Starting again by itself; nobody already sent is repeated.")
        self.g.jobs._save(jobs)
        return self.g.jobs.status()

    def test_a_restart_after_the_last_person_never_says_it_starts_again(self):
        out = self._restart_after_the_last_person()
        self.assertEqual((out["state"], out["error"]), ("Completed", ""))

    def test_a_restart_after_the_last_person_names_who_still_misses_a_message(self):
        out = self._restart_after_the_last_person(share_state="Not sent")
        self.assertEqual(out["state"], "Interrupted")
        self.assertIn("1 of them did not get all their messages", out["error"])
        self.assertNotIn("Starting again", out["error"])

    def test_a_short_giki_whatsapp_drop_is_waited_out_and_the_batch_goes_on(self):
        for i in range(3):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 200000{i}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})
        drops = [2]  # the case and the share message of the first person each meet one drop

        def flaky(body):
            if drops[0] and len(self.sent) in (0, 1):
                drops[0] -= 1
                raise ValueError("The Giki WhatsApp is disconnected. Tap Connect WhatsApp.")
            return self.send(body)

        self.g.jobs.send = flaky
        self.go(self.g, {"action": "send_all", "request_id": "r-drop", "poster": False})
        job = self.run_job(self.g.jobs)
        self.assertEqual((job["state"], job.get("error", "")), ("Completed", ""))
        self.assertEqual(len(self.sent), 6)  # 3 people x (case + share), nobody twice

    def test_dm_all_puts_the_pdf_and_video_between_the_case_and_the_share_message(self):
        self.on = [("video", "b" * 32), ("pdf", "a" * 32)]  # 2nd: video, 3rd: PDF
        self.g.mutate({"action": "add", "name": "Sara Giki", "phone": "0300 2000002"})
        self.g.mutate({"action": "message", "text": "Share this {name}"})
        self.go(self.g, {"action": "send_all", "request_id": "r2"})
        self.run_job(self.g.jobs)
        self.assertEqual(
            [(b["kind"], b.get("extra"), b["message"][:12]) for b in self.sent],
            [
                ("volunteer_batch", None, self.case[:12]),
                ("dm_extra", "video", ""),
                ("dm_extra", "pdf", ""),
                ("volunteer_batch", None, "Share this S"),
            ],
        )

    def test_a_person_without_a_real_first_name_gets_no_name_and_the_sentence_closes_up(self):
        self.g.mutate({"action": "add", "name": ". Giki Donor 4", "phone": "0300 2000002"})
        self.g.mutate({"action": "message", "text": "Salam {name}!"})
        self.go(self.g, {"action": "send_all", "request_id": "r3"})
        self.run_job(self.g.jobs)
        self.assertEqual(self.sent[-1]["message"], "Salam!")

    def test_dm_all_skips_people_already_messaged_and_says_so(self):
        for n, p in (("Sara", "0300 2000002"), ("Bilal", "0300 3000003")):
            self.g.mutate({"action": "add", "name": n, "phone": p})
        self.g.mutate({"action": "message", "text": "Salam {name}"})
        first = next(x for x in self.g.view()["items"] if x["name"] == "Sara")
        self.go(self.g, {"action": "send_case", "id": first["id"], "request_id": "one"})
        self.run_job(self.g.jobs)
        view = self.g.view()
        self.assertEqual((len(view["items"]), view["waiting"]), (2, 1))
        sent_before = len(self.sent)
        self.go(self.g, {"action": "send_all", "request_id": "all"})
        self.run_job(self.g.jobs)
        names = [b["name"] for b in self.sent[sent_before:]]
        self.assertEqual(
            names, ["Bilal Bhai", "Bilal Bhai"]
        )  # the case, then the share message: only for the one waiting
        self.assertEqual(self.g.view()["waiting"], 0)
        with self.assertRaisesRegex(ValueError, "already messaged"):
            self.g.mutate({"action": "send_all", "request_id": "again"})

    def test_dm_all_needs_a_share_message_that_fits_after_the_case(self):
        self.g.mutate({"action": "add", "name": "Sara", "phone": "0300 2000002"})
        with self.assertRaisesRegex(ValueError, "share message"):
            self.g.mutate({"action": "send_all", "request_id": "x1"})
        self.g.mutate({"action": "message", "text": "x" * 2500})
        with self.assertRaisesRegex(ValueError, "2,000"):
            self.g.mutate({"action": "send_all", "request_id": "x2"})
        self.assertEqual(self.sent, [])

    def test_the_same_dm_all_request_is_not_started_twice(self):
        self.g.mutate({"action": "add", "name": "Sara", "phone": "0300 2000002"})
        self.g.mutate({"action": "message", "text": "Salam"})
        a = self.go(self.g, {"action": "send_all", "request_id": "same-1"})
        b = self.go(self.g, {"action": "send_all", "request_id": "same-1"})
        self.assertEqual(a["job"]["id"], b["job"]["id"])
        self.assertEqual(len(self.g.jobs._load()["jobs"]), 1)

    def test_test_sends_the_whole_dm_to_yourself_with_the_pdf_and_video_that_are_on(self):
        self.g.mutate({"action": "message", "text": "Saved share"})
        self.on = [("pdf", "a" * 32)]
        out = self.g.mutate({"action": "test", "text": "Typed share {name}"})
        self.assertEqual(out["code"], "SUCCESS")
        self.assertEqual(
            self.tests, [(self.case, "Typed share {name}", True, False)]
        )  # the box text, even unsaved
        self.g.mutate({"action": "test"})
        self.assertEqual(self.tests[-1][1], "Saved share")
        self.assertEqual(self.sent, [])  # the test never goes through the list

    def test_test_still_sends_the_case_when_no_share_message_is_written_and_the_other_way_round(
        self,
    ):
        self.g.mutate({"action": "message", "text": ""})
        self.g.mutate({"action": "test"})
        self.assertEqual(self.tests[-1], (self.case, "", False, False))  # the case alone
        self.g.case_text = lambda: ""
        self.g.mutate({"action": "test", "text": "Only the share"})
        self.assertEqual(self.tests[-1], ("", "Only the share", False, False))  # the share alone
        before = len(self.tests)
        with self.assertRaisesRegex(ValueError, "Nothing to test"):
            self.g.mutate({"action": "test"})  # both missing
        self.assertEqual(len(self.tests), before)

    def test_the_timer_has_the_case_page_ranges_and_defaults(self):
        self.assertEqual(
            self.g.view()["pace"], {"gap_minutes": 5, "batch_size": 10, "rest_minutes": 20}
        )
        for body in (
            {"gap_minutes": 0},
            {"gap_minutes": 11},
            {"batch_size": 21},
            {"rest_minutes": 121},
            {"rest_minutes": 2.5},
            {"batch_size": "5"},
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.g.mutate({"action": "pace", **body})
        self.assertEqual(self.g.view()["pace"]["gap_minutes"], 5)  # nothing was saved
        self.g.mutate({"action": "pace", "gap_minutes": 10, "batch_size": 20, "rest_minutes": 120})
        self.assertEqual(
            self.g.view()["pace"], {"gap_minutes": 10, "batch_size": 20, "rest_minutes": 120}
        )

    def test_main_volunteers_keep_their_fixed_pace(self):
        self.main.mutate({"action": "add", "name": "Main One", "phone": "0300 1000001"})
        self.main.mutate({"action": "message", "text": "Hi"})
        self.main_up = True
        self.go(self.main, {"action": "send_all", "request_id": "m1", "poster": False})
        job = self.main.jobs._load()["jobs"][-1]
        self.assertEqual((job["gap_seconds"], job["chunk"]), (180, 20))
        self.run_job(self.main.jobs)
        self.assertNotIn("line", self.sent[0])


class GikiDmCase(Fixture):
    def start(self):
        self.g.mutate({"action": "add", "name": "Sara Giki", "phone": "0300 2000002"})
        pid = self.g.view()["items"][0]["id"]
        self.go(self.g, {"action": "send_case", "id": pid, "request_id": "c" + str(len(self.sent))})
        return self.run_job(self.g.jobs)

    def test_dm_case_sends_the_group_message_with_the_poster_and_no_extras_when_both_are_off(self):
        self.start()
        self.assertEqual(len(self.sent), 1)
        body = self.sent[0]
        self.assertEqual(
            body["message"], self.case
        )  # the Group msgs text, not the volunteer message
        self.assertIs(body["poster"], True)
        self.assertEqual(body["line"], "giki")

    def test_dm_case_sends_the_pdf_and_the_video_only_when_they_are_on(self):
        self.on = [("video", "b" * 32), ("pdf", "a" * 32)]
        self.start()
        self.assertEqual(
            [(b["kind"], b.get("extra")) for b in self.sent],
            [("volunteer_batch", None), ("dm_extra", "video"), ("dm_extra", "pdf")],
        )
        self.assertTrue(all(b["line"] == "giki" for b in self.sent))

    def test_one_extra_on_sends_only_that_one(self):
        self.on = [("video", "b" * 32)]
        self.start()
        self.assertEqual([b.get("extra") for b in self.sent], [None, "video"])

    def test_the_caption_follows_the_case_at_every_click(self):
        self.start()
        self.case = "A new case. Rs. 900 left."
        self.g.mutate({"action": "add", "name": "Bilal", "phone": "0300 3000003"})
        second = next(x for x in self.g.view()["items"] if x["name"] == "Bilal")
        self.go(self.g, {"action": "send_case", "id": second["id"], "request_id": "second"})
        self.run_job(self.g.jobs)
        self.assertEqual(
            [b["message"] for b in self.sent],
            ["Please help this family. Rs. 5,000 left.", "A new case. Rs. 900 left."],
        )

    def test_an_empty_group_bank_falls_back_to_the_saved_group_draft(self):
        self.case = "   "
        self.start()
        self.assertEqual(self.sent[0]["message"], "draft text")

    def test_main_volunteers_dm_case_is_unchanged(self):
        self.on = [("pdf", "a" * 32)]
        self.main.mutate({"action": "add", "name": "Main One", "phone": "0300 1000001"})
        pid = self.main.view()["items"][0]["id"]
        self.main_up = True
        self.go(self.main, {"action": "send_case", "id": pid, "request_id": "m"})
        self.run_job(self.main.jobs)
        self.assertEqual([b["message"] for b in self.sent], ["draft text"])


class GikiImport(Fixture):
    def test_a_table_file_gives_every_person_once_with_the_saved_name(self):
        rows, problems = parse_numbers(TABLE)
        self.assertEqual(problems, [])
        self.assertEqual(
            rows,
            [
                ("Giki Donor 4", "923001111111"),
                ("Ali Donor Giki", "923002222222"),
                ("Hassan 10k Afzal Giki", "97450557391"),
                ("💫 Giki Donor 1000", "923003333333"),
            ],
        )

    def test_plain_lines_and_bad_rows(self):
        rows, problems = parse_numbers(
            "Sara 0300 1234567\n2) Bilal Khan +92 321 7654321\nTwo numbers 0300 1111111 and 0300 2222222"
        )
        self.assertEqual(rows[:2], [("Sara", "923001234567"), ("Bilal Khan", "923217654321")])
        self.assertEqual(len(problems), 1)

    def test_check_first_then_add_and_never_twice(self):
        check = self.g.mutate({"action": "import", "text": TABLE, "dry_run": True})
        self.assertEqual((check["found"], check["added"], check["dry_run"]), (4, 4, True))
        self.assertEqual(self.g.view()["items"], [])  # a check adds nothing
        done = self.g.mutate({"action": "import", "text": TABLE})
        self.assertEqual((done["added"], done["existing"]), (4, 0))
        self.assertEqual(
            sorted(x["name"] for x in self.g.view()["items"]),
            sorted(
                ["Giki Donor 4", "Ali Donor Giki", "Hassan 10k Afzal Giki", "💫 Giki Donor 1000"]
            ),
        )
        again = self.g.mutate({"action": "import", "text": TABLE})
        self.assertEqual((again["added"], again["existing"]), (0, 4))
        self.assertEqual(len(self.g.view()["items"]), 4)

    def test_a_removed_person_comes_back_instead_of_doubling(self):
        self.g.mutate({"action": "import", "text": TABLE})
        first = self.g.view()["items"][0]
        self.g.mutate({"action": "delete", "id": first["id"]})
        self.assertEqual(len(self.g.view()["items"]), 3)
        again = self.g.mutate({"action": "import", "text": TABLE})
        self.assertEqual(again["added"], 1)
        self.assertEqual(len(self.g.view()["items"]), 4)

    def test_your_own_number_and_repeats_are_left_out(self):
        text = "| 1 | Me | 0300 0000000 | x |\n| 2 | Twice | 0300 5555555 | x |\n| 3 | Twice again | 0300 5555555 | x |\n"
        done = self.g.mutate({"action": "import", "text": text})
        self.assertEqual((done["added"], done["own"], done["repeats"]), (1, 1, 1))

    def test_nothing_to_add_is_a_clear_error(self):
        for text in ("", "   ", "no numbers here", None, 5):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.g.mutate({"action": "import", "text": text})

    def test_it_does_not_touch_the_main_volunteers(self):
        self.g.mutate({"action": "import", "text": TABLE})
        self.assertEqual(self.main.view()["items"], [])

    def test_the_list_you_gave_is_added_once_when_the_page_first_opens(self):
        seed = Path(self.folder.name) / "seed.md"
        seed.write_text(TABLE, encoding="utf-8")
        with patch.dict(os.environ, {"GIKI_SEED_FILE": str(seed)}):
            items = self.g.view()["items"]
            # the 4 people from the file, under Ahmad test and Zain test (they go to the test group)
            self.assertEqual([x["name"] for x in items[:2]], ["Ahmad test", "Zain test"])
            self.assertEqual(len(items), 6)
            self.assertEqual(self.g.view()["waiting"], 6)
            gone = self.g.view()["items"][2]
            self.g.mutate({"action": "delete", "id": gone["id"]})
            self.assertEqual(
                len(self.g.view()["items"]), 5
            )  # removed on purpose: it does not come back
        self.assertEqual(self.main.view()["items"], [])

    def test_a_missing_or_switched_off_seed_adds_nobody(self):
        with patch.dict(os.environ, {"GIKI_SEED_FILE": str(Path(self.folder.name) / "nope.md")}):
            self.assertEqual(self.g.view()["items"], [])
        with patch.dict(os.environ, {"GIKI_SEED_FILE": ""}):
            self.assertEqual(self.g.view()["items"], [])

    def test_the_bundled_list_is_the_42_people_from_the_file(self):
        from giki_line import SEED

        rows, problems = parse_numbers(SEED.read_text(encoding="utf-8"))
        self.assertEqual((len(rows), len({p for _, p in rows}), problems), (42, 42, []))
        self.assertEqual(rows[0][0], "Giki Donor 4")
        self.assertIn(("Hassan 10k Afzal Giki", "97450557391"), rows)
        with patch.dict(os.environ, {"GIKI_SEED_FILE": str(SEED)}):
            view = self.g.view()
        self.assertEqual(
            (len(view["items"]), view["waiting"]), (44, 44)
        )  # the 42 + Ahmad test, Zain test
        self.assertEqual([x["name"] for x in view["items"][:2]], ["Ahmad test", "Zain test"])

    def test_name_becomes_a_real_name_with_bhai_or_sister_or_nothing(self):
        import re as _re
        from giki_line import SEED, GREETING, fill_name, greeting

        rows, _ = parse_numbers(SEED.read_text(encoding="utf-8"))
        for label, _ in rows:  # every person you gave was checked by hand
            with self.subTest(label=label):
                key = " ".join(_re.sub(r"[^a-z0-9]+", " ", clean_name(label).lower()).split())
                self.assertIn(key, GREETING)
        cases = {
            "Asad GIKI Donor": "Asad Bhai",
            "Areeba Malik Giki": "Areeba Sister",
            "Giki Saim Donor Ali": "Saim Bhai",
            "ranaaziz Giki Donor": "Aziz Bhai",
            "Giki Donor": "",
            "ZB Giki Donor": "",
            "💫 Giki Donor 1000": "",
            "Giki 500 Girl": "",
            "Zoya Khan": "Zoya Sister",  # someone added later
            "Bilal": "Bilal Bhai",
            "Zoha Giki": "Zoha",  # a name we do not know: just the name
        }
        for label, want in cases.items():
            with self.subTest(label=label):
                self.assertEqual(greeting(label), want)
        self.assertEqual(
            fill_name("Assalam o alaikum {name}, please share.", "Asad Bhai"),
            "Assalam o alaikum Asad Bhai, please share.",
        )
        self.assertEqual(
            fill_name("Assalam o alaikum {name}, please share.", ""),
            "Assalam o alaikum, please share.",
        )
        self.assertEqual(fill_name("{name}, please share.", ""), "Please share.")
        self.assertEqual(fill_name("Hi {name}\nShare now", ""), "Hi\nShare now")
        self.assertEqual(fill_name("No placeholder here", ""), "No placeholder here")
        for (
            label,
            _,
        ) in rows:  # never a label, never "friend", never "Donor" / "Giki" in the greeting
            self.assertNotRegex(greeting(label).lower(), r"giki|donor|volunt|friend|\d")

    def test_first_names_skip_the_words_that_are_not_names(self):
        names = {
            ". Giki Donor 4": "",
            "Ali Donor Giki": "Ali",
            "Anas Giki 140": "Anas",
            "Giki 500 Girl": "",
            "Donor Giki Good": "",
            "Sheikh Jr. Giki": "Sheikh",
            "ZB Giki Donor": "ZB",
            "Ba-cha 😎 Giki Volunteer": "Ba-cha",
            "Hassan 10k Afzal Giki": "Hassan",
            "💫 Giki Donor 1000": "",
        }
        for label, want in names.items():
            with self.subTest(label=label):
                self.assertEqual(first_name(label)[0], want)
        self.assertEqual(clean_name(" . Giki   Donor "), "Giki Donor")


class FakeGateway:
    """Just enough of the WhatsApp gateway for the line: devices, status, login."""

    def __init__(self):
        self.devices = {}
        self.calls = []
        self.logged = set()

    def __call__(self, method, path, device="", body=None, timeout=15, raw=False):
        self.calls.append((method, path, device))
        route = path.split("?")[0]
        if (method, route) == ("GET", "/devices"):
            return {"results": [{"id": d} for d in self.devices] or None}
        if (method, route) == ("POST", "/devices"):
            self.devices[body["device_id"]] = {}
            return {"results": {"id": body["device_id"]}}
        parts = route.strip("/").split("/")
        if parts[0] == "devices" and len(parts) >= 2 and parts[1] not in self.devices:
            raise wa_lines.LineError("This WhatsApp line was not found.")
        if route.endswith("/status"):
            up = parts[1] in self.logged
            return {"results": {"is_connected": up, "is_logged_in": up}}
        if (method, len(parts)) == ("GET", 2):
            return {"results": {"id": parts[1], "jid": "923009998888:12@s.whatsapp.net"}}
        if route.endswith("/login/code"):
            return {"results": {"pair_code": "abcd1234"}}
        if route.endswith("/login"):
            return {"results": {"qr_link": "http://x/statics/qrcode/a.png", "qr_duration": 40}}
        if route.startswith("/statics/qrcode/"):
            return b"PNGDATA"
        if route.endswith("/reconnect"):
            return {}
        if route.endswith("/logout"):
            self.logged.discard(parts[1])
            return {}
        raise AssertionError("unexpected call " + method + " " + path)


class GikiReconnect(unittest.TestCase):
    """The Giki WhatsApp gets the same reconnect care as the main one, even with the page closed."""

    def test_a_dropped_link_is_asked_to_reconnect_after_45_s_and_not_more_than_every_90_s(self):
        import supervisor

        asked = []
        w = supervisor.DropWatch()
        w.step("dropped", 0, lambda: asked.append(0))
        w.step("dropped", 30, lambda: asked.append(30))
        self.assertEqual(asked, [])  # a short blip: wait
        w.step("dropped", 45, lambda: asked.append(45))
        w.step("dropped", 75, lambda: asked.append(75))
        w.step("dropped", 140, lambda: asked.append(140))
        self.assertEqual(asked, [45, 140])

    def test_a_working_or_logged_out_link_is_left_alone(self):
        import supervisor

        asked = []
        w = supervisor.DropWatch()
        for t, state in ((0, "ok"), (100, "logged_out"), (200, "ok"), (300, None)):
            w.step(state, t, lambda: asked.append(t))
        self.assertEqual(asked, [])
        w.step("dropped", 400, lambda: asked.append(400))
        w.step(
            "ok", 430, lambda: asked.append(430)
        )  # it came back by itself: the clock starts again
        w.step("dropped", 440, lambda: asked.append(440))
        self.assertEqual(asked, [])

    def test_the_launcher_watches_the_giki_line_with_it(self):
        src = (Path(__file__).resolve().parents[1] / "launcher.py").read_text(encoding="utf-8")
        self.assertIn("line_watch.setdefault(device, supervisor.DropWatch())", src)
        self.assertIn('"/reconnect", "POST"', src)
        self.assertIn("wa_lines.is_line_device", src)


class LineTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.gw = FakeGateway()
        self.line = wa_lines.Line("giki", self.store, "http://gateway", call=self.gw)

    def test_no_device_until_the_first_connect(self):
        self.assertEqual(self.line.device(), "")
        self.assertEqual(self.line.status()["state"], "none")
        self.assertFalse(self.line.ready())
        self.assertEqual(self.gw.calls, [])  # asking never creates a device

    def test_one_giki_device_is_made_once_and_saved(self):
        first = self.line.ensure()
        self.assertTrue(first.startswith("giki-"))
        self.assertEqual(self.line.ensure(), first)
        self.assertEqual(len([c for c in self.gw.calls if c[:2] == ("POST", "/devices")]), 1)
        again = wa_lines.Line("giki", self.store, "http://gateway", call=self.gw)  # after a restart
        self.assertEqual(again.device(), first)

    def test_status_words(self):
        device = self.line.ensure()
        self.assertEqual(self.line.status()["state"], "unlinked")
        self.gw.logged.add(device)
        st = self.line.status()
        self.assertEqual((st["state"], st["tail"]), ("ready", "8888"))
        self.assertTrue(self.line.ready())

    def test_a_device_the_gateway_forgot_is_linked_again_with_the_same_id(self):
        device = self.line.ensure()
        self.gw.devices.clear()
        self.assertEqual(self.line.status()["state"], "none")
        self.assertEqual(self.line.ensure(), device)

    def test_qr_and_pairing_code(self):
        qr = self.line.qr()
        self.assertTrue(qr["qr"].startswith("data:image/png;base64,"))
        self.assertEqual(qr["duration"], 40)
        self.assertEqual(self.line.pair_code("0300 1234567"), {"code": "ABCD-1234"})
        sent = [
            c for c in self.gw.calls if c[1].startswith(f"/devices/{self.line.device()}/login/code")
        ]
        self.assertIn("phone=923001234567", sent[0][1])
        with self.assertRaises(wa_lines.LineError):
            self.line.pair_code("hello")

    def test_logout_keeps_the_device_for_the_next_link(self):
        device = self.line.ensure()
        self.gw.logged.add(device)
        self.assertEqual(self.line.logout()["state"], "unlinked")
        self.assertEqual(self.line.device(), device)

    def test_gateway_text_never_reaches_the_owner(self):
        for raw, shown in (
            (
                'failed to dial whatsapp web websocket: Get "https://web.whatsapp.com/ws/chat"',
                "WhatsApp could not be reached. Try again in a minute.",
            ),
            (
                "device giki-1 is not logged in (session deleted)",
                "This WhatsApp is not linked yet.",
            ),
        ):
            self.assertEqual(wa_lines._friendly(raw), shown)
            self.assertNotIn("web.whatsapp", wa_lines._friendly(raw))

    def test_the_main_device_is_never_taken_for_a_line(self):
        self.assertTrue(wa_lines.is_line_device("giki-3d97901debdb"))
        self.assertFalse(wa_lines.is_line_device("6f0c2a10-aaaa-bbbb-cccc-0123456789ab"))
        self.assertFalse(wa_lines.is_line_device(""))
        self.assertFalse(wa_lines.is_line_device(None))


if __name__ == "__main__":
    unittest.main()


class FakeChat:
    """What really reached WhatsApp, per chat, like the gateway's history (the app's chat check reads it)."""

    TYPES = {"pdf": "document", "video": "video", "poster": "image"}

    def __init__(self):
        self.rows = []  # (message id, phone, type, what)
        self.readable = True

    def kind(self, body):
        if body.get("kind") == "dm_extra":
            return self.TYPES[body["extra"]]
        return "image" if body.get("poster") is True else ""

    def add(self, body):
        mid = "m%d" % (len(self.rows) + 1)
        what = body.get("extra") or ("case" if body.get("poster") is True else "share")
        self.rows.append((mid, body["phone"], self.kind(body), what))
        return mid

    def peek(self, body):
        if not self.readable:
            return None
        mine = [r for r in self.rows if r[1] == body["phone"]]
        return mine[-1][0] if mine else ""

    def seen(self, body, after):
        if not self.readable or not isinstance(after, str):
            return None
        mine = [r for r in self.rows if r[1] == body["phone"]]
        ids = [r[0] for r in mine]
        newer = mine[ids.index(after) + 1 :] if after else mine
        want = ("image", "video") if body.get("poster") is True else (self.kind(body),)
        hit = [r[0] for r in newer if r[2] in want]
        return hit[-1] if hit else ""

    def got(self, phone):
        return [r[3] for r in self.rows if r[1] == phone]


class GikiSelfHealing(Fixture):
    """An unclear or failed answer is looked up in the chat: there = it went (never sent twice); not there = sent
    again; the chat cannot be read = never sent again. One person is finished before the next."""

    def setUp(self):
        super().setUp()
        self.chat = FakeChat()
        self.script = []  # what happens to each send, in order: ok / drop (went, answer lost) / fail / lost
        self.calls = 0
        self.g.jobs.peek = self.chat.peek
        self.g.jobs.seen = self.chat.seen
        self.g.jobs.HEAL_WATCH = (0,)
        self.g.jobs.HEAL_QUICK = (0,)
        self.g.jobs.send = self.flaky_send
        self.on = [("poster", "p" * 32), ("pdf", "a" * 32)]  # 2nd: poster pic, 3rd: PDF
        for i in range(2):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 200000{i}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})

    def flaky_send(self, body):
        self.calls += 1
        if getattr(self, "never", None) == (body["phone"], body.get("extra")):
            return {"code": "INTERNAL_SERVER_ERROR", "message": "failed to send message"}
        what = self.script.pop(0) if self.script else "ok"
        if what in ("ok", "drop"):
            self.chat.add(body)
        if what in ("drop", "lost"):
            raise ConnectionError("the answer was lost")
        if what == "fail":
            return {"code": "INTERNAL_SERVER_ERROR", "message": "failed to send message"}
        return {"code": "SUCCESS"}

    def run_all(self, request_id="heal"):
        self.go(self.g, {"action": "send_all", "request_id": request_id, "poster": False})
        return self.run_job(self.g.jobs)

    def test_repeated_send_after_completion_returns_original_receipt(self):
        job = self.run_all("completed-click")
        before = list(self.chat.rows)
        result = self.g.send_all({"request_id": "completed-click"})
        self.assertEqual(result["job"]["id"], job["id"])
        self.assertEqual(result["job"]["state"], "Completed")
        self.assertEqual(self.chat.rows, before)
        self.assertEqual(len(self.g.jobs.export_jobs()["jobs"]), 1)

    def test_reused_request_cannot_acknowledge_a_different_attachment_order(self):
        self.run_all("ordered-click")
        self.on.reverse()
        with self.assertRaisesRegex(ValueError, "another Giki batch"):
            self.g.send_all({"request_id": "ordered-click", "skip_contacted": False})
        self.everyone_complete()

    def everyone_complete(self):
        for i in range(2):
            self.assertEqual(self.chat.got(f"92300200000{i}"), ["case", "poster", "pdf", "share"])

    def test_a_message_that_went_but_whose_answer_was_lost_is_never_sent_again(self):
        self.script = [
            "drop",
            "ok",
            "drop",
            "ok",
        ]  # the case and the PDF of person 0 went, answers lost
        job = self.run_all()
        self.assertEqual((job["state"], job["sent"]), ("Completed", 2))
        self.everyone_complete()
        self.assertEqual(self.calls, 8)  # 2 people x 4 messages: nothing sent twice

    def test_a_message_that_did_not_go_is_sent_again_until_it_goes(self):
        self.script = ["fail", "ok", "lost", "ok", "fail", "fail", "ok"]
        job = self.run_all()
        self.assertEqual((job["state"], job["sent"], job.get("error", "")), ("Completed", 2, ""))
        self.everyone_complete()

    def test_when_the_chat_cannot_be_read_nothing_is_sent_twice(self):
        self.chat.readable = False
        self.script = ["ok", "drop"]  # person 0's poster went but its answer was lost: cannot check
        job = self.run_all()
        self.assertEqual(self.chat.got("923002000000"), ["case", "poster"])
        self.assertEqual(
            job["receipts"][0]["steps"]["poster"], "Uncertain"
        )  # recorded, never resent
        self.assertEqual(self.chat.got("923002000001"), [])
        self.assertEqual(job["state"], "Stopped")
        self.assertEqual(self.g.jobs.finish_half_sent(), 0)
        self.assertEqual(self.chat.got("923002000000"), ["case", "poster"])

    def test_a_message_that_fails_three_times_stops_before_later_steps_and_people(self):
        self.script = ["ok", "fail", "fail", "fail"]  # person 0's poster does not go, 3 times
        job = self.run_all()
        self.assertEqual(job["state"], "Stopped")
        self.assertEqual(self.chat.got("923002000001"), [])
        self.assertEqual(self.chat.got("923002000000"), ["case"])
        self.assertEqual(job["receipts"][0]["steps"]["poster"], "Not sent")
        self.assertEqual(self.g.jobs.finish_half_sent(), 1)
        self.assertEqual(self.chat.got("923002000000"), ["case", "poster", "pdf", "share"])
        self.assertEqual(self.g.jobs.finish_half_sent(), 0)

    def test_a_failed_first_message_is_never_moved_behind_another_person(self):
        self.script = [
            "fail",
            "lost",
            "fail",
        ]  # person 0's case does not go, 3 times (checked in the chat)
        job = self.run_all()
        self.assertEqual((job["state"], job["sent"], job["failed"]), ("Stopped", 0, 1))
        self.assertEqual(self.chat.rows, [])
        self.assertEqual(len(self.g.waiting_ids()), 2)

    def test_a_message_that_never_goes_is_left_for_resume_and_never_doubled(self):
        self.never = (
            "923002000000",
            "poster",
        )  # person 0's poster never goes
        job = self.run_all()
        self.assertEqual(job["state"], "Stopped")
        self.assertEqual(job["receipts"][0]["steps"]["poster"], "Not sent")
        self.assertEqual(self.chat.got("923002000000"), ["case"])
        with self.assertRaisesRegex(ValueError, "remaining recipients are still waiting"):
            self.g.resume({})
        self.assertEqual(self.chat.got("923002000001"), [])
        self.never = None  # WhatsApp is fine again
        with patch.object(self.g.jobs, "_run"):
            self.g.resume({"request_id": "resumed-in-order"})
        self.assertEqual(self.chat.got("923002000000"), ["case", "poster", "pdf", "share"])
        self.assertEqual(self.chat.got("923002000001"), [])
        self.run_job(self.g.jobs)
        self.everyone_complete()
        self.assertEqual(self.g.jobs.finish_half_sent(), 0)

    def test_each_following_step_resumes_before_next_chat(self):
        for failed_step in (1, 2, 3):
            with self.subTest(failed_step=failed_step):
                self.script = ["ok"] * failed_step + ["fail"] * 3
                job = self.run_all(f"stop-{failed_step}")
                self.assertEqual(job["state"], "Stopped")
                steps = ["case", "poster", "pdf", "share"]
                self.assertEqual(self.chat.got("923002000000"), steps[:failed_step])
                self.assertEqual(self.chat.got("923002000001"), [])
                with patch.object(self.g.jobs, "_run"):
                    self.g.resume({"request_id": f"resume-{failed_step}"})
                self.run_job(self.g.jobs)
                expected = [(p, step) for p in ("923002000000", "923002000001") for step in steps]
                self.assertEqual([(r[1], r[3]) for r in self.chat.rows], expected)
                self.g.all_to_waiting()
                self.chat.rows.clear()

    def test_first_incomplete_chat_stops_the_batch_with_a_clear_reason(self):
        for i in range(2, 4):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 200000{i}"})
        self.script = ["ok"] + ["fail"] * 3 + ["ok", "ok"]  # person 0: poster fails
        self.script += ["ok"] + ["fail"] * 3 + ["ok", "ok"]  # person 1: poster fails
        self.script += ["ok"] + ["fail"] * 3 + ["ok", "ok"]  # person 2: poster fails
        job = self.run_all()
        self.assertEqual(job["state"], "Stopped")
        self.assertIn("poster picture", job["error"])
        for i in range(1, 4):
            self.assertEqual(self.chat.got(f"92300200000{i}"), [])

    def test_a_restart_in_the_middle_of_a_message_is_settled_by_the_chat(self):
        self.run_all()
        jobs = self.g.jobs._load()
        j = jobs["jobs"][-1]
        j.update(state="Interrupted", boot="an-older-boot")
        # person 0: the PDF was going out when the service stopped, and it did reach WhatsApp
        p0 = j["receipts"][0]
        p0["steps"]["pdf"] = "Sending"
        p0["follow_up"] = None  # the share never started: take it out of the chat
        self.chat.rows = [
            r for r in self.chat.rows if not (r[1] == "923002000000" and r[3] == "share")
        ]
        # person 1: the poster was going out and did NOT reach WhatsApp (take it out of the chat)
        p1 = j["receipts"][1]
        last_case = [r for r in self.chat.rows if r[1] == "923002000001" and r[3] == "case"][0][0]
        self.chat.rows = [
            r for r in self.chat.rows if not (r[1] == "923002000001" and r[3] != "case")
        ]
        p1["steps"] = {"poster": "Sending"}
        p1["after_ids"] = {"poster": last_case}
        p1["follow_up"] = None
        self.g.jobs._save(jobs)
        for receipt in j["receipts"]:
            self.g.book.follow_up(receipt["id"], None)
        self.chat.readable = False
        self.assertEqual(self.g.jobs.finish_half_sent(), 0)
        self.chat.readable = True
        self.assertEqual(self.g.jobs.finish_half_sent(), 2)
        self.assertEqual(
            self.chat.got("923002000000"), ["case", "poster", "pdf", "share"]
        )  # PDF not resent
        self.assertEqual(self.chat.got("923002000001"), ["case", "poster", "pdf", "share"])

    def test_a_restart_while_the_first_message_was_going_is_settled_by_the_chat(self):
        self.run_all()
        jobs = self.g.jobs._load()
        j = jobs["jobs"][-1]
        p1 = j["receipts"].pop()  # person 1: the case was going out; no record of how it ended
        j.update(state="Interrupted", boot="an-older-boot", sending={"id": p1["id"], "after": ""})
        self.g.jobs._save(jobs)
        self.g.book.delivery(p1["id"], "Sending")
        self.chat.rows = [
            r for r in self.chat.rows if not (r[1] == "923002000001" and r[3] != "case")
        ]
        self.g.book.follow_up(p1["id"], None)
        self.assertEqual(
            self.g.jobs.finish_half_sent(), 1
        )  # the case is in the chat: the rest follows
        self.assertEqual(self.chat.got("923002000001"), ["case", "poster", "pdf", "share"])
        # the same, when the case did NOT reach WhatsApp: they simply wait for the next send
        j = self.g.jobs._load()["jobs"][-1]
        j["receipts"] = [r for r in j["receipts"] if r["id"] != p1["id"]]
        j["sending"] = {"id": p1["id"], "after": ""}
        self.g.jobs._save({"jobs": [j]})
        data = (
            self.g.book._load()
        )  # as a first message caught mid-send leaves the person: never sent before
        rec = next(r for r in data["records"] if r["id"] == p1["id"])
        rec.update(dm_sent=False, last_sent_at=None, delivery="Sending")
        self.g.book._save(data)
        self.chat.rows = [r for r in self.chat.rows if r[1] != "923002000001"]
        self.assertEqual(self.g.jobs.finish_half_sent(), 0)
        self.assertEqual(self.chat.got("923002000001"), [])
        self.assertIn(p1["id"], self.g.waiting_ids())


class GikiTwoSelfHealing(GikiSelfHealing):
    line_class = Giki2Volunteers


class GikiTwoMove(Fixture):
    def test_the_chosen_people_move_to_giki_2_once_with_their_messaged_marks(self):
        from giki_line import Giki2Volunteers

        for name, phone in (
            ("Areeba Malik Giki", "0300 2000001"),
            ("Haris Giki 1500", "0300 2000002"),
            ("Faris Giki Donor", "0300 2000003"),  # not chosen: stays on Giki
        ):
            self.g.mutate({"action": "add", "name": name, "phone": phone})
        areeba = next(x for x in self.g.view()["items"] if x["name"] == "Areeba Malik Giki")
        self.g.book.delivery(areeba["id"], "Sent")  # already got this case from the Giki WhatsApp
        g2 = Giki2Volunteers(self.g.app, lambda phone: True)
        g2.source = self.g
        with patch.dict(os.environ, {"GIKI_SEED_FILE": ""}):
            v2 = g2.view()
            g2.view()  # once only
        self.assertEqual(sorted(x["name"] for x in v2["items"]), ["Areeba Malik Giki", "Haris Giki 1500"])
        self.assertEqual([x["name"] for x in self.g.view()["items"]], ["Faris Giki Donor"])
        # then, once, everyone on Giki 2 is back to Waiting (the owner asked): Areeba too
        self.assertFalse(any(x["dmed"] for x in v2["items"]))
        self.assertEqual(v2["waiting"], 2)
        self.assertTrue(self.store.get("giki2_all_waiting_v1"))
        g2.book.delivery(moved_id := v2["items"][0]["id"], "Sent")  # a later send stays: the reset is once only
        self.assertTrue(next(x for x in g2.view()["items"] if x["id"] == moved_id)["dmed"])


class GikiToWaiting(Fixture):
    def test_a_dmed_person_goes_back_to_waiting_and_resume_never_doubles_them(self):
        self.g.mutate({"action": "add", "name": "Areeba Malik Giki", "phone": "0300 2000001"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share."})
        self.go(self.g, {"action": "send_all", "request_id": "w1", "poster": False})
        self.run_job(self.g.jobs)
        areeba = self.g.view()["items"][0]
        self.assertTrue(areeba["dmed"])
        jobs = self.g.jobs._load()
        jobs["jobs"][-1]["receipts"][0]["follow_up"] = "Not sent"  # a half-sent record from before
        self.g.jobs._save(jobs)
        r = self.g.mutate({"action": "to_waiting", "id": areeba["id"]})
        self.assertIn("back in Waiting", r["reply"])
        view = self.g.view()
        self.assertFalse(view["items"][0]["dmed"])
        self.assertEqual(view["waiting"], 1)
        self.assertEqual(self.g.jobs.half_sent(), [])  # Resume adds nothing on top of the full resend


class GikiAllToWaiting(Fixture):
    def test_everyone_in_dmed_goes_back_to_waiting_at_once(self):
        for i in range(3):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 200000{i}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share."})
        self.go(self.g, {"action": "send_all", "request_id": "a1", "poster": False})
        self.run_job(self.g.jobs)
        self.assertTrue(all(x["dmed"] for x in self.g.view()["items"]))
        sent_before = len(self.sent)
        r = self.g.mutate({"action": "all_to_waiting"})
        self.assertEqual(r["moved"], 3)
        view = self.g.view()
        self.assertFalse(any(x["dmed"] for x in view["items"]))
        self.assertEqual(view["waiting"], 3)
        self.assertEqual(len(self.sent), sent_before)  # nothing is sent by the move
        self.assertEqual(self.g.jobs.half_sent(), [])
        with self.assertRaises(ValueError):
            self.g.mutate({"action": "all_to_waiting"})  # nobody left in DMed

    def test_not_while_dms_are_running(self):
        self.g.mutate({"action": "add", "name": "Giki P0", "phone": "0300 2000000"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share."})
        self.go(self.g, {"action": "send_all", "request_id": "a2", "poster": False})
        self.run_job(self.g.jobs)
        self.g.jobs.active = {"id": "busy"}
        try:
            with self.assertRaises(ValueError):
                self.g.mutate({"action": "all_to_waiting"})
        finally:
            self.g.jobs.active = None


class GikiOneRemovesTheMoved(Fixture):
    def test_opening_giki_first_also_takes_the_chosen_people_off_it(self):
        from giki_line import Giki2Volunteers

        for name, phone in (("Hajira Giki Donor 500", "0300 2000001"), ("Faris Giki Donor", "0300 2000002")):
            self.g.mutate({"action": "add", "name": name, "phone": phone})
        g2 = Giki2Volunteers(self.g.app, lambda phone: True)
        g2.source, self.g.partner = self.g, g2
        self.assertEqual([x["name"] for x in self.g.view()["items"]], ["Faris Giki Donor"])
        with patch.dict(os.environ, {"GIKI_SEED_FILE": ""}):
            self.assertEqual([x["name"] for x in g2.view()["items"]], ["Hajira Giki Donor 500"])


class GikiExactGap(Fixture):
    def test_the_gap_is_exactly_the_timer(self):
        for gap in (60, 300, 600):
            self.assertEqual(self.g.jobs._gap({"gap_seconds": gap}), float(gap))

    def timed_run(self, people, upload=10.0, blip_before=None):
        """DM all with each message taking `upload` seconds. Returns [(time, phone, what)] in the order sent."""
        for i in range(people):
            self.g.mutate({"action": "add", "name": f"Giki P{i}", "phone": f"0300 20000{i:02d}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})
        self.g.mutate({"action": "pace", "gap_minutes": 3, "batch_size": 3, "rest_minutes": 10})
        self.on = [("poster", "p1"), ("pdf", "f1")]
        self.go(self.g, {"action": "send_all", "request_id": "timed", "poster": True})
        clock, log, blip = [1_000_000.0], [], [0]

        class Line:  # WhatsApp: there, except for one short blip when asked
            def __bool__(self):
                if blip[0]:
                    blip[0] -= 1
                    return False
                return True

        self.line_up = Line()

        def on_send(body):
            what = body.get("extra") or ("case" if "after_steps" in body else "share")
            log.append((clock[0], body["phone"], what))
            if what == blip_before:
                blip[0] = 2  # the next 2 looks at WhatsApp say "not connected" (the app keeps a "no" for 1.5 s)
            clock[0] += upload

        self.on_send = on_send

        def wait(seconds):
            clock[0] += seconds
            return False

        job = self.g.jobs._load()["jobs"][-1]
        with (
            patch("donor_delivery.time.time", side_effect=lambda: clock[0]),
            patch("donor_delivery.time.sleep", side_effect=wait),
            patch.object(self.g.jobs.stop, "wait", side_effect=wait),
        ):
            self.g.jobs._run(job)
        return log

    def test_a_dm_every_timer_minutes_exactly_the_sending_time_is_not_added(self):
        log = self.timed_run(5)  # each person: 4 messages of 10 s each (40 s)
        cases = [t for t, _, what in log if what == "case"]
        self.assertEqual(len(cases), 5)
        self.assertEqual([what for _, _, what in log[:4]], ["case", "poster", "pdf", "share"])
        start = cases[0]
        # 3 min apart, case to case; the 4th starts the 2nd batch: 10 min rest after the 3rd case
        for got, want in zip(cases, (0, 180, 360, 960, 1140)):
            self.assertAlmostEqual(got - start, want, delta=0.11)

    def test_the_next_person_never_starts_before_the_last_one_finished(self):
        log = self.timed_run(3, upload=60.0)  # 4 minutes of sending per person, longer than the 3 min Timer
        for k in range(1, len(log)):
            self.assertGreaterEqual(log[k][0], log[k - 1][0] + 60.0)  # one message after another, never together
        phones = [p for _, p, _ in log]
        self.assertEqual(phones, sorted(phones, key=phones.index))  # each person's 4 messages together

    def test_a_whatsapp_blip_costs_two_seconds_not_fifteen(self):
        log = self.timed_run(1, blip_before="poster")
        times = {what: t for t, _, what in log}
        self.assertAlmostEqual(times["pdf"] - times["poster"], 10.0 + 2.0, delta=0.11)
        self.assertEqual(
            self.g.jobs._load()["jobs"][-1]["receipts"][0]["steps"], {"poster": "Sent", "pdf": "Sent"}
        )
