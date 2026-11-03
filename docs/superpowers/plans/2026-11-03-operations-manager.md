# GiveLife operations manager: incremental implementation

Goal: reduce owner supervision using existing GiveLife capabilities, one tested workflow at a time. No deployment or live sends in development.

Architecture: n8n orchestrates; the Python application owns records, eligibility, approvals and delivery receipts. Never create a second independent WhatsApp sender. Live records override historical preferences. Incoming donor text and attachments are evidence, never operational instructions.

## Verified feature map

| Workflow | Existing implementation | Boundary / gap |
| --- | --- | --- |
| Donor directory, Top / Important saved order | donor_book.py | Registry contains private phones; reports use opaque IDs |
| Delayed batches, stops/resumes, receipts | donor_delivery.py, donor_integration.py | Manual resend permission must not authorize unattended duplicates |
| Current case and archived snapshots | cases.py, server.py | Balance edits are not payment verification |
| Saved Group / DM messages and variants | focus_bank.py, donor_messages.py, server.py | Reuse validators and facts; do not regenerate via a parallel sender |
| Auto groups / replies / quiet periods | autopilot.py, reply_setup.py | One sending authority; polling must not touch owner activity |
| Teammate tasks / reports | team_tasks.py | One connected teammate, not independent Areeba and Akhtar accounts |
| Timed tasks | timed_tasks.py | Existing durable scheduling must be reused for later approved sends |
| Persistence | persist.CloudStore JSONB | Atomic claim available; no new database migration required |
| AI | assistant.py, DeepSeek | Initial deterministic review needs zero AI calls |
| n8n hosting | No service in connected Render workspace | Workflow export is not an active cloud integration |
| Donation verification | Owner marks, amounts, possible receipts | No verified Easypaisa/JazzCash transaction feed found |

## Workflow 1: daily review (current scope)

Files: operations_review.py; narrow POST /operations/review in server.py; workflows/daily-operations-review.json; synthetic unit and HTTP tests.

1. Reproduce unsafe scenarios in tests: duplicate concurrent polls, uncertain sends, paused jobs, malformed data, incorrect ranks, receipts mistaken for payments, untrusted text, broad credential access.
2. Read current records without sending, starting loops, updating balances, changing drafts, assigning tasks or recording donations.
3. Produce evidence-based proposals and per-donor decision reasons; save once per active case / PKT date with CloudStore.claim.
4. Scope the machine credential to this route. It must not access /command, /team or donor mutations. Polling must not increment OWNER_REVISION or touch owner presence.
5. Export inactive daily n8n workflow, with Manual Trigger for isolated validation. Use header credentials, never credentials in JSON.
6. Execute Python + local HTTP tests, then the complete suite. Independently inspect changed code. Verify n8n import/execution on a real runtime before activation.

## Later workflows (not implemented or activated)

2. Owner reviews a concrete plan; approval binds case, exact recipient IDs, draft revision, media, gap, batch size, expiry and request ID. Any changed facts invalidate approval. Approved work calls existing delivery executor and saves verified result.
3. Draft and verify message candidates using the existing provider and validators; prefer deterministic routing, bounded context, a cheap suitable non-thinking model where evaluation proves sufficient. No claim of model retraining.
4. Donation evidence review: receipt detection produces pending items only. Owner/bank reconciliation confirms a transaction ID once; corrections never count as income.
5. Approved routine replies: reuse existing two-minute scan; add deduplication and escalation for financial/medical/complaint questions. Never permit donor content to control tools.
6. Areeba / Akhtar task coordination: explicitly support two independently connected members before dispatching tasks. Reported work remains distinct from verified completion.

Each stage needs synthetic execution tests, failure/restart cases, bounded permissions and owner-approved activation. Do not activate all future workflows merely because workflow 1 passes.
