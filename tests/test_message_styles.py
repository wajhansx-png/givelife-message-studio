"""The four message buttons: exact structure, correct donor math, safe numbers, rotation, no repeats.
The AI is replaced by a scripted fake: nothing here calls a model or WhatsApp."""

import json, re, unittest
import test_manual_sends  # noqa: F401  (temporary data folder and import path)
import ai_call, focus_bank, message_styles as ms, team_rules

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


if __name__ == "__main__":
    unittest.main()
