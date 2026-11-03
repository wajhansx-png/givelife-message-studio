# Daily operations review

This first workflow saves a daily plan. It does not send, schedule sends, enable Auto, change messages, verify money or assign tasks. It costs no AI tokens. Existing campaigns, messages and delivery logic are unchanged.

## Activation checklist (not performed)

1. Finish tests and inspect this branch before merging. The existing Render service auto-deploys main; pushing main is a deployment.
2. Set a new random OPERATIONS_REVIEW_KEY of at least 32 characters in the GiveLife server's secure environment settings. Do not reuse UI_ACCESS_KEY. Keep the key in an n8n Header Auth credential: header Authorization, value Bearer followed by the key. Never commit or put it in a chat.
3. On an existing durable n8n server, import workflows/daily-operations-review.json. It is inactive. Set the HTTP URL to the deployed GiveLife /operations/review endpoint and select the header credential.
4. Execute the Manual Trigger against an isolated synthetic test app/database first. Inspect the saved review and confirm no WhatsApp traffic or donor/campaign mutations. JSON validation alone is not an n8n runtime test.
5. Inspect/approve the deployment and actual runtime result before publishing the workflow. The suggested time is 9 AM Asia/Karachi, editable in the Schedule Trigger. This is an inactive default, not an owner-created task deadline.
6. Configure n8n execution-failure alerts to an owner-approved destination. No alert destination is currently configured. Until configured, failures appear only in n8n execution history.

Official references: [Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/), [server CLI](https://docs.n8n.io/deploy/host-n8n/configure-n8n/use-the-command-line/).

## Contract

POST /operations/review with JSON {}. Requires the scoped review key or existing owner key. A scoped key cannot use other API endpoints. No provider calls, external URL fetches or message tools are reachable from the review.

200: state ready_for_review, report, day, case_id, created_at, duplicate. A repeat returns the previously saved report with duplicate true. Its created_at is the evidence timestamp; it is not a live monitor. A new case or PKT day creates a separate review.

409: an earlier review claimed the occurrence but did not finish. Inspect it; no automatic replay. 503: storage or input records failed validation. No success is claimed. An interrupted record is retained for inspection.

Audit records are stored as operations_review:<PKT-date>:<case-id-hash> using the existing durable CloudStore. No donor phones, raw chat history, attachments, credentials or arbitrary staff text are copied into the report. IDs remain sensitive operational metadata and require authentication. Existing rankings are read without normalization or writes.

Do not use a stale report to execute sends. A later approval executor must re-check recipients, holds, opt-outs, case facts, reservations, exact content and confirmed delivery history immediately before sending.

## Known limits

- No n8n service is connected in the approved Render workspace. Export generation does not make this run daily or with the laptop off.
- n8n is not installed locally; real import/execution remains unverified. Node 24.22.1 matches the registry's n8n 2.46.4 requirement (Node >=24), but only about 1.5 GB disk space remained during the audit; no large runtime install was attempted.
- The current free Render web service is not a proven always-on scheduler. Reliable laptop-off operations need an independently running n8n host with durable storage, credentials and failure monitoring.
- Only the current case is reviewed. Other cases remain archived; no archive is activated.
- Eligibility here is deliberately conservative: previous sent/unconfirmed/reserved records are excluded. This does not remove the owner's existing deliberate resend functionality.
- Group status reports pauses and last confirmed send only, not invented next times or a claimed WhatsApp connection check.
- Case snapshots share the existing case-transition lock in the current single-process app. This is not a cross-process database transaction or a guarantee for a future multi-worker deployment; revalidate that architecture before scaling.
- Saved draft readiness means non-empty text, not fresh content validation or guaranteed generation of ten unique variants.
- Owner-recorded donation amounts and possible receipts are separate; neither is claimed bank-verified.
- The teammate API supports one connected member. The plan flags missing Areeba/Akhtar connections rather than replacing the current teammate.
- Daily reports currently have no UI, approval executor, retention policy or automatic owner notification. They are available to authenticated workflow executions and stored audit records. Add these in the next approved workflow, not by calling existing send tools from n8n.
