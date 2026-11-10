# New studio control audit — 10 November 2026

The automated audit opens 46 screen states at 13 viewport sizes: **598 state checks, 7,362 control observations and 20,602 rendered-element observations**, with no recorded layout failures in the final combined inventory. Reviewed base: `ec8da4b` (including Thank donors and the new desktop DM controls). Counts repeat controls across states and sizes; they are not unique buttons.

## Viewports

280×480, 320×480, 390×844, 430×932, 568×320, 667×375, 768×1024, 899×700, 900×700, 1024×768, 1280×800, 1440×900 and 1920×1080. These include portrait, short landscape, tablet and the two sides of the 900px breakpoint.

## Opened states

Home; Preview; Chat; Notes unlocked and locked; Settings; Memory; Poster; Keyboard; WhatsApp connection; Donors All, Important, Top, Donated, Not messaged, Volunteers and Messages; donor Add, Paste and Speed; group choice and scheduling; advanced speed options; manual messages; Save Base confirmation; resume groups; home More; Preview three-dot menu; message editor; donor header More; donor row More; donor search; Follow-up; DM editor; DM menu; Case Writer; Report; Reply; Group Finder, its Import dialog and university targets; Thank donors composer, pace options, preview, recipients and media caption.

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
- Give Thank donors the central phone action slot so its label fits; keep its actions outside a scrolling composer so the footer cannot cover pace or recipient controls.

## Reproduce

```sh
pnpm exec playwright install chromium
pnpm test:e2e:controls
# Fast focused rerun (optional):
CONTROL_STATES=donated,thanks-pace pnpm test:e2e:controls
```

Use the project Python requirements and Node dependencies first. The Playwright configuration launches `tests/preview_fake.py --donors --test-api --fake-ai`; these checks use synthetic records and do not send real WhatsApp messages. There are no Claude/model API calls in this audit. CI runs it as an independent job and retains control inventories and failure traces.

## Evidence and limits

[Per-viewport counts](nov10-controls/matrix.json). Against `ec8da4b`, the integrated run passed 31 tests and identified failures at three short/narrow sizes in the newly added Thank donors flow. The failed states were fixed and rechecked: all five Thank donors states passed at all 13 sizes, and the Donated action button passed at all 13 sizes. The final combined inventory covers all 598 listed state/size pairs without failures. This is a combined inventory from the full run and scoped reruns, not a claim that the initial integrated run passed unchanged.

All 20 existing Report, desktop DM action and Thank donors functional tests passed in the integrated run. The timed Report/Reply regression passed. Formatting and `git diff --check` passed. The default CI command runs the entire matrix from scratch; `CONTROL_STATES` is only an optional local speed-up.

The earlier base `5aaa1a1` passed all 14 control tests and 10 Report layout tests before the new feature merge. The existing new-studio suite had also passed 85 cases after the initial CSS fixes. During the deeper audit, checking the real locked-Notes state exposed a hidden-workspace CSS override; failure screenshots identified Report's delayed restore covering Reply. Both fixes are retained.

The matrix is a finite Chromium layout check, not a claim to cover every possible width, all nested application states, all business outcomes, Safari/Firefox, physical-device keyboards or the deployed production account. Opening each listed surface and checking control reachability does not activate every action. Functional sending coverage uses the existing fake-transport suites. Production was not deployed by this change.

The review server is local to the cloud executor. This chat exposes no Desktop opener, and `sites-preview status` reports an unavailable relay, so its loopback URL is not a usable live preview on the user's computer.

## Screenshots (synthetic test data)

[Desktop home](nov10-controls/desktop-home.png) · [Phone Preview menu](nov10-controls/phone-reader-menu.png) · [Landscape donor menu](nov10-controls/landscape-donor-menu.png) · [Phone Follow-up](nov10-controls/phone-follow-up.png)
