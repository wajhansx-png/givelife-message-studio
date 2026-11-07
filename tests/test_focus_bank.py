import unittest, threading, copy
from types import SimpleNamespace
from unittest.mock import patch
from focus_bank import GEN, FocusBank, reject_reason


def valid(source, text, existing=()):
    return not reject_reason(source, text, existing)


SRC = "*Hook A*\n\nThey are worried about burial costs and cannot manage them alone this week, so they are asking people for any help.\n\nPlease read this carefully today and think about what you can give for them.\n\nRs. 50,000 needed\n\n03097458815 Easypaisa / JazzCash Wajdan Khan"
_H = [
    "Stop scrolling for one minute",
    "Imagine this were your own child",
    "Somebody is waiting on you right now",
    "Look at this family before you move on",
    "A mother is praying tonight",
    "Think of a small child in pain",
    "One quick tap can change this home",
    "You are the answer to their dua",
    "Do not let this be the post you ignore",
    "Their whole family is counting on kind strangers now",
]
_B = [
    "Their little one needs urgent care and they cannot pay the bills",
    "A parent is begging for help to cover treatment fees",
    "They have sold what they could and still fall short",
    "The doctors are waiting but the money is not there",
    "This family has nobody else to ask but you",
    "Every single hour without help makes this harder for them",
    "They never thought they would have to ask strangers",
    "A small gift from many hands would lift this burden",
    "They are trying to stay strong for their child",
    "Please do not leave them alone with this",
]
_T = [
    "Take two minutes for them now",
    "Send what you can this minute",
    "Help them before the day ends",
    "Be the reason they smile again",
    "Give once and tell one friend",
    "Stand with them today",
    "Share this with your family too",
    "Your kindness reaches them directly",
    "Make this your good deed today",
    "Do it now and thank you",
]
_A = [
    "Only Rs. 50,000 is still needed",
    "Rs. 50,000 remains to be raised",
    "We still need Rs. 50,000 together",
    "Rs. 50,000 is the gap left",
    "Just Rs. 50,000 stands between them and care",
    "Rs. 50,000 is all that is missing",
    "Rs. 50,000 more will complete it",
    "Rs. 50,000 left, nothing more",
    "The last Rs. 50,000 is needed",
    "Rs. 50,000 is what remains",
]
DEEP = [
    "*%s*\n\n%s.\n\n%s.\n\n%s\n\n03097458815 Easypaisa / JazzCash Wajdan Khan"
    % (_H[i], _B[i], _T[i], _A[i])
    for i in range(10)
]


class Store:
    def __init__(self):
        self.data = {}

    def get(self, k, d=None):
        return copy.deepcopy(self.data.get(k, d))

    def put(self, k, v):
        self.data[k] = copy.deepcopy(v)


