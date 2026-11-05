"""Property-based tests (Hypothesis): rules that must hold for ANY input, not just the examples we thought of."""

import sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from hypothesis import given, settings, strategies as st, HealthCheck, assume
except ImportError:  # the suite still runs without Hypothesis installed
    raise unittest.SkipTest("hypothesis is not installed")
import chat_policy, manual_commands as m, timed_tasks
from donor_book import send_request

FAST = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
SEND_KINDS = {"appeal", "appeals", "repeat", "text", "appeal_to", "say"}
SEND_TOOLS = ("send_message", "send_appeal", "send_dm_appeal", "dm_list", "dm_donors", "dm_group")
COMMANDS = [
    "send to main",
    "send it",
    "send all",
    "post in test group",
    "dm donors",
    "send hi to ali",
    "send now",
    "again",
    "send 20 dms to important donors",
    "resend",
    "send to fiverr",
    "bhejo",
    "send main now",
]
words = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "Zs", "Po")), max_size=40
)


class NeverCrash(unittest.TestCase):
    @FAST
    @given(st.text(max_size=200))
    def test_parsers_only_ever_raise_value_error(self, text):
        for fn in (
            m.parse,
            timed_tasks.parse,
            send_request,
            lambda t: chat_policy.permitted("send_message", t),
            lambda t: chat_policy.permitted("set_left", t),
            lambda t: chat_policy.intent(t),
        ):
            try:
                fn(text)
            except ValueError:
                pass


class NegationsAndQuestionsNeverSend(unittest.TestCase):
    @FAST
    @given(
        st.sampled_from(COMMANDS),
        st.sampled_from(["don't", "dont", "do not", "never"]),
        st.sampled_from(["", "please ", "bhai "]),
    )
    def test_negated_commands(self, cmd, neg, lead):
        text = f"{lead}{neg} {cmd}"
        self.assertNotIn((m.parse(text) or {}).get("kind"), SEND_KINDS, text)
        for tool in SEND_TOOLS:
            self.assertFalse(chat_policy.permitted(tool, text), (tool, text))

    @FAST
    @given(
        st.sampled_from(
            ["did you", "have you", "was it", "what if i", "how do i", "can you tell me if you"]
        ),
        st.sampled_from(COMMANDS),
    )
    def test_questions(self, q, cmd):
        text = f"{q} {cmd}?"
        for tool in ("send_appeal", "send_dm_appeal", "dm_donors", "set_left", "money_came"):
            self.assertFalse(chat_policy.permitted(tool, text), (tool, text))


class Money(unittest.TestCase):
    @FAST
    @given(
        st.integers(min_value=100, max_value=10_000_000),
        st.sampled_from(
            [
                "{n} left",
                "left {n}",
                "Rs. {c} left",
                "{c} left",
                "balance {n}",
                "{n} baqi",
                "now {n}",
            ]
        ),
    )
    def test_balance_is_read_exactly(self, n, form):
        text = form.format(n=n, c=f"{n:,}")
        plan = m.parse(text) or {}
        self.assertEqual((plan.get("kind"), plan.get("amount")), ("amount", n), text)

    @FAST
    @given(st.integers(min_value=1, max_value=9999))
    def test_k_suffix(self, k):
        self.assertEqual((m.parse(f"{k}k left") or {}).get("amount"), k * 1000)

    @FAST
    @given(
        st.integers(min_value=0, max_value=999_999_9).map(lambda n: "03" + str(n).zfill(9)),
        st.sampled_from(["{p}", "{p} ali", "ali {p}", "add {p}"]),
    )
    def test_a_phone_number_is_never_money(self, phone, form):
        text = form.format(p=phone)
        self.assertNotIn((m.parse(text) or {}).get("kind"), ("amount", "money"), text)

    @FAST
    @given(
        st.integers(min_value=1, max_value=99),
        st.sampled_from(["groups", "people", "members", "minutes", "messages", "dms", "donors"]),
    )
    def test_small_counts_are_never_money(self, n, unit):
        for text in (f"{n} {unit} left", f"left {n} {unit}", f"send {n} {unit}"):
            self.assertNotIn((m.parse(text) or {}).get("kind"), ("amount", "money"), text)


class LiteralWords(unittest.TestCase):
    @FAST
    @given(
        st.from_regex(r"[a-z]{2,8}( [a-z]{2,8}){0,3}", fullmatch=True),
        st.sampled_from(["ali", "wajdan", "jr account", "hamza"]),
    )
    def test_send_words_to_a_person_never_sends_the_poster_appeal(self, words_, who):
        assume(
            not __import__("re").search(
                r"\b(message|caption|dm|poster|wording|version|hook|appeal|emotional|stronger|shorter|longer|draft|format|paragraph|to|now|it|again|main|test|all|group|groups|fiverr|upwork|uet|community|free|freelance|toprated|rated|top|givelife|the|send|resend|post|share|bhejo|bhej|an|a|that|this|these|those|them|full|proper|with|and|man|bro|yaar|please|bhai|abhi|go|do|restart|reset|gap|timer|msg|image|picture|updated|amount|right|away|asap|immediately|fast|quick|only|current|latest)\b",
                words_,
            )
        )
        text = f"send {words_} to {who}"
        self.assertFalse(chat_policy.permitted("send_appeal", text), text)
        self.assertFalse(chat_policy.permitted("send_dm_appeal", text), text)


