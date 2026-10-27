# GiveLife UI verification, 27 October 2026

## User flow

Open the dashboard, find the current caption and connection/activity state, send to a known group, or open Chat. On mobile: type, Send, input loses focus immediately, the reply appears, and Main returns to the dashboard without losing the next draft or reading position. Sending tests use a fake WhatsApp service, never real recipients.

## Changes

- Removed the Suggestions dashboard block and its polling/one-click actions.
- Stable desktop columns; focusing chat no longer resizes the layout or shrinks send targets.
- Mobile GiveLife main and Chat sit on the right near the thumb. Main/Test are one tap; individual groups and all-group sends are two taps. Broad sends are disclosed inside Other groups.
- Removed the repeated header theme button and pace decoration. Appearance remains in Settings. Copy/Hide live under the caption overflow menu; technical AI checks are collapsed in Settings.
- At the owner’s latest request, mobile previews start at 14px and shrink to 10px only as needed to fit the full caption. Editing remains 16px on mobile and desktop previews remain 17px. Exceptionally long captions retain an internal scroll fallback. Group and DM preview positions are remembered separately. Caption text, formatter, donor restrictions and existing template rotation are preserved.
- Editing requires the explicit Edit action. Scrolling or tapping the preview no longer accidentally edits and saves the caption.
- Chat uses one system font, a compact growing input, separate attachment control, and a 56×56px Send target. Android-oriented handling blurs input synchronously before awaiting the action. Opening/closing chat or receiving replies never focuses the input automatically. Composition Enter is protected.
- Dedicated mobile Main row above the input, at the right. Desktop expanded chat has Main in its header.
- Shared unsent chat draft persists locally across switching/reloading. Conversations remain server-backed. Reading position survives returning to Main; reading older content is preserved when new replies arrive, with a conditional Latest reply shortcut. Long new replies show their beginning instead of jumping to their final paragraph. Removed simulated word-by-word reveal.
- Live balance and saved captions refresh together after background donations. Open edits, unsaved drafts and newer command results are protected against stale polls. Auto shows a loading state until the server confirms ON/OFF.
- One small real status strip shows Auto, current server/manual activity, check age, recent confirmed outcomes, and critical connection/send errors. Checked age comes from a successful server response. No simulated monitoring animation. Details remain available on tap. Screen readers receive new replies/errors rather than the clock every second.
- Pending per-action locks prevent rapid repeated sends. Locks remain until a group job receipt finishes; other destinations retain the existing manual preemption behavior. No automatic retry of uncertain sends was added.
- Campaign status keeps checking while idle, so batches started through chat become visible with Stop. Refreshes coalesce; stop failures surface safely. Scheduled cloud sends and hold states remain visible even when Auto is off.

## Screens reviewed

Group dashboard, DM form, caption editing/actions, chat/full-screen chat, campaign progress and Stop, Settings/appearance, AI diagnostics, memory review/correction, and WhatsApp connection/unlock/reconnect/logout. This repository has no separate donor-management or campaign-editor pages; those workflows use chat and the DM form. The separate DonorHub site was not changed.

## Evidence

| Boundary | Result |
|---|---|
| Responsive dashboard | Browser viewport checks at 360×740, 390×844, 430×932, 1024×768 and 1440×900: no horizontal or outer-document overflow |
| Reduced chat space | 390×480: Send 56×56, approximately 18px bottom clearance, no input overlap; Main above input |
| Send → reply | Browser input focus is BODY after Send; latest short reply is inside the log's visible bounds |
| Draft and reading position | Browser verified unsent draft survives Main → Chat; an older reading position restored to the same scroll offset |
| Long reply | 30-paragraph simulated reply remains readable; navigation/input remain accessible |
| Group send → API → transport → receipt | Fake service captured one poster+full-caption request; UI showed pending disabled state, confirmed result, then unlocked |
| DM form | Fake service received full formatted caption with Brother fallback for Jr Accounts; no greeting-only payload |
| Other screens | Group selector, Settings/appearance, memory review and return navigation inspected in browser; existing connection race and caption loading tests pass |

Commands run:

```
python -m unittest discover -s tests -q
node tests/test_connection.js
node tests/test_draft_loading.js
node tests/test_ui_behavior.js
node --check app.js
git diff --check
```

All 134 Python tests and all three Node test scripts pass. The new UI script covers synchronous blur, no automatic focus, draft persistence, blank input, desktop focus, viewport offsets, Main navigation, action locks, duplicate requests, receipt unlock, unchanged caption payload, truthful/stale/error status and campaign polling/Stop. Backend tests cover hold, cancellation, restart, scheduling, send uncertainty and integration boundaries.

## Limits

Viewport resizing and focus behavior were tested in Chromium, including reduced-height keyboard simulations. A physical Android phone/IME, iOS keyboard, touch reach with a real hand and screen-reader hardware were not available. These results do not establish complete WCAG conformance or guarantee every device's keyboard animation. Long conversations and exceptionally long captions may still require internal scrolling; the dashboard itself fits the tested viewports. Existing free-cloud sleep/cold-start limits remain. No group or donor sends were triggered as test actions. Production Auto retained its existing settings and may continue its normal work.

## Follow-up: highlighted and accurate activity strip

The phone status strip now has a strong contrast background, a colored border and a bold current action. It separates actual reply-read timestamps from page synchronization age, shows the next automatic or scheduled action, and counts down between recipients using the real job deadline. Idle time is labelled as waiting, never active reading. Worker scan phases and failures are observed in the engine; successful reply fetches record their actual timestamps. Unrecorded checks remain explicitly unknown. The truncated caption label is shortened to Group · poster / DM · poster. No caption wording, posting intervals or donor rules changed. Six additional backend tests cover idle versus reading, clearing activity after failure, real read timestamps, malformed replies, hold priority and error recovery. Browser checks cover phone and desktop strip sizes.

## Follow-up: centered hidden-message controls and compact previews

Hidden-message mode centers the action cluster in the available phone content area. The group selector stays centered and on screen; active campaign controls remain available. Desktop hidden-message mode keeps chat on the left and centers the action buttons on the right. Mobile previews fit the complete caption by adjusting only font size (14px down to 10px); caption content, WhatsApp formatting and send payloads are unchanged. Explicit editing uses 16px. The message overflow menu closes when the caption is hidden. Browser checks at 360×640, 390×700 and 430×800 confirmed complete sample captions and no page overflow; the centered group menu fits on screen. The UI test script also checks fitting, minimum-size fallback, hidden-preview behavior and unchanged desktop sizing.

## Follow-up: hidden by default, all group actions visible

The initial HTML hides the caption before JavaScript loads, and every page opening starts in that state regardless of the old saved visibility preference. Show message reveals the saved caption without editing it. All six production destinations, the test group, freelance batch and all-groups batch are visible directly; the Other groups menu and its auto-close behavior are removed. Mobile buttons are at least 48px high in a centered two-column grid, with Chat directly below. Desktop keeps chat on the left and the complete action grid centered on the right. Editing from a desktop shortcut also reveals the caption.

Browser checks at 360×640 and 390×700 confirm all default action buttons fit without page scrolling. Desktop 1280×720 checks confirm buttons stay below the header without overlap. Group/DM switching, show then reload, and Chat/Main navigation were checked with a fake WhatsApp server. The four Node scripts pass, including a new default-visibility regression check. Showing a caption alongside every group button leaves less preview space on small screens; long captions retain internal scrolling. Production sending logic, payloads, user data and Auto settings are unchanged.
