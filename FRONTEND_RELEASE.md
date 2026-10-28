# Fitted reading and pasted donor DMs

- Fixed-height desktop workspace; composer occupies a separate row and cannot cover the reply.
- Saved captions fit on desktop and phone layouts by adjusting display type/spacing only. Caption bytes and paragraph breaks sent to WhatsApp are unchanged.
- Mobile preview uses the screen for reading; Main returns to all sending controls in one tap. Extremely long content retains scrolling rather than being clipped or reduced below readable limits.
- Revised violet/neutral palette with amber for Important and explicit text labels for statuses. Both themes retain AA text/control contrast checks.
- DM → Send to more donors: paste up to 20 number/name lines (either order), preview names with numbers hidden, choose 1–10 minute gap. First sends immediately, then the selected gap. Existing caps, exclusions and uncertain-send protections remain.
- New contacts are saved only when starting. Existing donor metadata is preserved. Starting can save contacts before a later connection/cap failure; the UI explains that and never automatically retries.
- Repeated pasted clicks use one prepared token; batch captions vary and personalized names are snapshot privately in pasted order.
- Donor update version checks prevent stale browser edits overwriting newer values.

Verified: eight real-browser Playwright tests with fake WhatsApp; ten existing Node UI suites; four Vitest suites/properties (40 monetary cases, 20 phone cases across three formats, 25 duplicate-import cases, 200 arbitrary formatting inputs). Full local Python suite includes additional financial audit work; that financial work is deliberately not in this frontend release.

Test tools are development-only; Chromium and dependencies installed locally. Superpowers 7.0.1 verified installed during work. No runtime framework migration. No real donors/payments/outbound WhatsApp/Auto loops used for tests.

Separate local audit remains in BACKEND_AUDIT.md: financial request replay, whole-rupee validation and malformed-request cancellation fixes require their own production review. No financial ledger, recurring-donation model, multiple-case accounting, role-based user accounts or business-agent assignments exists in this repository.