class BatchRequests(unittest.TestCase):
    @FAST
    @given(
        st.integers(min_value=1, max_value=5000),
        st.sampled_from(
            [
                "send {n} dms to important donors",
                "dm {n} important donors",
                "send first {n} donors",
                "send {n} donors",
            ]
        ),
    )
    def test_batch_sizes_stay_inside_the_safe_limits(self, n, form):
        r = send_request(form.format(n=n))
        assume(r is not None)
        self.assertTrue(r["chunk"] is None or 1 <= r["chunk"] <= 20, r)
        self.assertTrue(r["limit"] is None or r["limit"] == n, r)
        self.assertGreater(r["gap_seconds"], 0)


if __name__ == "__main__":
    unittest.main()


class NobodyTwice(unittest.TestCase):
    """Any mix of failures, disconnects, pauses and restarts: continuing never DMs the same person twice,
    and everyone confirmed is eventually reached when the problems stop."""

    @settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        st.integers(min_value=2, max_value=30),
        st.lists(
            st.tuples(
                st.sampled_from(["fail", "uncertain", "pause", "restart"]),
                st.integers(min_value=0, max_value=29),
            ),
            max_size=5,
        ),
        st.sampled_from([None, 1, 3, 20]),
    )
    def test_continue_chains(self, people, events, chunk):
        import copy
        from donor_book import DonorBook
        from donor_delivery import DonorDelivery

        class Store:
            def __init__(self):
                self.data = {}

            def get(self, k, d=None):
                return copy.deepcopy(self.data.get(k, d))

            def put(self, k, v):
                self.data[k] = copy.deepcopy(v)

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = Store()
        book = DonorBook(folder.name, store)
        for i in range(people):
            book.update(
                book.add("P%02d" % i, "0300%07d" % (1000000 + i))["donor"]["id"], important=True
            )
        clock = [time.time()]
        delivered = []
        uncertain = set()
        plan = {}
        for kind, at in events:
            plan.setdefault(at % people, kind)

        def make():
            return DonorDelivery(
                folder.name,
                store,
                book,
                send,
                lambda: "saved **full**\n\nDM caption",
                lambda: True,
                lambda: False,
                lambda p: True,
                lambda n: (n, "Brother"),
                lambda n: ["w%d" % i for i in range(n)],
            )

        jobs = [None]

        def send(body):
            index = len(delivered) + len(uncertain)
            kind = plan.pop(index, None) if index in plan else None
            if kind == "fail":
                raise ValueError("WhatsApp is disconnected.")
            if kind == "uncertain":
                uncertain.add(body["name"])
                return {"code": "UNCERTAIN"}
            delivered.append(body["name"])
            if kind == "pause":
                jobs[0].stop.set()
            if kind == "restart":
                jobs[0].stop.set()
                jobs.append("restart")
            return {"code": "SUCCESS"}

        jobs[0] = make()

        def run(started):
            job = jobs[0]._load()["jobs"][-1]

            def wait(seconds):
                clock[0] += seconds
                return jobs[0].stop.is_set()

            with (
                patch("donor_delivery.time.time", side_effect=lambda: clock[0]),
                patch.object(jobs[0].stop, "wait", side_effect=wait),
            ):
                jobs[0]._run(job)

        args = dict(chunk=chunk, limit=people) if chunk else dict(limit=min(people, 20))
        for attempt in range(12):
            if jobs[-1] == "restart":
                jobs.pop()
                data = jobs[0]._load()
                data["jobs"][-1].update(state="Sending", boot="old")
                jobs[0]._save(data)
                jobs[0] = make()
            jobs[0].stop.clear()
            try:
                started = jobs[0].start("important", 60, run=False, **args)
            except ValueError:
                break
            run(started)
            if jobs[0].status()["state"] == "Completed" and not jobs[0].status().get("resumable"):
                break
        self.assertEqual(len(delivered), len(set(delivered)), f"someone got two DMs: {delivered}")
        self.assertFalse(set(delivered) & uncertain, "an unconfirmed person was sent again")


