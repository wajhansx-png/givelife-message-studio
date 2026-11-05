"""Regression gate for the GiveLife chat routing benchmark (no model, no WhatsApp)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chat_bench
import manual_commands


class ChatBench(unittest.TestCase):
    def test_every_tuned_case_routes_correctly(self):
        for case in chat_bench.CASES:
            with self.subTest(case["id"]):
                ok, problems = chat_bench.evaluate(case)
                self.assertTrue(ok, "; ".join(problems))

    def test_every_held_out_case_routes_correctly(self):
        for case in chat_bench.HELD_OUT:
            with self.subTest(case["id"]):
                ok, problems = chat_bench.evaluate(case)
                self.assertTrue(ok, "; ".join(problems))

    def test_benchmark_is_large_enough(self):
        self.assertGreaterEqual(len(chat_bench.CASES) + len(chat_bench.HELD_OUT), 80)

    def test_typos_never_change_a_literal_message(self):
        plan = manual_commands.parse("send snd the dnors list to ali")
        self.assertEqual(plan["kind"], "text")
        self.assertEqual(plan["text"], "snd the dnors list")

    def test_sent_is_not_corrected_to_send(self):
        self.assertEqual(manual_commands.fix_typos("was it sent to main?"), "was it sent to main?")

    def test_urgency_words_are_not_part_of_the_recipient(self):
        self.assertEqual(manual_commands.parse("send hi to ali now")["to"], "ali")
        self.assertEqual(manual_commands.parse('send "call me" to ali asap')["to"], "ali")

    def test_trace_records_intent_and_tools_but_no_private_text(self):
        import json
        from unittest.mock import patch
        import assistant, chat_runtime

        text = "dm all donors and add 03001234567 Ali Khan"
        with (
            patch.object(assistant, "client", return_value="key"),
            patch.object(assistant, "_chat_raw", return_value={"content": "Which donors?"}),
        ):
            out = chat_runtime.run_chat(text, [], chat_bench.STATE, [], {})
        diag = out["diagnostics"]
        self.assertIn("donor_action", diag["offered"])
        self.assertIn("send", diag["intent"])
        self.assertGreater(diag["context_chars"], 0)
        blob = json.dumps(diag)
        self.assertNotIn("03001234567", blob)
        self.assertNotIn("Ali Khan", blob)


if __name__ == "__main__":
    unittest.main()