class FocusTests(unittest.TestCase):
    def make(self):
        self.drafts = {
            "group": "*Please help this family today.*\n\nRs. 50,000 needed\n\n03097458815 Easypaisa / JazzCash Wajdan Khan",
            "dm": "Brother, support this family.",
        }
        bank = SimpleNamespace(
            lock=threading.RLock(),
            _save=lambda d: None,
            _fingerprint=lambda t: t,
            _entries=lambda ts: [{"text": t} for t in ts],
        )
        self.app = SimpleNamespace(
            donors=lambda: SimpleNamespace(messages=bank),
            read_left=lambda: 50000,
            STORE=Store(),
            LOCK=threading.RLock(),
            get_message=lambda k: {"text": self.drafts[k]},
            save_draft=lambda k, v: self.drafts.update({k: v}),
        )
        return FocusBank(self.app)

    def test_saved_original_and_custom_dm_survive_group_changes(self):
        b = self.make()
        with patch.object(b, "_spawn"):
            first = b.save("group", self.drafts["group"])
            dm = b.get("dm")
            self.assertTrue(dm["source"].startswith("Brother, "))
            b.save("dm", "My personal DM", dm["revision"])
            b.save("group", "Different case message", first["revision"])
            self.assertEqual(b.get("dm")["source"], "My personal DM")
            self.assertEqual(b.get("group")["history"], [first["source"]])
            with self.assertRaises(ValueError):
                b.save("group", "stale", first["revision"])

    def test_numbers_format_payment_and_real_rewrite_are_checked(self):
        self.assertTrue(valid(SRC, DEEP[0]))
        # Changing one word is not a rewrite, and facts/format/payment must survive.
        for candidate in (
            SRC.replace("Please", "Kindly"),
            SRC.replace("*", "_"),
            DEEP[0].replace("50,000", "40,000"),
            DEEP[0].replace("Easypaisa", "JazzCash"),
            DEEP[0] + "!" * 400,
        ):
            self.assertFalse(valid(SRC, candidate))

    def test_failed_generation_keeps_source_and_can_restart_with_new_instance(self):
        b = self.make()
        with patch.object(b, "_spawn"):
            row = b.save("group", self.drafts["group"])
        with patch("dm_variants.assistant.client", return_value=None):
            b._generate("group", row, ("group", row["revision"]))
        newer = FocusBank(self.app)
        self.assertEqual(newer.get("group")["source"], row["source"])
        self.assertEqual(newer.get("group")["state"], "Needs retry")
        self.assertEqual(self.drafts["group"], row["source"])

    def test_five_distinct_deep_versions_per_click_and_stale_results(self):
        b = self.make()
        source = SRC
        with patch("focus_bank.threading.Thread") as thread:
            row = b.save("group", source)
        thread.assert_not_called()  # saving the base message never writes versions
        self.assertEqual((row["state"], row["items"]), ("Not generated", []))
        versions = list(DEEP)
        with patch.object(b, "_spawn"):
            b.generate("group")
        self.assertEqual(b.get("group")["batch"]["goal"], 5)
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", return_value=versions),
        ):
            b._generate("group", b.get("group"), ("group", row["revision"]))
            self.assertEqual(b.get("group")["items"], versions[:5])  # exactly 5, never more
            self.assertEqual(b.get("group")["state"], "Ready")
            with patch.object(b, "_spawn"):
                b.generate("group")
            b._generate("group", b.get("group"), ("group", row["revision"]))
        self.assertEqual(b.get("group")["items"], versions)  # the next click adds the next 5
        self.assertEqual(self.drafts["group"], source)
        with patch.object(b, "_spawn"):
            latest = b.save("group", source + "!", row["revision"])
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", return_value=versions),
        ):
            b._generate("group", row, ("group", row["revision"]))
        self.assertEqual(b.get("group")["source"], latest["source"])
        self.assertEqual(b.get("group")["items"], [])

    def test_mixed_urdu_message_keeps_verse_and_still_makes_five(self):
        """The AI flips the Urdu hook to English and alters the verse; the app restores both."""
        hook = "*آپ کے صرف 1,000 روپے ایک مجبور باپ کی مدد کر سکتے ہیں۔*"
        verse = [
            "*اللّٰہ تعالیٰ کا ارشاد ہے:*",
            '"تم جو کچھ بھی (اللہ کی راہ میں) خرچ کرو گے، وہ اس کا بدل دے گا۔"',
            "(سورۃ سبا: 39)",
        ]
        source = "\n".join(
            [
                "🚨----- Latest update ----",
                "",
                hook,
                "_People are now coming to Yousaf's father's home, asking him to repay the money he borrowed for his little son's Janazah.💔_",
                "",
                "He has already lost his 2-year-old son, and Rs. 17,000 is still unpaid..",
                "",
                "",
                *verse,
                "",
                "🔴 Rs. 16,000 LEFT ONLY",
                "",
                "• _Just your 1,000 rs donation and 16 people can clear what remains._",
                "",
                "03097458815 Easypaisa / JazzCash Wajdan Khan",
            ]
        )
        b = self.make()
        with patch.object(b, "_spawn"):
            row = b.save("group", source)
            b.generate("group")
        a = [
            "Lenders keep knocking at the door of Yousaf's father. He borrowed that money to lay his small son to rest.",
            "Yousaf's father borrowed to bury his little boy, and now the lenders are at his gate.",
            "A grieving father is being chased for the money he spent on his young son's Janazah.",
            "Right now, people stand outside Yousaf's father's house asking for the loan he took for his boy's funeral.",
            "The loan for his little boy's Janazah is now being demanded back from Yousaf's father at his own door.",
        ]
        c = [
            "One loss was already too much: his 2-year-old is gone, and Rs. 17,000 is still left to repay..",
            "His 2-year-old has passed away, and still Rs. 17,000 of that debt stays unpaid..",
            "He buried his 2-year-old son. Today Rs. 17,000 of the cost is still waiting to be repaid..",
            "After losing a 2-year-old child, he is left holding Rs. 17,000 that he cannot repay..",
            "His boy was just 2 years old, and Rs. 17,000 of the burial debt is still open..",
        ]
        d = [
            "A gift of only 1,000 rs from 16 of us closes this debt for good.",
            "If each of us gives 1,000 rs, just 16 of us leave nothing owing.",
            "A 1,000 rs gift, from just 16 of us, can finish what remains today.",
            "Just 1,000 rs from 16 hands, and this father is free of the loan.",
            "It takes only 1,000 rs from 16 donors to clear the last of it.",
        ]
        lines = source.split("\n")
        versions = []
        for i in range(5):
            v = list(lines)
            v[3] = "_" + a[i] + "💔_"
            v[5] = c[i]
            v[14] = "• _" + d[i] + "_"
            v[2] = (
                "*Only 1,000 rupees can help a helpless father today.*"  # language flipped by the AI
            )
            v[9] = '"Whatever you spend in the way of Allah, He will replace it."'  # verse altered
            versions.append("\n".join(v))
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", return_value=versions),
        ):
            b._generate("group", b.get("group"), ("group", row["revision"]))
        got = b.get("group")
        self.assertEqual((got["state"], len(got["items"])), ("Ready", 5), got.get("error"))
        for text in got["items"]:
            self.assertIn(hook, text)
            for line in verse:
                self.assertIn(line, text)

    def test_failed_generation_names_the_reasons(self):
        b = self.make()
        with patch.object(b, "_spawn"):
            row = b.save("group", self.drafts["group"])
            b.generate("group")
        junk = ["same text"] * 5
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", return_value=junk),
        ):
            b._generate("group", b.get("group"), ("group", row["revision"]))
        err = b.get("group")["error"]
        self.assertIn("0 of 5 new versions passed every check.", err)
        self.assertRegex(err, r"\(\d+x\)")  # how often each reason happened

    def test_a_batch_that_keeps_timing_out_gives_up_on_time_and_says_why(self):
        import focus_bank

        b = self.make()
        with patch.object(b, "_spawn"):
            row = b.save("group", self.drafts["group"])
            b.generate("group")
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=RuntimeError("The AI service timed out")),
            patch("dm_variants._sleep"),
            patch.object(focus_bank, "MAX_RUN_SECONDS", 0),
        ):
            b._generate("group", b.get("group"), ("group", row["revision"]))
        got = b.get("group")
        self.assertNotEqual(got["state"], "Generating")  # never left "Writing 5 more…" forever
        self.assertEqual(got["note"], "")
        self.assertIn("0 of 5 new versions passed every check", got["error"])

    def test_deep_reasoning_mode_starts_after_near_copies(self):
        b = self.make()
        with patch.object(b, "_spawn"):
            row = b.save("group", self.drafts["group"])
            b.generate("group")
        source = b.get("group")["source"]
        flags = []

        def copies(api, prompt, deep=False):
            flags.append(deep)
            return [source, source, source]  # the AI hands back the original

        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", side_effect=copies),
            patch("dm_variants._sleep"),
        ):
            b._generate("group", b.get("group"), ("group", row["revision"]))
        self.assertFalse(flags[0])  # the first round is the normal, fast writer
        self.assertTrue(any(flags[3:]))  # after near-copies the next round reads in depth
        self.assertIn("repeated wording", b.get("group")["error"])

    def test_a_real_rewrite_of_a_verse_and_payment_message_is_not_called_too_similar(self):
        src = (
            "صرف 4 لوگوں کے 1,000 روپے ایک مجبور باپ کو اس قرض سے نجات دلا سکتے ہیں 🚨\n\n"
            "_People are now coming to Yousaf's father's home, asking him to repay the money he "
            "borrowed for his little son's Janazah._💔\n\n"
            "He has already lost his 2-year-old son, and Rs. 17,000 is still unpaid..\n\n\n"
            "*اللہ تعالیٰ کا ارشاد ہے:*\n"
            '"تم جو کچھ بھی (اللہ کی راہ میں) خرچ کرو گے، وہ اس کا بدلہ دے گا۔"\n'
            "(سورۃ سبا: 39)\n\n"
            "🔴 Rs. 4,000 LEFT ONLY\n\n"
            "• *_Just your 1,000 rs donstion and 4 people donating Rs. 1,000 can relief helpless "
            "father's pain._* 🤲\n\n\n"
            "03097458815\nEasypaisa / JazzCash (Wajdan Khan)\n\n— GiveLife Foundation"
        )
        rewrite = (
            src.replace(
                "صرف 4 لوگوں کے 1,000 روپے ایک مجبور باپ کو اس قرض سے نجات دلا سکتے ہیں",
                "صرف 4 لوگ مل کر 1,000 روپے دیں تو ایک بے بس باپ قرض کے بوجھ سے آزاد ہو سکتا ہے",
            )
            .replace(
                "People are now coming to Yousaf's father's home, asking him to repay the money he "
                "borrowed for his little son's Janazah.",
                "Right now, people stand at Yousaf's father's door, demanding the money he borrowed "
                "to bury his little boy.",
            )
            .replace(
                "He has already lost his 2-year-old son, and Rs. 17,000 is still unpaid..",
                "He has already lost his 2-year-old child. Rs. 17,000 of that debt is still waiting "
                "to be paid..",
            )
            .replace(
                "Just your 1,000 rs donstion and 4 people donating Rs. 1,000 can relief helpless "
                "father's pain.",
                "Your 1,000 rs plus 4 people giving Rs. 1,000 each can lift this helpless father's pain.",
            )
        )
        self.assertEqual(reject_reason(src, rewrite), "")
        light = src.replace("He has already lost", "He already lost")
        self.assertIn("not deeply rewritten", reject_reason(src, light))

    def test_partial_batch_keeps_valid_versions_and_retry_adds_the_next_five(self):
        b = self.make()
        source = SRC
        with patch.object(b, "_spawn"):
            row = b.save("group", source)
            b.generate("group")
        candidates = list(DEEP)
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", return_value=candidates[:2]),
        ):
            b._generate("group", b.get("group"), ("group", row["revision"]))
        partial = b.get("group")
        self.assertEqual(partial["state"], "Partial")
        self.assertEqual(len(partial["items"]), 2)
        self.assertIn("2 of 5", partial["error"])
        self.assertTrue(all(valid(source, t) for t in partial["items"]))
        with patch.object(b, "_spawn"):
            b.retry("group")
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch("dm_variants._call", return_value=candidates[2:]),
        ):
            b._generate("group", b.get("group"), ("group", row["revision"]))
        self.assertEqual(b.get("group")["state"], "Ready")
        self.assertEqual(len(b.get("group")["items"]), 7)  # 2 kept + 5 new
        self.assertEqual(b.get("group")["items"][:2], partial["items"])

    def test_empty_bank_sends_the_exact_saved_message_with_no_added_lines(self):
        b = self.make()
        source = "💔 2-year-old Yousaf has passed away.\n\nHis parents need burial support.\n\nRs. 47,000 STILL NEEDED.\n\n03097458815 — Easypaisa / JazzCash - Wajdan Khan"
        self.drafts["group"] = source
        with patch(
            "dm_variants.assistant.client", side_effect=AssertionError("Never call AI for recovery")
        ):
            row = b.ensure_group_ready()
            self.assertEqual(row["items"], [])
            self.assertEqual(b.reserve_groups(source, 6), [source] * 6)
        self.assertEqual(self.drafts["group"], source)

    def test_old_wrapped_fallbacks_are_removed_and_never_sent(self):
        b = self.make()
        source = self.drafts["group"] = SRC
        rewrite = DEEP[0]
        self.app.STORE.put(
            "focus_wording",
            {
                "group": {
                    "source": source,
                    "revision": "r1",
                    "items": [
                        rewrite,
                        "For everyone in this group, please read:\n\n" + source + "\n\nThank you.",
                    ],
                    "state": "Partial",
                    "local_fallback": 1,
                    "generator": GEN,
                }
            },
        )
        row = b.get("group")
        self.assertEqual(row["items"], [rewrite])
        self.assertNotIn("local_fallback", row)
        sent = b.reserve_groups(source, 4)
        self.assertEqual(sent, [rewrite, source, rewrite, source])
        self.assertTrue(all("please read:" not in x for x in sent))

    def test_owner_messages_teach_new_versions_their_voice(self):
        import dm_variants

        b = self.make()
        with patch.object(b, "_spawn"):
            b.save("group", "🚨 First appeal.\n\nPlease don't think someone else will help.")
            b.save("group", "🚨 Second appeal.\n\nOnly you can do this now.")
            b.save("group", SRC)
        style = b.owner_style(SRC)
        self.assertEqual(style[0], "🚨 Second appeal.\n\nOnly you can do this now.")
        self.assertIn("🚨 First appeal.\n\nPlease don't think someone else will help.", style)
        self.assertTrue(all(SRC not in t for t in style))
        saved = dm_variants.OWNER_STYLE
        dm_variants.OWNER_STYLE = lambda: style
        try:
            prompt = dm_variants._prompt(SRC, 3, [])
        finally:
            dm_variants.OWNER_STYLE = saved
        self.assertIn("OWNER'S OWN MESSAGES", prompt)
        self.assertIn("Only you can do this now.", prompt)
        self.assertIn("Never copy their facts", prompt)
        self.assertIn("bystander", prompt)
        self.assertIn("never from invented facts", dm_variants.SYSTEM)

    def test_nothing_generates_by_itself_after_an_upgrade_or_restart(self):
        b = self.make()
        source = self.drafts["group"]
        b.app.STORE.put(
            "focus_wording",
            {
                "group": {
                    "source": source,
                    "revision": "a",
                    "items": [],
                    "state": "Needs retry",
                    "error": "old",
                },
                "dm": {
                    "source": "d",
                    "revision": "b",
                    "items": [],
                    "state": "Generating",
                },  # old workflow
            },
        )
        with patch("focus_bank.threading.Thread") as thread:
            self.assertEqual(b.get("group")["state"], "Needs retry")
            self.assertEqual(b.get("dm")["state"], "Not generated")
        thread.assert_not_called()

    def test_a_batch_the_owner_started_resumes_after_a_restart(self):
        b = self.make()
        with patch.object(b, "_spawn"):
            b.save("group", self.drafts["group"])
            b.generate("group")
        newer = FocusBank(self.app)
        with patch("focus_bank.threading.Thread") as thread:
            self.assertEqual(newer.get("group")["state"], "Generating")
            newer.get("group")  # polling again must not start a second worker
        self.assertEqual(thread.call_count, 1)

    def test_manual_messages_are_distinct_and_group_sends_never_reuse(self):
        b = self.make()
        with patch.object(b, "_spawn"):
            b.save("group", self.drafts["group"])
        messages = ["Owner message " + str(i) for i in range(10)]
        b.manual("group", messages)
        first = b.reserve_groups(self.drafts["group"], 6)
        second = b.reserve_groups(self.drafts["group"], 4)
        self.assertEqual(len(set(first + second)), 10)
        self.assertEqual(b.reserve_groups(self.drafts["group"], 1), [first[0]])
        restarted = FocusBank(self.app)
        self.assertEqual(restarted.reserve_groups(self.drafts["group"], 1), [first[1]])
        self.assertEqual(len(set(first + second)), 10)
        with self.assertRaises(ValueError):
            b.manual("group", ["duplicate", "duplicate"])

    def test_regeneration_keeps_manual_slots_and_invalidates_old_worker(self):
        b = self.make()
        with patch.object(b, "_spawn"):
            old = b.save("group", self.drafts["group"])
        row = b.manual("group", ["A manually approved message"])
        self.assertFalse(b.record("group", old["revision"], {"items": ["stale"]}))
        with patch.object(b, "_spawn"):
            fresh = b.retry("group", fresh=True)
        self.assertEqual(fresh["items"], ["A manually approved message"])
        self.assertNotEqual(fresh["revision"], row["revision"])


