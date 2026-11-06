import copy, tempfile, types, unittest
from donor_book import DonorBook
from donor_delivery import DonorDelivery
from donor_integration import DonorIntegration


class Store:
    def __init__(self):
        self.data = {}

    def get(self, k, default=None):
        return copy.deepcopy(self.data.get(k, default))

    def put(self, k, v):
        self.data[k] = copy.deepcopy(v)


class FollowUpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store()
        self.book = DonorBook(self.tmp.name, self.store)
        self.id = self.book.add("Sohaib", "923001112220")["donor"]["id"]
        self.book.update(self.id, important=True)
        self.book.update(self.id, top_donor=True)
        self.sent = []

    def tearDown(self):
        self.tmp.cleanup()

    def jobs(self, replies=None, eligible=None):
        replies = list(replies or [])

        def send(body):
            self.sent.append(body)
            return replies.pop(0) if replies else {"code": "SUCCESS"}

        return DonorDelivery(
            self.tmp.name, self.store, self.book, send, lambda: "Case caption",
            lambda: True, lambda: False, eligible or (lambda p: True),
            lambda name: ("Sohaib", "Brother"),
        )

    def run_job(self, jobs, **kw):
        jobs.start("top", 180, run=False, skip_contacted=False, **kw)
        job = jobs._load()["jobs"][-1]
        jobs._run(job)
        return jobs._load()["jobs"][-1]

    def test_unchecked_sends_only_the_poster_dm(self):
        job = self.run_job(self.jobs())
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn("follow_up", job["receipts"][0])

    def test_checked_sends_poster_first_then_personal_follow_up(self):
        job = self.run_job(self.jobs(), follow_up="{name}, please do consider helping.")
        self.assertEqual([b["poster"] for b in self.sent], [True, False])
        self.assertEqual(self.sent[0]["message"], "Case caption")
        self.assertEqual(self.sent[1]["message"], "Sohaib Bhai, please do consider helping.")
        self.assertEqual(self.sent[1]["phone"], self.sent[0]["phone"])
        self.assertEqual(job["receipts"][0]["state"], "Sent")
        self.assertEqual(job["receipts"][0]["follow_up"], "Sent")
        self.assertEqual(self.book.list("all")["items"][0]["follow_up_state"], "Sent")

    def test_no_follow_up_when_first_message_not_confirmed(self):
        job = self.run_job(self.jobs([{"code": "FAILED"}]), follow_up="Hello {name}")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(job["state"], "Stopped")
        self.assertIsNone(self.book.list("all")["items"][0].get("follow_up_state"))

    def test_opt_out_before_follow_up_skips_it(self):
        eligible = lambda phone: not self.sent  # opts out after the first DM

        job = self.run_job(self.jobs(eligible=eligible), follow_up="Hello {name}")
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(job["receipts"][0]["follow_up"].startswith("Skipped"))

    def test_uncertain_follow_up_stops_and_is_never_resent(self):
        job = self.run_job(
            self.jobs([{"code": "SUCCESS"}, {"code": "TIMEOUT"}]), follow_up="Hello {name}"
        )
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(job["receipts"][0]["follow_up"], "Uncertain")
        self.assertEqual(job["state"], "Stopped")
        self.assertIn("No automatic retry", job["error"])

    def test_greeting_forms(self):
        f = DonorDelivery.follow_text
        self.assertEqual(f("{name} hi", "Areeba", "Sister"), "Areeba Sister hi")
        self.assertEqual(f("{name} hi", "", "Brother"), "Bhai hi")
        self.assertEqual(f("{name} hi", "Sam", "Neutral"), "Sam hi")
        self.assertEqual(f("Plain", "Sohaib", "Brother"), "Plain")

    def test_empty_follow_up_is_refused_and_saved_text_is_used(self):
        hub = DonorIntegration.__new__(DonorIntegration)
        hub.app = types.SimpleNamespace(STORE=self.store)
        with self.assertRaises(ValueError):
            hub._follow_up_for(True)
        self.assertIsNone(hub._follow_up_for(False))
        hub.set_follow_up("  {name}, please consider.  ")
        self.assertEqual(hub._follow_up_for(True), "{name}, please consider.")
        with self.assertRaises(ValueError):
            hub.set_follow_up("x" * 2001)


if __name__ == "__main__":
    unittest.main()


class GapSecondsTests(unittest.TestCase):
    setUp, tearDown, jobs = FollowUpTests.setUp, FollowUpTests.tearDown, FollowUpTests.jobs
    """Seconds-level gaps: accepted, honoured, and still bounded."""

    def test_short_gaps_are_accepted_and_bounded(self):
        jobs = self.jobs()
        jobs.start("top", 30, run=False, skip_contacted=False)
        self.assertEqual(jobs._load()["jobs"][-1]["gap_seconds"], 30)
        for bad in (0, 4, 601, float("nan")):
            with self.assertRaises(ValueError):
                self.jobs().start("top", bad, run=False, skip_contacted=False)

    def test_wait_follows_the_chosen_short_gap(self):
        jobs = self.jobs()
        for _ in range(50):
            self.assertTrue(30 <= jobs._gap({"gap_seconds": 30}) <= 37.5)
            self.assertTrue(180 <= jobs._gap({"gap_seconds": 240}) <= 420)
        self.assertGreaterEqual(jobs._gap({"gap_seconds": 10, "jitter": {"min": -50, "max": -40}}), 5.0)

    def test_configure_accepts_seconds(self):
        jobs = self.jobs()
        jobs.start("top", 240, run=False, skip_contacted=False)
        job_id = jobs._load()["jobs"][-1]["id"]
        jobs.configure(job_id, {"gap_seconds": 20})
        self.assertEqual(jobs._load()["jobs"][-1]["gap_seconds"], 20)
        with self.assertRaises(ValueError):
            jobs.configure(job_id, {"gap_seconds": 3})
