"""Generation transport failures must not discard accepted messages."""

import unittest
from unittest.mock import patch
import dm_templates
import dm_variants


class VariantProgressTests(unittest.TestCase):
    def test_partial_results_are_returned_and_reported_when_provider_fails(self):
        source = dm_templates.build(0, 25000)
        candidate = dm_templates.build(1, 25000)
        progress = []
        with (
            patch("assistant.client", return_value="fake"),
            patch(
                "dm_variants._call",
                side_effect=[[candidate], RuntimeError("DeepSeek returned 429")],
            ),
            patch("dm_variants.validate", return_value=""),
        ):
            result = dm_variants.generate(
                source, 2, progress=lambda texts: progress.append(list(texts)), allow_partial=True
            )
        self.assertEqual(result, [candidate])
        self.assertEqual(progress, [[candidate]])

    def test_rejection_reason_is_sent_to_model_on_retry(self):
        source = dm_templates.build(0, 25000)
        bad = dm_templates.build(1, 25000)
        good = dm_templates.build(2, 25000)
        with (
            patch("assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=[[bad], [good]]) as wire,
            patch("dm_variants.validate", side_effect=["payment details changed", ""]),
        ):
            self.assertEqual(dm_variants.generate(source, 1), [good])
        self.assertIn("payment details changed", wire.call_args.args[1])

    def test_callback_cancellation_stops_generation_without_more_api_calls(self):
        source = dm_templates.build(0, 25000)
        with (
            patch("assistant.client", return_value="fake"),
            patch("dm_variants._call", return_value=[dm_templates.build(1, 25000)]) as wire,
            patch("dm_variants.validate", return_value=""),
        ):
            with self.assertRaisesRegex(ValueError, "newer edit"):
                dm_variants.generate(
                    source,
                    2,
                    progress=lambda _: (_ for _ in ()).throw(ValueError("newer edit")),
                    allow_partial=True,
                )
        self.assertEqual(wire.call_count, 1)