if __name__ == "__main__":
    unittest.main()


class SendingWorkflow(unittest.TestCase):
    """Zero versions, rotation, background top-up, safe pause and Group/DM independence."""

    make = FocusTests.make

    def ready(self, n, kind="group"):
        b = self.make()
        with patch.object(b, "_spawn"):
            b.save("group", SRC)
            if kind == "dm":
                b.save("dm", SRC, b.get("dm")["revision"])
        data = b._load()
        data[kind]["items"] = list(DEEP[:n])
        data[kind]["state"] = "Ready" if n else "Not generated"
        b._put(data)
        return b

    def test_test_and_sends_work_with_zero_versions_using_the_base_message(self):
        b = self.ready(0)
        with patch.object(b, "generate") as gen:
            self.assertEqual(b.reserve_groups("x", 2, auto=True), [SRC, SRC])
        gen.assert_not_called()  # nothing is written until the owner clicks

    def test_top_up_starts_when_two_unused_remain_and_never_doubles(self):
        b = self.ready(5)
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch.object(b, "generate") as gen,
        ):
            for _ in range(2):
                b.reserve_groups("x", 1, auto=True)
            gen.assert_not_called()  # 4 of 6 unused
            for _ in range(3):
                b.reserve_groups("x", 1, auto=True)
        self.assertTrue(gen.called)
        self.assertEqual(gen.call_args.kwargs, {"auto": True})
        # the real generate refuses a second batch while one runs
        with patch.object(b, "_spawn"):
            b.generate("group", auto=True)
            before = b._load()["group"]["batch"]
            b.generate("group", auto=True)
        self.assertEqual(b._load()["group"]["batch"], before)

    def test_rotation_never_repeats_inside_a_round(self):
        b = self.ready(10)
        with patch.object(b, "_top_up"):
            sent = [b.reserve_groups("x", 1)[0] for _ in range(10)]
        self.assertEqual(len(set(sent)), 10)

    def test_auto_send_waits_or_pauses_when_everything_is_used(self):
        from focus_bank import VersionsPaused

        b = self.ready(5)
        with patch.object(b, "_top_up"):
            for _ in range(6):  # five versions and the base message
                b.reserve_groups("x", 1, auto=True)
        data = b._load()
        data["group"].update(state="Generating", batch={"goal": 10, "auto": True})
        b._put(data)
        with patch.object(b, "_spawn"), self.assertRaisesRegex(VersionsPaused, "not ready"):
            b.reserve_groups("x", 1, auto=True)
        self.assertEqual(
            len(b.reserve_groups("x", 1, auto=False)), 1
        )  # the owner's own send still works
        data = b._load()
        data["group"].update(state="Partial", auto_failed=True)
        b._put(data)
        with self.assertRaisesRegex(VersionsPaused, "paused"):
            b.reserve_groups("x", 1, auto=True)
        with patch.object(b, "_spawn"):
            b.generate("group")  # the owner's click clears the pause and starts the next 5
        self.assertFalse(b._load()["group"]["auto_failed"])

    def test_a_failed_top_up_waits_then_retries_by_itself(self):
        import time

        b = self.ready(5)

        def failed(ago, fails=1):
            data = b._load()
            data["group"].update(
                auto_failed=True, auto_fails=fails, auto_failed_at=time.time() - ago
            )
            b._put(data)
            return b._load()["group"]

        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch.object(b, "generate") as gen,
        ):
            b._top_up("group", failed(30), 5, 0)  # failed 30 s ago: not every minute
            gen.assert_not_called()
            b._top_up("group", failed(121), 5, 0)  # first wait (2 min) is over
            self.assertEqual(gen.call_count, 1)
            gen.reset_mock()
            b._top_up("group", failed(400, fails=2), 5, 0)  # second wait is 5 min: 400 s is enough
            self.assertEqual(gen.call_count, 1)
            gen.reset_mock()
            b._top_up("group", failed(400, fails=3), 5, 0)  # third wait is 15 min: too soon
            gen.assert_not_called()
            row = failed(0)
            del row["auto_failed_at"]
            data = b._load()
            data["group"].pop("auto_failed_at")
            b._put(data)
            b._top_up("group", b._load()["group"], 5, 0)  # an older stuck record heals at once
            self.assertEqual(gen.call_count, 1)

    def test_paused_send_starts_the_retry_itself_and_never_asks_for_a_click(self):
        import time
        from focus_bank import VersionsPaused

        b = self.ready(5)
        with patch.object(b, "_top_up"):
            for _ in range(6):
                b.reserve_groups("x", 1, auto=True)
        data = b._load()
        data["group"].update(
            state="Partial", auto_failed=True, auto_fails=1, auto_failed_at=time.time() - 500
        )
        b._put(data)
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch.object(b, "_spawn"),
            self.assertRaisesRegex(VersionsPaused, "not ready"),
        ):
            b.reserve_groups("x", 1, auto=True)  # the wait is over: a new batch is started
        self.assertEqual(b._load()["group"]["state"], "Generating")
        data = b._load()
        data["group"].update(
            state="Partial", auto_failed=True, auto_fails=1, auto_failed_at=time.time()
        )
        b._put(data)
        with self.assertRaises(VersionsPaused) as ctx:
            b.reserve_groups("x", 1, auto=True)
        self.assertIn("retries on its own", str(ctx.exception))
        self.assertNotIn("press", str(ctx.exception).lower())

    def test_heal_tops_up_low_banks_without_a_click(self):
        b = self.ready(5)
        with patch.object(b, "_top_up"):
            for _ in range(4):
                b.reserve_groups("x", 1, auto=True)  # 5 versions + base: 2 unused left
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch.object(b, "generate") as gen,
        ):
            b.heal()
        self.assertEqual(gen.call_args.args[0], "group")
        self.assertEqual(gen.call_args.kwargs, {"auto": True})
        full = self.ready(10)  # a full, unused bank needs nothing
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch.object(full, "generate") as gen,
        ):
            full.heal()
        gen.assert_not_called()

    def test_group_and_dm_keep_their_own_versions_and_rotation(self):
        b = self.ready(5, "dm")
        data = b._load()
        data["group"].update(items=list(DEEP[5:]), state="Ready")
        b._put(data)
        with patch.object(b, "_top_up"):
            g = [b.reserve_groups("x", 1)[0] for _ in range(3)]
            d = [b.next_dm_version() for _ in range(3)]
        self.assertTrue(all(x in DEEP[5:] or x == SRC for x in g))
        self.assertTrue(all(x in DEEP[:5] for x in d))
        rot = b.app.STORE.get
        self.assertNotEqual(rot("focus_group_rotation"), rot("focus_dm_rotation"))
        with patch.object(b, "_spawn"):
            b.generate("dm")
        self.assertEqual(b._load()["group"]["state"], "Ready")  # a DM batch never touches Group
        self.assertEqual(b._load()["dm"]["state"], "Generating")

    def test_dm_top_up_uses_the_same_rule(self):
        b = self.ready(5, "dm")
        with (
            patch("dm_variants.assistant.client", return_value="fake"),
            patch.object(b, "generate") as gen,
        ):
            for _ in range(2):
                b.next_dm_version()
            gen.assert_not_called()
            b.next_dm_version()
        self.assertEqual(gen.call_args.args, ("dm",))

    def test_every_saved_version_is_rechecked_against_the_original_before_use(self):
        b = self.ready(5)
        bad = DEEP[0].replace("50,000", "40,000")  # a wrong amount must never be sent
        data = b._load()
        data["group"]["items"][0] = bad
        b._put(data)
        with patch.object(b, "_top_up"):
            sent = [b.reserve_groups("x", 1)[0] for _ in range(6)]
        self.assertNotIn(bad, sent)


class FormatChecks(unittest.TestCase):
    def test_broken_markers_and_lost_bullets_are_rejected(self):
        from focus_bank import format_problem

        src = "*Hook*\n\n* Rs. 17,500 is still needed\n_Details here_"
        self.assertEqual(
            format_problem(src, "*New hook*\n\n* Rs. 17,500 is still needed\n_Other details_"), ""
        )
        self.assertIn(
            "unpaired", format_problem(src, "*New hook\n\n* Rs. 17,500 is still needed\n_x_")
        )
        self.assertIn(
            "bullet", format_problem(src, "*New hook*\n\nRs. 17,500 is still needed\n_x_")
        )
        self.assertIn("unpaired", reject_reason(SRC, DEEP[0].replace("*Stop", "Stop", 1)))