class Schedules(unittest.TestCase):
    @FAST
    @given(
        st.sampled_from(
            ["send to main", "post in test group", "send all", "send to fiverr", "send it"]
        ),
        st.sampled_from(
            [
                "at {h}pm",
                "at {h}am",
                "tomorrow at {h}pm",
                "in {m} min",
                "in {m} minutes",
                "after {m} min",
                "at {h}:30pm",
            ]
        ),
        st.integers(min_value=1, max_value=11),
        st.integers(min_value=1, max_value=120),
    )
    def test_a_message_with_a_time_never_sends_right_now(self, cmd, when, h, mins):
        text = f"{cmd} {when.format(h=h, m=mins)}"
        self.assertNotIn((m.parse(text) or {}).get("kind"), SEND_KINDS, text)
        for tool in ("send_appeal", "send_message", "send_dm_appeal"):
            self.assertFalse(chat_policy.permitted(tool, text), (tool, text))

    @FAST
    @given(st.integers(min_value=1, max_value=12), st.sampled_from(["am", "pm"]))
    def test_the_clock_is_read_exactly(self, h, ampm):
        plan = timed_tasks.parse(f"send to main at {h}{ampm}")
        self.assertEqual(plan["command"], "create")
        expect = (h % 12) + (12 if ampm == "pm" else 0)
        self.assertEqual(plan["clock"], f"{expect:02d}:00")
        self.assertGreater(plan["due"], time.time() - 60)
        self.assertLess(plan["due"], time.time() + 86400 + 60)

    @FAST
    @given(
        st.sampled_from(
            [
                "cancel it",
                "cancel all",
                "cancel 2nd",
                "cancel last",
                "remove all of them",
                "clear all",
                "delete all schedules",
                "cancel the duplicate",
                "undo it",
            ]
        )
    )
    def test_cancel_words_never_create_or_send(self, text):
        self.assertNotEqual((timed_tasks.parse(text) or {}).get("command"), "create", text)
        self.assertNotIn((m.parse(text) or {}).get("kind"), SEND_KINDS, text)

    @FAST
    @given(st.integers(min_value=1, max_value=4))
    def test_ordinals(self, n):
        word = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}[n]
        self.assertEqual(timed_tasks.parse(f"cancel {word}").get("index"), n - 1)


class PastedLists(unittest.TestCase):
    def helper(self):
        import copy
        from donor_book import DonorBook
        from donor_paste import PastedDonors

        class Store:
            def __init__(self):
                self.data = {}

            def get(self, k, d=None):
                return copy.deepcopy(self.data.get(k, d))

            def put(self, k, v):
                self.data[k] = copy.deepcopy(v)

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        return PastedDonors(
            DonorBook(folder.name, Store()),
            None,
            lambda: "923205069925",
            lambda label: (label.split()[0] if label else "", "Brother"),
        )

    @FAST
    @given(st.text(max_size=300))
    def test_any_paste_either_previews_or_says_why(self, text):
        try:
            out = self.helper().preview(text)
        except ValueError:
            return
        self.assertLessEqual(out["count"], 20)

    @FAST
    @given(
        st.lists(
            st.integers(min_value=0, max_value=9_999_999), min_size=1, max_size=20, unique=True
        ),
        st.sampled_from(["\n", " ", ", ", "; "]),
        st.booleans(),
    )
    def test_numbers_are_counted_once_and_never_shown(self, tails, sep, dup):
        phones = ["0300" + str(t).zfill(7) for t in tails]
        text = sep.join(phones + ([phones[0]] if dup else []))
        try:
            out = self.helper().preview(text)
        except ValueError:
            return
        self.assertEqual(out["count"], len(phones))
        shown = __import__("json").dumps({k: v for k, v in out.items() if k != "token"})
        for p in phones:
            self.assertNotIn(p[-7:], shown)


class OneBatchAtATime(unittest.TestCase):
    def test_two_simultaneous_starts_make_one_batch(self):
        import copy, threading
        from donor_book import DonorBook
        from donor_delivery import DonorDelivery

        class Store:
            def __init__(self):
                self.data = {}
                self.lock = threading.Lock()

            def get(self, k, d=None):
                return copy.deepcopy(self.data.get(k, d))

            def put(self, k, v):
                self.data[k] = copy.deepcopy(v)

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = Store()
        book = DonorBook(folder.name, store)
        for i in range(5):
            book.add("P%d" % i, "0300%07d" % (1000000 + i))
        jobs = DonorDelivery(
            folder.name,
            store,
            book,
            lambda b: {"code": "SUCCESS"},
            lambda: "saved **full**\n\nDM caption",
            lambda: True,
            lambda: False,
            lambda p: True,
            lambda n: (n, "Brother"),
        )
        results = []
        gate = threading.Barrier(8)

        def go(i):
            gate.wait()
            try:
                results.append(jobs.start("all", 60, run=False, request_id="r%d" % i)["job"]["id"])
            except ValueError:
                results.append("refused")

        threads = [threading.Thread(target=go, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        started = [r for r in results if r != "refused"]
        self.assertEqual(len(started), 1, results)
        self.assertEqual(len(jobs._load()["jobs"]), 1)
