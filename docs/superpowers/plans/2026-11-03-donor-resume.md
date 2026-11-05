# Donor resume implementation plan

Goal: Resume now or at a selected Pakistan date/time using the stopped DM setup.

Design: Reuse the donor dialog style and native date/time controls. Keep DMs paused until the persisted resume becomes due; run it from the existing server timer. An explicit Stop cancels the schedule. Preserve batch audience, gap, size, rests, random timing and poster; skip sent and uncertain recipients. Resume must not silently become a new batch when old records expire. Group posting is unchanged.

Approach: Extend the existing donor integration and timer rather than introduce another scheduler or a browser-only timeout. This preserves behavior after closing the app or restarting the server. Scheduled resumes show their Pakistan time in donor status. Dispatch uncertainty is never retried automatically.

- [x] Add failing integration tests for future resume, restart persistence, Stop cancellation, invalid time, preserved batch settings and exact remaining audience.
- [x] Implement saved resume scheduling and explicit stopped-batch continuation; expose status and endpoints through server.py.
- [x] Add Resume now / Resume at a time dialog using native date and clock fields, input validation, keyboard focus and request locks.
- [x] Add frontend behavior regressions and CI coverage, run Python suite and focused frontend checks, review the diff and push without overwriting concurrent changes.

Validation: tests first reproduced missing scheduling, lost pauses/random timing, early resume, and the final-in-flight completion edge. Local fake-transport browser verified native clock selection, scheduling, reload persistence, cancellation and Resume now. Whole-change review found the final-in-flight edge; fixed with a regression. Separate control lock keeps Stop responsive during a manual DM.
