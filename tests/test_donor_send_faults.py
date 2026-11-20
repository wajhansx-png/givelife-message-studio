"""Donor DMs under random WhatsApp trouble. The sender is replaced by one that, on every call, randomly:
delivers; delivers but loses the answer; does NOT deliver and says so; raises an error; or is disconnected for a few
calls. Whatever happens, and however often the owner presses Stop / Resume / Continue:

  1. nobody is ever messaged twice,
  2. nobody is marked Sent without a message having reached them (and everybody who got one is marked),
  3. the batch always ends (no endless wait),
  4. a person whose answer was unclear is never asked again (Uncertain stays Uncertain),
  5. the counts shown (sent / failed / skipped) match the people listed.

Fake WhatsApp only: nothing is sent. Seeds are fixed, so a failure can be repeated."""

import random, unittest
from collections import Counter
from unittest.mock import patch

import test_donor_hub as hub


class FaultySender:
    def __init__(self, rng, weights):
        self.rng = rng
        self.weights = weights
        self.delivered = Counter()  # phone -> messages that really reached them
        self.calls = Counter()
        self.disconnected_for = 0
        self.log = []

    def pick(self):
        kinds, w = zip(*self.weights.items())
        return self.rng.choices(kinds, w)[0]

    def __call__(self, body):
        phone = body["phone"]
        self.calls[phone] += 1
        kind = self.pick()
        self.log.append((phone, kind))
        if kind == "ok":
            self.delivered[phone] += 1
            return {"code": "SUCCESS"}
        if kind == "ack_lost":  # it went, but the answer was lost
            self.delivered[phone] += 1
            return {"code": "ERROR", "message": "timeout waiting for the gateway"}
        if kind == "lost":  # it did not go and the gateway says so
            return {"code": "ERROR", "message": "gateway refused"}
        if (
            kind == "boom"
        ):  # an error with no answer at all: it may or may not have gone; assume it went
            self.delivered[phone] += 1
            raise RuntimeError("socket closed")
        if kind == "ack_lost_raise":
            self.delivered[phone] += 1
            raise RuntimeError("socket closed")
        raise AssertionError(kind)


def step_of(body):
    if body.get("kind") == "dm_extra":
        return body["extra"]
    return "share" if body.get("kind") == "owner_text" else "case"


class StepSender(FaultySender):
    """Like FaultySender, but one person has several steps (case, video, pdf, share), each counted on its own."""

    def __init__(self, rng, weights):
        super().__init__(rng, weights)
        self.step_calls, self.step_delivered, self.order = Counter(), Counter(), []

    def __call__(self, body):
        key = (body["phone"], step_of(body))
        self.step_calls[key] += 1
        self.order.append(key)
        before = self.delivered[body["phone"]]
        try:
            return super().__call__(body)
        finally:
            if self.delivered[body["phone"]] > before:
                self.step_delivered[key] += 1


STEPS = ("case", "video", "pdf", "share")


