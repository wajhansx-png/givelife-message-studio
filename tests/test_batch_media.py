import base64, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import batch_media
import test_manual_sends as fixture
from test_manual_sends import app


class MediaTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_private_pdf_survives_missing_local_file_and_uses_file_gateway(self):
        data = (
            "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4\nTest document").decode()
        )
        ident = batch_media.save(app.STORE, data)
        path, mime = batch_media.load(app.STORE, ident, app.ATT)
        self.assertEqual(mime, "application/pdf")
        path.unlink()
        self.assertTrue(batch_media.load(app.STORE, ident, app.ATT)[0].exists())
        with patch.object(
            app.subprocess,
            "run",
            return_value=type("Response", (), {"stdout": b'{"code":"SUCCESS"}'})(),
        ) as wire:
            result = app.send_batch_attachment("923001234567", "Hi Ali", ident)
        self.assertEqual(result["code"], "SUCCESS")
        args = wire.call_args.args[0]
        self.assertIn(app.GOWA_URL + "/send/file", args)
        self.assertTrue(any(v.startswith("file=@") for v in args))

    def test_invalid_uploads_and_path_tokens_are_rejected(self):
        for data in (
            "not a file",
            "data:application/pdf;base64,YmFk",
            "data:text/html;base64,PGgxPng8L2gxPg==",
        ):
            with self.assertRaises(ValueError):
                batch_media.save(app.STORE, data)
        with self.assertRaises(ValueError):
            batch_media.load(app.STORE, "../../secret", app.ATT)

    def test_image_and_video_use_the_correct_gateway(self):
        for mime, raw, endpoint in [
            ("image/jpeg", b"\xff\xd8\xfftest", "image"),
            ("video/mp4", b"\x00\x00\x00\x18ftypisomtest", "video"),
        ]:
            ident = batch_media.save(
                app.STORE, "data:" + mime + ";base64," + base64.b64encode(raw).decode()
            )
            with patch.object(
                app.subprocess,
                "run",
                return_value=type("Response", (), {"stdout": b'{"code":"SUCCESS"}'})(),
            ) as wire:
                app.send_batch_attachment("923001234567", "Caption", ident)
            self.assertIn(app.GOWA_URL + "/send/" + endpoint, wire.call_args.args[0])

    def test_exclusion_reason_distinguishes_own_account_and_optout(self):
        hub = app.donors()
        self.assertIn("connected account", hub.exclusion_reason(app.norm_phone(app.OWNER_PHONE)))
        import hashlib

        phone = "923001234567"
        app.STORE.put("optout_" + hashlib.sha256(phone.encode()).hexdigest(), True)
        self.assertIn("opted out", hub.exclusion_reason(phone))
        self.assertFalse(hub.eligible(phone))


if __name__ == "__main__":
    unittest.main()
