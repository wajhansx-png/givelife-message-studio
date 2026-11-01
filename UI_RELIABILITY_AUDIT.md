# UI reliability audit — 1 November 2026

Scope: Main, Group/DM preview, chat, Donors and its filters/message bank/volunteers, Add/Bulk/Gap forms, campaign poster dialog, Notes, Team, Settings, Memory, keyboard help, and WhatsApp connection.

## Reproduced defects and changes

- A slow script allowed Main to paint before the requested donor tab (6 frames in the regression). An inline startup gate now hides the underlying workspace until the named screen is mounted. A recoverable load failure keeps the same URL.
- Notes and Team had no restorable route. Notes now retains its donor tab and parent navigation across refresh. Team, Memory, keyboard help, Add, Bulk, Gap and Poster screens also have explicit routes. Restoring a route invokes UI opening/read operations only, never sending, logout, upload or save.
- Duplicate popstate/hashchange notifications are coalesced. Unsaved Notes are saved before leaving; a failed save retains the editor and blocks closing. Reload warns while notes remain unsaved.
- Delayed Team/Gap responses could reopen a screen after Back. Current-path/request guards reject stale openers. A Notes navigation epoch is checked before closing, so an older pending save cannot close a newly restored route.
- A delayed Memory response could reopen the dialog after closing. Responses now require the current Memory route.
- Fixed Notes fullscreen-exit toolbar visibility and hidden-editor focus after a late load.
- Fixed invalid switch/tab accessibility states; added arrow/Home/End keyboard support for donor filters, a valid Message bank tab group, an accessible empty volunteer state, and readable donor counts.
- Fixed contrast for the preview Back button and Notes sync status in Light mode. Very narrow phones get a full-width case/balance picker instead of an arrow-only field.
- Added development-only @axe-core/playwright 4.14.0 from dequelabs/axe-core-npm. Existing UI UX Pro Max, Frontend Design and Web Design Guidelines informed the review. No new production UI framework or API key.

## Verification

37 distinct browser tests passed after fixes across the combined runs. The final self-contained suite passed 19/19 and exited cleanly, including starting and shutting down its isolated fake server.

Dark-theme accessibility/layout checks: 1440, 768, 390 and 320px. Light-theme/form checks: 1440 and 390px. Tests include route restoration, delayed scripts/responses, browser Back/Forward, unlock, chat autoscroll, Notes formatting/autosave/fullscreen, simulated keyboard resizing and reduced motion. Inspected rendered screenshots of Main, donor lists, message bank, chat and Team. No critical/serious axe findings remained in the scanned screen states. This is bounded automated evidence, not a whole-product WCAG certification.

JavaScript syntax checks passed for changed scripts; the fake preview Python file compiled. Two older browser tests were updated: Notes should now restore itself after reload; a Team error-display test now supplies a controlled API error instead of assuming deadlines are mandatory.

Run: `pnpm exec playwright test -c playwright.ui-audit.config.cjs ui_reliability delayed_navigation foundation_notes`. The config starts a temporary preview, clears production database/AI environment variables, and uses fake WhatsApp transport. For an already-running isolated preview on port 3055, set GIVELIFE_UI_EXISTING=1. No production messages or donor/payment mutations were exercised.

## Limits

Actual Android/iOS keyboard and physical-device gestures were not tested; browser viewports/touch events were simulated. Live production login, WhatsApp delivery, backend financial logic, Group Finder research and model answer quality were outside this UI pass. Not every content combination, browser extension or device can be certified error-free. Existing case text, donor data and sending policies were preserved.
