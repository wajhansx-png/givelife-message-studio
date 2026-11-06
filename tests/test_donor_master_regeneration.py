"""Regeneration follows the current, saved Message 1, never an old origin.

All rewrites are synthetic and no WhatsApp API or paid AI is called.
"""

import time
import unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app
import dm_composer, dm_templates
from donor_messages import MessageBank


class DonorMasterTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def regenerate(self, bank):
        """Start the real background regeneration and wait for its worker to finish."""
        bank.start_regeneration()
        deadline = time.monotonic() + 5
        while bank.regeneration_running and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(bank.regeneration_running, "regeneration did not finish")
        return bank.get()

    def approved_bank(self):
        """A healthy saved bank of twenty versions, whatever an earlier test left behind."""
        bank = app.donors().messages
        data = bank.get()
        data.update(
            mode="custom",
            items=bank._entries([dm_templates.build(i, app.read_left()) for i in range(20)]),
        )
        data.pop("generation", None)
        data.pop("previous_items", None)
        bank._save(data)
        return bank

    def fake_variants(self, source, count=10, avoid=None, **kwargs):
        # Only safe synthetic rewrites; keep original message facts and formatting.
        start = len(avoid or [])
        return [
            source.replace("Brother, ", "Bhai, ", 1)
            .replace("please read", "kindly read" if (start + i) % 2 else "do read", 1)
            .replace("the support", "the help" if (start + i) % 2 else "the care", 1)
            + (" " * (start + i + 1))
            for i in range(count)
        ]

    def partial_bank(self, ready=14, age=1000):
        """Message 1 plus rewrites, stopped part-way (Partial), as after a provider hiccup."""
        bank = self.approved_bank()
        data = bank.get()
        texts = [r["text"] for r in data["items"]][:ready]
        data.update(
            mode="custom",
            origin=texts[0],
            fingerprint=bank._fingerprint(texts[0]),
            items=bank._entries(texts),
            generation={
                "id": "partial-test",
                "source": texts[0],
                "target": 20,
                "accepted": texts[1:],
                "state": "Partial",
                "error": "Some versions are ready. Retry to finish the remaining versions.",
                "ready": ready,
                "started_at": time.time() - age,
            },
        )
        data.pop("previous_items", None)
        bank._save(data)
        return bank, texts

    def test_round_bigger_than_the_bank_rotates_instead_of_blocking(self):
        bank, texts = self.partial_bank(age=0)  # fresh attempt: no background top-up here
        picked = bank.reserve_round(20)
        self.assertEqual(len(picked), 20)
        self.assertTrue(all(t in texts for t in picked))
        self.assertEqual(len(set(picked)), 14)
        self.assertTrue(all(a != b for a, b in zip(picked, picked[1:])))

    def test_partial_bank_finishes_in_background_while_sending(self):
        bank, texts = self.partial_bank()
        with patch("dm_variants.generate", side_effect=self.fake_variants) as gen:
            picked = bank.reserve_round(20)
            deadline = time.monotonic() + 5
            while bank.regeneration_running and time.monotonic() < deadline:
                time.sleep(0.005)
        self.assertEqual(len(picked), 20)  # sending did not wait for generation
        self.assertTrue(gen.called)
        data = bank.get()
        self.assertEqual(data["generation"]["state"], "Ready")
        self.assertEqual(len(data["items"]), 20)
        self.assertEqual([r["text"] for r in data["items"]][:14], texts)  # kept, not replaced

    def test_failed_top_up_is_not_retried_on_every_round(self):
        bank, _ = self.partial_bank(age=10)
        with patch("dm_variants.generate", side_effect=ValueError("down")) as gen:
            bank.reserve_round(5)
        self.assertFalse(gen.called)

    def test_batch_start_accepts_fourteen_versions_for_twenty_donors(self):
        bank, texts = self.partial_bank(age=0)
        h = app.donors()
        h.jobs.import_jobs({"jobs": []})
        h.book._save({"version": 1, "records": []})
        for i in range(20):
            h.book.add("Synthetic " + str(i), "9230012300" + str(i).zfill(2))
        with patch.object(h.jobs, "connected", return_value=True):
            h.start_batch(scope="all", limit=20, run=False)
        job = h.jobs.export_jobs()["jobs"][-1]
        self.assertEqual(len(job["captions"]), 20)
        self.assertEqual(len(set(job["captions"])), 14)
        self.assertTrue(all(c in texts for c in job["captions"]))

    def test_saved_first_is_master_including_changed_angle_and_bold_italic(self):
        bank = app.donors().messages
        before = bank.get()
        first = before["items"][0]
        revised = first["text"].replace("Brother, ", "Bhai, ", 1)
        revised = revised.replace(
            "please read about Yousuf and the support his family requested.",
            "our community can help Yousuf and his grieving family today.",
            1,
        )
        revised = revised.replace("💔 ", "💔 *", 1).replace(
            "His parents reported that he was admitted to hospital for treatment.",
            "His parents reported that he was admitted for treatment.*",
            1,
        )
        self.assertTrue(dm_composer.complete(revised))
        bank.update(first["id"], revised)
        calls = []

        def fake(source, count=10, avoid=None, **kwargs):
            calls.append((source, count, list(avoid or [])))
            return [
                source.replace(
                    "our community can help", "we can stand with" if (j % 2) else "we can support"
                )
                + " " * (len(avoid or []) + j + 1)
                for j in range(count)
            ]

        with (
            patch("dm_variants.generate", side_effect=fake),
            patch("dm_templates.matches", return_value=True),
        ):
            result = self.regenerate(bank)
        self.assertEqual(result["mode"], "custom")
        self.assertEqual(len(result["items"]), 20)
        self.assertEqual(result["items"][0]["text"], revised)
        self.assertEqual(calls[0][0], revised)
        self.assertEqual(result["origin"], revised)
        self.assertTrue(all(revised.split("📲")[1] in x["text"] for x in result["items"]))
        self.assertTrue(all("💔 *" in x["text"] for x in result["items"]))
        self.assertEqual(len({r["text"] for r in result["items"]}), 20)

    def test_second_regeneration_uses_new_message_one_again(self):
        bank = app.donors().messages
        first = bank.get()["items"][0]
        with patch("dm_variants.generate", side_effect=self.fake_variants):
            bank.update(first["id"], first["text"].replace("Brother, ", "Bhai, ", 1))
            one = self.regenerate(bank)
            second = one["items"][0]["text"].replace("Yousuf", "Yousaf")
            bank.update(first["id"], second)
            two = self.regenerate(bank)
        self.assertEqual(two["items"][0]["text"], second)
        self.assertEqual(two["origin"], second)
        self.assertNotEqual(two["origin"], one["origin"])

    def test_master_edit_survives_main_dm_draft_changes(self):
        bank = app.donors().messages
        master = bank.get()["items"][0]
        edited = master["text"].replace("Brother, ", "Bhai, ", 1)
        bank.update(master["id"], edited)
        app.save_draft("dm", dm_templates.build(1, app.read_left()))
        restarted = MessageBank(app)
        self.assertEqual(restarted.get()["items"][0]["text"], edited)
        self.assertEqual(restarted.get()["mode"], "custom")

    def test_too_few_new_versions_restore_the_old_twenty(self):
        bank = self.approved_bank()
        first = bank.get()["items"][0]
        edited = first["text"].replace("Brother, ", "Bhai, ", 1)
        bank.update(first["id"], edited)
        old = bank.get()["items"]

        def incomplete(source, count=10, avoid=None, progress=None, **kwargs):
            progress(self.fake_variants(source, 4, avoid))
            raise ValueError("AI did not produce enough distinct body rewrites")

        with patch("dm_variants.generate", side_effect=incomplete):
            result = self.regenerate(bank)
        self.assertEqual(result["generation"]["state"], "Partial")
        self.assertEqual(len(result["generation"]["accepted"]), 4)
        self.assertEqual(result["items"], old)
        self.assertEqual(result["items"][0]["text"], edited)

    def test_model_failure_keeps_last_saved_master_and_previous_versions(self):
        bank = self.approved_bank()
        first = bank.get()["items"][0]
        new = first["text"].replace("Brother, ", "Bhai, ", 1)
        bank.update(first["id"], new)
        before = bank.get()
        with patch("dm_variants.generate", side_effect=ValueError("AI service unavailable")):
            result = self.regenerate(bank)
        self.assertIn("AI service unavailable", result["generation"]["error"])
        self.assertEqual(result["items"], before["items"])
        self.assertEqual(result["items"][0]["text"], new)

    def test_concurrent_first_edit_must_not_be_overwritten(self):
        bank = app.donors().messages
        original = bank.get()["items"][0]
        first = original["text"].replace("Brother, ", "Bhai, ", 1)
        later = original["text"].replace("Brother, ", "Ayesha Sister, ", 1)
        bank.update(original["id"], first)

        def rewrite(source, count=10, avoid=None, **kwargs):
            bank.update(original["id"], later)
            return self.fake_variants(source, count, avoid)

        with patch("dm_variants.generate", side_effect=rewrite):
            result = self.regenerate(bank)
        self.assertEqual(result["generation"]["state"], "Superseded")
        self.assertEqual(result["items"][0]["text"], later)


if __name__ == "__main__":
    unittest.main()
