"""How the owner really talks: Roman Urdu amounts, everyday edit phrases, and a scripted model run
proving the cancel tool is offered and the live schedules reach the model."""

import json, os, unittest
from unittest.mock import patch
import assistant, chat_policy, draft_flow, manual_commands as m


class Phrases(unittest.TestCase):
    def test_amounts_in_english_and_roman_urdu(self):
        for text, kind, amount in [
            ("34k left", "amount", 34000),
            ("25000 left", "amount", 25000),
            ("15 hazar baqi", "amount", 15000),
            ("15 hazar left", "amount", 15000),
            ("2 lakh baqi", "amount", 200000),
            ("came 2000", "money", 2000),
            ("2000 came", "money", 2000),
            ("5 hazar aaye", "money", 5000),
            ("5000 aye", "money", 5000),
            ("came 5 hazar", "money", 5000),
        ]:
            with self.subTest(text=text):
                plan = m.parse(text)
                self.assertEqual((plan["kind"], plan["amount"]), (kind, amount))

    def test_left_before_the_number_is_a_balance_but_counts_are_not(self):
        for text, amount in [("left 12k", 12000), ("left: 15000", 15000), ("left 2 lakh", 200000)]:
            self.assertEqual(m.parse(text)["amount"], amount, text)
        for text in ("left 2 groups", "left 5", "left 300 people", "how much left"):
            self.assertNotIn((m.parse(text) or {}).get("kind"), ("amount", "money"), text)

    def test_amount_words_do_not_turn_other_numbers_into_money(self):
        for text in (
            "send to 5 groups",
            "every 30 min",
            "fiverr every 15 minutes",
            "send 2 messages",
        ):
            with self.subTest(text=text):
                self.assertNotIn((m.parse(text) or {}).get("kind"), ("amount", "money"))

    def test_everyday_edit_phrases_are_edits_and_may_use_set_message(self):
        for text in (
            "add dua in the end",
            "put dua at the bottom",
            "remove the last line",
            "add my signature at the end",
            "make it shorter",
            "remove 2nd line",
            "new wording",
        ):
            with self.subTest(text=text):
                self.assertTrue(
                    chat_policy.permitted("set_message", text)
                    or chat_policy.permitted("new_wording", text)
                )

    def test_questions_never_authorize_money_or_sends(self):
        for text in (
            "what is my balance",
            "how much is left?",
            "did you send it",
            "what did you send",
            "do I have any task scheduled",
            "what is scheduled",
        ):
            with self.subTest(text=text):
                for tool in (
                    "set_left",
                    "money_came",
                    "send_appeal",
                    "send_message",
                    "dm_donors",
                    "autopilot",
                    "hold",
                ):
                    self.assertFalse(chat_policy.permitted(tool, text), (tool, text))


class ScriptedModel(unittest.TestCase):
    """The real chat loop with a scripted model and fake tools. No network, no WhatsApp."""

    def run_turn(self, text, reply_script, state=None, history=()):
        seen = {"tools": [], "messages": []}

        def fake(key, system, tools, messages):
            seen["tools"].append([t["function"]["name"] for t in tools])
            seen["messages"].append(messages)
            return reply_script.pop(0)

        calls = []
        do = {
            t["function"]["name"]: (
                lambda name: (
                    lambda **a: (
                        calls.append((name, a)),
                        "Cancelled: #30cdc6cc. Still pending: #f2c3c664."
                        if name == "schedule_task"
                        else "ok",
                    )[1]
                )
            )(t["function"]["name"])
            for t in assistant.CHAT_TOOLS
        }
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}),
            patch.object(assistant, "_chat_raw", fake),
        ):
            out = assistant.chat(
                text,
                list(history),
                state
                or {
                    "left": 15000,
                    "schedules": [
                        {
                            "position": 1,
                            "id": "f2c3c664",
                            "state": "pending",
                            "what": "Once · 10:00 AM · Resume main",
                        },
                        {
                            "position": 2,
                            "id": "30cdc6cc",
                            "state": "pending",
                            "what": "Once · 10:00 AM · Resume main",
                        },
                    ],
                },
                [],
                do,
            )
        return out, seen, calls

    def tool_call(self, name, args=None):
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args or {})},
                }
            ],
        }

    def test_cancel_second_offers_the_tool_runs_it_and_reports_the_receipt(self):
        out, seen, calls = self.run_turn(
            "Only 1 please cancel 2nd", [self.tool_call("schedule_task")]
        )
        self.assertIn("schedule_task", seen["tools"][0])
        self.assertEqual([c[0] for c in calls], ["schedule_task"])
        self.assertIn("Cancelled", out["reply"])
        self.assertNotIn("don't have", out["reply"].lower())

    def test_the_model_sees_the_live_numbered_schedules(self):
        out, seen, calls = self.run_turn(
            "what is your schedule i gave u task",
            [
                {
                    "role": "assistant",
                    "content": "Two resumes are pending at 10:00 AM: #f2c3c664 and #30cdc6cc.",
                }
            ],
        )
        context = [m["content"] for m in seen["messages"][0] if "APP_CONTEXT_JSON" in m["content"]][
            0
        ]
        self.assertIn("f2c3c664", context)
        self.assertIn("30cdc6cc", context)
        self.assertIn("ALL pending", context)
        self.assertEqual(calls, [])
        self.assertIn("f2c3c664", out["reply"])

    def test_a_status_question_cannot_cancel_or_send(self):
        out, seen, calls = self.run_turn(
            "what is scheduled?", [{"role": "assistant", "content": "Two tasks."}]
        )
        self.assertNotIn("schedule_task", seen["tools"][0])
        self.assertNotIn("send_appeal", seen["tools"][0])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()


class LongAnswersStayWhole(ScriptedModel):
    """The reply boxes (2-3 columns, no scroll) need the full text with its line breaks; nothing may flatten or cut it."""

    ANSWER = "Here's the real picture and what I'd do.\n\nWhere it stands\nBalance: Rs. 3,000 left. Auto is on for GiveLife main.\nWhatsApp: disconnected.\n\nWhat I'd do, in order\n1. Reconnect WhatsApp first.\n2. Post to GiveLife main.\n3. Send the donor DMs in two batches of 20.\n\nSuggestions\n- Ask 2 important donors for Rs. 1,500 each.\n- Use a fresh poster."

    def test_follow_up_requests_keep_the_whole_structured_answer(self):
        for text in ("give me suggestions", "suggest something", "any ideas", "what should I do"):
            with self.subTest(text=text):
                out, seen, calls = self.run_turn(
                    text, [{"role": "assistant", "content": self.ANSWER}]
                )
                self.assertEqual(out["reply"].strip(), self.ANSWER.strip())
                self.assertGreaterEqual(out["reply"].count("\n"), 10)

    def test_even_a_general_question_is_not_cut_when_the_answer_is_about_the_work(self):
        out, seen, calls = self.run_turn(
            "can you help me?", [{"role": "assistant", "content": self.ANSWER}]
        )
        self.assertEqual(out["reply"].strip(), self.ANSWER.strip())