class FaultTests(hub.DeliveryTests):
    WEIGHTS = {"ok": 70, "ack_lost": 8, "lost": 8, "boom": 6, "ack_lost_raise": 8}

    def setup_people(self, n, important=False):
        ids = []
        for i in range(n):
            d = self.add("P%02d" % i, "03001%06d" % (100 + i))
            if important:
                self.book.update(d["id"], important=True)
            ids.append(d["id"])
        return ids

    def run_until_done(self, scope, sender, max_rounds=60, **start):
        """Start / Continue again and again, like an owner who keeps pressing the button, until nothing is left."""
        self.jobs.send = sender
        states = []
        for _ in range(max_rounds):
            try:
                result = self.jobs.start(scope, 60, run=False, **start)
            except ValueError as e:
                states.append("refused: " + str(e)[:60])
                break
            if not self.jobs._load()["jobs"] or self.jobs._load()["jobs"][-1].get("state") not in (
                "Starting",
                "Sending",
                "Waiting",
            ):
                break
            self.guard = 0
            self.run_job(result)
            st = self.jobs.status()
            states.append(st["state"])
            self.check_counts(st)
            if st["state"] in ("Completed", "Nothing sent"):
                break
        return states

    def check_counts(self, st):
        listed = Counter(r.get("state") for r in st.get("receipts", []))
        self.assertEqual(st.get("sent", 0), listed.get("Sent", 0), st)
        self.assertEqual(
            st.get("failed", 0),
            listed.get("Uncertain", 0) + listed.get("Not sent", 0),
            ("failed does not match the people listed", st),
        )

    def check_invariants(self, sender, ids):
        for phone, n in sender.delivered.items():
            self.assertLessEqual(n, 1, ("a person was messaged twice", phone, sender.log))
        book = {r["id"]: r for r in self.book._load()["records"]}
        for ident in ids:
            rec = book[ident]
            got = (
                sender.delivered["0" + rec["phone"][2:]]
                if False
                else sender.delivered[rec["phone"]]
            )
            if rec.get("dm_sent"):
                self.assertEqual(
                    got, 1, ("marked Sent but nothing reached them", rec["name"], sender.log)
                )
            if got and not rec.get("dm_sent"):
                # it reached them but the answer was lost: never asked again, shown as Uncertain
                self.assertIn(
                    rec.get("delivery"),
                    ("Uncertain", "Sending"),
                    ("delivered, not shown", rec["name"], rec.get("delivery")),
                )
        for ident in ids:
            if book[ident].get("delivery") == "Uncertain":
                self.assertLessEqual(
                    sender.calls[book[ident]["phone"]], 1, "an unclear person was asked again"
                )

    def test_random_trouble_never_messages_anybody_twice(self):
        for seed in range(150):
            with self.subTest(seed=seed):
                self.tearDown()
                self.setUp()
                rng = random.Random(seed)
                ids = self.setup_people(rng.randint(2, 9), important=bool(seed % 2))
                sender = FaultySender(rng, self.WEIGHTS)
                states = self.run_until_done("all" if seed % 2 == 0 else "important", sender)
                self.assertTrue(states, "the batch never started")
                self.check_invariants(sender, ids)

    def test_trouble_in_any_step_never_repeats_a_step_skips_ahead_or_mixes_people(self):
        """Poster + caption, then the video, then the PDF, then the share question: one person at a time, in that
        order. A step that is confirmed is never sent again; one that is unclear is never retried; and nothing later
        is sent to a person whose earlier step did not go."""
        for seed in range(80):
            with self.subTest(seed=seed):
                self.tearDown()
                self.setUp()
                rng = random.Random(5000 + seed)
                self.setup_people(rng.randint(2, 6))
                sender = StepSender(rng, self.WEIGHTS)
                self.jobs.send = sender
                result = self.jobs.start(
                    "all", 60, run=False, video=True, pdf=True, follow_up="Please share this"
                )
                self.run_job(result)
                phones = []
                for key in sender.order:
                    if key[0] not in phones:
                        phones.append(key[0])
                # one person at a time: every person's calls sit together
                blocks = [k[0] for k in sender.order]
                self.assertEqual(
                    blocks, sorted(blocks, key=phones.index), ("people interleaved", sender.order)
                )
                for phone in phones:
                    mine = [step for p, step in sender.order if p == phone]
                    self.assertEqual(
                        mine, [s for s in STEPS if s in mine], ("steps out of order", phone, mine)
                    )
                    for step in STEPS:
                        self.assertLessEqual(
                            sender.step_delivered[(phone, step)],
                            1,
                            ("a step went twice", phone, step),
                        )
                        self.assertLessEqual(
                            sender.step_calls[(phone, step)],
                            1,
                            ("a step was tried again", phone, step),
                        )
                    went = [s for s in STEPS if sender.step_delivered[(phone, s)]]
                    self.assertEqual(
                        went,
                        list(STEPS[: len(went)]),
                        ("a step went after one that did not", phone, went),
                    )

    def test_a_flaky_connection_waits_and_nobody_is_sent_twice(self):
        """WhatsApp drops for a few calls in a row, then comes back; the same person is not messaged twice."""
        for seed in range(60):
            with self.subTest(seed=seed):
                self.tearDown()
                self.setUp()
                rng = random.Random(1000 + seed)
                ids = self.setup_people(rng.randint(3, 8))
                sender = FaultySender(rng, {"ok": 100})
                down = {"left": 0}
                real = sender.__call__

                def flaky(body):
                    if down["left"] > 0:
                        down["left"] -= 1
                        raise ValueError("WhatsApp is disconnected.")
                    if rng.random() < 0.3:
                        down["left"] = rng.randint(1, 3)
                        raise ValueError("WhatsApp is disconnected.")
                    return real(body)

                self.jobs.send = flaky
                result = self.jobs.start("all", 60, run=False)
                self.run_job(result)
                states = [self.jobs.status()["state"]]
                for _ in range(20):
                    if states[-1] in ("Completed", "Nothing sent"):
                        break
                    try:
                        result = self.jobs.start("all", 60, run=False)
                    except ValueError:
                        break
                    self.run_job(result)
                    states.append(self.jobs.status()["state"])
                self.check_invariants(sender, ids)
                self.assertEqual(sum(sender.delivered.values()), len(sender.delivered))

    def test_stop_at_any_point_then_continue_reaches_everybody_exactly_once(self):
        for stop_after in range(0, 8):
            with self.subTest(stop_after=stop_after):
                self.tearDown()
                self.setUp()
                ids = self.setup_people(7)
                sender = FaultySender(random.Random(stop_after), {"ok": 100})
                calls = {"n": 0}

                def with_stop(body):
                    calls["n"] += 1
                    if calls["n"] == stop_after + 1:
                        self.jobs.stop.set()  # the owner presses Stop while this message is being sent
                    return sender(body)

                self.jobs.send = with_stop
                self.run_job(self.jobs.start("all", 60, run=False))
                self.jobs.stop.clear()
                self.jobs.send = sender
                if self.jobs.status()["state"] == "Completed":
                    # Stop landed during the very last message: the batch had already reached everybody. A NEW
                    # "send to all" after a finished batch is the owner's choice to message everyone again.
                    self.check_invariants(sender, ids)
                    self.assertEqual(len(sender.delivered), 7)
                    continue
                for _ in range(5):
                    try:
                        result = self.jobs.start("all", 60, run=False)
                    except ValueError:
                        break
                    self.run_job(result)
                    if self.jobs.status()["state"] == "Completed":
                        break
                self.check_invariants(sender, ids)
                self.assertEqual(
                    len(sender.delivered), 7, ("not everybody was reached", sender.log)
                )

    def test_a_person_deleted_while_the_batch_waits_is_listed_as_skipped(self):
        ids = self.setup_people(4)
        sender = FaultySender(random.Random(1), {"ok": 100})
        self.jobs.send = sender
        victim = ids[2]
        real_resolve = self.book.resolve
        state = {"n": 0}

        def resolve(ident):
            # the second look at the person (just before sending) finds them deleted
            if ident == victim:
                state["n"] += 1
                if state["n"] == 2:
                    raise ValueError("Donor not found")
            return real_resolve(ident)

        with patch.object(self.book, "resolve", side_effect=resolve):
            self.run_job(self.jobs.start("all", 60, run=False))
        st = self.jobs.status()
        listed = [r for r in st["receipts"] if r["id"] == victim]
        self.assertEqual(st["skipped"], 1)
        self.assertEqual(len(listed), 1, "the skipped person must be listed too, not only counted")
        self.assertEqual(st["sent"], 3)


def _no_inherited_tests(cls, parent):
    """The parent class only supplies the fixture; its own tests are not run again here."""
    for name in dir(parent):
        if name.startswith("test_") and name not in vars(cls):
            setattr(cls, name, None)


_no_inherited_tests(FaultTests, hub.DeliveryTests)


if __name__ == "__main__":
    unittest.main()
