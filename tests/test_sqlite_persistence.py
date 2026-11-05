"""Unit tests for SQLite persistent storage and recovery."""

import os
import tempfile
import unittest
import persist


class SqlitePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "studio_state.sqlite")
        self.store = persist.SqliteStore(self.db_path)
        self.store.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_put_and_get_dict(self):
        data = {"turn": 1, "knowledge": ["polite tone", "no urgency"], "nested": {"count": 42}}
        self.store.put("test_key", data)
        retrieved = self.store.get("test_key")
        self.assertEqual(retrieved, data)

    def test_get_many(self):
        self.store.put("k1", {"val": 1})
        self.store.put("k2", {"val": 2})
        res = self.store.get_many(["k1", "k2", "missing"])
        self.assertEqual(res.get("k1"), {"val": 1})
        self.assertEqual(res.get("k2"), {"val": 2})
        self.assertNotIn("missing", res)

    def test_seed_does_not_overwrite(self):
        self.store.put("seed_key", {"initial": True})
        self.store.seed("seed_key", {"initial": False})
        self.assertTrue(self.store.get("seed_key")["initial"])

    def test_lease_acquire_and_release(self):
        # Owner 1 acquires lease
        self.assertTrue(self.store.lease_acquire("lease_1", "owner1", ttl=5))
        # Owner 2 cannot acquire active lease
        self.assertFalse(self.store.lease_acquire("lease_1", "owner2", ttl=5))
        # Owner 1 can refresh
        self.assertTrue(self.store.lease_acquire("lease_1", "owner1", ttl=5))
        # Owner 1 releases
        self.store.lease_release("lease_1", "owner1")
        # Owner 2 can now acquire
        self.assertTrue(self.store.lease_acquire("lease_1", "owner2", ttl=5))

    def test_persistence_across_reconnect(self):
        self.store.put("permanent", {"important": "wedding notes and donor facts"})
        # Instantiate brand new store object on same file
        reopened = persist.SqliteStore(self.db_path)
        reopened.initialize()
        self.assertEqual(reopened.get("permanent")["important"], "wedding notes and donor facts")


if __name__ == "__main__":
    unittest.main()
