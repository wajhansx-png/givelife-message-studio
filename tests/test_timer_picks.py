"""The Timer time the owner picks stays picked (database) until another time is picked or it is deselected."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import persist
import server


class TimerPicksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = persist.SqliteStore(str(Path(self.tmp.name) / "t.db"))
        store.initialize()
        self.patch = mock.patch.object(server, "STORE", store)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_pick_stays_until_changed_or_deselected(self):
        self.assertEqual(server.timer_picks(), {})
        server.set_timer_pick("main", 30)
        server.set_timer_pick("free", 15)
        self.assertEqual(server.timer_picks(), {"main": 30, "free": 15})
        server.set_timer_pick("main", 60)  # a new time replaces the old one
        self.assertEqual(server.timer_picks()["main"], 60)
        server.set_timer_pick("free")  # deselect
        self.assertEqual(server.timer_picks(), {"main": 60})


if __name__ == "__main__":
    unittest.main()
