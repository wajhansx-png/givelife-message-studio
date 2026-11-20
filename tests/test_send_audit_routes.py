"""Audit: who a route may message. Fake WhatsApp only: nothing is sent.

* a Test DM reaches only the test number and changes nothing else (no donor marked, production rotation untouched);
* the case run's GIKI rows (donors tagged "GIKI 1" / "GIKI 2") and the GIKI pages (their own contact books) are
  separate entry points: each messages only its own people;
* a person in several donor lists is messaged once, by the first list."""

import copy
import unittest
from unittest.mock import patch

import test_donor_hub as hub
import test_case_audience_routing as routing
from test_manual_sends import app


def _no_inherited_tests(cls, parent):
    """The parent class only supplies the fixture; its own tests are not run again here."""
    for name in dir(parent):
        if name.startswith("test_") and name not in vars(cls):
            setattr(cls, name, None)


class TestDm(hub.IntegrationTests):
    def test_a_test_dm_reaches_only_the_test_number_and_touches_nothing_else(self):
        registry = app.donors()
        donors = [registry.book.add(f"Donor {i}", f"0300123456{i}")["donor"] for i in range(3)]
        registry.book.update(donors[0]["id"], important=True)
        before = copy.deepcopy(registry.book._load()["records"])
        rotation = app.STORE.get("donor_single_rotation")
        daily = app.STORE.get("dm_daily")
        calls = []
        with (
            patch.object(app, "wa_ok", return_value=True),
            patch.object(
                app,
                "send_image",
                side_effect=lambda jid, text, *a, **k: (
                    calls.append((jid, text)) or {"code": "SUCCESS"}
                ),
            ),
            patch.object(
                app,
                "send_text",
                side_effect=lambda jid, text, *a, **k: (
                    calls.append((jid, text)) or {"code": "SUCCESS"}
                ),
            ),
        ):
            for poster in (True, False):
                registry.test_dm(poster=poster, files=False)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            {jid for jid, _ in calls}, {app.norm_phone(app.TEST_DM_PHONE or app.OWNER_PHONE)}
        )
        self.assertTrue(all(text.startswith("🧪 TEST DM") for _, text in calls))
        donor_phones = {registry.book.resolve(d["id"])["phone"] for d in donors}
        self.assertFalse([1 for jid, _ in calls if jid in donor_phones])
        self.assertEqual(registry.book._load()["records"], before, "a Test changed a donor")
        self.assertEqual(
            app.STORE.get("donor_single_rotation"), rotation, "a Test used the production rotation"
        )
        self.assertEqual(app.STORE.get("dm_daily"), daily, "a Test counted as a donor DM")
        self.assertFalse([k for k in app.STORE.data if str(k).startswith("dm_recipient_")])

    def test_testing_does_not_move_the_production_rotation(self):
        registry = app.donors()
        expected = registry.messages._rotation_texts()[0]
        with (
            patch.object(app, "wa_ok", return_value=True),
            patch.object(app, "send_image", return_value={"code": "SUCCESS"}),
        ):
            for _ in range(3):
                registry.test_dm(files=False)
        self.assertEqual(registry.messages.reserve_one(), expected)


_no_inherited_tests(TestDm, hub.IntegrationTests)


class Entry(routing.Routing):
    def setUp(self):
        super().setUp()
        self.giki_page = getattr(self.h, "giki", None)
        self.assertIsNotNone(self.giki_page, "the hub has no GIKI page")

    def sent_phones(self, kind=None):
        return [c["phone"] for c in self.calls if kind is None or c["kind"] == kind]

    def test_the_case_run_giki_rows_message_only_tagged_donors_never_the_giki_page_people(self):
        self.giki_page.mutate({"action": "add", "name": "Page Person", "phone": "0300 7770001"})
        page_phone = self.giki_page.book._load()["records"][0]["phone"]
        self.plan({"giki1", "giki2"})
        self.approve()
        self.assertTrue(
            self.tick_until(
                lambda: (
                    not self.h.jobs.active
                    and all(
                        self.state()["rows"][k]["state"] in ("done", "off")
                        for k in ("giki1", "giki2")
                    )
                )
            )
        )
        phones = self.sent_phones()
        self.assertTrue(phones)
        self.assertNotIn(page_phone, phones)
        tagged = {
            self.phone(self.ids[n])
            for n in (
                "First cohort first",
                "First cohort later",
                "Second cohort first",
                "Second cohort later",
            )
        }
        self.assertEqual(set(phones), tagged)
        self.assertIn(
            self.giki_page.book._load()["records"][0].get("delivery"), (None, "Not contacted")
        )

    def test_a_person_in_giki_1_top_and_important_is_messaged_once_by_the_first_row(self):
        first = self.ids["First cohort first"]  # tagged GIKI 1 and already Top
        self.h.book.update(first, important=True)
        self.cr.set_plan(
            {
                "giki1": {"enabled": True},
                "giki2": {"enabled": False},
                "top": {"enabled": True},
                "important": {"enabled": True, "ids": [first, self.ids["Normal high"]]},
                "group": {"enabled": False},
                "volunteers": {"enabled": False},
            }
        )
        aud = self.cr.summary()["audiences"]
        seen = [i for key in ("giki1", "giki2", "top", "important") for i in aud[key]]
        self.assertEqual(len(seen), len(set(seen)), aud)
        self.assertIn(first, aud["giki1"])
        self.assertNotIn(first, aud["top"] + aud["important"])

    def test_similar_group_names_are_not_giki_rows(self):
        data = self.h.book._load()
        extra = {"GIKI 10": "Normal low", "GIKI": "Normal high"}
        for r in data["records"]:
            for label, name in extra.items():
                if r["id"] == self.ids[name]:
                    r["group"] = label
        spaced = self.ids["First cohort first"]
        for r in data["records"]:
            if r["id"] == spaced:
                r["group"] = "  giki   1 "
        self.h.book._save(data)
        self.plan({"giki1"})
        aud = self.cr.summary()["audiences"]
        self.assertIn(spaced, aud["giki1"])  # spacing and case do not matter
        self.assertNotIn(self.ids["Normal low"], aud["giki1"])  # "GIKI 10" is not GIKI 1
        self.assertNotIn(self.ids["Normal high"], aud["giki1"])  # neither is plain "GIKI"


