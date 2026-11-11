"""A round of rewrites runs its AI calls at the same time, so a batch takes one call, not many."""

import threading
import time
import unittest
from unittest.mock import patch

import focus_bank
from tests import test_focus_bank as fb

DEEP, SRC = fb.DEEP, fb.SRC


class ParallelRound(unittest.TestCase):
    make = fb.FocusTests.make

    def run_batch(self, per_call_seconds, answers):
        b = self.make()
        with patch.object(b, "_spawn"):
            b.save("group", SRC)
        prompts, lock, depth = [], threading.Lock(), {"now": 0, "max": 0}

        def slow_call(api, prompt, deep=False):
            with lock:
                prompts.append(prompt)
                depth["now"] += 1
                depth["max"] = max(depth["max"], depth["now"])
                n = len(prompts)
            time.sleep(per_call_seconds)
            with lock:
                depth["now"] -= 1
            return answers(n)

        row = b.get("group")
        start = time.time()
        with (
            patch("dm_variants.assistant.client", return_value="key"),
            patch("dm_variants._call", slow_call),
            patch("quality.review", lambda chat, src, passed, *a, **k: [""] * len(passed)),
        ):
            b._generate("group", row, ("group", row["revision"]))
        return b.get("group"), prompts, depth["max"], time.time() - start

    def test_calls_in_one_round_overlap_and_use_different_angles(self):
        row, prompts, overlap, took = self.run_batch(
            0.4, lambda n: [DEEP[n % 10], DEEP[(n + 3) % 10]]
        )
        self.assertGreaterEqual(overlap, 3)
        first_round = prompts[: focus_bank.PARALLEL_CALLS]
        angles = {p.split("FOR THIS SET: ")[1].split(".")[0] for p in first_round}
        self.assertEqual(len(angles), focus_bank.PARALLEL_CALLS)
        self.assertTrue(all("EXACT NUMBERS" in p for p in first_round))
        self.assertLess(took, 0.4 * len(prompts))  # not one call after another

    def test_one_failing_call_does_not_lose_the_others(self):
        def answers(n):
            if n == 1:
                raise RuntimeError("server hiccup 500")
            return [DEEP[n], DEEP[n + 3]]

        row, prompts, overlap, took = self.run_batch(0.05, answers)
        self.assertGreaterEqual(len(row["items"]), 1)


if __name__ == "__main__":
    unittest.main()
