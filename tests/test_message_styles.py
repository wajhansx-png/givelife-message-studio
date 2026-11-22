"""The four message buttons: exact structure, correct donor math, safe numbers, rotation, no repeats.
The AI is replaced by a scripted fake: nothing here calls a model or WhatsApp."""

import json, re, unittest
from unittest.mock import patch
import test_manual_sends  # noqa: F401  (temporary data folder and import path)
import ai_call, dm_composer, focus_bank, message_styles as ms, team_rules

GROUP = (
    "*Yousaf's father needs help.*\n\n_People are asking his father for the money borrowed for his son's Janazah._\n\n"
    "🔴 Rs. 4,000 LEFT\n\n*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n- GiveLife Foundation"
)
CTX = dict(
    left=4000, facts="Case: Yousaf\n" + GROUP, group_text=GROUP, dm_text="", current_text=GROUP
)
GOOD = dict(
    hook="صرف 4 لوگوں کے 1,000 روپے ایک مجبور باپ کو قرض سے نجات دلا سکتے ہیں",
    story="People are coming to Yousaf's father's home asking for the money borrowed for his son's Janazah. His father is helpless.",
    help="this helpless father",
    verse="q34_39",
    concept="father debt janazah",
)


def script(*answers):
    """chat() that returns each scripted answer in turn (dicts are sent as JSON)."""
    queue, seen = list(answers), []

    def chat(system, prompt):
        seen.append(prompt)
        a = queue.pop(0) if queue else queue_end
        return json.dumps(a, ensure_ascii=False) if isinstance(a, dict) else a

    queue_end = "not json"
    chat.seen = seen
    return chat


def make(style="ur_en", state=None, ctx=None, *answers, today="2026-11-07"):
    return ms.generate(
        style, ctx or CTX, state or {}, script(*answers), ai_call.json_of, today=today
    )


class DonorMath(unittest.TestCase):
    def test_known_amounts(self):
        for left, want in {1: (1, 1), 700: (1, 700), 1000: (1, 1000), 1500: (2, 1000), 4000: (4, 1000),
                           4500: (5, 1000), 10001: (6, 2000), 25000: (5, 5000)}.items():  # fmt: skip
            self.assertEqual(ms.donor_math(left), want, left)

    def test_always_covers_what_is_left_and_never_asks_for_a_whole_extra_person(self):
        for left in range(1, 250000, 137):
            people, each = ms.donor_math(left)
            self.assertGreaterEqual(people * each, left, left)
            self.assertLess((people - 1) * each, left, left)

    def test_a_finished_case_is_refused(self):
        with self.assertRaises(ValueError):
            ms.donor_math(0)
        with self.assertRaises(ValueError):
            make("ur_en", None, dict(CTX, left=0), GOOD)


class Structure(unittest.TestCase):
    def test_urdu_english_follows_the_required_order(self):
        result, _ = make("ur_en", None, None, GOOD)
        paras = result["text"].split("\n\n")
        self.assertRegex(paras[0], r"^\*[^*\n]+\*$")  # bold Urdu hook
        self.assertTrue(re.search(r"[؀-ۿ]", paras[0]))
        self.assertRegex(paras[1], r"^_.+ 💔_$")  # italic English explanation ending 💔
        self.assertIn("سورۃ سبا: 39", paras[2])  # the verse and its reference
        self.assertEqual(paras[3], "🔴 Rs. 4,000 LEFT")
        self.assertEqual(
            paras[4], "• *_Just 4 people donating Rs. 1,000 can help this helpless father._* 🤲"
        )
        self.assertIn("03097458815", paras[5])
        self.assertTrue(result["text"].rstrip().endswith("GiveLife Foundation"))
        self.assertEqual(focus_bank.format_problem("*a* _b_", result["text"], bullets=False), "")

    def test_english_message_has_no_urdu_and_translated_verse(self):
        eng = dict(GOOD, hook="A helpless father cannot repay the loan for his son's Janazah")
        result, _ = make("en", None, None, eng)
        self.assertFalse(re.search(r"[؀-ۿ]", result["text"]))
        self.assertIn("Allah says:", result["text"])
        self.assertIn("Surah Saba 34:39", result["text"])

    def test_a_single_donor_reads_correctly(self):
        result, _ = make(
            "en",
            None,
            dict(CTX, left=700),
            dict(
                GOOD,
                hook="One person can end this worry today",
                story="The family needs a small amount.",
            ),
        )
        self.assertIn("Just 1 person donating Rs. 700 can help", result["text"])

    def test_the_verse_text_comes_only_from_the_approved_list(self):
        for ident, v in ms.VERSES.items():
            if v["kind"] == "hadith":
                self.assertIn(v["ur_full"], team_rules.HADITH)
            else:
                self.assertIn(v["ur_ref"], ms.verse_block(ident, False))
                self.assertIn(v["en_ref"], ms.verse_block(ident, True))
        with self.assertRaises(
            ValueError
        ):  # an invented verse id is never printed, whatever the AI says
            make("ur_en", None, None, *[dict(GOOD, verse="made_up_verse")] * 3)


