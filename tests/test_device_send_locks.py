"""Independent WhatsApp devices can upload concurrently. Fake sends only."""

import gc
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_manual_sends import app
import test_manual_sends as fixture


class DeviceSendLocks(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def routing(self):
        return patch.multiple(
            app,
            DEVICE="main-device",
            LINES={
                "giki": SimpleNamespace(device=lambda: "device-one"),
                "giki2": SimpleNamespace(device=lambda: "device-two"),
                "alias": SimpleNamespace(device=lambda: "device-one"),
                "main_alias": SimpleNamespace(device=lambda: "main-device"),
                "missing": SimpleNamespace(device=lambda: ""),
            },
        )

    def parallel(self, first, second, *, independent):
        entered, released, done = threading.Event(), threading.Event(), threading.Event()
        errors = []

        def hold():
            entered.set()
            if not released.wait(3):
                raise RuntimeError("test did not release the fake upload")

        def worker(fn):
            try:
                fn()
            except BaseException as error:
                errors.append(error)

        one = threading.Thread(target=worker, args=(lambda: first(hold),), daemon=True)
        two = threading.Thread(target=worker, args=(lambda: second(done.set),), daemon=True)
        one.start()
        self.assertTrue(entered.wait(2))
        two.start()
        try:
            self.assertEqual(done.wait(0.2), independent)
        finally:
            released.set()
            one.join(2)
            two.join(2)
        self.assertFalse(one.is_alive())
        self.assertFalse(two.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(done.is_set())

    def wire(self, line):
        def call(fn):
            with app.on_line(line):
                app.serialized_send(fn)()

        return call

    def test_wire_upload_does_not_block_another_device_or_main(self):
        with self.routing():
            for other in ("giki2", ""):
                with self.subTest(other=other):
                    self.parallel(self.wire("giki"), self.wire(other), independent=True)

    def test_aliases_of_the_same_physical_device_still_serialize(self):
        with self.routing():
            self.parallel(self.wire("giki"), self.wire("alias"), independent=False)
            self.parallel(self.wire(""), self.wire("main_alias"), independent=False)

    def test_other_send_cannot_enter_between_messages_in_one_chat(self):
        steps = []

        def chat(hold):
            with app.send_chat("giki"):
                app.serialized_send(steps.append)("first attachment")
                hold()
                app.serialized_send(steps.append)("second attachment")
                app.serialized_send(steps.append)("share message")

        def competing(done):
            self.wire("alias")(lambda: (steps.append("next chat"), done()))

        with self.routing():
            self.parallel(chat, competing, independent=False)
        self.assertEqual(
            steps, ["first attachment", "second attachment", "share message", "next chat"]
        )

    def test_missing_device_never_calls_the_transport(self):
        called = []
        with self.routing(), app.on_line("missing"), self.assertRaises(ValueError):
            app.serialized_send(lambda: called.append(1))()
        self.assertEqual(called, [])

    def test_nested_sends_reuse_a_reentrant_wire_lock(self):
        called = []

        @app.serialized_send
        def nested():
            return app.serialized_send(lambda: called.append(1))()

        with self.routing(), app.on_line("giki"):
            nested()
        self.assertEqual(called, [1])

    def test_outer_send_lock_does_not_block_another_device(self):
        gates = {}

        def image(phone, _text):
            gates[phone]()
            return {"code": "SUCCESS"}

        def sender(line, phone):
            def call(fn):
                gates[phone] = fn
                app.send_custom(
                    {
                        "line": line,
                        "target": "phone",
                        "phone": phone,
                        "message": "Synthetic message",
                        "poster": True,
                        "kind": "owner_text",
                    }
                )

            return call

        with self.routing(), patch.object(app, "send_image", side_effect=image):
            self.parallel(
                sender("giki", "923001234590"), sender("giki2", "923001234591"), independent=True
            )

    def test_same_dm_recipient_does_not_upload_simultaneously_on_two_devices(self):
        # The outer fake upload blocks; the second device may enter only after it.
        gates = {}

        def upload(phone, _text):
            gates[threading.current_thread().name]()
            return {"code": "SUCCESS"}

        def call(line):
            def dispatch(fn):
                gates[threading.current_thread().name] = fn
                app.send_custom(
                    {
                        "line": line,
                        "target": "phone",
                        "phone": "923001234592",
                        "message": "Synthetic message",
                        "poster": True,
                        "kind": "owner_text",
                    }
                )

            return dispatch

        with self.routing(), patch.object(app, "send_image", side_effect=upload):
            self.parallel(call("giki"), call("giki2"), independent=False)

    def test_real_poster_paths_keep_headers_recipients_and_both_receipts(self):
        barrier = threading.Barrier(2)
        uploaded, results, errors = [], [], []

        def upload(args, **kwargs):
            header = next(a for a in args if a.startswith("X-Device-Id:"))
            phone = next(a for a in args if a.startswith("phone="))
            uploaded.append((header, phone))
            barrier.wait(2)
            return SimpleNamespace(
                stdout=json.dumps({"code": "SUCCESS", "results": {"message_id": header}}).encode()
            )

        def send(line, phone):
            try:
                results.append(
                    app.send_custom(
                        {
                            "line": line,
                            "target": "phone",
                            "phone": phone,
                            "message": "Synthetic message",
                            "poster": True,
                            "kind": "owner_text",
                        }
                    )
                )
            except BaseException as error:
                errors.append(error)

        original_get = app.STORE.get

        def slow_get(key, default=None):
            value = original_get(key, default)
            if key == "last_sent":
                time.sleep(0.01)  # expose a stale-map overwrite without the state lock
            return value

        with (
            self.routing(),
            patch.object(app.subprocess, "run", side_effect=upload),
            patch.object(app.STORE, "get", side_effect=slow_get),
        ):
            threads = [
                threading.Thread(target=send, args=values, daemon=True)
                for values in (("giki", "923001234593"), ("giki2", "923001234594"))
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(4)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual([r["code"] for r in results], ["SUCCESS", "SUCCESS"])
        self.assertCountEqual(
            uploaded,
            [
                ("X-Device-Id: device-one", "phone=923001234593"),
                ("X-Device-Id: device-two", "phone=923001234594"),
            ],
        )
        self.assertEqual(set(app.STORE.get("last_sent")), {"923001234593", "923001234594"})
        self.assertEqual(set(app.STORE.get("last_deliveries")), {"923001234593", "923001234594"})

    def test_finished_device_locks_are_not_retained(self):
        pool = type(app._DEVICE_LOCKS)()
        locks = [pool.get(("wire", "gateway", "device" + str(n))) for n in range(20)]
        self.assertEqual(len(pool.snapshot()), 20)
        del locks
        gc.collect()
        self.assertEqual(pool.snapshot(), [])

    def test_device_change_while_waiting_refuses_transport_and_releases_lock(self):
        chosen, state = threading.Event(), {"id": "device-one"}

        def selected():
            value = state["id"]
            if threading.current_thread().name == "route-waiter":
                chosen.set()
            return value

        errors, sent = [], []

        def waiting():
            try:
                self.wire("giki")(lambda: sent.append(1))
            except ValueError as error:
                errors.append(str(error))

        with self.routing():
            app.LINES["giki"] = SimpleNamespace(device=selected)
            with app.on_line("giki"):
                held = app._wire_lock()
                held.acquire()
            thread = threading.Thread(target=waiting, name="route-waiter", daemon=True)
            thread.start()
            self.assertTrue(chosen.wait(1))
            state["id"] = "device-new"
            held.release()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(sent, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("device changed", errors[0])
            with app.on_line("giki"):
                app.serialized_send(lambda: sent.append(2))()
            self.assertEqual(sent, [2])

    def test_device_change_during_preparation_fails_closed(self):
        sent = []
        with self.routing(), app.on_line("giki"):

            @app.serialized_send
            def prepare():
                app.LINES["giki"] = SimpleNamespace(device=lambda: "device-new")
                sent.append(app.device())

            with self.assertRaisesRegex(ValueError, "device changed"):
                prepare()
        self.assertEqual(sent, [])

    def test_main_device_transition_cannot_split_an_alias_lock(self):
        first, release, other = threading.Event(), threading.Event(), threading.Event()

        def main_upload():
            with app.on_line(""), app._wire_lock():
                first.set()
                release.wait(2)

        with self.routing():
            thread = threading.Thread(target=main_upload, daemon=True)
            thread.start()
            self.assertTrue(first.wait(1))
            app.DEVICE = "main-new"
            alias = threading.Thread(target=lambda: self.wire("main_alias")(other.set), daemon=True)
            alias.start()
            try:
                self.assertFalse(other.wait(0.1))
            finally:
                release.set()
                thread.join(2)
                alias.join(2)
            self.assertTrue(other.is_set())

    def test_restart_guard_sees_an_active_giki_device_lock(self):
        idle = SimpleNamespace(active=False, _cache={"jobs": []})
        hub = SimpleNamespace(
            jobs=idle,
            volunteers=SimpleNamespace(jobs=idle),
            giki=SimpleNamespace(jobs=idle),
            giki2=SimpleNamespace(jobs=idle),
        )
        entered, release = threading.Event(), threading.Event()

        def upload():
            with app.on_line("giki"), app._send_lock():
                entered.set()
                release.wait(2)

        with self.routing(), patch.object(app, "donors", return_value=hub):
            thread = threading.Thread(target=upload, daemon=True)
            thread.start()
            self.assertTrue(entered.wait(1))
            try:
                self.assertTrue(app.sending_now())
            finally:
                release.set()
                thread.join(2)
            self.assertFalse(app.sending_now())


if __name__ == "__main__":
    unittest.main()
