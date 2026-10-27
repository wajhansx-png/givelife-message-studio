# GiveLife logic audit, 27 October 2026

This release fixes execution paths, permission checks, request context and tool outcomes. It does not retrain the model or promise error-free AI.

## Reproduced failures and fixes

- A year/group count before the balance could be used as money: `send all 6 groups with 25k left` parsed 6. Amount extraction now binds the number to balance wording; conflicting balances require clarification.
- A group alias inside an outgoing sentence could become its destination: `send all the best to Ali`. Literal text and its recipient are resolved before alias scanning, with a matching server permission check.
- Future/negated actions and hypothetical questions could reach the immediate path. Shared intent checks now distinguish these from current commands, preserve quoted text, and block unauthorized mutations.
- Combined edit/send or donation/send instructions could take a shortcut that skipped the first part. These now use the ordered tool workflow, with edit-before-send and failure dependencies retained.
- A status request incremented the owner revision and applied destination options. It could cancel pending work or retarget a draft. Read-only status no longer does either; new edits, sends and cancellation instructions still supersede older work.
- Concurrent chat requests shared an image slot. Attachments are now scoped to the request thread, so a status question cannot replace an in-flight picture.
- Direct wording corrections left a custom task hash stale, losing its poster/recipient context. The task is revised with the caption; donation-option reordering preserves unrelated lines and a short caption's line layout.
- Model-selected deletion targets, Auto switch values and group pace arguments could disagree with the owner. Server checks now validate the destination, direction and known interval against the current instruction. Oversized donations and empty/inconsistent-balance captions are rejected.
- Empty contact lookups could verify a recipient accidentally. An empty search no longer grants sending permission.
- Tool arguments were checked sequentially. Every proposed tool batch is now schema-checked before any member executes; invalid batches run no partial action.
- Error-shaped/empty tool results could be called completed. Result validation now rejects these, including failed lookups before dependent sends. Passive unsupported completion claims are also checked.
- A timed-out donation mutation could be attempted again. Financial/deletion uncertainty now terminates the turn; the owner must inspect current state rather than risk a duplicate mutation.
- Malformed WhatsApp metadata/status/message containers could raise `.get` errors. Boundary normalization produces safe failure/unknown results. Malformed hold data fails closed. Tests cannot accidentally call the configured WhatsApp service: their transport URL is isolated.
- A small bare number such as `2` could become a balance. Small choices need money wording to change funds. Recent numbered draft proposals enable only the caption edit for that choice, preserving the same draft; no money/send/Auto tool is granted. Unrelated or missing choices need clarification.

## Verification

- 219 Python tests passed, including 37 new deep-audit regression tests and concurrent-request tests.
- Seven existing Node UI suites passed; JavaScript syntax and Python compilation checks passed.
- Fake transports only: no real WhatsApp messages were sent for testing.
- Existing coverage includes restarts, scheduling, persisted memory/corrections, quotes and prompt injections, contact ambiguity, stale actions, duplicates, uncertain delivery, formatting, draft/test/send continuity and UI action locks.
- The in-app isolated AI checks now include a numbered-hook follow-up alongside drafting, short hadith/test/main flow, greeting, contact typo, name correction, multiple instructions and prompt-injection checks. These call the configured model with fake action tools, not WhatsApp.

## Limits

Natural-language interpretation and newly generated prose can still be wrong. The checks prevent the reproduced failure classes, not every possible mistake. No physical model retraining happened. Clear short commands use deterministic routes; complex edits can require several model calls and cannot be guaranteed within one second. Network/provider failures, free-host sleeping and missing/uncertain delivery receipts remain external limits. One-time schedules remain subject to cloud availability. This release preserves the UI, stored captions, balance, credentials, recipient data and existing Auto settings during deployment.
