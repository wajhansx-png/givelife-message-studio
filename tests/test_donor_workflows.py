import hashlib, time, types, unittest
from unittest.mock import patch
import test_donor_hub as hub
import manual_commands, chat_policy, persist
from donor_messages import MessageBank
from donor_book import DonorBook


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = hub.IntegrationTests()
        self.fixture.setUp()
        self.app = self.fixture.app
        if not self.app.AUTO.exists():
            self.app.AUTO.write_text('{"on":false}')
        self.auto = self.app.AUTO.read_bytes()
        self.hold = self.app.HOLD.read_bytes()

    def tearDown(self):
        self.app.AUTO.write_bytes(self.auto)
        self.app.HOLD.write_bytes(self.hold)
        self.fixture.tearDown()

    def test_dm_pause_does_not_stop_groups(self):
        self.app.AUTO.write_text('{"on":true}')
        before = self.app.HOLD.read_bytes()
        with patch.object(self.app, "cancel_jobs") as groups:
            result = self.app.manual_command("hold dm's")
            groups.assert_not_called()
        self.assertTrue(self.app.auto_on())
        self.assertEqual(before, self.app.HOLD.read_bytes())
        self.assertTrue(self.app.donors().paused)
        self.assertIn("Group posting", result["reply"])
        self.assertFalse(chat_policy.permitted("hold", "hold dm's"))
        self.app.manual_command("resume dms")
        self.assertFalse(self.app.donors().paused)
        self.assertTrue(self.app.auto_on())

    def test_context_control_scope(self):
        for text in (
            "hold dms",
            "hold my DMs",
            "pause personal messages",
            "stop donor messages",
            "hold dms and keep groups running",
        ):
            self.assertEqual(manual_commands.parse(text)["kind"], "stop_dms", text)
        for text in ("hold everything", "stop dms and groups"):
            self.assertEqual(manual_commands.parse(text)["kind"], "hold")
        self.assertIsNone(manual_commands.dm_control("dont stop dms"))

    def test_new_pause_rejects_older_private_send_tool(self):
        callbacks = self.app.chat_callbacks(
            "send to important donors", self.app.OWNER_REVISION, "old-dm-task"
        )
        self.app.donors().pause_personal()
        with self.assertRaisesRegex(ValueError, "newer instruction"):
            callbacks["donor_action"](action="send", scope="important")

    def test_prior_confirmed_and_legacy_campaign_contacts_are_eligible(self):
        app = self.app
        phone = "923001234567"
        digest = hashlib.sha256(phone.encode()).hexdigest()
        jid = hashlib.sha256((phone + "@s.whatsapp.net").encode()).hexdigest()
        with (
            patch.object(app, "CAMPAIGN_CONTACTED", {digest}),
            patch.object(app, "BLOCKED", {digest}),
        ):
            app.STORE.put("dm_recipient_" + jid, {"state": "SUCCESS"})
            self.assertTrue(app.donors().eligible(phone))
            app.STORE.put("optout_" + digest, True)
            self.assertFalse(app.donors().eligible(phone))

    def test_uncertain_is_not_automatically_retried(self):
        digest = hashlib.sha256(b"923001234567").hexdigest()
        self.app.STORE.put("dm_recipient_" + digest, {"state": "UNCERTAIN"})
        self.assertTrue(
            self.app.donors().eligible("923001234567"),
            "an explicit new batch may send again; nothing retries by itself",
        )

    def test_old_zero_send_batch_is_not_displayed_as_success(self):
        result = self.app.donors().jobs._public(
            {"state": "Completed", "sent": 0, "skipped": 3, "total": 3}
        )
        self.assertEqual(result["state"], "Nothing sent")
        self.assertIn("No DM was sent", result["error"])

    def test_chat_send_20_dms_continues_through_the_whole_audience(self):
        registry = self.app.donors()
        for i in range(45):
            d = registry.book.add("Donor " + str(i), "92300" + str(1000000 + i))["donor"]
            registry.book.update(d["id"], important=True)
        with patch("donor_delivery.threading.Thread"):
            result = registry.command(
                "send 20 dms to important donors with 3 minutes gap", request_id="chat-rounds"
            )
        job = registry.jobs._load()["jobs"][-1]
        self.assertEqual((job["total"], job["chunk"], job["gap_seconds"]), (45, 20, 180))
        self.assertIn("by itself", result["reply"])

    def test_bare_stop_stops_a_running_donor_batch_and_does_nothing_otherwise(self):
        registry = self.app.donors()
        registry.book.add("Ali", "923001234567")["donor"]
        self.assertIsNone(registry.command("stop", request_id="nothing-running"))
        registry.jobs.active = "running"
        for word in ("stop", "Stop it", "pause", "ruk jao", "band karo", "stop all"):
            registry.jobs.stop.clear()
            result = registry.command(word, request_id="x" + word)
            self.assertIn("stopped", result["reply"].lower(), word)
            self.assertTrue(registry.jobs.stop.is_set(), word)
        registry.jobs.active = None

    def test_chat_continue_resumes_a_stopped_batch_without_resending(self):
        registry = self.app.donors()
        for i in range(6):
            d = registry.book.add("Donor " + str(i), "92300" + str(1000000 + i))["donor"]
            registry.book.update(d["id"], important=True)
        with patch("donor_delivery.threading.Thread"):
            registry.command("send 3 dms to important donors", request_id="first-run")
        job = registry.jobs._load()["jobs"][-1]
        first = job["ids"][:2]
        data = registry.jobs._load()
        data["jobs"][-1].update(
            state="Stopped",
            receipts=[{"id": i, "name": "x", "state": "Sent"} for i in first],
            boot=registry.jobs.boot,
        )
        registry.jobs._save(data)
        registry.jobs.active = None
        with patch("donor_delivery.threading.Thread"):
            result = registry.command("continue", request_id="second-run")
        again = registry.jobs._load()["jobs"][-1]
        self.assertEqual(again["ids"], job["ids"][2:])
        self.assertIn("Continuing", result["reply"])

    def test_20_unique_messages_first_immediate_then_chosen_gap(self):
        registry = self.app.donors()
        for i in range(25):
            d = registry.book.add("Donor " + str(i), "92300" + str(1000000 + i))["donor"]
            registry.book.update(d["id"], important=True)
        registry.start_batch(
            scope="important", gap_seconds=240, run=False, request_id="twenty-test"
        )
        job = registry.jobs._load()["jobs"][-1]
        self.assertEqual(job["total"], 20)
        self.assertEqual(len(set(job["captions"])), 20)
        clock = [1000.0]
        sent = []

        def send(body):
            sent.append((clock[0], body))
            return {"code": "SUCCESS"}

        registry.jobs.send = send

        def wait(seconds):
            clock[0] += seconds
            return False

        with (
            patch("donor_delivery.time.time", side_effect=lambda: clock[0]),
            patch.object(registry.jobs.stop, "wait", side_effect=wait),
        ):
            registry.jobs._run(job)
        self.assertEqual(len(sent), 20)
        self.assertEqual(sent[0][0], 1000.0)
        self.assertTrue(sent[0][1]["first_in_batch"])
        self.assertTrue(all(sent[i][0] - sent[i - 1][0] >= 240 for i in range(1, 20)))
        self.assertEqual(registry.jobs.status()["sent"], 20)

    def test_message_bank_complete_and_edit_persists(self):
        import dm_composer

        registry = self.app.donors()
        bank = registry.messages.get()
        self.assertEqual(len(bank["items"]), 20)
        self.assertEqual(len({r["text"] for r in bank["items"]}), 20)
        for r in bank["items"]:
            self.assertTrue(dm_composer.complete(r["text"]))
            self.assertLess(r["text"].index("2,000"), r["text"].index("1,000"))
            self.assertIn("💔 ", r["text"])
            self.assertIn("⚠️ *", r["text"])
            self.assertIn("💰 *_Rs. ", r["text"])
            self.assertRegex(r["text"], r"\n_[^\n]+_ ")
            self.assertIn("📲 *03097458815*", r["text"])
            self.assertIn("Reply *Done* after donating.", r["text"])
            self.assertIn("short of breath", r["text"])
            self.assertNotIn("Name Brother", r["text"])
        row = bank["items"][0]
        edited = row["text"].replace("you can close this chat", "you can close this message")
        registry.messages.update(row["id"], edited)
        restored = MessageBank(self.app)
        self.assertEqual(restored.get()["items"][0]["text"], edited)

    def test_batch_default_four_minutes_and_max_ten(self):
        registry = self.app.donors()
        d = registry.book.add("Ali", "03001234567")["donor"]
        registry.book.update(d["id"], important=True)
        result = registry.start_batch(scope="important", run=False, request_id="default-gap")
        self.assertEqual(result["job"]["gap_seconds"], 240)
        registry.jobs.active = None
        with self.assertRaisesRegex(ValueError, "5 seconds to 10 minutes"):
            registry.start_batch(scope="important", gap_seconds=601, run=False)

    def test_book_reads_are_cached_and_status_survives_restart(self):
        class CountingStore(hub.Store):
            reads = 0

            def get(self, k, d=None):
                self.reads += 1
                return super().get(k, d)

        store = CountingStore()
        book = DonorBook(self.fixture.scope.name, store)
        d = book.add("Ali", "03001234567")["donor"]
        reads = store.reads
        for _ in range(100):
            book.list()
        self.assertEqual(store.reads, reads)
        book.update(d["id"], donated=True, amount=2000)
        other = DonorBook(self.fixture.scope.name, store)
        self.assertEqual(other.list()["counts"]["donated_amount"], 2000)

    def test_first_explicit_batch_send_has_no_prior_send_cooldown(self):
        app = self.app
        registry = app.donors()
        registry.book.add("Ali", "03001234567")
        day = (
            app.datetime.datetime.fromtimestamp(
                time.time(), app.datetime.timezone(app.datetime.timedelta(hours=5))
            )
            .date()
            .isoformat()
        )
        app.STORE.put("dm_daily", {"day": day, "count": 1, "last": time.time()})
        with patch.object(app, "send_image", return_value={"code": "SUCCESS"}):
            result = app.send_custom(
                {
                    "target": "phone",
                    "phone": "03001234567",
                    "message": app.get_message("dm")["text"],
                    "kind": "donor_batch",
                    "first_in_batch": True,
                    "poster": True,
                }
            )
        self.assertEqual(result["code"], "SUCCESS")


