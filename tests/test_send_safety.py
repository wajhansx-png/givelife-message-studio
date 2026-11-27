"""Send safety across routes, restarts and partial results. Fake WhatsApp only: every check looks at the exact
recipient, account, message and order that went out, never only at a count."""

import threading
import time
from unittest.mock import patch

import test_case_audience_routing as tcar
import test_giki_line as tgl


class TwoRoutesOnePerson(tcar.Routing):
    """A donor who is Top and in GIKI 1 must get the appeal once, whichever route starts first."""

    def appeals(self):
        return [c for c in self.calls if c["kind"] == "donor_batch"]

    def settle(self):
        self.assertTrue(
            self.tick_until(
                lambda: (
                    not self.h.jobs.active
                    and all(
                        self.state()["rows"][k]["state"] in ("done", "off", "idle")
                        for k in ("giki1", "giki2", "top")
                        if k in self.state()["rows"]
                    )
                )
            )
        )

    def test_manual_send_and_case_auto_started_together_reach_each_person_once(self):
        from unittest.mock import patch

        self.plan({"giki1", "top"})
        token = self.cr.summary()["token"]
        gate, refused = threading.Barrier(2), []

        def manual():
            gate.wait()
            try:
                self.h.jobs.start("important", gap_seconds=0, poster=False)
            except ValueError as e:
                refused.append(("manual", str(e)))

        def case():
            gate.wait()
            try:
                self.cr.start(token)
            except ValueError as e:
                refused.append(("case", str(e)))

        with patch.object(tcar.app, "set_auto"):
            runs = [threading.Thread(target=manual), threading.Thread(target=case)]
            [t.start() for t in runs]
            [t.join(10) for t in runs]
            self.settle()
            # the owner tries the refused route again once the first one finished: still nobody twice
            if any(who == "case" for who, _ in refused):
                summary = self.cr.summary()
                if not summary["blockers"]:
                    self.cr.start(summary["token"])
            elif any(who == "manual" for who, _ in refused):
                try:
                    self.h.jobs.start("important", gap_seconds=0, poster=False)
                except ValueError:
                    pass
            self.settle()
        phones = [c["phone"] for c in self.appeals()]
        self.assertTrue(phones, refused)
        self.assertEqual(len(phones), len(set(phones)), phones)
        everyone = {self.phone(i) for i in self.ids.values()}
        self.assertTrue(set(phones) <= everyone)
        self.assertFalse([c for c in self.calls if c.get("line")])  # all from the main account


class StepsPerPerson(tgl.Fixture):
    """One person gets case, video, PDF, share in that order before the next chat starts; a video swap, a double
    Resume or an opt-out in the middle never makes a step go twice or reach the wrong person."""

    def setUp(self):
        super().setUp()
        self.on = [("video", "b" * 32), ("pdf", "a" * 32)]

    def people(self, n):
        for i in range(n):
            self.g.mutate({"action": "add", "name": f"Step P{i}", "phone": f"0300 700000{i}"})
        self.g.mutate({"action": "message", "text": "Salam {name}, please share this."})
        return [b["phone"] for b in self.g.book._load()["records"]]

    def got(self):
        def step(b):
            return b["extra"] if b.get("kind") == "dm_extra" else ("case" if b.get("poster") else "share")

        return [(b["phone"], step(b), b.get("line")) for b in self.sent]

    def test_a_video_swapped_mid_batch_reaches_each_person_once_and_in_order(self):
        phones = self.people(3)

        def swap(body):
            if body.get("extra") == "video" and body["phone"] == phones[0]:
                self.on = [("video", "c" * 32), ("pdf", "a" * 32)]  # the owner picks another video now

        self.on_send = swap
        self.go(self.g, {"action": "send_all", "request_id": "swap", "poster": False})
        self.run_job(self.g.jobs)
        got = self.got()
        self.assertEqual(
            [(p, s) for p, s, _ in got],
            [(p, s) for p in phones for s in ("case", "video", "pdf", "share")],
        )
        self.assertTrue(all(line == "giki" for _, _, line in got))

    def test_resume_pressed_twice_sends_every_missing_step_once(self):
        phones = self.people(3)

        def stop_at_video(body):
            if body.get("extra") == "video" and body["phone"] == phones[1]:
                self.g.jobs.stop.set()  # Stop while person 2's video is uploading

        self.on_send = stop_at_video
        self.go(self.g, {"action": "send_all", "request_id": "twice", "poster": False})
        self.run_job(self.g.jobs)
        self.on_send = None
        self.g.jobs.stop.clear()
        gate, answers = threading.Barrier(2), []

        def press():
            gate.wait()
            try:
                answers.append(self.g.mutate({"action": "resume"}))  # the real background sender
            except ValueError as e:
                answers.append(str(e))

        taps = [threading.Thread(target=press) for _ in range(2)]
        with patch("giki_line.time.sleep", lambda s: time.sleep(0.01)):  # "still stopping" waits 10 ms, not 1 s
            [t.start() for t in taps]
            [t.join(60) for t in taps]
        for _ in range(300):  # the resumed batch has one person left: their first DM goes at once
            if not self.g.jobs.active and self.g.jobs._load()["jobs"][-1].get("state") == "Completed":
                break
            time.sleep(0.05)
        got = [(p, s) for p, s, _ in self.got()]
        self.assertEqual(len(got), len(set(got)), ("a step went twice", got, answers))
        self.assertEqual(
            sorted(got),
            sorted((p, s) for p in phones for s in ("case", "video", "pdf", "share")),
            answers,
        )

    def test_an_opt_out_after_the_first_message_stops_that_persons_other_steps(self):
        phones = self.people(3)
        out = set()
        self.g.jobs.eligible = lambda phone: phone not in out

        def opt_out(body):
            if body["phone"] == phones[1] and not body.get("kind") == "dm_extra":
                out.add(phones[1])  # person 2 replies STOP right after the case message

        self.on_send = opt_out
        self.go(self.g, {"action": "send_all", "request_id": "optout", "poster": False})
        self.run_job(self.g.jobs)
        # their other steps are not sent; the queue pauses there (nothing unclear is pushed on) until Resume
        self.assertEqual(self.g.jobs._load()["jobs"][-1]["state"], "Stopped")
        self.assertEqual([p for p, _, _ in self.got()].count(phones[2]), 0)
        with patch.object(self.g.jobs, "_run"):
            self.g.mutate({"action": "resume"})
        self.run_job(self.g.jobs)
        got = [(p, s) for p, s, _ in self.got()]
        self.assertEqual([s for p, s in got if p == phones[1]], ["case"])
        for p in (phones[0], phones[2]):
            self.assertEqual([s for q, s in got if q == p], ["case", "video", "pdf", "share"], p)


for _name in [n for n in dir(tcar.Routing) if n.startswith("test_")]:
    setattr(TwoRoutesOnePerson, _name, None)  # run only the tests written here, not Routing's again


if __name__ == "__main__":
    import unittest

    unittest.main()
