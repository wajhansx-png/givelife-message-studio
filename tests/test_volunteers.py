"""Volunteers: their own list, their own message and batch; never mixed with donors."""

import sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from donor_book import DonorBook
from volunteers import Volunteers


class Store:
    def __init__(self):
        self.data = {}

    def get(self, k, d=None):
        return __import__("copy").deepcopy(self.data.get(k, d))

    def put(self, k, v):
        self.data[k] = __import__("copy").deepcopy(v)


class VolunteerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store()
        self.sent = []
        self.clock = time.time()
        app = SimpleNamespace(
            DATA=Path(self.folder.name),
            STORE=self.store,
            OWNER_PHONE="923000000000",
            send_custom=self.send,
            wa_ok=lambda: True,
            on_hold=lambda: False,
        )
        self.v = Volunteers(app, lambda phone: True)
        self.donors = DonorBook(self.folder.name, self.store)

    def tearDown(self):
        self.folder.cleanup()

    def send(self, body):
        self.sent.append(body)
        return {"code": "SUCCESS"}

    def run_job(self):
        job = self.v.jobs._load()["jobs"][-1]

        def wait(seconds):
            self.clock += seconds
            return False

        with (
            patch("donor_delivery.time.time", side_effect=lambda: self.clock),
            patch.object(self.v.jobs.stop, "wait", side_effect=wait),
        ):
            self.v.jobs._run(job)

    def test_name_and_number_are_needed_and_lists_are_separate(self):
        with self.assertRaisesRegex(ValueError, "name"):
            self.v.mutate({"action": "add", "name": "  ", "phone": "03001234567"})
        with self.assertRaisesRegex(ValueError, "number"):
            self.v.mutate({"action": "add", "name": "Sara", "phone": ""})
        with self.assertRaisesRegex(ValueError, "connected account"):
            self.v.mutate({"action": "add", "name": "Me", "phone": "923000000000"})
        self.v.mutate({"action": "add", "name": "Sara", "phone": "03001234567"})
        self.assertEqual([x["name"] for x in self.v.view()["items"]], ["Sara"])
        self.assertEqual(self.donors.list()["items"], [])
        self.assertTrue(
            all("phone" not in x for x in self.v.view()["items"]), "numbers stay hidden"
        )

    def test_rename_updates_the_saved_name(self):
        item = self.v.mutate({"action": "add", "name": "Sara", "phone": "03001234567"})
        self.v.mutate({"action": "update", "id": item["donor"]["id"], "name": "Sara Khan"})
        self.assertEqual([x["name"] for x in self.v.view()["items"]], ["Sara Khan"])

    def test_message_is_saved_and_required_before_sending(self):
        self.v.mutate({"action": "add", "name": "Sara", "phone": "03001234567"})
        with self.assertRaisesRegex(ValueError, "Write the message"):
            self.v.mutate({"action": "send_all", "request_id": "r1aaaaaaaa"})
        self.v.mutate(
            {"action": "message", "text": "Assalam o alaikum {name}, please share this case."}
        )
        self.assertEqual(
            self.v.view()["message"], "Assalam o alaikum {name}, please share this case."
        )

    def test_batch_sends_the_message_once_to_each_volunteer_with_the_volunteer_kind(self):
        for n, p in (("Sara", "03001234567"), ("Ali", "03007654321")):
            self.v.mutate({"action": "add", "name": n, "phone": p})
        self.v.mutate({"action": "message", "text": "Please share: {name}"})
        with patch.object(self.v.jobs, "_run"):
            self.v.mutate({"action": "send_all", "request_id": "req-vol-0001", "gap_seconds": 60})
        self.run_job()
        self.assertEqual(sorted(b["name"] for b in self.sent), ["Ali", "Sara"])
        self.assertTrue(
            all(
                b["kind"] == "volunteer_batch" and b["message"] == "Please share: {name}"
                for b in self.sent
            )
        )
        self.assertEqual(self.v.jobs.status()["sent"], 2)
        self.assertEqual(self.donors.list()["counts"]["all"], 0)

    def test_one_volunteer_can_be_messaged_by_themselves(self):
        a = self.v.mutate({"action": "add", "name": "Sara", "phone": "03001234567"})["donor"]
        self.v.mutate({"action": "add", "name": "Ali", "phone": "03007654321"})
        self.v.mutate({"action": "message", "text": "Hi"})
        with patch.object(self.v.jobs, "_run"):
            self.v.mutate({"action": "send_one", "id": a["id"], "request_id": "req-vol-0002"})
        self.run_job()
        self.assertEqual([b["name"] for b in self.sent], ["Sara"])

    def test_delete_and_restore(self):
        a = self.v.mutate({"action": "add", "name": "Sara", "phone": "03001234567"})["donor"]
        self.v.mutate({"action": "delete", "id": a["id"]})
        self.assertEqual(self.v.view()["items"], [])
        self.v.mutate({"action": "restore", "id": a["id"]})
        self.assertEqual(len(self.v.view()["items"]), 1)
