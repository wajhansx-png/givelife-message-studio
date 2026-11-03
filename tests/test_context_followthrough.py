"""Owner transcript regressions. Synthetic drafts; no external sends or API."""

import unittest
import chat_runtime
import draft_flow
import chat_memory, task_intent, tempfile
import assistant, json, time, threading, urllib.request
import rules, manual_commands
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app


class ContextFollowthrough(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_show_reads_active_dm_instead_of_dashboard_group(self):
        reads = []
        state = {"screen": {"view": "group"}, "draft_task": {"kind": "dm", "state": "ready"}}
        result = chat_runtime.run_chat(
            "show",
            [],
            state,
            [],
            {"get_message": lambda kind: reads.append(kind) or {"text": "Saved DM"}},
        )
        self.assertEqual(reads, ["dm"])
        self.assertEqual(result["reply"], "Saved DM")

    def test_half_prompt_edit_works_through_real_server_guard(self):
        original = app.get_message("dm")["text"]
        app.workflow().begin("make the DM shorter", "dm", original)
        app.workflow().revise(original)
        callback = app.chat_callbacks("fix that", revision=app.OWNER_REVISION)
        result = callback["set_message"](
            kind="dm", text=original.replace("Brother,", "Brother, please read this.")
        )
        self.assertTrue(result)
        self.assertEqual(app.workflow().data["kind"], "dm")

    def test_explicit_group_overrides_active_dm_and_screen(self):
        self.assertEqual(
            draft_flow.current_kind(
                "show group message", {"draft_task": {"kind": "dm"}, "screen": {"view": "dm"}}
            ),
            "group",
        )

    def test_context_never_grants_send_or_ui_changes(self):
        state = {"draft_task": {"kind": "dm", "state": "ready"}}
        self.assertFalse(chat_runtime.contextual_draft_fix("fix that dropdown UI", [], state))
        self.assertFalse(chat_runtime.contextual_draft_fix("fix that", [], {}))
        callback = app.chat_callbacks("fix that", revision=app.OWNER_REVISION)
        with self.assertRaises(ValueError):
            callback["send_dm_appeal"](to="923001234567")

    def test_wrong_draft_kind_is_rejected_for_half_prompt(self):
        text = app.get_message("dm")["text"]
        app.workflow().begin("edit DM", "dm", text)
        app.workflow().revise(text)
        before = app.get_message("group")["text"]
        with self.assertRaisesRegex(ValueError, "active dm"):
            app.chat_callbacks("fix that", revision=app.OWNER_REVISION)["set_message"](
                kind="group", text="Wrong draft"
            )
        self.assertEqual(app.get_message("group")["text"], before)

    def test_dm_screen_with_no_active_task_does_not_start_group_edit(self):
        app.workflow().data = {}
        original = app.get_message("dm")["text"]
        group = app.get_message("group")["text"]
        callback = app.chat_callbacks(
            "make it shorter", revision=app.OWNER_REVISION, screen={"view": "dm"}
        )
        callback["set_message"](kind="dm", text=original)
        self.assertEqual(app.workflow().data["kind"], "dm")
        self.assertEqual(app.get_message("group")["text"], group)

    def test_context_cannot_override_no_edit_or_different_task(self):
        original = app.get_message("dm")["text"]
        app.workflow().begin("edit DM", "dm", original)
        app.workflow().revise(original)
        for prompt in (
            "fix that but do not change the caption",
            "fix that task for Akhtar",
            "fix that batch timer",
        ):
            with self.subTest(prompt=prompt):
                self.assertFalse(
                    draft_flow.contextual_edit(prompt, [], {"draft_task": app.workflow().data})
                )
                if "do not change" in prompt:
                    with self.assertRaises(ValueError):
                        app.chat_callbacks(prompt, revision=app.OWNER_REVISION)["set_message"](
                            kind="dm", text="Wrong change"
                        )
        self.assertEqual(app.get_message("dm")["text"], original)

    def test_retired_correction_stays_retired_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            k = chat_memory.Knowledge(folder)
            k.archive("app", "Old reply", "reply")
            old = "Use Sister when the name is unclear."
            k.feedback("reply", old, True)
            k.archive("you", old)
            k.remember("Use Brother when the name is unclear.", "owner_confirmed_correction")
            reloaded = chat_memory.Knowledge(folder)
            found = reloaded.retrieve("unclear name greeting Brother Sister", 20)
            self.assertFalse(any(x["text"] == old for x in found))
            self.assertTrue(any("Use Brother" in x["text"] for x in found))

    def test_half_prompt_retrieval_gets_topic_but_no_action_permission(self):
        query = task_intent.retrieval_query(
            "fix it", [{"who": "you", "text": "Keep bold and italic in the DM caption."}], {}
        )
        self.assertIn("bold and italic", query)
        self.assertEqual(task_intent.retrieval_query("hello", [], {}), "hello")

    def test_old_case_draft_hash_does_not_select_current_case_kind(self):
        state = {
            "screen": {"view": "group"},
            "draft_task": {"kind": "dm", "state": "ready", "hash": "older-case-hash"},
            "drafts": {"dm": "New case DM"},
        }
        self.assertEqual(draft_flow.current_kind("show", state), "group")
        self.assertFalse(draft_flow.contextual_edit("fix that", [], state))
        self.assertFalse(
            draft_flow.contextual_edit(
                "fix that",
                [{"who": "you", "text": "Make the DM shorter for the old patient."}],
                state,
            )
        )

    def test_schedule_read_failure_is_unknown_not_no_tasks(self):
        with patch.object(app, "timed_scheduler", side_effect=OSError("offline")):
            state = app.studio_state()
        self.assertIsNone(state["schedules"])
        self.assertIn("unavailable", assistant._slim(state)["schedules_note"])

    def test_speed_words_never_create_an_unnamed_all_group_rule(self):
        self.assertEqual(rules.pace_rules("send fast"), [])
        self.assertEqual(rules.pace_rules("send thanks to Akhtar fast"), [])
        self.assertEqual(manual_commands.parse("send thanks to Akhtar fast")["to"], "Akhtar")
        self.assertEqual(rules.pace_rules("post in main fast")[0]["group"], "main")
        self.assertEqual(rules.pace_rules("post in all groups slow")[0]["minutes"], 60)
        rule, _ = rules.parse("send to Ali every 30 minutes")
        self.assertFalse(rule and rule.get("kind") == "gap")

    def test_http_half_prompt_updates_dm_then_show_reads_it(self):
        original = app.get_message("dm")["text"]
        updated = original.replace("Brother,", "Brother, please read this.")
        app.workflow().begin("rewrite this DM", "dm", original)
        app.workflow().revise(original)
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def request(path, body=None):
            req = urllib.request.Request(
                "http://127.0.0.1:" + str(server.server_port) + path,
                data=json.dumps(body).encode() if body else None,
                headers={
                    "Authorization": "Bearer test-only-studio-access-key",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req) as r:
                return json.load(r)

        responses = [
            {
                "tool_calls": [
                    {
                        "id": "edit",
                        "function": {
                            "name": "set_message",
                            "arguments": json.dumps({"kind": "dm", "text": updated}),
                        },
                    }
                ]
            },
            {"content": "Saved."},
        ]
        try:
            with (
                patch.object(assistant, "client", return_value="fake"),
                patch.object(assistant, "_chat_raw", side_effect=responses),
            ):
                started = request(
                    "/assistant",
                    {
                        "text": "fix that",
                        "request_id": "context-http-edit",
                        "screen": {"view": "group"},
                    },
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    result = request("/assistant-status/" + started["task_id"])
                    if result.get("done"):
                        break
                    time.sleep(0.02)
                self.assertTrue(result.get("done"))
                self.assertNotIn("error", result)
            self.assertEqual(app.get_message("dm")["text"], updated)
            self.assertEqual(
                request("/assistant", {"text": "show", "screen": {"view": "group"}})["reply"],
                updated,
            )
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
