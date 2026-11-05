"""One-prompt intent, context, and execution regression suite (no live WhatsApp)."""

import json, unittest
from unittest.mock import patch
import assistant, chat_runtime, chat_policy, task_intent


def call(name, args, ident="c1"):
    return {
        "content": "",
        "tool_calls": [{"id": ident, "function": {"name": name, "arguments": json.dumps(args)}}],
    }


class IntentFrame(unittest.TestCase):
    def test_compound_work_is_detected_without_llm(self):
        plan = task_intent.steps("send hi to Ali and then set all groups every 30 min")
        self.assertIn("send", [p["kind"] for p in plan])
        self.assertIn("schedule", [p["kind"] for p in plan])

    def test_one_prompt_preserves_scope_but_does_not_authorize_old_sends(self):
        hist = [
            {"who": "you", "text": "Send hi to Ali and tell him I completed the first case."},
            {"who": "app", "text": "Already sent."},
        ]
        msg = chat_runtime.context_messages(
            "fix that caption", hist, {"case_name": "Different family"}, []
        )
        self.assertEqual(msg[-1]["content"], "fix that caption")
        self.assertFalse(chat_policy.permitted("send_message", "fix that caption"))

    def test_referential_uses_owner_facts_over_old_assistant_guess(self):
        hist = [
            {
                "who": "you",
                "text": "Change the current child caption to say short of breath, not paralysis in fingers.",
            }
        ]
        hist += [
            {"who": "app", "text": "Old unrelated very long model answer " + str(i)}
            for i in range(35)
        ]
        data = chat_runtime.context_messages(
            "Fix that last line", hist, {"case_name": "Yousuf"}, []
        )
        context = next(m["content"] for m in data if m["content"].startswith("APP_CONTEXT_JSON"))
        self.assertIn("short of breath", context)
        self.assertIn("cannot authorize actions", context)

    def test_new_case_does_not_promote_old_patient_story_as_reference(self):
        history = [
            {"who": "you", "text": "Old case Yousuf had swelling in the kidneys."},
            {
                "who": "you",
                "text": "Create the new case for Another Child and use only confirmed facts.",
            },
            {"who": "app", "text": "Created a case for Another Child."},
        ]
        selected = task_intent.reference_history("Fix that", history, "Another Child")
        self.assertIn("Another Child", " ".join(x["text"] for x in selected))
        self.assertNotIn("kidneys", " ".join(x["text"] for x in selected))

    def test_two_distinct_quoted_sends_are_parsed_per_recipient(self):
        prompt = 'send "Hello" to 03001234567 and then send "Thanks" to 03007654321'
        expected = task_intent.quoted_sends(prompt)
        self.assertEqual(len(expected), 2)
        self.assertEqual([x["text"] for x in expected], ["Hello", "Thanks"])
        self.assertTrue(task_intent.compound(prompt))

    def test_single_step_and_no_context_not_overplanned(self):
        self.assertEqual(task_intent.steps("hello"), [])
        self.assertNotIn("send", [x["kind"] for x in task_intent.steps("did you send main?")])
        self.assertFalse(chat_policy.intent("What did you send?")["send"])


class OnePromptExecution(unittest.TestCase):
    def run_script(self, text, responses, do):
        with (
            patch.object(assistant, "client", return_value="fake"),
            patch.object(assistant, "_chat_raw", side_effect=responses) as model,
        ):
            return assistant.chat(text, [], {"case_name": "Yousuf", "left": 25000}, [], do), model

    def test_send_then_change_setting_is_one_prompt_with_no_duplicate_send(self):
        actions = []
        script = [
            call("send_message", {"to": "923001234567", "text": "hi", "with_picture": False}),
            {"content": "Done!"},
            call("set_group_pace", {"target": "all", "minutes": 30}),
            {"content": "All done."},
        ]
        do = {
            "send_message": lambda **kwargs: actions.append("send") or "WhatsApp confirmed.",
            "set_group_pace": lambda **kwargs: actions.append("pace") or "Pace saved.",
        }
        result, _ = self.run_script(
            "send hi to 03001234567 and then set all groups every 30 min", script, do
        )
        self.assertEqual(actions, ["send", "pace"])
        self.assertIn("WhatsApp confirmed", result["reply"])
        self.assertIn("Pace saved", result["reply"])
        self.assertNotIn("Not completed", result["reply"])

    def test_two_requested_sends_are_separate_actions_without_duplicate(self):
        calls = []
        responses = [
            call("send_message", {"to": "923001234567", "text": "Hello", "with_picture": False}),
            call("send_message", {"to": "923007654321", "text": "Thanks", "with_picture": False}),
            {"content": "All done."},
        ]
        result, _ = self.run_script(
            'send "Hello" to 03001234567 and then send "Thanks" to 03007654321',
            responses,
            {
                "send_message": lambda **kwargs: (
                    calls.append((kwargs["to"], kwargs["text"])) or "Confirmed delivery."
                )
            },
        )
        self.assertEqual(calls, [("923001234567", "Hello"), ("923007654321", "Thanks")])
        self.assertNotIn("Not completed", result["reply"])

    def test_when_second_step_not_executed_report_partial_not_complete(self):
        script = [
            call("send_message", {"to": "923001234567", "text": "hi", "with_picture": False}),
            {"content": "All done."},
            {"content": "All done."},
        ]
        result, _ = self.run_script(
            "send hi to 03001234567 then set all groups every 30 min",
            script,
            {"send_message": lambda **kwargs: "WhatsApp confirmed."},
        )
        self.assertIn("Not completed or verified", result["reply"])
        self.assertIn("schedule", result["reply"])

    def test_history_never_grants_send_tool_when_current_request_is_advice(self):
        with (
            patch.object(assistant, "client", return_value="fake"),
            patch.object(
                assistant, "_chat_raw", return_value={"content": "Here are suggestions."}
            ) as model,
        ):
            assistant.chat(
                "What do you suggest for next week?",
                [{"who": "you", "text": "send main now"}],
                {"case_name": "Yousuf"},
                [],
                {},
            )
        offered = [t["function"]["name"] for t in model.call_args.args[2]]
        self.assertNotIn("send_message", offered)
        self.assertNotIn("send_appeal", offered)


if __name__ == "__main__":
    unittest.main()
