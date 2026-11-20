"""Audit: from the owner's master to the final WhatsApp payload. Fake WhatsApp, fake AI, temporary storage.

Two visibly different cases (Ahmed, Bilal) are used. Nothing real is sent and no paid AI is called."""

import math, shutil, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch

import test_manual_sends as fixture
from test_manual_sends import app
import dm_composer, dm_variants


def appeal(name, age, story, left):
    p2, p1 = math.ceil(left / 2000), math.ceil(left / 1000)
    return (
        f"Brother, please read about {name} and the support the family requested.\n\n"
        f"💔 {story}\n"
        f"_{name} is {age}. The family asked for help with the hospital bills._\n\n"
        f"💰 *_Rs. {left:,} still needed for treatment._*\n\n"
        f"*_Just {p2} people donating Rs. 2,000_*\n"
        f"*_OR {p1} people contributing Rs. 1,000 🤲_*\n\n"
        "_If you are reading this, it's you._ Don't wait for someone else.\n\n"
        "📲 *03097458815*\nEASYPAISA ONLY\nWajdan Khan (GiveLife Foundation account)\n\n"
        "Reply *Done* after donating."
    )


class Base(unittest.TestCase):
    setUp = fixture.SendTests.setUp
    tearDown = fixture.SendTests.tearDown

    def left(self):
        return app.read_left()

    def master_a(self):
        return appeal(
            "Ahmed", 9, "His parents reported an accident and a leg operation.", self.left()
        )

    def master_b(self):
        return appeal(
            "Bilal", 4, "His parents reported a high fever and a long hospital stay.", self.left()
        )

    def rewrites(self, master, n):
        """n valid-looking distinct versions of a master (wording changes only; facts and shape kept)."""
        out = []
        openers = ("kindly read about", "do read about", "please see")
        asks = (
            "requested",
            "asked for",
            "is hoping for",
            "is praying for",
            "has appealed for",
            "needs",
            "is waiting for",
        )
        for i in range(n):
            out.append(
                master.replace("please read about", openers[i % 3], 1)
                .replace("the family requested", f"the family {asks[(i // 3) % len(asks)]}", 1)
                .replace(
                    "hospital bills", "hospital costs" + " today" * (i // 21) + " now" * (i % 3), 1
                )
            )
        return out

    def approved(self, master, n=20, **extra):
        bank = app.donors().messages
        data = bank.get()
        texts = [master] + self.rewrites(master, n - 1)[: n - 1]
        data.update(mode="custom", origin=master, base=master, items=bank._entries(texts), **extra)
        data.pop("generation", None)
        data.pop("previous_items", None)
        bank._save(data)
        return bank, texts

    def wait_idle(self, bank, seconds=5):
        end = time.monotonic() + seconds
        while bank.regeneration_running and time.monotonic() < end:
            time.sleep(0.005)
        self.assertFalse(bank.regeneration_running, "regeneration did not finish")


class CrossCase(Base):
    def test_fixtures_are_complete_and_visibly_different(self):
        a, b = self.master_a(), self.master_b()
        self.assertTrue(dm_composer.complete(a) and dm_composer.complete(b))
        self.assertIn("Ahmed", a)
        self.assertNotIn("Bilal", a)
        self.assertNotIn("Ahmed", b)

    def test_a_new_master_for_another_case_never_falls_back_to_the_old_case(self):
        bank, old = self.approved(self.master_a())
        bank.set_base(self.master_b())
        with patch("dm_variants.generate", side_effect=ValueError("provider down")):
            bank.start_regeneration()
            self.wait_idle(bank)
        shown = [r["text"] for r in bank.get()["items"]]
        self.assertFalse([t for t in shown if "Ahmed" in t], "case A is on screen in case B")
        # what any DM route may use: never case A
        try:
            texts = bank._rotation_texts()
        except ValueError:
            texts = []
        self.assertFalse([t for t in texts if "Ahmed" in t], "case A would be sent as case B")
        for count in (1, 5):
            try:
                picked = bank.reserve_one() if count == 1 else bank.reserve_round(count)
            except ValueError:
                continue
            picked = [picked] if isinstance(picked, str) else picked
            self.assertTrue(all("Bilal" in t and "Ahmed" not in t for t in picked), picked)

    def test_a_new_master_for_another_case_reaches_the_final_payload_as_that_case_only(self):
        bank, old = self.approved(self.master_a())
        registry = app.donors()
        donor = registry.book.add("Zed", "03001234567")["donor"]
        bank.set_base(self.master_b())
        with patch.object(app, "send_image", return_value={"code": "SUCCESS"}) as image:
            registry.send_one(donor["id"], "case-b-click-001")
        sent = image.call_args.args[1]
        self.assertIn("Bilal", sent)
        self.assertNotIn("Ahmed", sent)

    def test_same_case_recovery_is_kept_when_the_same_appeal_is_edited(self):
        """A typo fix to the same appeal: the earlier approved versions keep sending while the new ones are made."""
        bank, old = self.approved(self.master_a())
        fixed = self.master_a().replace("support the family", "support this family", 1)
        bank.set_base(fixed)
        with patch("dm_variants.generate", side_effect=ValueError("provider down")):
            bank.start_regeneration()
            self.wait_idle(bank)
        texts = bank._rotation_texts()
        self.assertGreaterEqual(len(texts), bank.MIN_VERSIONS)
        self.assertTrue(all("Ahmed" in t for t in texts))
        self.assertEqual(len(bank.reserve_round(6)), 6)

    def test_regeneration_started_for_case_a_cannot_write_into_case_b(self):
        bank, old = self.approved(self.master_a())
        gate, started = threading.Event(), threading.Event()

        def slow(source, count=10, avoid=None, progress=None, **kw):
            started.set()
            gate.wait(5)
            made = self.rewrites(source, count + 1)[1:]
            if progress and progress(list(made)) is False:
                raise ValueError("Generation stopped because the source changed.")
            return made

        with patch("dm_variants.generate", side_effect=slow):
            bank.set_base(self.master_a().replace("support the family", "support this family", 1))
            bank.start_regeneration()
            self.assertTrue(started.wait(5))
            bank.set_base(self.master_b())  # the owner pastes case B while A is still being written
            gate.set()
            self.wait_idle(bank)
        data = bank.get()
        self.assertEqual([r["text"] for r in data["items"]], [self.master_b()])
        self.assertEqual(data.get("generation") or {}, {})
        self.assertFalse(
            [r for r in data.get("previous_items") or [] if "Ahmed" in r["text"]],
            "case A's versions are still queued to be sent in case B",
        )

    def test_switching_the_case_while_a_regeneration_is_saving_cannot_put_case_a_into_case_b(self):
        h = app.donors()
        bank, old = self.approved(self.master_a())
        first = h.cases.view()["current"]
        saved = {}
        # A real case switch rewrites the poster, drafts and amount of the whole test app: put every file back after.
        backup = Path(tempfile.mkdtemp())
        shutil.copytree(app.DATA, backup / "data", dirs_exist_ok=True)

        def restore():
            try:
                h.cases.switch(first)
            except Exception:
                pass
            for item in list(app.DATA.iterdir()):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.name != "studio_state.sqlite":
                    item.unlink(missing_ok=True)
            shutil.copytree(
                backup / "data",
                app.DATA,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("studio_state.sqlite*"),
            )
            shutil.rmtree(backup, ignore_errors=True)
            app.set_left(25000)

        self.addCleanup(restore)

        def work(source, count=10, avoid=None, progress=None, **kw):
            made = self.rewrites(source, count + 1)[1:]
            progress(list(made))
            return made

        real_save = bank._save

        def save_during_a_switch(data):
            if (data.get("generation") or {}).get("state") == "Generating" and "go" not in saved:
                saved["go"] = threading.Thread(
                    target=lambda: h.cases.new("Bilal case", self.left())
                )
                saved["go"].start()
                saved["go"].join(0.4)  # a switch that does not wait for the bank finishes here
            return real_save(data)

        with (
            patch("dm_variants.generate", side_effect=work),
            patch.object(bank, "_save", side_effect=save_during_a_switch),
        ):
            bank.set_base(self.master_a().replace("support the family", "support this family", 1))
            bank.start_regeneration()
            self.wait_idle(bank)
        if "go" in saved:
            saved["go"].join(5)
        stored = app.STORE.get("donor_messages") or {}
        texts = [
            r.get("text", "")
            for r in (stored.get("items") or []) + (stored.get("previous_items") or [])
        ]
        self.assertFalse(
            [t for t in texts if "Ahmed" in t], "case A's bank was written into case B"
        )
        self.assertNotEqual(h.cases.view()["current"], first)


class Validator(Base):
    """Bad model output through the REAL validator. Every defect starts from one good rewrite."""

    def good(self):
        left = self.left()
        p2, p1 = math.ceil(left / 2000), math.ceil(left / 1000)
        return (
            "Brother, kindly take a moment to read about Ahmed and what his family is asking for.\n\n"
            "💔 His parents told us he was hurt in an accident and now needs a leg operation.\n"
            "_Ahmed is 9 years old, and the family is struggling with the hospital expenses._\n\n"
            f"💰 *_Rs. {left:,} still needed for treatment._*\n\n"
            f"*_Just {p2} people donating Rs. 2,000_*\n"
            f"*_OR {p1} people contributing Rs. 1,000 🤲_*\n\n"
            "_If this reached you, it is meant to be you._ Please do not wait for somebody else.\n\n"
            "📲 *03097458815*\nEASYPAISA ONLY\nWajdan Khan (GiveLife Foundation account)\n\n"
            "Reply *Done* after donating."
        )

    def test_the_good_rewrite_is_accepted(self):
        self.assertEqual(dm_variants.validate(self.master_a(), self.good()), "")
        self.assertEqual(dm_variants.fact_problem(self.master_a(), self.good()), "")

    def test_every_bad_output_is_refused_with_a_reason(self):
        left, a, good = self.left(), self.master_a(), self.good()
        bad = {
            "another case": self.master_b(),
            "swapped account digit": good.replace("03097458815", "03097458851"),
            "changed amount": good.replace(f"Rs. {left:,} still", f"Rs. {left + 1000:,} still"),
            "invented diagnosis": good.replace("hospital expenses", "cancer treatment"),
            "invented death": good.replace("struggling", "mourning a death and struggling"),
            "invented urgency": good.replace(
                "Please do not wait", "He is fighting for his life. Do not wait"
            ),
            "invented deadline": good.replace("Please do not wait", "Please help before tonight"),
            "another patient's name": good.replace("Ahmed", "Bilal"),
            "payment line changed": good.replace("EASYPAISA ONLY", "JazzCash"),
            "reply instruction dropped": good.replace("Reply *Done* after donating.", "Thank you."),
            "urdu where english was": good.replace(
                "_Ahmed is 9 years old, and the family is struggling with the hospital expenses._",
                "_احمد کے گھر والے ہسپتال کے خرچ سے پریشان ہیں اور مدد چاہتے ہیں اللہ آپ کو جزا دے_",
            ),
            "line breaks changed": good.replace("\n\n💰", "\n💰", 1),
            "emoji moved": good.replace("💔 ", "", 1).replace("treatment._*", "treatment._* 💔", 1),
            "bold lost": good.replace("*_Just", "_Just", 1),
            "too short": good[:100],
            "not text": None,
            "empty": "",
        }
        for label, text in bad.items():
            with self.subTest(label):
                self.assertNotEqual(dm_variants.validate(a, text), "", label + " was accepted")

    def test_a_rewrite_that_keeps_the_patients_name_may_add_a_capitalised_word(self):
        a, good = self.master_a(), self.good()
        more = good.replace(
            "what his family is asking for", "what his family in Madinah Town is asking for", 1
        )
        self.assertEqual(dm_variants.validate(a, more), "")
        self.assertEqual(dm_variants.fact_problem(a, more), "")
        no_name = good.replace("about Ahmed and", "about this boy and", 1)
        self.assertEqual(
            dm_variants.fact_problem(a, no_name), ""
        )  # dropping the name is not another person

    def test_a_duplicate_or_the_master_itself_is_refused(self):
        a, good = self.master_a(), self.good()
        self.assertEqual(dm_variants.validate(a, good, existing=[good]), "duplicate wording")
        self.assertEqual(dm_variants.validate(a, a), "same as the source")

    def test_roles_in_the_wrong_places_do_not_add_up(self):
        left = self.left()
        wrong = self.good().replace(
            f"Just {math.ceil(left / 2000)} people", f"Just {math.ceil(left / 1000)} people", 1
        )
        self.assertNotEqual(dm_variants.arithmetic_problem(wrong), "")
        self.assertEqual(dm_variants.arithmetic_problem(self.good()), "")
        # even when the master carries the same wrong numbers, a rewrite cannot be better than its master but may not make it worse
        self.assertNotEqual(
            dm_variants.fact_problem(self.good(), wrong.replace("Just", "Only")), ""
        )

    def test_malformed_model_replies_never_become_versions(self):
        for raw in (
            "",
            "no json here",
            "{}",
            "[1, 2, 3]",
            "[null, 5, {}]",
            '["ok"',
            "```json\n[\n```",
            '[""," "]',
        ):
            with self.subTest(raw=raw):
                try:
                    out = dm_variants._json_list(raw)
                except ValueError:
                    continue  # refused as a whole: nothing becomes a version
                for text in out:
                    self.assertNotEqual(dm_variants.validate(self.master_a(), text), "")

    def test_generation_keeps_only_valid_unique_versions_from_a_noisy_provider(self):
        a, good = self.master_a(), self.good()
        noisy = [
            good,
            good,
            self.master_b(),
            good.replace("03097458815", "03097458851"),
            good.replace("hospital expenses", "cancer treatment"),
            "junk",
            None,
            5,
        ]
        calls = {"n": 0}

        def fake_call(key, prompt, deep=False):
            calls["n"] += 1
            return noisy if calls["n"] == 1 else []

        with (
            patch.object(dm_variants.assistant, "client", return_value="fake"),
            patch.object(dm_variants, "_call", fake_call),
            patch.object(dm_variants, "_sleep"),
        ):
            made = dm_variants.generate(a, 1)
        self.assertEqual(made, [good])


class Payload(Base):
    """The master all the way to the final WhatsApp caption."""

    def send(self, donor, request):
        registry = app.donors()
        with patch.object(app, "send_image", return_value={"code": "SUCCESS"}) as image:
            registry.send_one(donor["id"], request)
        return image.call_args.args[1]

    def donor(self, name, label, salutation):
        registry = app.donors()
        d = registry.book.add(label, "03001234%03d" % (hash(name) % 900 + 100))["donor"]
        registry.book.update(d["id"], dm_name=name, dm_salutation=salutation)
        return d

    def test_greeting_is_written_once_and_no_placeholder_is_left(self):
        bank, texts = self.approved(self.master_a())
        for name, salutation, want in (
            ("Ali", "Brother", "Ali Bhai, "),
            ("Ayesha", "Sister", "Ayesha Sister, "),
            ("Sara", "Neutral", "Sara, "),
        ):
            with self.subTest(name):
                bank.cache = None
                sent = self.send(
                    self.donor(name, name + " donor", salutation), "greet-" + name.lower() + "-0001"
                )
                self.assertTrue(sent.startswith(want), sent[:40])
                self.assertEqual(
                    sent.count(want.strip(", ")),
                    1 if salutation != "Sister" else sent.count("Ayesha"),
                    sent[:60],
                )
                self.assertNotIn("{name}", sent)
                self.assertNotRegex(
                    sent, r"(?i)^(?:\w+ )?(?:bhai|sister|brother)[, ]+(?:bhai|sister|brother),"
                )
                self.assertEqual(sent.count("Ahmed"), self.master_a().count("Ahmed"))

    def test_sister_is_sister_all_the_way_through(self):
        bank, texts = self.approved(self.master_a().replace("Brother, please", "Brother, please"))
        sent = self.send(self.donor("Hira", "Hira donor", "Sister"), "sister-0000001")
        self.assertNotIn("Brother", sent)

    def test_the_amount_and_arithmetic_in_the_payload_follow_the_current_balance(self):
        bank, texts = self.approved(self.master_a())
        app.set_left(9500)
        try:
            sent = self.send(self.donor("Omar", "Omar donor", "Brother"), "balance-000001")
        finally:
            app.set_left(self.left())
        self.assertIn("Rs. 9,500", sent)
        self.assertIn("5 people donating Rs. 2,000", sent)
        self.assertIn("10 people contributing Rs. 1,000", sent)
        self.assertEqual(dm_variants.arithmetic_problem(sent), "")
        self.assertIn("03097458815", sent)
        self.assertEqual(sent.count("EASYPAISA ONLY"), 1)

    def test_a_version_damaged_after_saving_is_never_sent(self):
        bank, texts = self.approved(self.master_a())
        data = bank.get()
        data["items"][3]["text"] = data["items"][3]["text"].replace("03097458815", "03097458851")
        bank._save(data)
        picked = bank.reserve_round(19)
        self.assertEqual(len(picked), 19)
        self.assertFalse([t for t in picked if "03097458851" in t])


if __name__ == "__main__":
    unittest.main()


URDU_LINE = '_"اور جس نے ایک جان کو بچایا گویا اس نے پوری انسانیت کو بچایا" (القرآن)_'


class Styles(Base):
    """The owner's other message styles: a GIKI share request, a thank-you, and a master that carries an Urdu verse."""

    def urdu_master(self):
        return self.master_a().replace("📲", URDU_LINE + "\n\n📲", 1)

    def urdu_good(self):
        return Validator.good(self).replace("📲", URDU_LINE + "\n\n📲", 1)

    def test_a_giki_share_request_has_the_greeting_exactly_once_or_closes_up(self):
        import giki_line

        share = "Salam {name}, please share this with your class group.\n\nJazakAllah 🤲"
        for name in ("Ali Bhai", "Areeba Sister", "Hira"):
            out = giki_line.fill_name(share, name)
            self.assertEqual(out.count(name), 1, out)
            self.assertNotIn("{name}", out)
            self.assertTrue(out.startswith("Salam " + name + ","), out)
        closed = giki_line.fill_name(share, "")
        self.assertTrue(closed.startswith("Salam, please share"), closed)
        self.assertNotIn("{name}", closed)
        self.assertNotIn(" ,", closed)

    def test_the_thank_you_asks_for_no_money_and_carries_no_payment_details(self):
        text = app.thank_text()
        self.assertNotRegex(text, r"(?i)rs\.?\s*\d|\bleft\b|\bneeded\b|easypaisa|03097458815")
        self.assertIn("share", text.lower())
        self.assertEqual(text.count("JazakAllah"), 1)
        self.assertFalse(dm_composer.complete(text), "a thank-you must not pass as an appeal")

    def test_a_master_with_an_urdu_verse_keeps_it_word_for_word(self):
        master, good = self.urdu_master(), self.urdu_good()
        self.assertIn(URDU_LINE, master)
        self.assertEqual(dm_variants.validate(master, good), "")
        # the model translated the verse into English: the app puts the owner's line back, so the version is saved intact
        translated = good.replace(
            URDU_LINE, '_"Whoever saves one life saves all of humanity" (Quran)_'
        )
        repaired = dm_variants.repair(master, translated)
        self.assertIn(URDU_LINE, repaired)
        self.assertEqual(dm_variants.validate(master, repaired), "")
        # the model dropped the verse line altogether: refused, never saved
        dropped = good.replace(URDU_LINE + "\n\n", "")
        self.assertNotEqual(dm_variants.validate(master, dm_variants.repair(master, dropped)), "")
        # the section order stays: appeal, balance, contribution lines, verse, payment, reply instruction
        order = [
            good.index(x)
            for x in ("Ahmed", "still needed", "Just", URDU_LINE, "03097458815", "Reply *Done*")
        ]
        self.assertEqual(order, sorted(order))
