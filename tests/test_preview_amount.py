"""A group message preview shows the live amount, like a real send."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as app


class PreviewAmount(unittest.TestCase):
    def test_next_message_preview_uses_the_live_amount(self):
        old = "*Rs. 17,500 is still left to clear this debt.*\n\n03097458815"
        bank = mock.Mock()
        bank.get.return_value = {"revision": "r", "items": [old]}
        with (
            mock.patch.object(app, "STORE", object()),
            mock.patch.object(app, "focus_bank", return_value=bank),
            mock.patch.object(app, "save_draft"),
            mock.patch.object(
                app.caption_facts, "current", lambda _a, t: t.replace("17,500", "19,500")
            ),
        ):
            self.assertIn("19,500", app.next_message())


if __name__ == "__main__":
    unittest.main()
