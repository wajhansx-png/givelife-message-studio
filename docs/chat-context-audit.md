# Chat reliability audit — 2 November 2026

Evidence: owner-provided app transcripts in the Codex conversation, current repository, and isolated synthetic-state replays. Production conversation storage was not accessible in this workspace; this is not a claim that every cloud conversation was examined. No configured local DeepSeek key was found. Live semantic accuracy is therefore unmeasured.

## Verified causes and repairs

| Historical failure pattern | Technical cause / check | Repair |
| --- | --- | --- |
| Several prompts needed to edit the same DM | Runtime exposed a contextual edit while server permission rejected it; callbacks also defaulted unspecified edits to group | Shared draft resolution, inherited kind, contextual permission at both layers, wrong-kind rejection |
| Show returns an older or different message | Runtime preview and HTTP fast path chose screen mode rather than the active persisted draft | Both now resolve explicit kind, valid active draft, then screen |
| Earlier correction resurfaces | Old feedback and archived owner turns could retrieve text from a retired preference | Retired text/source IDs excluded; verified across memory reload |
| Short follow-up retrieves nothing useful | Retrieval used only “fix it”, with no topic words | Retrieval-only query includes active instruction and last owner turn; execution still uses original current request |
| New correction races an earlier AI edit | Bare contextual edits were not included in owner revision invalidation | Short contextual edits now advance owner revision |
| “Nothing is scheduled” on a failed read | Schedule exception became an empty list | Unknown is now distinct from no pending tasks |
| “Send thanks … to Akhtar fast” changes group posting | Speed parser ran before literal-recipient routing and defaulted unnamed pace to all groups | Exact text takes precedence; speed rules require named group scope |
| Previous case influences current draft | Persisted task could refer to a different draft hash | Reject stale task for context and preview resolution |

## Transcript regression catalogue

Existing and new tests cover: “how r u”; typo group aliases; “send now”; explicit custom words versus appeal; name-only changes preserving caption; “2000 first then 1000” without changing balance; “hold DMs” versus group posting; “Add this as hook reath point”; “only 3 lines”; read-only “show”; test then main target; schedule duplication; “cancel 2nd”; injected transcript commands; uncertain sends; false WhatsApp confirmations; malformed string/dict provider data; long histories; old case facts; compound actions; stale revisions and persisted corrections.

Tests live in test_manual_sends, test_draft_followups, test_draft_workflow, test_schedule_context, test_ai_architecture, test_one_prompt_engine, and test_context_followthrough. Run `python scripts/evaluate_chat_context.py` for a structured offline report. Keep live-model evals in chat_eval separate: simulated model outputs prove control flow and side effects, not that a model will choose the right tool for arbitrary language.

## Baseline and limitations

Before this change the four initial context regressions had one failed assertion and one error: wrong preview kind and rejected contextual save. The expanded regression suite adds persistence, wrong-kind protection, stale-case checks and HTTP execution. Three old one-prompt tests also failed because their model stubs omitted required `with_picture`; the fixtures were corrected without weakening the production schema. Do not count these as intelligence gains.

No weights were trained or fine-tuned. Existing persistent preferences, feedback, archived turns and failure lessons remain; this release repairs retrieval and execution paths. Historical text remains untrusted evidence, not send permission. Unknown recipients, uncertain deliveries, ambiguous times and obsolete case facts must not be guessed. New corrections need human confirmation before becoming standing preferences. Add a minimized redacted transcript and an expected state/tool assertion for each future failure.

The offline pass rate is not a real-world intent-accuracy percentage. Full production history review and an independent live-model holdout evaluation remain necessary. The broader repository has unrelated baseline test failures documented in the cleanup work; this release does not certify the whole application.

The additional manual-send suite initially reproduced the Akhtar/fast routing failure and passes after the repair. New end-to-end coverage uses an actual local HTTP server, fake model responses, and synthetic storage: /assistant → runtime → guarded callback → persisted DM → read-only show. It does not replace a live-model evaluation.


# Update — 3 November 2026 (owner transcript review)

Evidence: the owner's pasted chat transcript, the repository, and offline replays through the real runtime, server callbacks and HTTP endpoint with a scripted model. No live model key was available in this workspace, so model wording and tool choice by the real model remain unmeasured.

## Real failures found in the transcript, with cause and repair

| What the owner saw | Cause | Repair |
| --- | --- | --- |
| "resume group dm's by 11 am" resumed DMs immediately | The donor DM control ignored the time words | A time makes it a scheduled resume; "pause dms for 1 hour" / "hold dms till 11am" stop now and resume then; "stop dms at 11pm" changes nothing and says so |
| "Givelife main today by 11am" failed with "Give a group/action and a future time" | "by 11am" and repeated identical times were rejected; the answer lost the earlier request | One time parser (by/at/till/today/tomorrow, Urdu baje/subah/shaam, ghante baad); a short answer inherits the question it answers |
| Test failed 7 times with "0/10 versions", "caption is empty" | The test send required the full ten-version bank, and an empty caption was an error | A test send no longer needs the bank and fills an empty caption first |
| Chat had no context | Identical notice lines flooded the context window; short replies ("yes", "kar do", "1", "and fiverr") had no permission or meaning | Repeats collapse to one line; a reply is resolved against the question it answers, the numbered option it picks, or the offer it accepts |

## Dangerous misreads found by fuzzing, now fixed

"in an hour", "in half an hour", "kal subah 9 baje", "10 minute baad" and "tonight" posted immediately; "main me mat bhejo", "post nahi karna", "delete mat karo" sent or deleted; "send except upwork" sent to upwork; "the post in main is old", "draft the post", "main post status" sent or re-sent; "remaining 5000 is wrong", "with 4 min gap", "3 came" changed the balance; "dm poster off" stopped DMs; "then rest 20 minutes" became the gap; questions ending in "?" or starting with kya/kitne acted as commands. Each now has a permanent regression test (test_owner_transcript_dm_times, test_mentions_are_not_sends, test_hold_and_delete_need_commands, test_group_wording, test_tool_permission_corpus, test_followup_replies, test_donor_request_wording).

## Limits

The permission layer is still regex based. It now has a 64-phrase positive corpus and several hundred negative look-alikes, but new phrasings will appear. Add each real failure as a minimized phrase to the corpus.

## Suggested next work

1. Run the 20 golden transcripts against the real model with every outbound action mocked and score tool choice, arguments and partial-completion reports (EVALS.md, "Future live-model evaluation").
2. Support a scheduled donor DM batch start ("dm 20 important donors at 8pm"); today the app says plainly that it cannot.
3. Support "stop DMs at 11pm" as a scheduled stop.
4. Replace regex tool gating with a small intent classifier over (current text, last assistant turn, active draft), keeping the regex rules as a veto layer.
5. Show the owner what was understood in one line before any send ("Posting the saved caption to GiveLife main now"), with an undo window for non-delivered jobs.
6. Log every rejected tool call with its phrase so the owner can mark "this should have worked" and the corpus grows from real use.
