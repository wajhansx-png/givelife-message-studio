"""Reply scans must not re-read idle chats, and must never miss a new message."""

import datetime
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as app


def iso(seconds_ago):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds_ago)
    return t.isoformat()


class ScanCache(unittest.TestCase):
    def setUp(self):
        app._CHAT_CACHE.clear()
        app._CHAT_STAMPS.update(at=0.0, map={})
        self.stamps, self.reads = {}, []

        def api_result(path):
            return {"data": [{"jid": j, "last_message_time": t} for j, t in self.stamps.items()]}

        def api_messages(path):
            self.reads.append(path)
            return [{"id": "m%d" % len(self.reads)}]

        self.patches = [
            mock.patch.object(app, "api_result", api_result),
            mock.patch.object(app, "api_messages", api_messages),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def fresh_list(self):
        app._CHAT_STAMPS["at"] = 0.0  # let the next scan see the newest chat list

    def test_idle_chat_is_read_once_then_served_from_memory(self):
        self.stamps = {"a@s.whatsapp.net": iso(3600)}
        first = app.scan_messages("a@s.whatsapp.net")
        self.fresh_list()
        second = app.scan_messages("a@s.whatsapp.net")
        self.assertEqual(first, second)
        self.assertEqual(len(self.reads), 1)

    def test_new_message_is_read_straight_away(self):
        self.stamps = {"a@s.whatsapp.net": iso(3600)}
        app.scan_messages("a@s.whatsapp.net")
        self.stamps = {"a@s.whatsapp.net": iso(5)}
        self.fresh_list()
        app.scan_messages("a@s.whatsapp.net")
        self.assertEqual(len(self.reads), 2)

    def test_chat_with_very_recent_activity_is_never_cached(self):
        self.stamps = {"a@s.whatsapp.net": iso(20)}  # could still receive a same-second message
        for _ in range(3):
            self.fresh_list()
            app.scan_messages("a@s.whatsapp.net")
        self.assertEqual(len(self.reads), 3)

    def test_unknown_chat_or_unreadable_list_always_reads_live(self):
        for _ in range(2):
            self.fresh_list()
            app.scan_messages("zzz@s.whatsapp.net")
        self.assertEqual(len(self.reads), 2)

    def test_cache_expires_after_fifteen_minutes(self):
        self.stamps = {"a@s.whatsapp.net": iso(7200)}
        app.scan_messages("a@s.whatsapp.net")
        jid = "a@s.whatsapp.net"
        stamp, messages, at = app._CHAT_CACHE[jid]
        app._CHAT_CACHE[jid] = (stamp, messages, at - 901)
        self.fresh_list()
        app.scan_messages(jid)
        self.assertEqual(len(self.reads), 2)

    def test_sending_and_delete_checks_always_read_live(self):
        self.stamps = {"a@g.us": iso(3600)}
        app.scan_messages("a@g.us")
        app.group_messages("a@g.us")
        app.group_messages("a@g.us")
        self.assertEqual(len(self.reads), 3)


if __name__ == "__main__":
    unittest.main()
