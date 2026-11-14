import os, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gateway_registry, wa_lines


class Store(dict):
    def put(self, key, value):
        self[key] = value


def gateway_file(path, devices):
    """A chat-storage file shaped like the gateway's own (WAL, devices + chats + messages + scheduled sends)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE schema_info (version INTEGER)")
    db.execute("INSERT INTO schema_info VALUES (12)")
    db.execute(
        "CREATE TABLE devices (device_id TEXT PRIMARY KEY, display_name TEXT, jid TEXT, ad_jid TEXT)"
    )
    db.executemany("INSERT INTO devices VALUES (?, '', ?, ?)", devices)
    db.execute("CREATE TABLE chats (jid TEXT, name TEXT)")
    db.execute("CREATE TABLE messages (id TEXT, body TEXT)")
    db.execute("CREATE TABLE scheduled_sends (id TEXT, body TEXT)")
    db.executemany("INSERT INTO messages VALUES (?, ?)", [(str(i), "x" * 500) for i in range(200)])
    db.execute("INSERT INTO chats VALUES ('1@g.us', 'Group')")
    db.execute("INSERT INTO scheduled_sends VALUES ('s1', 'hello')")
    db.commit()
    return db  # kept open, like the running gateway


MAIN = ("main-1", "923000000001@s.whatsapp.net", "923000000001:4@s.whatsapp.net")
GIKI = ("giki-abc", "923000000002@s.whatsapp.net", "923000000002:9@s.whatsapp.net")


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        gateway_registry._last.clear()
        env = mock.patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": ""})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.dir.cleanup()

    def test_a_deploy_keeps_the_giki_name_tied_to_its_login(self):
        store = Store()
        live = gateway_file(self.root / "old" / "storages" / "chatstorage.db", [MAIN, GIKI])
        self.assertTrue(
            gateway_registry.save(store, self.root / "old" / "storages" / "chatstorage.db")
        )
        live.close()
        fresh = self.root / "new" / "storages" / "chatstorage.db"  # the wiped disk
        self.assertTrue(gateway_registry.restore(store, fresh))
        db = sqlite3.connect(fresh)
        self.assertEqual(
            db.execute("SELECT * FROM devices ORDER BY device_id").fetchall(),
            [
                (GIKI[0], "", GIKI[1], GIKI[2]),
                (MAIN[0], "", MAIN[1], MAIN[2]),
            ],
        )
        self.assertEqual(db.execute("SELECT version FROM schema_info").fetchall(), [(12,)])
        # no chats, messages or scheduled sends come back (nothing can be sent again)
        for table in ("chats", "messages", "scheduled_sends"):
            self.assertEqual(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)
        db.close()

    def test_an_unchanged_list_is_saved_once_and_a_change_is_saved_again(self):
        store = Store()
        path = self.root / "storages" / "chatstorage.db"
        live = gateway_file(path, [MAIN])
        self.assertTrue(gateway_registry.save(store, path))
        self.assertFalse(gateway_registry.save(store, path))
        live.execute("INSERT INTO devices VALUES (?, '', ?, ?)", GIKI)
        live.commit()
        self.assertTrue(gateway_registry.save(store, path))
        live.close()

    def test_restore_never_overwrites_a_file_the_gateway_already_has(self):
        store = Store()
        path = self.root / "storages" / "chatstorage.db"
        gateway_file(path, [MAIN]).close()
        gateway_registry.save(store, path)
        self.assertFalse(gateway_registry.restore(store, path))

    def test_nothing_saved_yet_or_no_file_does_nothing(self):
        store = Store()
        self.assertFalse(gateway_registry.restore(store, self.root / "storages" / "chatstorage.db"))
        self.assertFalse(gateway_registry.save(store, self.root / "missing.db"))
        self.assertEqual(store, {})

    def test_sealed_when_the_storage_key_is_set(self):
        with mock.patch.dict(os.environ, {"GIVELIFE_STORAGE_KEY": "k" * 40}):
            store = Store()
            path = self.root / "a" / "chatstorage.db"
            gateway_file(path, [MAIN, GIKI]).close()
            self.assertTrue(gateway_registry.save(store, path))
            self.assertTrue(store[gateway_registry.KEY]["sealed"])
            self.assertNotIn(
                b"923000000002", __import__("base64").b64decode(store[gateway_registry.KEY]["data"])
            )
            self.assertTrue(gateway_registry.restore(store, self.root / "b" / "chatstorage.db"))


class MainDeviceTest(unittest.TestCase):
    def test_the_giki_login_is_never_taken_for_the_main_whatsapp(self):
        store = Store({"wa_line_giki": {"device": "giki-abc", "number": "923000000002"}})
        devices = [
            {
                "id": "923000000002:9@s.whatsapp.net",
                "jid": "923000000002@s.whatsapp.net",
            },  # Giki, back by number
            {"id": "giki-abc", "jid": "923000000002@s.whatsapp.net"},
            {"id": "923000000001:4@s.whatsapp.net", "jid": "923000000001@s.whatsapp.net"},
        ]
        self.assertEqual(
            [d["id"] for d in wa_lines.main_candidates(devices, store)],
            ["923000000001:4@s.whatsapp.net"],
        )

    def test_with_no_saved_giki_number_only_the_giki_name_is_skipped(self):
        devices = [{"id": "giki-abc"}, {"id": "main-uuid"}]
        self.assertEqual(
            [d["id"] for d in wa_lines.main_candidates(devices, Store())], ["main-uuid"]
        )

    def test_the_line_remembers_its_number_once_linked(self):
        store = Store({"wa_line_giki": {"device": "giki-abc"}})

        def call(method, path, device="", body=None, timeout=15, raw=False):
            if path.endswith("/status"):
                return {"results": {"is_connected": True, "is_logged_in": True}}
            return {"results": {"jid": "923000000002:9@s.whatsapp.net"}}

        line = wa_lines.Line("giki", store, "http://gw", call=call)
        self.assertEqual(line.status()["state"], "ready")
        self.assertEqual(store["wa_line_giki"], {"device": "giki-abc", "number": "923000000002"})
        line._save("giki-new")  # a new device keeps the number
        self.assertEqual(store["wa_line_giki"]["number"], "923000000002")


if __name__ == "__main__":
    unittest.main()
