import concurrent.futures
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from case_writer import CaseWriter
from message_library import MessageLibrary, library_for
from persist import SqliteStore
import ai_call
import message_styles
import dm_templates
import dm_variants
from donor_messages import MessageBank


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.store = SqliteStore(self.folder / "studio.sqlite")
        self.store.initialize()
        self.library = MessageLibrary(self.folder, self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_archive_survives_paging_restart_and_context_window_limit(self):
        for i in range(270):
            self.library.record("dm", f"Complete message {i}")
        restored = MessageLibrary(self.folder, self.store)
        self.assertEqual(restored.count(), 270)
        self.assertEqual(len(restored.recent(1000)), 270)
        self.assertEqual(restored.recent(1)[0]["text"], "Complete message 269")
        self.assertEqual(restored.recent(1000)[-1]["text"], "Complete message 0")
        # A fresh local folder can restore from the existing database alone.
        self.assertEqual(MessageLibrary(self.folder / "new-instance", self.store).count(), 270)

    def test_repeated_text_is_deduplicated_and_owner_edits_win(self):
        ident = self.library.record("dm", "A draft", quality="candidate")
        self.library.record("dm", "A draft", quality="validated")
        self.library.record("dm", "A draft", quality="owner")
        self.library.record("dm", "A draft", quality="candidate")
        self.assertEqual(self.library.count(), 1)
        self.assertEqual(self.library.recent(1)[0]["id"], ident)
        self.assertEqual(self.library.recent(1)[0]["quality"], "owner")

    def test_local_atomic_copies_work_without_database(self):
        local = MessageLibrary(self.folder)
        local.record("group", "A complete group appeal")
        self.assertEqual(
            MessageLibrary(self.folder).recent(1)[0]["text"], "A complete group appeal"
        )

    def test_existing_banks_and_drafts_seed_the_archive_without_changing_them(self):
        bank = {
            "base": "An owner-approved base",
            "items": [{"text": "A current DM version"}],
            "previous_items": [{"text": "An older DM version"}],
        }
        focus = {"group": {"source": "An approved group appeal", "manual": ["My hand edit"]}}
        self.store.put("donor_messages", bank)
        self.store.put("focus_wording", focus)
        drafts = self.folder / "drafts.json"
        drafts.write_text(json.dumps({"group": "An existing draft"}), encoding="utf-8")
        app = SimpleNamespace(DATA=self.folder, STORE=self.store, DRAFT=drafts)
        archive = library_for(app)
        self.assertEqual(archive.count(), 6)
        self.assertEqual(archive.examples("group")[0], "My hand edit")
        self.assertEqual(self.store.get("donor_messages"), bank)
        self.assertEqual(self.store.get("focus_wording"), focus)
        del app._MESSAGE_LIBRARY
        self.assertEqual(library_for(app).count(), 6)

    def test_failed_index_write_recovers_without_losing_or_double_counting_message(self):
        original = self.store.put
        failed = []

        def fail_once(key, value):
            if key == self.library.INDEX and not failed:
                failed.append(True)
                raise OSError("temporary database failure")
            return original(key, value)

        with patch.object(self.store, "put", side_effect=fail_once):
            with self.assertRaises(OSError):
                self.library.record("dm", "Keep this generated message")
        restored = MessageLibrary(self.folder, self.store)
        restored.record("dm", "Keep this generated message")
        self.assertEqual(restored.count(), 1)
        self.assertEqual(restored.recent(1)[0]["text"], "Keep this generated message")

    def test_concurrent_generators_keep_all_unique_messages(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: self.library.record("group", f"Message {i % 12}"), range(48)))
        self.assertEqual(self.library.count(), 12)

    def test_rejected_candidates_are_saved_but_not_used_as_style_examples(self):
        self.library.record("group", "Invented unsafe claim", quality="candidate")
        self.library.record("dm", "An accepted draft", quality="validated")
        self.library.record("dm", "My edited preferred wording", quality="owner")
        self.assertEqual(self.library.examples()[0], "My edited preferred wording")
        self.assertNotIn("Invented unsafe claim", self.library.examples())
        self.assertEqual(len(self.library.recent()), 3)

    def test_replacing_a_live_dm_bank_preserves_older_versions_and_learns_edits(self):
        app = SimpleNamespace(
            DATA=self.folder,
            STORE=self.store,
            read_left=lambda: 25000,
            active_case_name=lambda: "Current case",
            get_message=lambda kind: {"text": dm_templates.build(0, 25000)},
        )
        bank = MessageBank(app)
        original = bank.get()["items"]
        edited = "*Your small gift can lift this burden.*\n\n" + original[0]["text"]
        bank.set_base(edited)
        self.assertEqual(len(bank.get()["items"]), 1)
        archive = library_for(app)
        self.assertTrue(
            {r["text"] for r in original}.issubset({r["text"] for r in archive.recent(100)})
        )
        with patch.object(dm_variants, "OWNER_STYLE", lambda: archive.examples(kind="dm")):
            prompt = dm_variants._prompt(original[1]["text"], 1, [])
        self.assertIn("Your small gift can lift this burden", prompt)

    def test_raw_ai_dm_candidates_are_archived_before_validation(self):
        candidates = ["Rejected candidate that changes the amount", "Another candidate"]
        with (
            patch.object(
                dm_variants.assistant, "_chat_raw", return_value={"content": json.dumps(candidates)}
            ),
            patch.object(
                dm_variants,
                "RECORD",
                lambda text, quality, kind="message": self.library.record(
                    kind, text, quality=quality
                ),
            ),
        ):
            self.assertEqual(dm_variants._call("fake-key", "Test prompt"), candidates)
        self.assertEqual(self.library.count(), 2)
        self.assertEqual(self.library.examples(), [])


class CaseWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = SqliteStore(self.root / "studio.sqlite")
        self.store.initialize()
        self.case, self.left, self.used, self.calls = "case-one", 25000, [], []
        self.app = SimpleNamespace(
            DATA=self.root,
            STORE=self.store,
            read_left=lambda: self.left,
            donors=lambda: SimpleNamespace(
                cases=SimpleNamespace(view=lambda: {"current": self.case}),
                messages=SimpleNamespace(set_base=lambda text: self.used.append(text)),
            ),
            save_draft=lambda kind, text: self.used.append((kind, text)),
            message_style=self.generate,
        )
        self.writer = CaseWriter(self.app)

    def tearDown(self):
        self.temp.cleanup()

    def generate(self, body):
        self.calls.append(body)
        return {"text": "*Please help this family*\n\n" + body["case_details"]}

    def body(self, **changes):
        v = self.writer.view()
        return {
            k: changes.get(k, v[k]) for k in ("case_id", "revision", "details", "style", "text")
        }

    def test_notes_and_output_remain_independently_editable_across_restart(self):
        result = self.writer.generate(self.body(details="Sara needs food for her family."))
        self.assertEqual(self.used, [], "generation must not apply or send")
        old_text = result["text"]
        self.writer.save(self.body(details="Sara also needs rent support."))
        self.assertEqual(self.writer.view()["text"], old_text)
        changed = self.writer.generate(self.body())
        edited = changed["text"] + "\n\nPlease help today."
        self.writer.save(self.body(text=edited))
        restored = CaseWriter(self.app).view()
        self.assertEqual(restored["details"], "Sara also needs rent support.")
        self.assertEqual(restored["text"], edited)
        self.assertEqual(len(self.calls), 2)
        archive = library_for(self.app)
        self.assertEqual(archive.count(), 3)
        self.assertEqual(archive.examples()[0], edited)

    def test_edit_during_generation_preserves_new_notes_and_archives_unused_result(self):
        def while_writing(body):
            self.writer.save(self.body(details="A newer fact entered while writing."))
            return {"text": "An older generated result"}

        self.app.message_style = while_writing
        with self.assertRaisesRegex(ValueError, "changed while writing"):
            self.writer.generate(self.body(details="The original notes."))
        self.assertEqual(self.writer.view()["details"], "A newer fact entered while writing.")
        self.assertEqual(self.writer.view()["text"], "")
        self.assertEqual(library_for(self.app).recent(1)[0]["text"], "An older generated result")

    def test_old_case_notes_cannot_overwrite_new_case(self):
        original = self.body(details="Original case notes")
        self.writer.save(original)
        self.case = "case-two"
        with self.assertRaisesRegex(ValueError, "active case changed"):
            self.writer.save(original)
        self.assertEqual(self.writer.view()["details"], "")
        self.case = "case-one"
        self.assertEqual(self.writer.view()["details"], "Original case notes")

    def test_balance_conflict_keeps_notes_without_generating_wrong_amount(self):
        with self.assertRaisesRegex(ValueError, "current case balance"):
            self.writer.generate(self.body(details="A family needs help. Rs. 50,000 left."))
        self.assertEqual(self.calls, [])
        self.assertIn("50,000", self.writer.view()["details"])

    def test_using_a_draft_is_explicit_and_stale_details_require_regeneration(self):
        self.writer.generate(self.body(details="Current verified case facts."))
        self.writer.save(self.body(details="Corrected case facts."))
        with self.assertRaisesRegex(ValueError, "Generate again"):
            self.writer.use(self.body())
        self.assertEqual(self.used, [])
        self.writer.generate(self.body())
        self.writer.use(self.body())
        self.assertEqual(self.used[0], self.writer.view()["text"])


class LearningPromptTests(unittest.TestCase):
    def test_future_writer_uses_owner_style_separately_from_current_case_facts(self):
        ctx = {
            "left": 25000,
            "facts": "Sara's family needs food and rent support.",
            "style_examples": ["*An older hook*\n\nYousuf medical case, Rs. 99,000."],
        }
        parts = dict(
            hook="Help a family put food on the table",
            story="Sara's family needs food and rent support.",
            help="this family",
            verse="q5_2",
            concept="food",
        )
        prompts, records = [], []

        def chat(system, prompt):
            prompts.append(prompt)
            return json.dumps(parts)

        result, _ = message_styles.generate(
            "en", ctx, {}, chat, ai_call.json_of, archive=lambda text, q: records.append((text, q))
        )
        facts = prompts[0].split("CASE FACTS", 1)[1].split("MONEY:", 1)[0]
        self.assertIn("Sara", facts)
        self.assertNotIn("Yousuf", facts)
        self.assertIn("untrusted reference data", prompts[0])
        self.assertNotIn("99,000", result["text"])
        self.assertIn("Rs. 25,000 LEFT", result["text"])
        self.assertEqual([q for _, q in records], ["candidate", "validated"])


if __name__ == "__main__":
    unittest.main()
