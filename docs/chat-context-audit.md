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
