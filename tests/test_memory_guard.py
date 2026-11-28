import tempfile
import unittest
from pathlib import Path

import memory_guard

MB = 1024 * 1024
LIMIT = 512 * MB


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.now = [0.0]
        self.logs = []
        self.g = memory_guard.Guard(clock=lambda: self.now[0], log=self.logs.append)
        self.now[0] = 3600  # past the first 30 minutes

    def step(self, used, busy=False):
        return self.g.step(used * MB, LIMIT, {"whatsapp": 100 * MB, "app": 200 * MB}, lambda: busy)

    def test_low_memory_never_restarts(self):
        self.assertIsNone(self.step(300))

    def test_high_memory_waits_while_a_person_is_being_sent_to(self):
        self.assertIsNone(self.step(430, busy=True))
        self.assertIn("between two people", self.step(430, busy=False))

    def test_near_the_limit_it_restarts_even_mid_person(self):
        self.assertTrue(
            self.step(480, busy=True)
        )  # the restart still lets that person finish first

    def test_no_restart_in_the_first_30_minutes(self):
        self.g = memory_guard.Guard(clock=lambda: self.now[0], log=self.logs.append)
        self.assertIsNone(self.step(500))

    def test_cannot_tell_if_busy_counts_as_busy(self):
        def broken():
            raise OSError

        self.assertIsNone(self.g.step(430 * MB, LIMIT, {}, broken))

    def test_memory_is_logged_every_10_minutes_by_part(self):
        self.step(300)
        self.step(300)
        self.assertEqual(len(self.logs), 1)
        self.assertIn("whatsapp=100 MB", self.logs[0])
        self.now[0] += 600
        self.step(300)
        self.assertEqual(len(self.logs), 2)


class ContainerMemoryTest(unittest.TestCase):
    def test_cgroup_v2_leaves_out_droppable_file_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "memory.current").write_text(str(400 * MB))
            (root / "memory.max").write_text(str(LIMIT))
            (root / "memory.stat").write_text(f"anon 1\ninactive_file {100 * MB}\n")
            self.assertEqual(memory_guard.container_memory(root), (300 * MB, LIMIT))

    def test_no_limit_and_no_cgroup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(memory_guard.container_memory(root), (None, None))
            (root / "memory.current").write_text(str(MB))
            (root / "memory.max").write_text("max")
            self.assertEqual(memory_guard.container_memory(root), (MB, None))


if __name__ == "__main__":
    unittest.main()
