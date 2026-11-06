"""AI generation failures for DM and Group versions. The model is stubbed; no paid AI is called."""

import unittest
from unittest.mock import patch
import dm_templates
import dm_variants

SRC = dm_templates.build(0, 25000)
GOOD = [dm_templates.build(i, 25000) for i in range(1, 6)]


class DmGenerationFailures(unittest.TestCase):
    def gen(self, replies, count=2, validate=""):
        naps = []
        with (
            patch("assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=replies) as wire,
            patch("dm_variants.validate", side_effect=validate)
            if callable(validate) or isinstance(validate, list)
            else patch("dm_variants.validate", return_value=validate),
            patch("dm_variants._sleep", side_effect=naps.append),
        ):
            try:
                out = dm_variants.generate(SRC, count)
            except ValueError as exc:
                out = exc
        return out, wire.call_count, naps

    def test_rate_limit_waits_and_retries_instead_of_failing(self):
        out, calls, naps = self.gen([RuntimeError("DeepSeek returned 429"), GOOD[:2]])
        self.assertEqual(out, GOOD[:2])
        self.assertEqual((calls, naps), (2, [5]))

    def test_server_error_and_timeout_are_retried(self):
        out, _, naps = self.gen(
            [RuntimeError("HTTP 503"), RuntimeError("read timed out"), GOOD[:2]]
        )
        self.assertEqual(out, GOOD[:2])
        self.assertEqual(naps, [5, 15])

    def test_bad_key_stops_at_once(self):
        out, calls, naps = self.gen([RuntimeError("DeepSeek returned 401")] * 5)
        self.assertIsInstance(out, ValueError)
        self.assertEqual((calls, naps), (1, []))

    def test_content_rejections_cost_no_extra_ai_calls(self):
        out, calls, _ = self.gen([[GOOD[0]]] * 20, validate="an emoji changed or moved")
        self.assertIsInstance(out, ValueError)
        self.assertEqual(calls, 5)
        self.assertIn("an emoji changed or moved (5x)", str(out))


class RepairTests(unittest.TestCase):
    SOURCE = 'Hook line\n*اللّٰہ تعالیٰ کا ارشاد ہے:*\n"تم جو کچھ بھی خرچ کرو گے، وہ اس کا بدل دے گا۔"\n(سورۃ سبا: 39)\n03097458815 Easypaisa Wajdan Khan'

    def test_verse_reference_and_payment_lines_are_put_back(self):
        src = self.SOURCE.replace("\\\n", "\n")
        broken = src.split("\n")
        broken[0] = "New hook line"
        broken[2] = '"Whatever you spend, He will replace it."'
        broken[3] = "(Surah Saba: 39)"
        broken[4] = "0309 7458815 EasyPaisa Wajdan"
        fixed = dm_variants.repair(src, "\n".join(broken)).split("\n")
        self.assertEqual(fixed[0], "New hook line")  # the rewritten line is kept
        self.assertEqual(fixed[1:], src.split("\n")[1:])

    def test_different_line_count_is_left_for_the_checks(self):
        self.assertEqual(dm_variants.repair("a\nb", "a"), "a")


class GroupGenerationFailures(unittest.TestCase):
    def make(self):
        import test_focus_bank as fb

        t = fb.FocusTests()
        bank = t.make()
        with patch.object(bank, "_spawn"):
            row = bank.save("group", fb.SRC)
            bank.generate("group")
        bank.running.add(("group", row["revision"]))  # as _spawn does: one worker per batch
        return bank, row, fb.DEEP

    def test_rate_limit_is_waited_out(self):
        bank, row, deep = self.make()
        naps = []
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=[RuntimeError("429 Too Many Requests"), deep]),
            patch("dm_variants._sleep", side_effect=naps.append),
        ):
            bank._generate("group", bank.get("group"), ("group", row["revision"]))
        got = bank.get("group")
        self.assertEqual((got["state"], len(got["items"]), naps), ("Ready", 5, [5]))

    def test_bad_key_stops_with_reason(self):
        bank, row, _ = self.make()
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=RuntimeError("DeepSeek returned 403")) as wire,
        ):
            bank._generate("group", bank.get("group"), ("group", row["revision"]))
        got = bank.get("group")
        self.assertEqual((got["state"], wire.call_count), ("Needs retry", 1))
        self.assertIn("403", got["error"])

    def test_rejected_candidates_use_at_most_six_calls(self):
        bank, row, _ = self.make()
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", return_value=["same text"] * 5) as wire,
        ):
            bank._generate("group", bank.get("group"), ("group", row["revision"]))
        self.assertEqual(wire.call_count, 6)


if __name__ == "__main__":
    unittest.main()
