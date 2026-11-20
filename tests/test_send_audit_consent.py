"""Audit: consent. A decline, an opt-out or an unclear reply never starts the agreed-to-share sequence; an opt-out that
arrives while a send is queued is honoured by every route. Fake WhatsApp only: nothing is sent."""

import unittest

import case_run
import test_donor_hub as hub
from test_case_run import Base
from test_manual_sends import app

CASE = "decline"


class Replies(Base):
    """GIKI 1 person receives the case, then answers."""

    def setUp(self):
        super().setUp()
        saved = set(
            app.BLOCKED
        )  # an opt-out is remembered in a module-wide set: put it back after each test
        self.addCleanup(lambda: (app.BLOCKED.clear(), app.BLOCKED.update(saved)))

    def waiting(self):
        top, giki = self.people(1, 1)
        self.fast.start()
        self.addCleanup(self.fast.stop)
        self.approve()
        self.addCleanup(self.stop_everything)
        self.assertTrue(self.tick_until(lambda: self.state()["giki"].get(self.phone(giki[0]))))
        return giki[0]

    def answer(self, text):
        did = self.waiting()
        self.reply(did, text, "c1")
        self.tick_until(lambda: self.state()["giki"][self.phone(did)]["step"] != "waiting", 120)
        step = self.state()["giki"][self.phone(did)]["step"]
        self.tick_until(lambda: False, 6)  # give a wrongly started share every chance to go out
        return did, step

    def check_no_share(self, text, allowed):
        did, step = self.answer(text)
        self.assertIn(step, allowed, (text, step))
        self.assertEqual(self.shared, [], f"{text!r} started the share sequence")
        return did, step


DECLINES = ("No", "nahi", "Not now", "sorry", "no thanks", "Na", "no problem but not now")
UNCLEAR = (
    "maybe",
    "I will think and tell you",
    "who are you?",
    "ok but later",
    "yes no",
    "ok no thanks",
    "g nahi",
    "yes sure why not",
    "Yes, I can't",
    "yes stop",
    "haan lekin abhi nahi",
)
OPT_OUTS = ("stop", "STOP", "unsubscribe", "please do not message me again", "dont message me")

for _i, _text in enumerate(DECLINES):
    setattr(
        Replies,
        f"test_decline_{_i}_never_shares",
        lambda self, t=_text: self.check_no_share(t, ("declined", "needs")) and None,
    )
for _i, _text in enumerate(UNCLEAR):
    setattr(
        Replies,
        f"test_unclear_{_i}_waits_for_the_owner",
        lambda self, t=_text: self.check_no_share(t, ("needs", "declined")) and None,
    )


def _opt_out(self, text):
    did, step = self.check_no_share(text, ("declined", "needs"))
    phone = self.phone(did)
    self.assertTrue(
        self.h.exclusion_reason(case_run.normalize_phone(phone)), "the opt-out was not recorded"
    )
    self.assertFalse(self.h.eligible(case_run.normalize_phone(phone)))


for _i, _text in enumerate(OPT_OUTS):
    setattr(
        Replies,
        f"test_opt_out_{_i}_is_recorded_and_never_shares",
        lambda self, t=_text: _opt_out(self, t),
    )


class Words(unittest.TestCase):
    def test_a_yes_with_a_no_in_it_is_never_an_agreement(self):
        for text in DECLINES + UNCLEAR:
            self.assertNotEqual(case_run.agreement(text), "agree", text)
        for text in ("Yes", "yes sure", "ok", "Haan ji", "Jee zaroor", "Bilkul"):
            self.assertEqual(case_run.agreement(text), "agree", text)


class Mid(hub.DeliveryTests):
    """An opt-out that arrives while the batch is queued or between a person's steps."""

    def setUp(self):
        super().setUp()
        self.opted = set()
        self.jobs.eligible = lambda phone: phone not in self.opted

    def test_an_opt_out_while_the_batch_waits_skips_that_person_and_nobody_else(self):
        ids = [self.add("P%d" % i, "03001%06d" % (100 + i))["id"] for i in range(4)]
        victim = self.book.resolve(ids[2])["phone"]
        first = self.book.resolve(ids[0])["phone"]
        real = self.send

        def send(body):
            out = real(body)
            if body["phone"] == first:
                self.opted.add(victim)  # the opt-out arrives while the first person is being sent
            return out

        self.jobs.send = send
        self.run_job(self.jobs.start("all", 60, run=False))
        phones = [b["phone"] for b, _ in self.sent]
        self.assertNotIn(victim, phones)
        self.assertEqual(len(phones), 3)
        st = self.jobs.status()
        self.assertEqual((st["sent"], st["skipped"]), (3, 1))
        listed = [r["state"] for r in st["receipts"] if r["id"] == ids[2]]
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0].startswith("Skipped"), listed)

    def test_an_opt_out_between_the_case_and_the_share_message_stops_the_share(self):
        self.add("Ali", "03001230001")
        real = self.send

        def send(body):
            out = real(body)
            if body.get("kind") != "owner_text":
                self.opted.add(body["phone"])  # "stop" arrives right after the first message
            return out

        self.jobs.send = send
        self.run_job(self.jobs.start("all", 60, run=False, follow_up="Please share this"))
        kinds = [b.get("kind") for b, _ in self.sent]
        self.assertNotIn("owner_text", kinds, kinds)
        self.assertEqual(
            self.jobs.status()["receipts"][0].get("follow_up"), "Skipped: opted out or blocked"
        )


def _no_inherited_tests(cls, parent):
    """The parent class only supplies the fixture; its own tests are not run again here."""
    for name in dir(parent):
        if name.startswith("test_") and name not in vars(cls):
            setattr(cls, name, None)


_no_inherited_tests(Mid, hub.DeliveryTests)


if __name__ == "__main__":
    unittest.main()
