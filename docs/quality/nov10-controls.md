# New studio control audit — 10 November 2026

The automated audit opens 41 screen states at 13 viewport sizes: **533 state checks, 6,776 control observations and 18,537 rendered-element observations**, with no recorded layout failures after fixes. Reviewed base: `5aaa1a1` (main including the Donors/Volunteers header update). Counts repeat controls across states and sizes; they are not unique buttons.

## Viewports

280×480, 320×480, 390×844, 430×932, 568×320, 667×375, 768×1024, 899×700, 900×700, 1024×768, 1280×800, 1440×900 and 1920×1080. These include portrait, short landscape, tablet and the two sides of the 900px breakpoint.

## Opened states

Home; Preview; Chat; Notes unlocked and locked; Settings; Memory; Poster; Keyboard; WhatsApp connection; Donors All, Important, Top, Donated, Not messaged, Volunteers and Messages; donor Add, Paste and Speed; group choice and scheduling; advanced speed options; manual messages; Save Base confirmation; resume groups; home More; Preview three-dot menu; message editor; donor header More; donor row More; donor search; Follow-up; DM editor; DM menu; Case Writer; Report; Reply; Group Finder, its Import dialog and university targets.

The test inventories every visible control within each listed surface. It scrolls controls into view, then checks horizontal clipping, label overflow, minimum 24px targets, hit-test reachability, rendered-element clipping, page overflow and JavaScript exceptions. It waits for Reply data and Notes unlock to finish before measuring.

## Fixed failures

- Wrap Notes formatting tools on very narrow phones; ensure the workspace actually disappears when Notes is locked.
- Keep the Preview three-dot menu inside the phone viewport and scroll its contents when the screen is short.
- Keep Next/Regenerate above the phone action dock in landscape; hide them while editing.
- Let opened donor row menus escape row rendering containment; use a viewport panel on short phones.
- Hide covered donor tabs while phone search is expanded.
- Keep Follow-up fields separate from the DM-only reader and actions.
- Keep Reply actions in flow so they do not cover Add on short screens.
- Prevent the remembered Report from reopening over a dialog the user has just opened. A deterministic browser-clock regression checks this case.
- Fit the Messages Back label on narrow phones and the amount chip near the desktop breakpoint.

## Reproduce

```sh
pnpm exec playwright install chromium
pnpm test:e2e:controls
```

Use the project Python requirements and Node dependencies first. The Playwright configuration launches `tests/preview_fake.py --donors --test-api --fake-ai`; these checks use synthetic records and do not send real WhatsApp messages. There are no Claude/model API calls in this audit. CI runs it as an independent job and retains control inventories and failure traces.

## Evidence and limits

[Per-viewport counts](nov10-controls/matrix.json). The final run passed **all 14 control tests** in 3.5 minutes: 13 complete viewport matrices and the timed Report/Reply regression. All 10 existing Report layout tests also passed after the Report change. Formatting and `git diff --check` passed.

The existing new-studio suite passed 85 cases after the initial CSS fixes. Before the fixes, 110 existing new-studio, Report, Volunteer and Case Writer tests passed, demonstrating why the additional geometry audit was needed. During the deeper audit, checking the real locked-Notes state exposed a hidden-workspace CSS override; failure screenshots also identified Report's delayed restore covering Reply. The final run includes both fixes.

The matrix is a finite Chromium layout check, not a claim to cover every possible width, all nested application states, all business outcomes, Safari/Firefox, physical-device keyboards or the deployed production account. Opening each listed surface and checking control reachability does not activate every action. Functional sending coverage uses the existing fake-transport suites. Production was not deployed by this change.

The review server is local to the cloud executor. This chat exposes no Desktop opener, and `sites-preview status` reports an unavailable relay, so its loopback URL is not a usable live preview on the user's computer.

## Screenshots (synthetic test data)

[Desktop home](nov10-controls/desktop-home.png) · [Phone Preview menu](nov10-controls/phone-reader-menu.png) · [Landscape donor menu](nov10-controls/landscape-donor-menu.png) · [Phone Follow-up](nov10-controls/phone-follow-up.png)
