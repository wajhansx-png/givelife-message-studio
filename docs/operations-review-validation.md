# Workflow 1 validation — 3 November 2026

## Actual results

- Full Python suite: **839 tests, passed, 1 skipped**, 82.151 seconds. The existing suite emits temporary-directory ResourceWarnings. No live donor, payment, AI or WhatsApp service used.
- New review tests: **18 passed** in the final focused run. Cover independent rankings, sent/unconfirmed/reserved recipients, duplicate IDs/phones/ranks, opt-outs, interrupted batches, holds, closed cases, invalid financial values, missing drafts, durable-claim concurrency, PKT midnight, repeated review calls, interrupted claims, database failures, untrusted text, privacy and inactive workflow configuration. The full-suite run above preceded the last added duplicate/missing-rank test; no production code changed afterward.
- New real local HTTP tests: **4 passed**. Verify review execution, saved repeat results, credential isolation from donor/team/campaign/send endpoints, malformed requests, foreign origins, database error redaction, and no owner-presence or revision mutation.
- Compilation: operations_review.py, server.py, chat_memory.py passed Python compilation.
- Git whitespace check passed.
- Independent code review identified a case transition race. A regression reproduced new case data being readable before cases.current changed. Collection now shares the existing Cases.lock; the regression passes.
- A new credential-redaction regression initially failed, then passed after extending existing chat/outbound credential guards to OPERATIONS_REVIEW_KEY.
- Initial feature test failed before operations_review.py existed; implementation followed that failing test. No claim that all historical app problems were fixed by this workflow.

## Evidence boundaries

- Durable claim concurrency was exercised with eight simultaneous requests and a locked synthetic store. CloudStore.claim's existing PostgreSQL INSERT ... ON CONFLICT primitive was inspected; a live PostgreSQL restart/multi-process test was not run.
- The workflow JSON was structurally tested; **n8n import and execution were not run**. No local n8n runtime, Docker or connected n8n service was found. The npm registry reported n8n 2.46.4 requires Node >=24; local Node is 24.22.1. Local C: free space fell below 1 GB, so no large runtime install was attempted.
- Render service inventory was read only. The approved workspace has GiveLife and proposal-studio, no n8n service. Main auto-deploys; this work remains isolated from main and is not deployed.
- No UI was changed, so no new visual/browser verification is claimed.
- No real outbound send, payment verification, staff assignment, schedule activation, provider evaluation, cloud scheduler execution or automatic owner alert has been verified or activated by this change.
