"""Audit: GIKI 1 and GIKI 2. Fake WhatsApp only: nothing is sent.

* each page sends only to its own people, only from its own WhatsApp line;
* one person gets every step (case + poster, 2nd, 3rd, share) before the next person starts;
* Stop at ANY step boundary, then Resume: nobody gets a step twice, nobody is left short, the order holds."""

import unittest
from collections import Counter
from unittest.mock import patch

from giki_line import Giki2Volunteers
from test_giki_line import Fixture

STEPS = ("case", "video", "pdf", "share")


def step_of(body):
    if body.get("kind") == "dm_extra":
        return body["extra"]
    return "case" if body.get("poster") else "share"


class GikiAudit(Fixture):
    def setUp(self):
        super().setUp()
        self.on = [("video", "b" * 32), ("pdf", "a" * 32)]  # 2nd: video, 3rd: PDF

    def people(self, page, n, prefix="1"):
        for i in range(n):
            page.mutate(
                {"action": "add", "name": f"Giki P{prefix}{i}", "phone": f"0300 {prefix}00000{i}"}
            )
        page.mutate({"action": "message", "text": "Salam {name}, please share this."})
        return [b["phone"] for b in page.book._load()["records"]]

    def sequence(self):
        return [(b["phone"], step_of(b), b.get("line")) for b in self.sent]

    def test_each_page_sends_only_to_its_own_people_from_its_own_line(self):
        g2 = Giki2Volunteers(self.g.app, lambda phone: True)
        g2.source = self.g
        first = self.people(self.g, 2, "1")
        second = self.people(g2, 2, "2")
        self.go(self.g, {"action": "send_all", "request_id": "a1", "poster": False})
        self.run_job(self.g.jobs)
        self.go(g2, {"action": "send_all", "request_id": "b1", "poster": False})
        self.run_job(g2.jobs)
        seq = self.sequence()
        self.assertEqual(len(seq), 16, "2 people x 4 steps on each page, nothing else")
        for phone, step, line in seq[:8]:
            self.assertEqual((line, phone in first, phone in second), ("giki", True, False), seq)
        for phone, step, line in seq[8:]:
            self.assertEqual((line, phone in second, phone in first), ("giki2", True, False), seq)
        self.assertEqual(Counter(self.sequence()).most_common(1)[0][1], 1, "a step went twice")

    def test_one_person_finishes_all_steps_before_the_next_starts_and_in_book_order(self):
        phones = self.people(self.g, 3)
        self.go(self.g, {"action": "send_all", "request_id": "o1", "poster": False})
        self.run_job(self.g.jobs)
        got = [(p, s) for p, s, _ in self.sequence()]
        want = [(p, s) for p in phones for s in STEPS]
        self.assertEqual(got, want)

    def stop_and_resume(self, boundary):
        phones = self.people(self.g, 3)

        def on_send(body):
            if len(self.sent) == boundary:
                self.g.jobs.stop.set()  # Stop pressed while this step was being sent

        self.on_send = on_send
        self.go(self.g, {"action": "send_all", "request_id": "s%d" % boundary, "poster": False})
        self.run_job(self.g.jobs)
        self.on_send = None
        self.g.jobs.stop.clear()
        for _ in range(4):
            if not self.g.view()["resumable"]:
                break
            with patch.object(self.g.jobs, "_run"):
                self.g.mutate({"action": "resume"})
            self.run_job(self.g.jobs)
        return phones

    def test_stop_at_every_step_then_resume_sends_every_step_exactly_once_in_order(self):
        for boundary in range(1, 12):
            with self.subTest(boundary=boundary):
                self.tearDown()
                self.setUp()
                phones = self.stop_and_resume(boundary)
                got = [(p, s) for p, s, _ in self.sequence()]
                self.assertEqual(Counter(got).most_common(1)[0][1], 1, ("a step went twice", got))
                self.assertEqual(
                    sorted(got), sorted((p, s) for p in phones for s in STEPS), "someone is short"
                )
                # one person at a time: a person's steps are never interleaved with another's
                order = [p for p, _ in got]
                self.assertEqual(order, sorted(order, key=phones.index), "people out of order")
                for p in phones:
                    self.assertEqual([s for q, s in got if q == p], list(STEPS), p)


if __name__ == "__main__":
    unittest.main()
