import hashlib, time, types, unittest, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
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

    def test_batch_replay_does_not_advance_real_message_rotation(self):
        registry = self.app.donors()
        for name, phone in (("Ali", "03001234567"), ("Sara", "03001234568")):
            registry.book.add(name, phone)
        first = registry.jobs.start("all", 60, request_id="same-real-bank", run=False)
        rotation = self.app.STORE.get(registry.messages.ROTATION_KEY)
        again = registry.jobs.start("all", 60, request_id="same-real-bank", run=False)
        self.assertEqual(again["job"]["id"], first["job"]["id"])
        self.assertEqual(self.app.STORE.get(registry.messages.ROTATION_KEY), rotation)
        self.assertEqual(len(registry.jobs._load()["jobs"]), 1)
        with self.assertRaisesRegex(ValueError, "different batch"):
            registry.jobs.start("all", 120, request_id="same-real-bank", run=False)
        self.assertEqual(self.app.STORE.get(registry.messages.ROTATION_KEY), rotation)

    def test_batch_replay_with_a_stale_second_worker_does_not_reserve_again(self):
        registry = self.app.donors()
        for name, phone in (("Ali", "03001234567"), ("Sara", "03001234568")):
            registry.book.add(name, phone)
        jobs = registry.jobs
        second = type(jobs)(
            self.fixture.scope.name, jobs.store, jobs.book, jobs.send, jobs.caption,
            jobs.connected, jobs.held, jobs.eligible, jobs.name_for,
            variants=jobs.variants, case_closed=jobs.case_closed, reserve=jobs.reserve,
            refresh_caption=jobs.refresh_caption, balance=jobs.balance,
        )
        second._load()  # This worker read state before the first worker started.
        first = jobs.start("all", 60, request_id="stale-worker", run=False)
        rotation = self.app.STORE.get(registry.messages.ROTATION_KEY)
        again = second.start("all", 60, request_id="stale-worker", run=False)
        self.assertEqual(again["job"]["id"], first["job"]["id"])
        self.assertEqual(self.app.STORE.get(registry.messages.ROTATION_KEY), rotation)

    def test_concurrent_sqlite_batch_claim_reserves_and_starts_once(self):
        db = Path(self.fixture.scope.name) / "shared.sqlite"
        self.app.STORE = persist.SqliteStore(db)
        self.app.STORE.initialize()
        registry = self.app.donors()
        for name, phone in (("Ali", "03001234567"), ("Sara", "03001234568")):
            registry.book.add(name, phone)
        jobs = registry.jobs
        second = type(jobs)(
            self.fixture.scope.name, persist.SqliteStore(db), jobs.book, jobs.send,
            jobs.caption, jobs.connected, jobs.held, jobs.eligible, jobs.name_for,
            variants=jobs.variants, case_closed=jobs.case_closed, reserve=jobs.reserve,
            refresh_caption=jobs.refresh_caption, balance=jobs.balance,
        )
        gate = threading.Barrier(2)

        def connected():
            gate.wait(timeout=5)
            return True

        reserve = unittest.mock.Mock(wraps=jobs.reserve)
        jobs.reserve = second.reserve = reserve
        jobs.connected = second.connected = connected
        with patch.object(jobs, "_run") as first_run, patch.object(second, "_run") as second_run:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(job.start, "all", 60, request_id="concurrent", run=True)
                           for job in (jobs, second)]
                results = [future.result(timeout=10) for future in futures]
            self.assertEqual(first_run.call_count + second_run.call_count, 1)
        self.assertEqual(results[0]["job"]["id"], results[1]["job"]["id"])
        self.assertEqual(reserve.call_count, 1)
        self.assertEqual(len(self.app.STORE.get(jobs.KEY)["jobs"]), 1)

    def test_disconnected_batch_does_not_advance_rotation(self):
        registry = self.app.donors()
        registry.book.add("Ali", "03001234567")
        before = self.app.STORE.get(registry.messages.ROTATION_KEY)
        with patch.object(registry.jobs, "connected", return_value=False):
            with self.assertRaisesRegex(ValueError, "disconnected"):
                registry.jobs.start("all", 60, request_id="offline", run=False)
        self.assertEqual(self.app.STORE.get(registry.messages.ROTATION_KEY), before)

    def test_active_batch_does_not_consume_more_wording(self):
        registry = self.app.donors()
        registry.book.add("Ali", "03001234567")
        registry.jobs.start("all", 60, request_id="first-batch", run=False)
        before = self.app.STORE.get(registry.messages.ROTATION_KEY)
        with self.assertRaisesRegex(ValueError, "already running"):
            registry.jobs.start("all", 60, request_id="second-batch", run=False)
        self.assertEqual(self.app.STORE.get(registry.messages.ROTATION_KEY), before)

    def test_failed_or_crashed_start_is_never_reserved_again(self):
        self.app.STORE = persist.SqliteStore(Path(self.fixture.scope.name) / "claims.sqlite")
        self.app.STORE.initialize()
        registry = self.app.donors()
        registry.book.add("Ali", "03001234567")
        for number, error in enumerate((RuntimeError("preparation failed"), SystemExit("crash"))):
            rid = "interrupted-" + str(number)
            before = self.app.STORE.get(registry.messages.ROTATION_KEY)
            with patch.object(registry.jobs, "reserve", side_effect=error) as reserve:
                with self.assertRaises(type(error)):
                    registry.jobs.start("all", 60, request_id=rid, run=False)
                again = registry.jobs.start("all", 60, request_id=rid, run=False)
                self.assertIn(again["job"]["state"], ("Starting", "Interrupted"))
                self.assertEqual(reserve.call_count, 1)
            self.assertEqual(self.app.STORE.get(registry.messages.ROTATION_KEY), before)
            self.assertFalse(self.app.STORE.get(registry.jobs.KEY, {}).get("jobs"))

    def test_failure_after_rotation_keeps_claim_and_does_not_repeat_rotation(self):
        self.app.STORE = persist.SqliteStore(Path(self.fixture.scope.name) / "rotated.sqlite")
        self.app.STORE.initialize()
        registry = self.app.donors()
        registry.book.add("Ali", "03001234567")
        reserve = registry.jobs.reserve

        def fail_after_reserving(count):
            reserve(count)
            raise RuntimeError("reply lost")

        with patch.object(registry.jobs, "reserve", side_effect=fail_after_reserving) as called:
            with self.assertRaisesRegex(RuntimeError, "reply lost"):
                registry.jobs.start("all", 60, request_id="after-rotation", run=False)
            rotated = self.app.STORE.get(registry.messages.ROTATION_KEY)
            again = registry.jobs.start("all", 60, request_id="after-rotation", run=False)
            self.assertEqual(again["job"]["state"], "Interrupted")
            self.assertEqual(called.call_count, 1)
            self.assertEqual(self.app.STORE.get(registry.messages.ROTATION_KEY), rotated)
        with self.assertRaisesRegex(ValueError, "different batch"):
            registry.jobs.start("all", 60, request_id="after-rotation", follow_up="Changed", run=False)

    def test_request_claim_survives_job_history_trimming(self):
        self.app.STORE = persist.SqliteStore(Path(self.fixture.scope.name) / "trimmed.sqlite")
        self.app.STORE.initialize()
        registry = self.app.donors()
        registry.book.add("Ali", "03001234567")
        first = registry.jobs.start("all", 60, request_id="old-job", run=False)
        registry.jobs._update(first["job"]["id"], state="Stopped", failed=1,
                              receipts=[{"id": "example", "state": "Uncertain"}])
        registry.jobs.import_jobs({"jobs": []})
        with patch.object(registry.jobs, "reserve") as reserve:
            again = registry.jobs.start("all", 60, request_id="old-job", run=False)
            reserve.assert_not_called()
        self.assertEqual(first["job"]["id"], again["job"]["id"])
        self.assertEqual(again["job"]["state"], "Stopped")
        self.assertEqual(again["job"]["receipts"][0]["state"], "Uncertain")

    def test_failure_after_job_save_does_not_launch_or_reserve_again(self):
        self.app.STORE = persist.SqliteStore(Path(self.fixture.scope.name) / "saved.sqlite")
        self.app.STORE.initialize()
        registry = self.app.donors()
        registry.book.add("Ali", "03001234567")
        save = registry.jobs._save

        def lose_response(data):
            save(data)
            raise RuntimeError("save reply lost")

        with patch.object(registry.jobs, "_save", side_effect=lose_response):
            with self.assertRaisesRegex(RuntimeError, "save reply lost"):
                registry.jobs.start("all", 60, request_id="saved-job", run=False)
        rotated = self.app.STORE.get(registry.messages.ROTATION_KEY)
        with patch.object(registry.jobs, "reserve") as reserve, patch.object(registry.jobs, "_run") as worker:
            again = registry.jobs.start("all", 60, request_id="saved-job", run=True)
            self.assertEqual(again["job"]["state"], "Starting")
            reserve.assert_not_called()
            worker.assert_not_called()
        self.assertEqual(self.app.STORE.get(registry.messages.ROTATION_KEY), rotated)

    def test_orphan_legacy_claim_does_not_guess_by_reserving_again(self):
        self.app.STORE = persist.SqliteStore(Path(self.fixture.scope.name) / "legacy.sqlite")
        self.app.STORE.initialize()
        registry = self.app.donors()
        rid = "legacy-orphan"
        self.app.STORE.claim(registry.jobs.CLAIM + hashlib.sha256(rid.encode()).hexdigest(),
                             {"id": "old", "signature": "unknown", "state": "Starting"})
        with patch.object(registry.jobs, "reserve") as reserve:
            with self.assertRaisesRegex(ValueError, "already tracked"):
                registry.jobs.start("all", 60, request_id=rid, run=False)
            reserve.assert_not_called()

    def test_one_usable_message_cannot_advance_a_rejected_round(self):
        bank = self.app.donors().messages
        before = self.app.STORE.get(bank.ROTATION_KEY)
        with patch.object(bank, "_rotation_texts", return_value=["One complete saved wording"]):
            with self.assertRaisesRegex(ValueError, "at least 2"):
                bank.reserve_round(2)
        self.assertEqual(self.app.STORE.get(bank.ROTATION_KEY), before)

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
