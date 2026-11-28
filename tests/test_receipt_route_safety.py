"""Revoke only the selected device's own message; fake transport throughout."""

import io
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_manual_sends as fixture
from test_manual_sends import app


class ReceiptRouteSafety(unittest.TestCase):
    def setUp(self):
        fixture.SendTests.setUp(self)
        route = patch.multiple(
            app,
            DEVICE="main-device",
            LINES={"giki": SimpleNamespace(device=lambda: "giki-device")},
        )
        route.start()
        self.addCleanup(route.stop)
        self.jid = app.GROUPS["main"][1]

    tearDown = fixture.SendTests.tearDown

    def receipt(self, ident, device="main-device"):
        return {"message_id": ident, "gateway": app.GOWA_URL, "device": device}

    @staticmethod
    def success(*_args, **_kwargs):
        return io.BytesIO(json.dumps({"code": "SUCCESS"}).encode())

    def test_new_receipts_remember_the_device_and_gateway_that_sent_them(self):
        with app.on_line("giki"):
            app.record_delivery(
                self.jid,
                "Approved case",
                {
                    "code": "SUCCESS",
                    "results": {"message_id": "giki-message"},
                },
            )
        row = app.DELIVERIES[self.jid]
        self.assertEqual((row.get("gateway"), row.get("device")), (app.GOWA_URL, "giki-device"))
        self.assertEqual(app.STORE.get("last_deliveries")[self.jid], row)

    def test_matching_receipt_is_used_without_looking_up_another_message(self):
        app.DELIVERIES[self.jid] = self.receipt("my-message")
        with (
            patch.object(app, "group_messages") as lookup,
            patch.object(app.urllib.request, "urlopen", side_effect=self.success) as wire,
        ):
            app.delete_last_group("main")
        lookup.assert_not_called()
        self.assertTrue(wire.call_args.args[0].full_url.endswith("/my-message/revoke"))
        self.assertNotIn(self.jid, app.DELIVERIES)

    def test_other_device_cached_receipt_is_never_revoked_from_main(self):
        other = self.receipt("giki-message", "giki-device")
        app.DELIVERIES[self.jid] = other.copy()
        with (
            patch.object(
                app,
                "group_messages",
                return_value=[
                    {"id": "incoming", "is_from_me": False, "timestamp": "2099"},
                    {"id": "main-message", "is_from_me": True, "timestamp": "2026"},
                ],
            ),
            patch.object(app.urllib.request, "urlopen", side_effect=self.success) as wire,
        ):
            app.delete_last_group("main")
        request = wire.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/main-message/revoke"))
        self.assertEqual(request.get_header("X-device-id"), "main-device")
        self.assertEqual(app.DELIVERIES[self.jid], other)

    def test_legacy_receipt_requires_verified_own_message_and_cannot_delete_an_incoming_one(self):
        legacy = {"message_id": "unverified-old-device"}
        app.DELIVERIES[self.jid] = legacy.copy()
        with (
            patch.object(
                app,
                "group_messages",
                return_value=[
                    {"id": "someone-elses-message", "is_from_me": False},
                ],
            ),
            patch.object(app.urllib.request, "urlopen") as wire,
        ):
            with self.assertRaisesRegex(ValueError, "own sent message"):
                app.delete_last_group("main")
        wire.assert_not_called()
        self.assertEqual(app.DELIVERIES[self.jid], legacy)

    def test_device_selection_precedes_request_construction_and_own_message_lookup(self):
        app.DELIVERIES[self.jid] = self.receipt("old-device-message")
        original = app._wire_lock

        def switch_and_lock():
            app.DEVICE = "new-device"
            return original()

        with (
            patch.object(app, "_wire_lock", side_effect=switch_and_lock),
            patch.object(
                app,
                "group_messages",
                return_value=[
                    {"id": "new-device-message", "is_from_me": True},
                ],
            ),
            patch.object(app.urllib.request, "urlopen", side_effect=self.success) as wire,
        ):
            app.delete_last_group("main")
        request = wire.call_args.args[0]
        self.assertEqual(request.get_header("X-device-id"), "new-device")
        self.assertTrue(request.full_url.endswith("/new-device-message/revoke"))

    def test_revoke_keeps_a_newer_receipt_even_with_the_same_id_on_another_device(self):
        app.DELIVERIES[self.jid] = self.receipt("same-id")
        errors = []

        def concurrent_receipt():
            try:
                with app.on_line("giki"):
                    app.record_delivery(
                        self.jid,
                        "New confirmed message",
                        {
                            "code": "SUCCESS",
                            "results": {"message_id": "same-id"},
                        },
                    )
            except BaseException as error:
                errors.append(error)

        def revoke(*args, **kwargs):
            thread = threading.Thread(target=concurrent_receipt, daemon=True)
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive(), "receipt lock must not cover network waits")
            return self.success()

        with patch.object(app.urllib.request, "urlopen", side_effect=revoke):
            app.delete_last_group("main")
        self.assertEqual(errors, [])
        self.assertEqual(app.DELIVERIES[self.jid]["device"], "giki-device")
        self.assertEqual(app.STORE.get("last_deliveries")[self.jid]["device"], "giki-device")

    def test_failed_revoke_preserves_receipt_and_does_not_retry(self):
        entry = self.receipt("my-message")
        app.DELIVERIES[self.jid] = entry.copy()
        with patch.object(
            app.urllib.request,
            "urlopen",
            return_value=io.BytesIO(
                json.dumps({"code": "ERROR"}).encode(),
            ),
        ) as wire:
            with self.assertRaisesRegex(ValueError, "refused deletion"):
                app.delete_last_group("main")
        self.assertEqual(wire.call_count, 1)
        self.assertEqual(app.DELIVERIES[self.jid], entry)


if __name__ == "__main__":
    unittest.main()
