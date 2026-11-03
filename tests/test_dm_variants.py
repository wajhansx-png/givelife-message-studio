import json, unittest
from unittest.mock import patch

import test_manual_sends as fixture
from test_manual_sends import app

import assistant
import chat_policy
import dm_composer
import dm_templates
import dm_variants


class VariantTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def source(self):
        return dm_templates.build(0, app.read_left())

    def test_variant_request_is_a_bank_task_not_a_single_caption_edit(self):
        text = "generate 10 versions of this message:\n" + self.source()
        self.assertTrue(chat_policy.variant_request(text))
        self.assertTrue(chat_policy.permitted("generate_dm_variants", text))
        self.assertFalse(chat_policy.permitted("set_message", text))
        self.assertFalse(chat_policy.permitted("new_wording", text))
        self.assertFalse(chat_policy.variant_request("send 10 donors"))
        self.assertFalse(chat_policy.permitted("generate_dm_variants", "send 10 donors"))

    def test_validator_rejects_changed_structure_numbers_and_payment_line(self):
        source = self.source()
        near_copy = dm_templates.build(1, app.read_left())
        self.assertIn("not deeply rewritten", dm_variants.validate(source, near_copy))
        self.assertIn(
            "number", dm_variants.validate(source, near_copy.replace("Rs. 25,000", "Rs. 20,000"))
        )
        self.assertIn(
            "line breaks", dm_variants.validate(source, near_copy.replace("\n\n", "\n", 1))
        )
        self.assertIn(
            "payment",
            dm_variants.validate(
                source, near_copy.replace("EASYPAISA ONLY", "EASYPAISA or Cash")
            ),
        )
        self.assertIn("duplicate", dm_variants.validate(source, near_copy, [near_copy]))

    def test_fully_reworded_burial_message_passes_and_small_changes_fail(self):
        source = (
            "Bhai, Please help this grieving family with burial costs.\n\n"
            "💔 Their child has passed away. The family is seeking help with burial expenses.\n\n"
            "*They need kind people who can support them today.*\n\n"
            "Rs. 45,000 LEFT.\n\n"
            "*_Just 23 people donating Rs. 2,000 can complete the amount._*\n\n"
            "Please support them if you can.\n\n"
            "03097458815 — EASYPAISA ONLY Wajdan Khan"
        )
        rewritten = (
            "Bhai, The parents are asking for help to cover their child's burial.\n\n"
            "💔 This family lost their child and is now struggling to pay the funeral bills.\n\n"
            "*Any person who is able to give can stand beside them.*\n\n"
            "Rs. 45,000 LEFT.\n\n"
            "*_Only 23 supporters giving Rs. 2,000 each could cover this cost._*\n\n"
            "Even a small contribution would matter.\n\n"
            "03097458815 — EASYPAISA ONLY Wajdan Khan"
        )
        self.assertEqual(dm_variants.validate(source, rewritten), "")
        small = source.replace("Please help", "Please kindly help")
        self.assertIn("not deeply rewritten", dm_variants.validate(source, small))
        self.assertIn(
            "too similar",
            dm_variants.validate(
                source, rewritten, [rewritten.replace("The parents", "These parents")]
            ),
        )
        self.assertIn("number", dm_variants.validate(source, rewritten.replace("45,000", "40,000")))

    def test_canonical_bank_generate_has_twenty_unique_complete_versions(self):
        bank = app.donors().messages.generate(self.source(), 10)
        self.assertEqual(len(bank["items"]), 20)
        self.assertEqual(bank["requested"], 10)
        self.assertEqual(len({row["text"] for row in bank["items"]}), 20)
        self.assertTrue(all(dm_composer.complete(row["text"]) for row in bank["items"]))
        self.assertEqual(bank["items"][0]["text"], self.source())
        self.assertEqual(bank["mode"], "structured")

    def test_callback_puts_first_version_on_dm_screen(self):
        source = self.source()
        callbacks = app.chat_callbacks(
            "generate 10 versions of this message:\n" + source, revision=app.OWNER_REVISION
        )
        result = callbacks["generate_dm_variants"](source=source, count=10)
        self.assertIn("Prepared 10 versions", result["reply"])
        bank = app.donors().messages.get()
        self.assertEqual(app.get_message("dm")["text"], bank["items"][0]["text"])
        self.assertEqual(result["bank_count"], 20)

    def test_assistant_calls_generate_tool_and_saves_bank(self):
        source = self.source()
        prompt = "generate 10 versions of this message:\n" + source
        messages = [
            {
                "tool_calls": [
                    {
                        "id": "gen",
                        "function": {
                            "name": "generate_dm_variants",
                            "arguments": json.dumps({"source": source, "count": 10}),
                        },
                    }
                ]
            },
            {"content": "Done."},
        ]
        with (
            patch.object(assistant, "client", return_value="fake-key"),
            patch.object(assistant, "_chat_raw", side_effect=messages),
        ):
            result = assistant.chat(
                prompt,
                [],
                {"drafts": json.loads(app.DRAFT.read_text(encoding="utf-8"))},
                [],
                app.chat_callbacks(prompt, revision=app.OWNER_REVISION),
            )
        self.assertIn("Prepared 10 versions", result["reply"])
        self.assertEqual(
            app.get_message("dm")["text"], app.donors().messages.get()["items"][0]["text"]
        )

    def test_custom_bank_survives_dm_screen_changes(self):
        custom = self.source().replace("EASYPAISA ONLY", "EASYPAISA or Cash")

        def fake_generate(source, count=10, avoid=None):
            start = len(avoid or [])
            return [
                dm_templates.build(start + i, app.read_left()).replace(
                    "EASYPAISA ONLY", "EASYPAISA or Cash"
                )
                for i in range(count)
            ]

        with patch("dm_variants.generate", side_effect=fake_generate):
            bank = app.donors().messages.generate(custom, 10)
        self.assertEqual(len(bank["items"]), 20)
        self.assertEqual(bank["mode"], "custom")
        first = bank["items"][0]["text"]
        app.save_draft("dm", dm_templates.build(0, app.read_left()))
        self.assertEqual(app.donors().messages.get()["items"][0]["text"], first)
        app.set_left(30000)
        synced = app.donors().messages.get()["items"][0]["text"]
        self.assertIn("Rs. 30,000", synced)
        self.assertNotIn("Rs. 25,000", synced)


if __name__ == "__main__":
    unittest.main()
