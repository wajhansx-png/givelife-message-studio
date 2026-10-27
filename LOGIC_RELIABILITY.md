# Chat logic reliability, 27 October 2026

This change strengthens the current Python/DeepSeek architecture; it does not retrain the model or change campaign captions.

- Preview, show, draft and review requests cannot authorize immediate sends. They bypass the direct command sender. Reading schedules remains available.
- Single-quoted commands are treated as data; apostrophes in ordinary instructions are preserved.
- Group exclusions are resolved before aggregate groups expand. Both direct commands and AI callbacks enforce the resulting list. Contact lookup cannot re-authorize an excluded group. Empty or unclear exclusions require a clear recipient instead of falling back to the previous group.
- Retrieved context accepts legacy JSON-text lists, ignores malformed records and copies entries before truncating them. Preparing a model request no longer modifies the memory supplied to it.
- Malformed tool-call collections, mixed valid/invalid calls and duplicate IDs are rejected before any tool in that response executes.
- A read-only lookup does not justify a new completion claim. Unsupported first-person or standalone completion claims are replaced with an honest lack-of-confirmation response.
- Model/API failures return a structured reply and diagnostics. Already completed edits remain reported if the next model call fails. Successful argument repair clears the obsolete error for that tool.

Validation: 151 Python tests passed, including 17 new regression tests. All three JavaScript suites passed (UI behavior, draft-loading gate, connection refresh). The Python suite uses isolated state, mocked model responses and fake WhatsApp transports. No real messages were sent by these tests. No live-model evaluation was run in this change, so natural-language accuracy remains model-dependent. Complex preview-and-send requests beginning with preview/review are deliberately conservative and require a separate explicit send instruction. Existing uncertain-send protection, stale-instruction guards, scheduling, DM composition and timers remain covered by the suite.