class Safety(unittest.TestCase):
    def test_invented_numbers_are_rejected_then_a_clean_retry_is_used(self):
        bad = dict(GOOD, story="Rs. 9,500 are due by 3 days and 12 people are waiting.")
        result, _ = make("ur_en", None, None, bad, GOOD)
        self.assertNotIn("9,500", result["text"])

    def test_always_failing_ai_changes_nothing(self):
        state = {"n": 3}
        with self.assertRaises(ValueError) as caught:
            make("ur_en", state, None, "not json", "not json", "not json")
        self.assertIn("Nothing was changed", str(caught.exception))
        self.assertEqual(state, {"n": 3})

    def test_other_payment_methods_and_invented_medical_claims_are_rejected(self):
        for story in (
            "Send it by JazzCash today.",
            "His fingers are paralysed and numbness is spreading.",
        ):
            with self.assertRaises(ValueError):
                make(
                    "ur_en",
                    None,
                    None,
                    dict(GOOD, story=story),
                    dict(GOOD, story=story),
                    dict(GOOD, story=story),
                )

    def test_english_message_cannot_smuggle_urdu(self):
        with self.assertRaises(ValueError):
            make("en", None, None, *[GOOD] * 3)

    def test_payment_account_is_the_saved_one(self):
        self.assertEqual(
            ms.payment_block(GROUP),
            "*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n- GiveLife Foundation",
        )
        self.assertIn("EASYPAISA ONLY", ms.payment_block("no account here"))
        long = "Story\n\n📲 *03097458815*\nEASYPAISA ONLY: Wajdan Khan\nFor GiveLife Foundation\n\nReply *Done* after donating."
        self.assertEqual(
            ms.payment_block(long),
            "📲 *03097458815*\nEASYPAISA ONLY: Wajdan Khan\nFor GiveLife Foundation",
        )

    def test_owner_jazzcash_only_is_kept(self):
        own = "Story\n\n*JazzCash ONLY*\n03097458815\n*Wajdan Khan (GiveLife Foundation account)*"
        self.assertEqual(ms.payment_block(own), own.split("\n\n", 1)[1])
        self.assertEqual(dm_composer.payment_fix(own), own)
        self.assertIn("EASYPAISA ONLY", dm_composer.payment_fix("03097458815 Easypaisa / JazzCash"))


