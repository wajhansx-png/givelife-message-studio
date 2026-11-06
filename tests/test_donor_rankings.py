import copy, tempfile, unittest
from donor_book import DonorBook, send_request


class Store:
    def __init__(self):
        self.data = {}

    def get(self, k, default=None):
        return copy.deepcopy(self.data.get(k, default))

    def put(self, k, v):
        self.data[k] = copy.deepcopy(v)


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store()
        self.book = DonorBook(self.tmp.name, self.store)
        self.ids = [
            self.book.add(n, "92300111222" + str(i))["donor"]["id"]
            for i, n in enumerate(["Zara", "Ahmed", "Ali"])
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def ids_for(self, tab):
        return [r["id"] for r in self.book.list(tab)["items"]]

    def test_independent_append_order_and_durable_ranks(self):
        for i in self.ids:
            self.book.update(i, important=True)
        for i in reversed(self.ids):
            self.book.update(i, top_donor=True)
        self.assertEqual(self.ids_for("important"), self.ids)
        self.assertEqual(self.ids_for("top"), list(reversed(self.ids)))
        self.book.delivery(self.ids[0], "Sent")
        self.book.update(self.ids[0], name="AAA", donated=True, amount=500)
        self.book = DonorBook(self.tmp.name, self.store)
        self.assertEqual(self.ids_for("important"), self.ids[1:] + self.ids[:1])
        top = [self.ids[0], self.ids[2], self.ids[1]]  # known amount first, rest keep manual order
        self.assertEqual(self.ids_for("top"), top)
        self.assertEqual(
            [r["id"] for r in self.book.recipients("important")], self.ids[1:] + self.ids[:1]
        )  # sent people sink to the end
        self.assertEqual([r["id"] for r in self.book.recipients("top")], top)
        self.assertEqual(self.book.list("important", query="Ali")["items"][0]["important_rank"], 3)

    def test_duplicate_mark_keeps_rank_and_readd_appends(self):
        for i in self.ids:
            self.book.update(i, important=True)
        self.book.update(self.ids[0], important=True)
        self.assertEqual(self.ids_for("important"), self.ids)
        self.book.update(self.ids[0], important=False)
        self.book.update(self.ids[0], important=True)
        self.assertEqual(self.ids_for("important"), self.ids[1:] + self.ids[:1])

    def test_top_requires_important_but_memberships_are_independent(self):
        with self.assertRaises(ValueError):
            self.book.update(self.ids[0], top_donor=True)
        self.book.update(self.ids[0], important=True)
        self.book.update(self.ids[0], top_donor=True)
        self.book.update(self.ids[0], important=False)
        self.assertEqual(self.ids_for("top"), self.ids[:1])
        self.book.update(self.ids[0], top_donor=False)
        self.assertEqual(self.ids_for("top"), [])

    def test_legacy_migration_keeps_members_and_saves_once(self):
        raw = self.store.get("donor_book")
        for r in raw["records"]:
            r["important"] = True
        self.store.put("donor_book", raw)
        self.book = DonorBook(self.tmp.name, self.store)
        order = self.ids_for("important")
        self.assertEqual(set(order), set(self.ids))
        self.assertTrue(
            all(r.get("important_order") for r in self.store.get("donor_book")["records"])
        )
        self.book = DonorBook(self.tmp.name, self.store)
        self.assertEqual(self.ids_for("important"), order)

    def test_top_batch_parser(self):
        self.assertEqual(send_request("send to top donors with 3 minute gap")["scope"], "top")

    def test_queued_batch_follows_top_rank_without_touching_delivery_safety(self):
        from donor_delivery import DonorDelivery

        for i in self.ids:
            self.book.update(i, important=True)
        for i in reversed(self.ids):
            self.book.update(i, top_donor=True)
        jobs = DonorDelivery(
            self.tmp.name,
            self.store,
            self.book,
            lambda body: (_ for _ in ()).throw(AssertionError("No real sends")),
            lambda: "Saved full message",
            lambda: True,
            lambda: False,
            lambda p: True,
            lambda name: (name, "Brother"),
            variants=lambda n: ["Version " + str(i) for i in range(n)],
        )
        jobs.start("top", 180, run=False, skip_contacted=False)
        self.assertEqual(jobs._load()["jobs"][-1]["ids"], list(reversed(self.ids)))
        self.assertEqual(jobs._load()["jobs"][-1]["gap_seconds"], 180)

    def test_case_restore_keeps_independent_ranks(self):
        for i in self.ids:
            self.book.update(i, important=True)
        for i in reversed(self.ids):
            self.book.update(i, top_donor=True)
        saved = self.book.export_case_fields()
        self.book.import_case_fields()
        self.assertEqual(self.ids_for("top"), [])
        self.book.import_case_fields(saved)
        self.assertEqual(self.ids_for("important"), self.ids)
        self.assertEqual(self.ids_for("top"), list(reversed(self.ids)))


class AutoRankTests(unittest.TestCase):
    setUp, tearDown, ids_for = RankingTests.setUp, RankingTests.tearDown, RankingTests.ids_for

    def test_top_sorted_by_known_total_unverified_last_and_no_zero(self):
        for i in self.ids:
            self.book.update(i, important=True)
            self.book.update(i, top_donor=True)
        self.book.update(self.ids[1], normal_amount=5000)
        self.book.update(self.ids[2], donated=True, amount=2000)
        rows = self.book.list("top")["items"]
        self.assertEqual([r["id"] for r in rows], [self.ids[1], self.ids[2], self.ids[0]])
        self.assertEqual([r["top_rank"] for r in rows], [1, 2, 3])
        self.assertIsNone(rows[2]["known_total"])
        self.assertTrue(rows[2]["unverified"])
        self.assertEqual(rows[0]["historical_amount"], 5000)
        self.assertIsNone(rows[0]["current_amount"])
        self.assertEqual(self.book.list("top")["items"][0]["donor_rank"], 1)
        self.assertEqual([r["id"] for r in self.book.recipients("top")], [r["id"] for r in rows])
        self.book = DonorBook(self.tmp.name, self.store)
        self.assertEqual(self.ids_for("top"), [r["id"] for r in rows])
