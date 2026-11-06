"""No network/WhatsApp access: approval and selection regression tests."""

import threading
import unittest

from agents_system import Manager, Writer, intent_text


class MemoryBank:
    def __init__(self):
        self.source = "Original saved Group message"
        self.revision = "r1"
        self.saves = 0

    def save(self, kind, text, revision=None):
        assert kind == "group"
        if revision != self.revision:
            raise ValueError("Message changed on another screen.")
        self.source = text
        self.revision = "r2"
        self.saves += 1
        return {"source": text}


class FakeApp:
    def __init__(self):
        self.bank = MemoryBank()

    def focus_bank(self):
        return self.bank

    def get_message(self, kind):
        return {"text": self.bank.source}


class Checker:
    def __init__(self):
        self.errors = []

    def problems(self, text, kind="group"):
        return list(self.errors)


class FakeSystem:
    def __init__(self):
        self.app = FakeApp()
        self.state = {
            "writer_preview": {
                "id": "review-one",
                "status": "pending",
                "kind": "group",
                "text": "*Help this family*\nRs. 20,000 still needed.",
                "base_revision": "r1",
            },
            "chat": [],
            "ctx": {}
        }
        self.ctx = self.state["ctx"]
        self.agents = {"checker": Checker()}
        self.approved = []

    def note_draft(self, status, draft):
        self.approved.append((status, draft))


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.sys = FakeSystem()
        self.writer = Writer(self.sys)

    def test_explicit_approval_language(self):
        for words in ("Approved", "approve this", "I approve it", "Approved, save it to Group"):
            with self.subTest(words=words):
                self.assertIsNotNone(Writer.APPROVE.fullmatch(intent_text(words)))
        for words in ("okay", "please send it", "write another", "maybe approved"):
            self.assertIsNone(Writer.APPROVE.fullmatch(intent_text(words)))

    def test_saved_only_after_matching_approval(self):
        self.assertEqual(self.sys.app.bank.saves, 0)
        ok, msg = self.writer.approve("review-one")
        self.assertTrue(ok, msg)
        self.assertEqual(self.sys.app.bank.saves, 1)
        self.assertEqual(self.sys.app.bank.source, "*Help this family*\nRs. 20,000 still needed.")
        self.assertIsNone(self.sys.state["writer_preview"])
        self.assertEqual(len(self.sys.approved), 1)
        self.assertIn("Nothing was sent", msg)

    def test_stale_id_and_double_approval_cannot_save(self):
        self.assertFalse(self.writer.approve("wrong-id")[0])
        self.assertEqual(self.sys.app.bank.saves, 0)
        self.assertTrue(self.writer.approve("review-one")[0])
        self.assertFalse(self.writer.approve("review-one")[0])
        self.assertEqual(self.sys.app.bank.saves, 1)

    def test_checker_blocks_unapproved_facts(self):
        self.sys.agents["checker"].errors = ["wrong amount"]
        ok, reason = self.writer.approve("review-one")
        self.assertFalse(ok)
        self.assertIn("wrong amount", reason)
        self.assertEqual(self.sys.app.bank.saves, 0)

    def test_changed_group_draft_is_not_overwritten(self):
        self.sys.app.bank.revision = "updated-on-another-screen"
        ok, reason = self.writer.approve("review-one")
        self.assertFalse(ok)
        self.assertIn("changed", reason)
        self.assertEqual(self.sys.app.bank.saves, 0)

    def test_manager_approve_requires_selected_id(self):
        mgr = Manager.__new__(Manager)
        mgr.app = self.sys.app
        mgr.lock = threading.RLock()
        mgr.state = self.sys.state
        mgr.agents = {"writer": self.writer}
        mgr._say = lambda *args: None
        mgr.save = lambda: None
        mgr.view = lambda: {"writer_preview": mgr.state.get("writer_preview")}
        with self.assertRaises(ValueError):
            mgr.act({"action": "writer_approve", "preview_id": "old-id"})
        self.assertEqual(self.sys.app.bank.saves, 0)
        result = mgr.act({"action": "writer_approve", "preview_id": "review-one"})
        self.assertIn("saved to Group Messages", result["reply"])
        self.assertEqual(self.sys.app.bank.saves, 1)

    def test_next_never_saves_and_rejects_old_preview(self):
        mgr = Manager.__new__(Manager)
        mgr.app = self.sys.app
        mgr.lock = threading.RLock()
        mgr.state = self.sys.state
        mgr.agents = {"writer": self.writer}
        mgr._say = lambda *args: None
        mgr.save = lambda: None
        mgr.view = lambda: {"writer_preview": mgr.state.get("writer_preview")}

        def run(agent, prompt, fn):
            self.assertIn("Change BOTH the opening and body", prompt)
            mgr.state["writer_preview"] = {
                **mgr.state["writer_preview"],
                "id": "review-two",
                "text": "*Another hook*\nSame confirmed facts",
            }

        mgr._run = run
        result = mgr.act({"action": "writer_next", "preview_id": "review-one"})
        self.assertEqual(result["writer_preview"]["id"], "review-two")
        self.assertEqual(self.sys.app.bank.saves, 0)
        with self.assertRaises(ValueError):
            mgr.act({"action": "writer_next", "preview_id": "review-one"})


if __name__ == "__main__":
    unittest.main()
