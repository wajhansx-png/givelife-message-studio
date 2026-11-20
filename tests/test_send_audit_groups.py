"""Audit: a post to several groups, one of which fails. Fake transport at the lowest level (the gateway call):
the recorded sequence (chat, caption, picture) and the saved results are compared with independent expectations."""

import json, types, unittest
from pathlib import Path
from unittest.mock import patch

import test_manual_sends as fixture
from test_manual_sends import app


class GroupPartialFailure(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown
    wait = fixture.SendTests.wait

    def record(self, fail_jid):
        wire = []

        def curl(args, **kwargs):
            fields = [args[i + 1] for i, x in enumerate(args) if x == "-F"]
            by = {x.split("=", 1)[0]: x.split("=", 1)[1] for x in fields if "=" in x}
            jid = by["phone"]
            caption = Path(by["caption"].lstrip("<")).read_text(encoding="utf-8")
            wire.append({"jid": jid, "caption": caption, "picture": by.get("image", "")})
            if jid == fail_jid:
                return types.SimpleNamespace(
                    stdout=json.dumps({"code": "ERROR", "message": "group refused"}).encode()
                )
            return types.SimpleNamespace(
                stdout=json.dumps(
                    {"code": "SUCCESS", "results": {"message_id": "m%d" % len(wire)}}
                ).encode()
            )

        return wire, curl

    def test_the_failed_group_is_reported_not_retried_and_the_others_keep_their_own_text(self):
        keys = ["fiverr", "main", "community"]  # not alphabetical, not the saved order
        jids = [app.GROUPS[k][1] for k in keys]
        wire, curl = self.record(fail_jid=jids[1])
        with patch.object(app.subprocess, "run", curl):
            with patch.object(
                app.threading.Thread, "start"
            ):  # run it here, without the real wait between groups
                ident = app.start_send_job(keys, "ignored caption", manual=True)
            job = app.JOBS[ident]
            with patch.object(app.JOB_CANCEL[ident], "wait", return_value=False):
                app.run_job(ident, job["keys"], job["caption"])
        # the exact order the owner chose, one call per group, no retry of the failed one; an incomplete group post
        # leaves every later group untouched (by design), so the third group is never called
        self.assertEqual([w["jid"] for w in wire], jids[:2])
        self.assertNotIn(jids[2], [w["jid"] for w in wire])
        # each group got its own saved version (never the same text twice, never the ignored caption)
        bank = app.STORE.get("focus_wording")["group"]["items"]
        self.assertEqual(len({w["caption"] for w in wire}), 2)
        self.assertTrue(all(w["caption"] in bank for w in wire))
        self.assertEqual([w["caption"] for w in wire], job["captions"][:2])
        self.assertFalse(any("ignored caption" in w["caption"] for w in wire))
        # the receipts say who got it and who did not
        self.assertEqual([r["code"] for r in job["results"]], ["SUCCESS", "ERROR"])
        self.assertEqual(sum(1 for r in job["results"] if r["code"] == "SUCCESS"), 1)
        self.assertIn("group refused", json.dumps(job["results"]))
        # the picture goes with every group's message
        self.assertTrue(all(w["picture"] for w in wire))


if __name__ == "__main__":
    unittest.main()


class BalanceAtSendTime(unittest.TestCase):
    """The amount in a caption is today's amount at the moment it is sent, on every DM route, not the amount when the
    batch was started."""

    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    TEXT = (
        "Brother, please read about Ahmed and the support the family requested.\n\n"
        "💔 His parents reported an accident and a leg operation.\n_Ahmed is 9._\n\n"
        "💰 *_Rs. 25,000 still needed for treatment._*\n\n"
        "*_Just 13 people donating Rs. 2,000_*\n*_OR 25 people contributing Rs. 1,000 🤲_*\n\n"
        "_If you are reading this, it's you._ Don't wait for someone else.\n\n"
        "📲 *03097458815*\nEASYPAISA ONLY\nWajdan Khan (GiveLife Foundation account)\n\nReply *Done* after donating."
    )

    def final_caption(self, kind):
        app.set_left(18000)  # donations arrived after the batch was started
        body = {
            "target": "phone",
            "phone": "923001112233",
            "message": self.TEXT,
            "poster": True,
            "kind": kind,
            "name": "Ali",
            "gender": "Brother",
        }
        result = app.send_custom(body)
        self.assertEqual(result["code"], "SUCCESS", result)
        return self.sent[-1]["text"]

    def test_every_dm_route_sends_todays_amount(self):
        for kind in (
            "donor_batch",
            "donor_manual",
            "owner_text",
            "volunteer_batch",
            "volunteer_manual",
        ):
            with self.subTest(kind):
                self.tearDown()
                self.setUp()
                text = self.final_caption(kind)
                self.assertIn("Rs. 18,000", text, kind)
                self.assertNotIn("25,000", text, kind)
                self.assertIn("9 people donating Rs. 2,000", text)
                self.assertIn("18 people contributing Rs. 1,000", text)
