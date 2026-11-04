"""Poster and chat attachments can be an MP4 video for DMs and groups."""

import base64, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def url(raw, mime):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


class VideoPoster(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        d = Path(self.dir.name)
        (d / "attachments").mkdir()
        self.patches = [
            patch.object(server, "DATA", d),
            patch.object(server, "ATT", d / "attachments"),
            patch.object(server, "STORE", None),
            patch.object(server, "DONORS", None),
            patch.dict(server.CAMPAIGN, {"running": False}),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])
        self.d = d

    def test_a_video_poster_is_used_for_sends_until_a_picture_replaces_it(self):
        (self.d / "poster.jpg").write_bytes(JPG)
        self.assertEqual(server.poster_media().name, "poster.jpg")
        self.assertEqual(server.save_upload(url(MP4, "video/mp4"), "poster"), "poster")
        self.assertEqual(server.poster_media().name, "poster.mp4")
        server.save_upload(url(JPG, "image/jpeg"), "poster")
        self.assertEqual(server.poster_media().name, "poster.jpg")

    def test_poster_changes_during_an_active_send_and_the_next_message_uses_it(self):
        (self.d / "poster.jpg").write_bytes(JPG)
        busy = type("D", (), {"jobs": type("J", (), {"active": True})()})()
        new = b"\xff\xd8\xff\xe1" + b"\x01" * 64
        with patch.object(server, "DONORS", busy), patch.dict(server.CAMPAIGN, {"running": True}):
            self.assertEqual(server.save_upload(url(new, "image/jpeg"), "dm_poster"), "poster")
        self.assertEqual(server.poster_media("dm").read_bytes(), new)
        self.assertEqual(server.poster_media("group").read_bytes(), new)
        self.assertEqual([x.name for x in self.d.glob("*.tmp")], [])

    def test_missing_local_poster_is_restored_from_saved_data(self):
        store = type("Store", (), {"get": lambda self, key, default=None: {"poster_b64": base64.b64encode(JPG).decode(), "poster_kind": "image"}.get(key, default)})()
        with patch.object(server, "STORE", store):
            self.assertEqual(server.poster_media().read_bytes(), JPG)

    def test_missing_poster_is_reported_before_any_gateway_call(self):
        with patch.object(server.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "poster.*upload|poster.*attach"):
                server.post_media("test@g.us", self.d / "caption.txt", self.d / "missing.jpg")
            run.assert_not_called()

    def test_missing_video_never_falls_back_to_an_old_picture(self):
        (self.d / "poster.jpg").write_bytes(JPG)
        (self.d / "poster-kind.txt").write_text("video")
        selected = server.poster_media()
        self.assertEqual(selected.name, "poster.mp4")
        self.assertFalse(selected.exists())

    def test_video_over_3mb_is_durable_and_restored_without_reverting_to_picture(self):
        class MemoryStore:
            values = {}
            def put(self, key, value):
                self.values[key] = value
            def get(self, key, default=None):
                return self.values.get(key, default)

        raw = MP4 + b"x" * 3_100_000
        (self.d / "poster.jpg").write_bytes(JPG)
        store = MemoryStore()
        with patch.object(server, "STORE", store):
            self.assertEqual(server.save_upload(url(raw, "video/mp4"), "dm_poster"), "poster")
            self.assertEqual(len(base64.b64decode(store.get("poster_video_b64"))), len(raw))
            (self.d / "poster.mp4").unlink()
            self.assertEqual(server.poster_media("dm").read_bytes(), raw)
            self.assertEqual(server.poster_media("group").read_bytes(), raw)

    def test_failed_persistence_does_not_select_an_unsaved_video(self):
        class BrokenStore:
            def put(self, key, value):
                raise RuntimeError("Database unavailable")
            def get(self, key, default=None):
                return default

        (self.d / "poster.jpg").write_bytes(JPG)
        (self.d / "poster-kind.txt").write_text("image")
        with patch.object(server, "STORE", BrokenStore()):
            with self.assertRaisesRegex(RuntimeError, "Database unavailable"):
                server.save_upload(url(MP4, "video/mp4"), "poster")
            self.assertEqual(server.poster_media().name, "poster.jpg")

    def test_only_real_mp4_under_the_whatsapp_limit(self):
        with self.assertRaisesRegex(ValueError, "MP4"):
            server.save_upload(url(b"not a video at all", "video/webm"), "poster")
        with self.assertRaisesRegex(ValueError, "too big"):
            server.save_upload(
                url(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 15_000_001, "video/mp4"), "attachment"
            )

    def test_video_attachments_are_found_for_chat_sends(self):
        aid = server.save_upload(url(MP4, "video/mp4"), "attachment")
        self.assertEqual(server.image_path(aid).suffix, ".mp4")
        pic = server.save_upload(url(JPG, "image/jpeg"), "attachment")
        self.assertEqual(server.image_path(pic).suffix, ".jpg")

    def test_the_gateway_video_endpoint_is_used_for_video_and_image_endpoint_for_pictures(self):
        seen = []
        (self.d / "poster.mp4").write_bytes(MP4)
        (self.d / "poster.jpg").write_bytes(JPG)
        with patch.object(
            server.subprocess,
            "run",
            side_effect=lambda cmd, **k: seen.append(cmd) or type("R", (), {"stdout": b"{}"})(),
        ):
            server.post_media("1@s.whatsapp.net", self.d / "c.txt", self.d / "poster.mp4")
            server.post_media("1@s.whatsapp.net", self.d / "c.txt", self.d / "poster.jpg")
        self.assertTrue(any(str(x).endswith("/send/video") for x in seen[0]))
        self.assertTrue(any(str(x).startswith("video=@") for x in seen[0]))
        self.assertTrue(any(str(x).endswith("/send/image") for x in seen[1]))


if __name__ == "__main__":
    unittest.main()


class GuardStaysOnTheSender(unittest.TestCase):
    def test_the_stop_and_supersede_guard_wraps_the_real_senders_not_the_helpers(self):
        self.assertTrue(hasattr(server.send_image, "__wrapped__"))
        self.assertTrue(hasattr(server.send_with_image, "__wrapped__"))
        self.assertFalse(hasattr(server.poster_media, "__wrapped__"))
        self.assertFalse(hasattr(server.post_media, "__wrapped__"))
