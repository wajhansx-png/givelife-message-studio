# GiveLife comfort redesign

Operate mode. The owner has requested implementation and delegated layout and palette choices.

## Alternatives considered
1. Existing broad chat plus a heavily colored right rail: familiar but visually noisy, and replies start far from the input's reading area.
2. Bottom action dock: short mouse travel, but competes with mobile chat input and reduces caption height.
3. Selected: a bounded reading column with a quiet adjacent send rail on desktop; a compact centered action workspace and dedicated chat on mobile. A shared slim header and semantic activity strip make state easy to find.

## Visual system
Reference: https://givebutter.com/donor-management-crm and its official contact-management screenshot. Use warm-neutral charcoal for default dark mode, soft off-white for optional light mode, crisp restrained blue actions, gold importance and distinct success/warning/error colors. The earlier slate-blue proposal was rejected by the owner and is not the selected design. Avoid pure-white expanses, vivid purple panels, repeated card decoration and unnecessary shadows. Both themes must pass AA text contrast; colors alone are not promised to prevent fatigue.

Use a self-contained Geist variable font (29.4 KB WOFF2, SIL Open Font License), regular prose, 600-weight controls, a bounded desktop reading measure and compact numeric rows. No third-party font request occurs in the browser. Preserve the owner's centered reply text and box, centered feedback/actions, WhatsApp status dot, Donors header position and desktop Settings footer position. These were independently updated on GitHub through commit 890b3c9 and incorporated before any styling. Accessible scrolling remains for content beyond screen capacity; never clip replies or disable zoom.

## Interaction and verification
Keep all existing element IDs, endpoints and message text. Keep frequent groups visible. Align composer and next actions with the reading column. Reserve input/return rows so neither covers content. Make donor tabs keyboard operable, keep stable focus, and preserve drafts. Verify themes, small mobile, tablet, desktop, long text, dialogs, donor rows, keyboard behavior and fake delivery. Native Android keyboard and real hardware comfort remain manual checks.


## Interaction refinement
Desktop group destinations form a compact action list with receipt ages aligned beside their names. Mobile retains all group buttons in a thumb-height grid. The donor message library uses a master/detail list on desktop and one native selector on mobile. Keep unsaved edits and selected variants across reloads. Snapshot saves, retain newer typing and share save/regeneration locks across rerenders. First use is dark even on a light operating system; explicit Light and Auto remain persistent options.