_no_inherited_tests(Entry, routing.Routing)


class Competing(hub.IntegrationTests):
    """The owner taps DM on a person while a batch is waiting between two people."""

    def sends(self):
        calls = []
        patcher = patch.object(
            app,
            "send_image",
            side_effect=lambda jid, text, *a, **k: calls.append(jid) or {"code": "SUCCESS"},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_a_manual_tap_during_a_batch_means_the_batch_skips_that_person(self):
        registry = app.donors()
        calls = self.sends()
        people = [registry.book.add(f"Person {i}", f"0300999000{i}")["donor"] for i in range(3)]
        for p in people:
            registry.book.update(p["id"], important=True)
        phones = [registry.book.resolve(p["id"])["phone"] for p in people]
        done = {"tapped": False}

        def gap(job):
            if not done["tapped"]:
                done["tapped"] = True
                registry.send_one(
                    people[1]["id"], "manual-during-batch-1"
                )  # the owner taps DM on the 2nd person
            return 0

        registry.jobs._gap = gap
        registry.jobs._rest = lambda j, b: 0
        registry.jobs.start("all", 5, run=False)
        registry.jobs._run(registry.jobs._load()["jobs"][-1])
        norm = [app.norm_phone(x) for x in phones]
        self.assertEqual(sorted(calls), sorted(norm), "everybody exactly once")
        self.assertEqual(len(calls), len(set(calls)), calls)
        st = registry.jobs.status()
        self.assertEqual((st["sent"], st["skipped"]), (2, 1), st)

    def test_two_manual_taps_with_different_request_ids_are_two_deliberate_sends(self):
        """By design: each tap is the owner's own decision, so a second tap with a new request id sends again;
        the SAME request id (a retried tap) never does."""
        registry = app.donors()
        calls = self.sends()
        person = registry.book.add("Solo", "03009990001")["donor"]
        registry.send_one(person["id"], "tap-one-0000001")
        registry.send_one(person["id"], "tap-one-0000001")  # a retry of the same tap
        self.assertEqual(len(calls), 1)
        registry.send_one(person["id"], "tap-two-0000002")  # a new tap
        self.assertEqual(len(calls), 2)


_no_inherited_tests(Competing, hub.IntegrationTests)


class AutoAudience(hub.DeliveryTests):
    """Auto: every Top donor not yet contacted, richest giver first, and nobody else."""

    def people(self):
        out = {}
        for name, amount, top, important in (
            ("Ann", 3000, True, True),
            ("Ben", 5000, True, True),
            ("Cal", 7000, True, True),
            ("Dee", 9000, True, True),
            ("Eve", 8000, False, True),  # Important, not Top
            ("Fay", 9500, False, False),  # neither
        ):
            d = self.add(name, "03001%06d" % (500 + len(out)))
            self.book.update(d["id"], important=important, normal_amount=amount)
            if top:
                self.book.update(d["id"], top_donor=True)  # Top needs Important first
            out[name] = d["id"]
        return out

    def run_auto(self):
        from donor_auto import DonorAuto

        auto = DonorAuto(self.store, self.jobs, lambda follow: None, busy=lambda: False)
        with patch.object(self.jobs, "_run"):
            auto.set(True)
        self.run_job(None)
        return [self.book.resolve(i)["name"] for i in self.sent_ids()]

    def sent_ids(self):
        by_phone = {r["phone"]: r["id"] for r in self.book._load()["records"]}
        return [by_phone[b["phone"]] for b, _ in self.sent]

    def test_auto_messages_top_donors_not_yet_contacted_richest_first_and_nobody_else(self):
        ids = self.people()
        self.book.delivery(ids["Cal"], "Sent")  # already got this case
        self.book.delivery(ids["Dee"], "Uncertain")  # may have got it: never asked again
        self.assertEqual(self.run_auto(), ["Ben", "Ann"])
        self.assertTrue(
            all(b["kind"] == "donor_batch" and b["target"] == "phone" for b, _ in self.sent)
        )

    def test_auto_skips_an_opted_out_top_donor_and_carries_on(self):
        ids = self.people()
        opted = self.book.resolve(ids["Dee"])["phone"]
        self.jobs.eligible = lambda phone: phone != opted
        self.assertEqual(self.run_auto(), ["Cal", "Ben", "Ann"])


_no_inherited_tests(AutoAudience, hub.DeliveryTests)


if __name__ == "__main__":
    unittest.main()
