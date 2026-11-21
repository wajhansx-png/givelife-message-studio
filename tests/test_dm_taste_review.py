"""DM versions get the owner's taste review, like the Group versions. The model is stubbed; nothing is sent."""

import json
import unittest
from unittest.mock import patch

import dm_templates
import dm_variants
import quality

SRC = dm_templates.build(0, 25000)
GOOD = [dm_templates.build(i, 25000) for i in range(1, 9)]
ROBOTIC = "review: sounds robotic"


class DmTasteReview(unittest.TestCase):
    def gen(self, replies, review, count=2, validate=""):
        with (
            patch("assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=replies) as wire,
            patch("dm_variants.validate", return_value=validate),
            patch("dm_variants._sleep"),
            patch.object(dm_variants, "REVIEW", review),
        ):
            try:
                return dm_variants.generate(SRC, count), wire.call_count
            except ValueError as exc:
                return exc, wire.call_count

    def test_versions_in_the_owners_taste_come_first(self):
        review = lambda source, versions: [ROBOTIC if v == GOOD[0] else "" for v in versions]
        out, calls = self.gen([GOOD[:2], GOOD[2:4]], review, count=3)
        self.assertEqual(out, [GOOD[1], GOOD[2], GOOD[3]])
        self.assertEqual(calls, 2)

    def test_too_few_in_taste_are_made_up_from_versions_that_kept_every_rule(self):
        out, calls = self.gen([[g] for g in GOOD[:5]], lambda s, v: [ROBOTIC] * len(v), count=2)
        self.assertEqual(out, GOOD[:2])  # the owner still gets the full count, never an error
        self.assertEqual(calls, 5)

    def test_a_new_fact_is_never_used_even_to_make_up_the_count(self):
        review = lambda s, v: ['review: new fact not in the source: "his son Ali"'] * len(v)
        out, _ = self.gen([[g] for g in GOOD[:5]], review, count=2)
        self.assertIsInstance(out, ValueError)
        self.assertIn("new fact", str(out))
        self.assertIn("not changed", str(out))  # the saved DM and bank stay as they were

    def test_a_broken_review_never_blocks_versions(self):
        def review(source, versions):
            raise RuntimeError("model down")

        out, _ = self.gen([GOOD[:2]], review, count=2)
        self.assertEqual(out, GOOD[:2])

    def test_the_real_review_drops_an_invented_fact_and_keeps_the_rest(self):
        bad = GOOD[1] + "\nHis son Ali is 7 years old."
        answer = {
            "scores": [
                {"i": 0, "owner": 5, "natural": 5, "calm": 5, "follows": 5, "invented": ""},
                {
                    "i": 1,
                    "owner": 5,
                    "natural": 5,
                    "calm": 5,
                    "follows": 5,
                    "invented": "His son Ali is 7 years old",
                },
            ]
        }
        review = lambda s, v: quality.review(lambda prompt: json.dumps(answer), s, v, [], [])
        out, _ = self.gen([[GOOD[0], bad], [GOOD[2]]], review, count=2)
        self.assertEqual(out, [GOOD[0], GOOD[2]])

    def test_progress_sees_versions_added_from_the_backup(self):
        seen = []
        with (
            patch("assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=[[g] for g in GOOD[:5]]),
            patch("dm_variants.validate", return_value=""),
            patch("dm_variants._sleep"),
            patch.object(dm_variants, "REVIEW", lambda s, v: [ROBOTIC] * len(v)),
        ):
            out = dm_variants.generate(SRC, 2, progress=lambda texts: seen.append(len(texts)))
        self.assertEqual(out, GOOD[:2])
        self.assertEqual(seen, [2])

    def test_a_source_change_during_backup_stops_like_a_normal_round(self):
        with (
            patch("assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=[[g] for g in GOOD[:5]]),
            patch("dm_variants.validate", return_value=""),
            patch("dm_variants._sleep"),
            patch.object(dm_variants, "REVIEW", lambda s, v: [ROBOTIC] * len(v)),
            self.assertRaises(ValueError) as caught,
        ):
            dm_variants.generate(SRC, 2, progress=lambda texts: False)
        self.assertIn("source changed", str(caught.exception))

    def test_the_default_review_keeps_everything(self):
        self.assertEqual(dm_variants.REVIEW("s", ["a", "b"]), ["", ""])


if __name__ == "__main__":
    unittest.main()
