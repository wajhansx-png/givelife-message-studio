"""The actual attachment sender reuses bytes without mixing recipients or accounts."""

import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_media
import test_manual_sends as fixture
from test_manual_sends import app


class CachedMediaDispatch(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_main_groups_and_both_giki_accounts_use_the_exact_cached_file(self):
        raw = b"%PDF-1.7\n" + b"private synthetic document " * 80000
        expected_digest = hashlib.sha256(raw).hexdigest()
        ident = batch_media.save(app.STORE, "data:application/pdf;base64," + base64.b64encode(raw).decode())
        calls = []

        def wire(command, **kwargs):
            fields = [command[i + 1] for i, part in enumerate(command) if part == "-F"]
            headers = [command[i + 1] for i, part in enumerate(command) if part == "-H"]
            path = next(part for part in fields if part.startswith("file=@"))[6:].split(";", 1)[0]
            calls.append((headers, next(part for part in fields if part.startswith("phone=")),
                          hashlib.sha256(Path(path).read_bytes()).hexdigest()))
            return SimpleNamespace(stdout=b'{"code":"SUCCESS","results":{"message_id":"fake"}}')

        routes = [("", "main-device", app.GROUPS["main"][1]),
                  ("giki", "giki-device", "923001230093"),
                  ("giki2", "giki2-device", "923001230094")]
        with patch.object(app, "DEVICE", "main-device"), \
             patch.dict(app.LINES, {"giki": SimpleNamespace(device=lambda: "giki-device"),
                                    "giki2": SimpleNamespace(device=lambda: "giki2-device")}), \
             patch.object(app.STORE, "get", wraps=app.STORE.get) as read, \
             patch.object(app.subprocess, "run", side_effect=wire):
            for line, _device, recipient in routes:
                with app.on_line(line):
                    self.assertEqual(app.send_batch_attachment(recipient, "", ident)["code"], "SUCCESS")
            self.assertEqual(sum(c.args[0] == "batch_media_" + ident for c in read.call_args_list), 1)
        self.assertEqual(calls, [(["X-Device-Id: " + device], "phone=" + recipient, expected_digest)
                                 for _line, device, recipient in routes])


if __name__ == "__main__":
    unittest.main()
