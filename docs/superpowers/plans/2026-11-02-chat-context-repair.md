# Chat context repair

1. Reproduce supplied transcript failures using synthetic state and the real runtime/server guards. Keep historical instructions as data, never fresh authorization.
2. Unify active draft resolution and follow-up edit permissions in draft_flow, runtime and server callbacks. Verify explicit scope wins and short follow-ups preserve the existing target.
3. Retrieve relevant owner context for short requests, preserving provenance and current-case boundaries. Keep live schedules and receipts authoritative.
4. Review correction memory for stale or conflicting retrieval; persist only explicit preferences, not inferred payments or recipients.
5. Add a transcript regression catalogue and isolated replay suite. Test malformed provider responses, injection, long histories, interruptions and real callback execution. Label model-stub tests honestly.
6. Run focused suites, then broader regressions; record baseline failures separately. Publish only verified chat changes, preserving pending cleanup work.

No real WhatsApp sends, donations, or production writes in tests. No model retraining claims. Live model testing, if available, uses simulated tools only.
