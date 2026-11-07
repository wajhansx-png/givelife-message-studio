import copy, json, threading, time, unittest
from unittest.mock import patch
import test_manual_sends as fixture
from test_manual_sends import app, commands
import assistant, autopilot


class RestartTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_saved_context_roundtrip_and_legacy_json_text(self):
        value = {"kind": "dm_appeal", "to": "923001234567@s.whatsapp.net", "name": "Wajdan"}
        app.remember_manual(value)
        self.assertIsInstance(app.STORE.get("manual_context"), dict)
        for old in (json.dumps(value), json.dumps(json.dumps(value)), value):
            app.LAST_MANUAL = copy.deepcopy(old)
            self.assertEqual(app.manual_recipient()["id"], value["to"])
            self.assertIsInstance(app.LAST_MANUAL, dict)

    def test_sometimes_corrupt_history_memory_and_state_do_not_crash_chat(self):
        history = [{"who": "you", "text": "hello"}, "old string", None, {"text": 42}]
        memory = ["use simple language", {"rule": "keep formatting"}, None, 42, {"rule": None}]
        for engine, screen in [("legacy text", "group"), ("{}", "{}"), ({}, {}), (None, None)]:
            with (
                patch.object(assistant, "client", return_value="fake"),
                patch.object(
                    assistant, "_chat_raw", return_value={"content": "I'm good, you?"}
                ) as model,
            ):
                result = assistant.chat(
                    "how r u", history, {"engine": engine, "screen": screen}, memory, {}
                )
            self.assertEqual(result["reply"], "I'm good, you?")
            self.assertNotIn("use simple language", model.call_args.args[1])
            self.assertIn("use simple language", json.dumps(model.call_args.args[3]))

    def test_how_are_you_after_legacy_restore_uses_complete_request_path(self):
        app.LAST_MANUAL = json.dumps(
            {"kind": "dm_appeal", "to": "923001234567@s.whatsapp.net", "name": "Wajdan"}
        )
        app.MEMORY.write_text(
            json.dumps(["remember paragraphs", {"rule": "Use Brother when unclear"}]),
            encoding="utf-8",
        )
        app.CHATLOG.write_text(
            json.dumps(["old record", {"who": "you", "text": "how r u"}]), encoding="utf-8"
        )
        app.ASSIST_TASKS.clear()
        with (
            patch.object(assistant, "client", return_value="fake"),
            patch.object(assistant, "_chat_raw", return_value={"content": "I'm good, you?"}),
        ):
            ident = app.assistant_task(
                {"text": "how r u", "request_id": "restart-how-are-you", "screen": "legacy screen"}
            )
            end = time.monotonic() + 2
            while not app.ASSIST_TASKS[ident]["done"] and time.monotonic() < end:
                time.sleep(0.005)
        self.assertNotIn("error", app.ASSIST_TASKS[ident])
        self.assertEqual(app.ASSIST_TASKS[ident]["result"]["reply"], "I'm good, you?")
        self.assertEqual(self.sent, [])

    def test_status_has_no_send_tools_and_never_requests_a_send(self):
        with (
            patch.object(assistant, "client", return_value="fake"),
            patch.object(
                assistant, "_chat_raw", return_value={"content": "Checking status."}
            ) as model,
        ):
            assistant.chat("what is going on?", [], {}, [], {})
        names = [t["function"]["name"] for t in model.call_args.args[2]]
        self.assertNotIn("send_appeal", names)
        self.assertNotIn("send_message", names)
        app.manual_command("Update")
        app.manual_command("Nothing sent yet man")
        self.assertEqual(self.sent, [])

    def test_contact_name_is_not_sent_as_literal_text(self):
        self.assertIsNone(commands.parse("send jr account"))
        self.assertIsNone(commands.parse("send jr account the message of poster and case"))

    def test_per_group_pace_changes_only_named_groups(self):
        app.ENGINE.s["rules"] = []
        app.ENGINE.s["pace_override"] = None
        app.manual_command("send in fiverr slow and in upwork fast")
        gaps = app.ENGINE.summary()["group_intervals"]
        self.assertEqual(gaps["fiverr"], 60)
        self.assertEqual(gaps["upwork"], 15)
        self.assertEqual(gaps["community"], 30)
        self.assertEqual(gaps["uet"], 30)
        self.assertEqual(self.sent, [])

    def test_recurrence_is_saved_without_immediate_post(self):
        app.ENGINE.s["rules"] = []
        app.manual_command("send to freelance groups every 30 mnts")
        self.assertEqual(app.ENGINE.gap_for("community", 90), 30)
        self.assertEqual(self.sent, [])


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.started = []
        self.last = {k: 10000 for k in app.GROUPS}
        self.eng = autopilot.Engine(
            {
                **app.ENGINE.h,
                "store_get": lambda k: None,
                "persist": lambda *a: None,
                "enabled": lambda: True,
                "on_hold": lambda: False,
                "wa_ok": lambda: True,
                "groups": lambda: list(app.GROUPS),
                "last_sent": lambda: dict(self.last),
                "busy": lambda: False,
                "start_job": lambda keys, caption: self.started.append(list(keys)) or True,
                "log": lambda *a: None,
            }
        )
        self.eng.s["rules"] = [{"kind": "gap", "group": "free", "minutes": 30, "id": 1}]
        self.eng.s["pace_override"] = None
        self.eng.s["quiet"] = None
        self.eng.s["paused"] = {}
        self.eng.s["pending_post"] = 0
        self.eng.save = lambda: None

    def test_all_five_freelance_groups_send_at_thirty_minutes_at_night(self):
        self.last["main"] = 11800
        with (
            patch.object(autopilot, "now", return_value=11800),
            patch.object(self.eng, "rhythm", return_value=(2, "Night")),
        ):
            self.eng.posting_step()
        self.assertEqual(self.started, [app.FREELANCE])
        self.assertEqual(self.eng.gap_for("community", 90), 30)

    def test_no_early_send_and_manual_confirmation_restarts_timer(self):
        self.last = {k: 11800 for k in app.GROUPS}
        self.last["main"] = 13600
        with patch.object(autopilot, "now", return_value=13599):
            self.eng.posting_step()
        self.assertEqual(self.started, [])
        self.last["main"] = 13600
        with patch.object(autopilot, "now", return_value=13600):
            self.eng.posting_step()
        self.assertEqual(self.started, [app.FREELANCE])

    def test_waiting_timer_blocks_auto_for_its_groups_only(self):
        self.last = {k: 0 for k in app.GROUPS}
        waiting = set(app.FREELANCE)
        self.eng.h["timer_waiting"] = lambda k: k in waiting
        with patch.object(autopilot, "now", return_value=20000):
            self.eng.posting_step()
        self.assertEqual(self.started, [["main"]])
        self.started.clear()
        self.last["main"] = 20000
        self.eng.s["pending_post"] = 0
        waiting.clear()  # the timer sent or was cancelled: auto resumes by its own gaps
        with patch.object(autopilot, "now", return_value=20000):
            self.eng.posting_step()
        self.assertEqual(self.started, [app.FREELANCE])

    def test_posting_independent_of_reply_scan_lock(self):
        self.last["main"] = 11800
        self.eng.lock.acquire()
        try:
            with patch.object(autopilot, "now", return_value=11800):
                t = threading.Thread(target=self.eng.posting_step)
                t.start()
                t.join(0.5)
            self.assertFalse(t.is_alive())
            self.assertEqual(self.started, [app.FREELANCE])
        finally:
            self.eng.lock.release()

    def test_hold_and_auto_off_block_independent_scheduler(self):
        self.eng.h["on_hold"] = lambda: True
        self.eng.posting_step()
        self.eng.h.update(on_hold=lambda: False, enabled=lambda: False)
        self.eng.posting_step()
        self.assertEqual(self.started, [])

    def test_specific_pace_and_broad_pace_use_latest_owner_instruction(self):
        self.eng.add_rule({"kind": "gap", "group": "fiverr", "minutes": 60})
        self.assertEqual(self.eng.gap_for("fiverr", 30), 60)
        self.assertEqual(self.eng.gap_for("upwork", 30), 30)
        self.eng.add_rule({"kind": "gap", "group": "all", "minutes": 15})
        self.assertEqual(self.eng.gap_for("fiverr", 30), 15)

    def test_restart_migrates_old_ladder_once_and_preserves_new_overrides(self):
        old = {
            "rules": [{"kind": "gap", "group": "free", "minutes": 90, "id": 1}],
            "pace_override": [15, 60],
        }
        self.eng.h["store_get"] = lambda k: json.dumps(old)
        restored = self.eng._load()
        self.eng.s = restored
        self.assertEqual(self.eng.gap_for("fiverr", 60), 30)
        self.eng.add_rule({"kind": "gap", "group": "fiverr", "minutes": 60})
        saved = copy.deepcopy(self.eng.s)
        self.eng.h["store_get"] = lambda k: json.dumps(saved)
        self.eng.s = self.eng._load()
        self.assertEqual(self.eng.gap_for("fiverr", 60), 60)


if __name__ == "__main__":
    unittest.main()
