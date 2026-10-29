# UI smoothness verification — 29 October 2026

## Scope

Based on published GitHub main `70e4c75`. This release changes frontend navigation, motion, reading space and focused test infrastructure only. No AI, scheduler, outbound messaging, donation or database logic is changed. Earlier unpublished logic work remains separate.

## Changes

- Close controls return synchronously to a validated parent route. They no longer queue a delayed browser Back operation that can race the next tap or refresh.
- Browser Back/Forward and direct hash changes render the corresponding screen. Closing a refreshed overlay also visibly restores its Preview parent.
- Refresh restores Donors and its selected filter/Messages panel immediately, without flashing the default filter while data loads. Existing selected-message persistence is retained.
- Route restoration waits for the access form to close. The WhatsApp connection screen is now addressable and refreshable; restoring it only checks status, never reconnects or sends automatically.
- After an explicit chat submission finishes or fails, the latest response is revealed even when the user was reading older turns. This does not move focus back to the input or trigger another request.
- Short interruptible opacity fades follow screen changes. State changes run immediately; there is no animation wait before requests. Reduced-motion settings disable motion.
- Reply text no longer waits through staggered line reveals. Continuous decorative animation is stopped to reduce unnecessary rendering work.
- Desktop quick actions move below the reply near the composer. The group panel is 248–288 px wide, reclaiming space for the answer while retaining every group action and receipt label. Mobile controls and existing colors/icon locations remain intact.

## Actual checks

- `tests/e2e/smoothness.spec.cjs`: all 11 cases passed, in a final 10-case run plus the separately added Back/Forward case. Synthetic data and fake WhatsApp only.
- The cases include explicit-send scrolling while reading history, an extra scroll while awaiting a reply, unlock/restoration, WhatsApp refresh, reduced motion, each donor filter and Messages after refresh, rapid Close/open sequences, and Preview-parent restoration.
- Tested navigation at 1280×720, 1024×600, 390×700 and 320×568; inspected actual desktop and mobile screenshots.
- All 11 existing JavaScript check suites passed: connection, dashboard defaults, desktop navigation, draft loading, next actions, reading receipts, UI behavior, donor feedback, donor state, design system and reply renderer.
- JavaScript syntax checks and `git diff --check` passed.
- The local preview now permits a larger connection backlog; the default Python backlog caused concurrent asset requests to be refused on Windows during rapid reload checks. An optional `GIVELIFE_TEST_PORT` avoids clashes with another local preview. Neither changes production HTTP behavior.

## Limits and earlier failures

An earlier broad pre-final browser run was 33/45, with connection/time-out failures and saved-message editing failures. That entire suite was not certified by this focused release. Its failures are retained as follow-up evidence rather than silently presented as passing.

Physical Android keyboard behavior is not certified by Chromium viewport emulation. Very long replies still scroll accessibly; their content is not shortened. API response time and delivery decisions are unchanged. No real messages, donations or paid model calls were triggered by these tests.