class Variety(unittest.TestCase):
    def test_the_same_opening_is_not_used_twice_in_a_day(self):
        _, state = make("ur_en", None, None, GOOD)
        second = dict(GOOD, hook="ایک باپ کے آنسو کون پونچھے گا")
        result, _ = make("ur_en", state, None, GOOD, second)
        self.assertIn(second["hook"], result["text"])  # the repeated first line was refused
        # A new day may reuse it.
        result, _ = make("ur_en", state, None, GOOD, today="2026-11-08")
        self.assertIn(GOOD["hook"], result["text"])

    def test_angles_rotate_and_triggers_change_the_whole_concept(self):
        names, state = [], {}
        for i in range(6):
            hook = "ایک نئی شروعات نمبر " + "ا" * (i + 1)
            result, state = make(
                "ur_en",
                state,
                None,
                dict(GOOD, hook=hook, story="Different story number " + "x" * i + "."),
                today="d%d" % i,
            )
            names.append(result["angle"])
        self.assertEqual(len(set(names)), 6)
        before = state["angle"]
        stronger = dict(
            GOOD,
            hook="اگر آج مدد نہ ہوئی تو یہ گھر اور بکھر جائے گا",
            story="Neighbours keep coming to the door. The father cannot answer them.",
            verse="h_muslim_2699",
        )
        result, state = make(
            "ur_en_more",
            state,
            dict(
                CTX,
                current_text="old",
            ),
            stronger,
        )
        self.assertNotEqual(result["angle"], before)

    def test_a_trigger_that_only_swaps_words_is_refused(self):
        same = dict(GOOD, story=GOOD["story"].replace("helpless", "powerless"))
        fresh = dict(
            GOOD,
            hook="دروازے پر دستک ہے اور باپ کے پاس جواب نہیں",
            story="Neighbours keep knocking. The father has nothing to give them.",
            verse="q2_261",
        )
        cur = ms.assemble(
            "ur_en", GOOD, dict(CTX, people=4, each=1000, payment=ms.payment_block(GROUP))
        )
        result, _ = make("ur_en_more", None, dict(CTX, current_text=cur), same, fresh)
        self.assertIn(fresh["hook"], result["text"])
        self.assertNotIn("powerless", result["text"])

    def test_trigger_makes_the_message_on_screen_stronger_not_a_different_one(self):
        shown = ms.assemble(
            "ur_en", GOOD, dict(CTX, people=4, each=1000, payment=ms.payment_block(GROUP))
        )
        stronger = dict(
            GOOD,
            hook="اگر آج مدد نہ ہوئی تو یہ باپ ٹوٹ جائے گا",
            story="People keep coming to Yousaf's father's home for the money borrowed for his son's Janazah. His father is helpless and has nothing left to give.",
        )
        chat = script(stronger)
        state = {"angle": "need"}
        result, new_state = ms.generate(
            "ur_en_more", dict(CTX, current_text=shown), state, chat, ai_call.json_of, today="2026-11-07"
        )
        prompt = chat.seen[0]
        self.assertIn("THE MESSAGE ON SCREEN (make THIS one stronger)", prompt)
        self.assertIn("Keep the SAME concept", prompt)
        self.assertIn(shown[:60], prompt)  # the shown message itself is in the prompt
        self.assertNotIn("Change the whole concept", prompt)
        self.assertNotIn("do not reuse its ideas", prompt)
        self.assertIn("Never add a new danger", prompt)  # stronger feeling, never new facts
        self.assertEqual(result["angle"], "stronger")
        self.assertEqual(new_state["angle"], "need")  # the usual rotation is not moved on
        self.assertIn(stronger["hook"], result["text"])
        self.assertIn("Janazah", result["text"])  # the same story is still there

    def test_trigger_keeps_the_verse_the_message_already_has(self):
        shown = ms.assemble(
            "ur_en", dict(GOOD, verse="h_muslim_2699"), dict(CTX, people=4, each=1000, payment=ms.payment_block(GROUP))
        )
        self.assertEqual(ms.verse_in(shown), "h_muslim_2699")
        self.assertEqual(ms.verse_in("no verse here"), "")
        chat = script(dict(GOOD, hook="اگر آج مدد نہ ہوئی تو یہ باپ ٹوٹ جائے گا", verse="h_muslim_2699"))
        result, _ = ms.generate(
            "ur_en_more", dict(CTX, current_text=shown), {"last": {"verse": "h_muslim_2699"}}, chat, ai_call.json_of, today="2026-11-07"
        )
        self.assertIn('already uses the verse id "h_muslim_2699"', chat.seen[0])
        self.assertIn(ms.VERSES["h_muslim_2699"]["ur_full"], result["text"])  # the same verse is fine now

    def test_trigger_with_nothing_on_screen_still_writes_a_fresh_stronger_message(self):
        chat = script(dict(GOOD, hook="اگر آج مدد نہ ہوئی تو یہ باپ ٹوٹ جائے گا"))
        ms.generate("ur_en_more", dict(CTX, current_text=""), {}, chat, ai_call.json_of, today="2026-11-07")
        self.assertNotIn("THE MESSAGE ON SCREEN", chat.seen[0])
        self.assertIn("STRONGER VERSION", chat.seen[0])

    def test_prompt_carries_the_live_case_and_todays_openings_but_no_secrets(self):
        chat = script(GOOD)
        ms.generate(
            "ur_en",
            CTX,
            {"openings": {"2026-11-07": ["old opening"]}},
            chat,
            ai_call.json_of,
            today="2026-11-07",
        )
        prompt = chat.seen[0]
        self.assertIn("Rs. 4,000 is still needed", prompt)
        self.assertIn("Just 4 people giving Rs. 1,000", prompt)
        self.assertIn("old opening", prompt)
        self.assertIn("Janazah", prompt)


