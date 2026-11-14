"""The Giki list and its own WhatsApp. Synthetic numbers only; nothing is ever sent (fake transport)."""

import os, sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wa_lines
from giki_line import GikiVolunteers, clean_name, first_name, parse_numbers
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
            send_giki_test=self.fake_test,
            get_message=lambda kind: {"text": "draft text"},
            focus_bank=lambda: SimpleNamespace(get=lambda kind: {"source": self.case}),
        )
        self.g = GikiVolunteers(app, lambda phone: True)
        self.main = Volunteers(app, lambda phone: True)
        self.tests = []
        self.patches = [
            patch.dict(os.environ, {"GIKI_SEED_FILE": ""}),
            patch("caption_facts.current", side_effect=lambda app, text: text),
            patch("group_extras.to_send", side_effect=lambda store: list(self.on)),
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
        return {"code": "SUCCESS"}

    def fake_test(self, case, share, pdf=False, video=False):
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
            share["message"], "Salam Sara, please share this."
        )  # then the share message
        self.assertIs(share["poster"], False)
        self.assertTrue(
            all(b["line"] == "giki" and b["kind"] == "volunteer_batch" for b in self.sent)
        )
        self.assertIn("case first", r["reply"])

    def test_dm_all_puts_the_pdf_and_video_between_the_case_and_the_share_message(self):
        self.on = [("pdf", "a" * 32), ("video", "b" * 32)]
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

    def test_a_person_without_a_real_first_name_gets_friend_not_a_label(self):
        self.g.mutate({"action": "add", "name": ". Giki Donor 4", "phone": "0300 2000002"})
        self.g.mutate({"action": "message", "text": "Salam {name}!"})
        self.go(self.g, {"action": "send_all", "request_id": "r3"})
        self.run_job(self.g.jobs)
        self.assertEqual(self.sent[-1]["message"], "Salam friend!")

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
            names, ["Bilal", "Bilal"]
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
        self.on = [("pdf", "a" * 32), ("video", "b" * 32)]
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
            self.assertEqual(len(self.g.view()["items"]), 4)
            self.assertEqual(self.g.view()["waiting"], 4)
            gone = self.g.view()["items"][0]
            self.g.mutate({"action": "delete", "id": gone["id"]})
            self.assertEqual(
                len(self.g.view()["items"]), 3
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
        self.assertEqual((len(view["items"]), view["waiting"]), (42, 42))

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
