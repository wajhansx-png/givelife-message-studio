# Pasted donor batch review

`DonorIntegration.pasted.preview(text)` accepts 1–20 nonempty lines with one name and phone per line, in either order. Common separators, local Pakistani numbers, international prefixes, spaces, parentheses, hyphens, and periods are accepted. It returns `{token, names, count, duplicates, warnings, expires_in}` without phone numbers. Duplicate numbers retain the first pasted name. Invalid lines, own-account numbers, or oversized input reject the entire preview. Preview does not save contacts.

`DonorIntegration.pasted.start(token, gap_seconds=240, request_id=..., poster=True)` returns `{job, reply, saved: {added, duplicates}}`. Gaps must be 60–600 seconds. Request IDs must contain 8–100 letters, digits, underscores, or hyphens. Prepared data stays in memory for 10 minutes, with at most 50 entries; restart, expiry, or eviction requires a new preview.

Start atomically adds valid contacts through `DonorBook.add_contacts`, then starts the existing delivery worker. **Contacts remain saved if the subsequent delivery start fails**, such as when disconnected, another batch is running, or insufficient distinct saved messages exist. Failed/uncertain starts consume the preview and are not automatically retried. An identical successful request returns its tracked result; changed options require a new preview.

Pasted order is restored after registry selection. Batch-specific personal names are snapshotted privately, excluded from public job/status responses, and cleared from the stored job after completion. Existing donor names and metadata remain intact. Public receipt names use registry labels. Clean explicitly supplied personal names may personalize this batch; account/business/random labels retain the Brother fallback, and recognized female names use Sister.

Existing dispatch checks remain active: own account, opt-outs, blocked or uncertain recipients, deletion, hold, first immediate send, chosen spacing, cancellation, and no automatic replay after an uncertain send or restart. Distinct saved wording is required per recipient. Donor edits forward optional `expected_updated_at` while preserving the editable-field whitelist.

Verification: 13 focused pasted-donor tests pass with fake delivery callbacks and mocked outbound calls. No live WhatsApp messages were sent. Earlier full-suite audit failures were reported separately while server audit fixes were still being integrated.