class TriggerRoute(unittest.TestCase):
    SHOWN = "*Mirha cannot breathe.*\n\n_Her lungs are almost failing and her life is in real danger._\n\n🔴 Rs. 4,000 LEFT\n\n*03097458815*\nEASYPAISA ONLY (Wajdan Khan)\n- GiveLife Foundation"

    def run_style(self, style, **fakes):
        import server

        with (
            patch.object(server.assistant, "client", return_value=object()),
            patch.object(server, "read_left", return_value=4000),
        ):
            return server.message_style({"style": style, "kind": "group", "current": self.SHOWN})

    def test_trigger_makes_the_message_on_screen_stronger_in_place(self):
        with patch("dm_variants.generate", return_value=["STRONGER TEXT"]) as g:
            out = self.run_style("en_more")
        self.assertEqual(out["text"], "STRONGER TEXT")
        self.assertEqual(out["angle"], "stronger")
        self.assertEqual(g.call_args.args[0], self.SHOWN)  # the shown message itself is what is rewritten
        self.assertEqual(g.call_args.kwargs["mode"], "stronger")

    def test_every_button_rewrites_the_message_on_screen_never_a_different_one(self):
        for style, mode in (("en", "en"), ("ur_en", "ur_en"), ("en_more", "stronger"), ("ur_en_more", "stronger")):
            with patch("dm_variants.generate", return_value=["SAME MESSAGE " + mode]) as g, patch("message_styles.generate") as fresh:
                out = self.run_style(style)
            self.assertEqual(out["text"], "SAME MESSAGE " + mode)
            self.assertEqual(g.call_args.args[0], self.SHOWN)
            self.assertEqual(g.call_args.kwargs["mode"], mode)
            fresh.assert_not_called()  # never a fresh message from the case while one is on screen

    def test_a_refused_rewrite_leaves_the_message_alone_and_says_so(self):
        with patch("dm_variants.generate", side_effect=ValueError("Rejected because: a number changed.")), patch(
            "message_styles.generate"
        ) as fresh:
            with self.assertRaises(ValueError) as e:
                self.run_style("ur_en_more")
        fresh.assert_not_called()
        self.assertIn("Your message is unchanged", str(e.exception))
        self.assertIn("a number changed", str(e.exception))

    def test_with_nothing_on_screen_a_button_writes_from_the_case(self):
        import server

        fresh = ({"text": "FRESH", "angle": "family", "concept": ""}, {})
        with (
            patch.object(server.assistant, "client", return_value=object()),
            patch.object(server, "read_left", return_value=4000),
            patch("dm_variants.generate") as g,
            patch("message_styles.generate", return_value=fresh),
        ):
            out = server.message_style({"style": "en", "kind": "group", "current": ""})
        g.assert_not_called()
        self.assertEqual(out["text"], "FRESH")

    def test_rewrites_must_use_easy_english(self):
        import dm_variants, quality

        self.assertEqual(quality.fancy_words("plain", "Her plight is dire"), ["dire", "plight"])
        self.assertEqual(quality.fancy_words("Her plight", "Her plight"), [])  # the owner's own words are fine
        self.assertIn("EASY ENGLISH", dm_variants._prompt("x" * 200, 1, []))
        self.assertIn("SAME MESSAGE, IN EASY ENGLISH", dm_variants._prompt("x" * 200, 1, [], mode="en"))
        self.assertIn("FIRST line (the hook) is in simple, moving Urdu", dm_variants._prompt("x" * 200, 1, [], mode="ur_en"))

    def test_the_trigger_rewrite_prompt_asks_for_much_harder_but_never_new_facts(self):
        import dm_variants

        src = "x" * 200
        plain, strong = dm_variants._prompt(src, 1, []), dm_variants._prompt(src, 1, [], True)
        self.assertNotIn("TRIGGER MODE", plain)
        self.assertIn("TRIGGER MODE", strong)
        self.assertIn("same concept, story, facts, line structure", strong.lower().replace("exactly the ", ""))
        self.assertIn("never add a new fact", strong.lower())


if __name__ == "__main__":
    unittest.main()
