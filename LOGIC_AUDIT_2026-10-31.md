# GiveLife V1 — AI/chat reliability audit (31 October 2026)

## Evidence and limits

This audit covers the connected GitHub source code, existing automated tests,
workflow logs, and **examples the owner supplied in ChatGPT**. The private live
GiveLife chat archive was **not** directly accessible through the connected
browser (browser context unavailable); Render workspace selection was unavailable.
The app has an internal, retained-archive history-review path, but it has not
been validated against the actual full production archive in this review.
**Do not treat the case counts below as production failure rates.**

## Recurring failure patterns and engineering response

| Severity | User-reported behavior | Underlying failure mode | Code / test approach |
|---|---|---|---|
| Critical | Claimed WhatsApp confirmation when no action was verified | Incomplete completion-claim detection and bad branch ordering | `chat_runtime.py`: recognize varied claimed-success wording, require tool receipt; tested with mocked assistant |
| Critical | Historical or invented medical details survived corrections | Assistant output ranked as history evidence; stale case context | `chat_memory.py`: owner-first retrieval, old AI answers read-only on explicit request; case isolation regression tests |
| High | Asked for future recommendations, got today's Rs. 0 / Auto off recap | History-review intent failures, latest-state bias, insufficient retrospection | `conversation_insights.py`, `server.py`, `chat_runtime.py`: summarize retained owner turns and owner-reported corrections; use a read-only history-review path |
| High | “Analyze past conversations” ignored | Rigid lexical match omitted plural “conversations” and spelling variants | Normalized history intent, golden regressions |
| High | “Fix that last line” failed to edit the active caption | Referent from prior turn not connected to permitted edit tool | `chat_runtime.py`: context-scoped draft edit only; explicitly no send permission |
| High | Two steps in one prompt; later steps not completed | Single-action shortcut and incomplete action tracking | `task_intent.py` plus mocked multi-step execution tests |
| High | Named teammate or exact message went to wrong/no recipient | Recipient resolution and exact-text fidelity ambiguity | Existing verified-contact and per-recipient text tests; do not infer unknown contacts |
| High | “Hold evverything”/“Post every 15 min” behaved unexpectedly | Generic AI handler and imperative-versus-setting confusion | Direct global hold and explicit scheduling semantics; fake-transport tests |
| Medium | Repeated app complaints not learned from | Owner complaints stored only on narrow trigger words | Save reviewable failures, not auto-enforced rules; aggregate tool-error categories privately |
| Medium | Long generated advice with irrelevant status | No separation of retrospective strategy from operational status | History review relevance checks and compact, evidence-based suggestions |
| Medium | Chat message columns and unreadable dropdown | Excessive fit-to-viewport styling and missing native theme | Existing UI work; separate browser tests |

## GitHub evaluation framework

- **Promptfoo** — selected for an offline, low-cost golden test runner, custom
  Python provider and CI gate. Its current test provider calls the app's actual
  intent/permission modules with synthetic state. This is not a live DeepSeek
  correctness score.
- **DeepEval** — evaluated for future optional agent tool-accuracy, trajectory
  and multi-turn faithfulness assessments. Not installed in production because
  it could add dependencies, model cost, and private-trace exposure.

The dataset `tests/evals/goldens.json` contains **20 sanitized checks**, a
mix of user-reported failures and synthetic negatives. It contains **no
production chat export**. The first complete Promptfoo gate passed 20/20 after
a test-detected history-routing bug was repaired.

## Remaining risks (not certified fixed)

1. In-memory or temporary-job state can be interrupted by app restarts;
   uncertain sends must not be automatically repeated.
2. Current Render deployment SHA is not verified against GitHub head.
3. End-to-end quality of the **live DeepSeek model** has not been measured on
   a private held-out corpus. Green deterministic policy tests alone do not
   show real semantic accuracy.
4. The complete private chat history was not accessible. Owner-approved,
   anonymized export/analysis would be needed for real per-category failure
   counts and time trends.
5. A production hosting tier with uninterrupted workers and a durable queue is
   needed before promising reliable recurring automation.
6. Browser/UI regression completion must be checked separately. No active
   donor, volunteer, group or patient should receive a test message.

## Suggested release gates

- All security and tool-intent cases pass.
- Zero known false delivery confirmations or unconsented recipients.
- Mocked multi-action scenarios report confirmed/uncertain/not-attempted
  independently and preserve explicit recipient text.
- Browser tests pass at narrow phones, common mobile widths, and desktop.
- Review the owner correction dataset after anonymization, test model
  trajectories several times, and manually sign off on high-risk actions.
- Record error rates and new confirmed failures; add a golden for each distinct
  root cause. Never promise a perfect or self-trained model merely because
  tests pass.

## What was not done

No real WhatsApp messages were sent, no Auto posting was enabled, no donor
records were changed, and no private chat transcript was copied to GitHub.