class PoolTests(unittest.TestCase):
    def test_stale_read_reconnects_but_write_is_not_replayed(self):
        created = []

        class DB:
            closed = False

            def execute(self, sql, args=None):
                if len(created) == 1:
                    raise ConnectionError("stale socket")
                return types.SimpleNamespace(fetchone=lambda: ("ok",))

            def close(self):
                self.closed = True

        def connect(*a, **k):
            db = DB()
            created.append(db)
            return db

        with (
            patch.object(
                persist,
                "psycopg",
                types.SimpleNamespace(connect=connect, OperationalError=ConnectionError),
            ),
            patch.object(persist, "Jsonb", lambda x: x),
        ):
            self.assertEqual(persist.CloudStore("fake").get("a"), "ok")
            self.assertEqual(len(created), 2)
            created.clear()
            with self.assertRaises(ConnectionError):
                persist.CloudStore("fake").put("a", 1)
            self.assertEqual(len(created), 1, "Uncertain writes must never automatically replay")

    def test_reuses_connection_and_batches_key_reads(self):
        calls = []

        class DB:
            closed = False

            def execute(self, sql, args=None):
                calls.append(sql)
                return types.SimpleNamespace(
                    fetchone=lambda: ({"a": 1},), fetchall=lambda: [("a", 1), ("b", 2)]
                )

            def close(self):
                self.closed = True

        factory = types.SimpleNamespace(
            connect=lambda *a, **k: DB(), OperationalError=ConnectionError
        )
        with patch.object(persist, "psycopg", factory):
            store = persist.CloudStore("fake")
            with patch.object(factory, "connect", wraps=factory.connect) as connect:
                for _ in range(40):
                    store.get("a")
                self.assertEqual(connect.call_count, 1)
                self.assertEqual(store.get_many(["a", "b"]), {"a": 1, "b": 2})
            self.assertEqual(len(calls), 41)


if __name__ == "__main__":
    unittest.main()
