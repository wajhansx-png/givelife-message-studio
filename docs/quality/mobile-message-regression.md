# Mobile Messages and right-thumb navigation

The supplied Samsung screenshot reproduced at a 393 × 700 CSS viewport with 1.5 device scale. At `f869b69`, the message preview measured 207px high and the action toolbar 310px. The earlier geometry audit checked clipping, minimum targets and reachability; it did not reject this poor use of space. Its passing result did not establish usability.

The phone Messages layout now uses one bounded reading pane above a compact dock. Competing mobile layout blocks were removed. Edit, Bold, Italic and Copy share one row; Base message and Test share another; navigation occupies the last row. Each control retains a 44px target. Message text stays at 16px and scrolls within the pane. A short viewport scrolls the workspace instead of placing controls over the message.

A single message has no disabled Next button or redundant version picker. Multiple messages retain Next and Previous navigation. Back sits at the right edge. Mobile donor, preview, volunteer, Notes, Settings, chat, bulk-message and research navigation use the same right-thumb policy. Notes moves the existing control between its phone footer and desktop header without duplicating its handler.

`donor-message-phone.spec.cjs` first failed on the 207px preview. It now requires the message to occupy at least half of a normal phone/tablet viewport, limits the toolbar to 160px, verifies readable long English/Urdu content, inner scrolling, editing, and version navigation. It covers one and 20 saved versions, including the screenshot's 393 × 700 layout.

`mobile-back-thumb.spec.cjs` first failed on the donor Back control at the left edge. It checks ten screen states at 393 × 700 and 320 × 568: Back's center must be in the rightmost quarter and bottom 30%, fully visible with a 44px target and no overlapping control. The Bulk dialog footer remains visible while its fields scroll.

Screenshots and traces are available as CI artifacts. These checks use a local fake WhatsApp backend and Chromium mobile emulation; they do not substitute for physical device review. The previous eight-size audit report records its original commit's results, not a guarantee about all visual or ergonomic requirements.

Final verification: the four reading-priority cases, thirteen Donors regressions, four focused Group/DM editor checks, three Notes formatting checks, two ten-state thumb-placement cases and the narrow Notes keyboard case passed. The final locked/writing Notes surfaces also passed the element audit at 320 × 256. The earlier 390 × 844 and 768 × 1024 matrix runs passed. A full matrix repeat after the final Notes footer adjustment was stopped at the user's request to conserve remaining credits.
