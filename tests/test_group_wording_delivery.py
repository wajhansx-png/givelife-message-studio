import unittest, io, json
from unittest.mock import patch, Mock
import test_manual_sends as fixture
from test_manual_sends import app
import assistant


class GroupWordingDeliveryTests(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def test_group_worker_dispatches_distinct_reserved_captions(self):
        ident = "wording-worker"
        keys = ["main", "community"]
        captions = ["First owner-approved wording", "Second owner-approved wording"]
        app.JOBS[ident] = {
            "results": [],
            "manual": True,
            "captions": captions,
            "with_picture": True,
            "keys": keys,
            "caption": "Original",
        }
        event = Mock()
        event.is_set.return_value = False
        event.wait.return_value = False
        app.JOB_CANCEL[ident] = event
        app.ACTIVE = ident
        with (
            patch.object(app, "send_image", return_value={"code": "SUCCESS"}) as send,
            patch.object(app, "on_hold", return_value=False),
        ):
            app.run_job(ident, keys, "Original")
        self.assertEqual([c.args[1] for c in send.call_args_list], captions)
        self.assertEqual(len(app.JOBS[ident]["results"]), 2)

    def test_writing_call_disables_reasoning_without_changing_chat_default(self):
        response = io.StringIO(
            json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}]})
        )
        with (
            patch.dict(
                assistant.os.environ,
                {"DEEPSEEK_THINKING": "enabled", "DEEPSEEK_REASONING_MODEL": "deepseek-reasoner"},
            ),
            patch.object(assistant.urllib.request, "urlopen") as network,
        ):
            network.return_value.__enter__.return_value = response
            assistant._chat_raw(
                "fake-key",
                "system",
                [],
                [{"role": "user", "content": "Synthetic"}],
                thinking_mode=False,
            )
            body = json.loads(network.call_args.args[0].data)
            self.assertEqual(body["thinking"], {"type": "disabled"})
            self.assertNotIn("reasoning_effort", body)
