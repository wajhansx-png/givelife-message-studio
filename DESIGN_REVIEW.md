# GiveLife workbench design review

## Scope and audit before implementation

This is an existing HTML/CSS/JavaScript operations tool, not a marketing site. Screens actually present: group dashboard, caption preview/editor, direct-message composer, full chat/history, live activity disclosure, Settings, AI checks, memory/feedback, WhatsApp connection/QR, cloud access, donor directory, Add/import, recoverable deletion, donor batch settings, editable message bank, and poster replacement. Campaigns and timed tasks are controlled through chat/live activity; there are no separate campaign/template/navigation pages to invent.

| Workflow | Finding | Design response |
|---|---|---|
| Dashboard and group sending | Equal emphasis everywhere; disconnected controls | Quiet chat workbench; adjacent sending rail; main send above freelance controls |
| Live activity | Competes with decorative UI; stale success can dominate | Strong semantic activity band, real events retained; errors keep priority |
| Chat/history | Raw Markdown, inconsistent measure, feedback competing with replies | Escaped formatting, 68-character reading measure, shaded reply surface, quiet correction action |
| Mobile chat | Keyboard space and safe areas are critical | Keep synchronous blur, dedicated Main row and large right-hand Send; no autofocus added |
| Caption editor | Must retain precise WhatsApp text and whitespace | Preserve renderer and saved drafts; no message rewriting in redesign |
| Single DM | Placeholder-only fields | Persistent Name and Private number labels; correct input type |
| Donors | Tiny controls, wide mouse travel, heavy rendering | Compact bounded workbench; 44px coarse-pointer rows; content visibility for long list |
| Messages/batch | Form styles differ; relation to saved facts is important | Shared dialog and card tokens; readable previews; original batch rules unchanged |
| Add/import | Weak field-error association | Explicit names, descriptions, invalid state and focused field error |
| Poster | Different visual treatment | Shared modal, full preview, unchanged Save action |
| Settings/memory/feedback | Repeated visual styles and oversized controls | Shared type, spacing, borders, focus and destructive text |
| Login/WhatsApp | Missing dialog names; QR can shift | Accessible names, reserved image dimensions, shared themed surfaces |

## Design plan and self-review

Palette: pearl `#F3F6F6`, white `#FFFFFF`, ink `#182E2B`, forest `#09664F`, muted `#526862`, Important amber `#F0B65B`. Dark mode uses blue-green surfaces `#111E20` / `#19292B`, pale ink `#EDF5F1`, and readable mint `#93E5C7`. Amber remains a meaning (Important), not decoration.

Typography: Segoe UI Variable Text, Segoe UI and system fallbacks, intentionally local for immediate/offline rendering. 12px compact data, 13px controls, 15–16px chat/form text, 19–24px page/dialog titles. Tabular figures for money/time. No external font request.

Layout:

```text
Desktop: identity / mode / preview       balance / donors / connection / settings
         current activity + last real event                              Auto
         latest conversation                  main send / test
         reply and contextual actions          freelance group grid
         composer                              all groups

Mobile:  mode / balance / donors / connection / settings
         current activity + real update / Auto
         optional compact preview
         centred group controls
         Chat
```

The skill search produced marketing hero and scholarly typography suggestions even after one narrower retry. Those results were rejected as unsuitable. Its minimal grid, density and focus/accessibility guidance fit this app. No generated recommendation was persisted as a verified design system. This reviewed plan is the project-specific source of truth.

Restraint pass: no hero, gradients, decorative charts, new dashboard Suggestions or extra navigation. The strongest visual element is live operational status. Sending labels, target IDs, message text, backend sending logic and user data remain intact.

## Final audit and evidence

Review against the current Vercel Web Interface Guidelines after implementation, then record resolved findings and verification below. Simulated WhatsApp is mandatory for send tests; real donor data must not be altered during UI QA.

### Second-pass findings resolved

- `studio.css:4` — control borders initially below 3:1; strengthened both theme tokens and added a contrast regression test.
- `studio.css:170` — narrow phone header had 1px overflow and sub-44px primary targets; rebalanced 320px layout, verified zero overflow and 44px targets.
- `app.js:32` / `format.js:33` — raw double-asterisk assistant Markdown; added escaped basic formatting without altering WhatsApp caption rendering.
- `index.html:71` — no skip destination; added skip link and focusable main workspace.
- `index.html:108` — placeholder-only DM fields; added persistent labels, names and tel semantics.
- `connection.js:9` — unnamed cloud/connection dialogs and QR layout shift; names and image dimensions added.
- `donors.js:41` — unsaved message-bank edits lost after navigation; session drafts restored on tab switch/reload, cleared after Save, with a warning before Regenerate discards them.
- `donors.js:99` — donor validation lacked associated invalid state; error described by field, invalid state exposed, field focused for repair.
- `studio.css:123` — long donor list rendered every offscreen row; content visibility skips offscreen painting, with explicit override for focused rows and open menus.

### Verification

Automated: full Python regression suite; existing nine Node suites; additional design suite covering light/dark text contrast (4.5:1), control boundaries (3:1), button text, escaped assistant formatting, unchanged WhatsApp formatting and preserved paragraphs.

Browser: desktop, 390×844 and 320×640 portrait, 844×390 landscape; both themes; dashboard/preview/DM switching; all group controls; full chat and long replies; accessible Main focus without keyboard autofocus; donor tabs, error recovery, message draft retention across reload; poster/memory/correction/connection dialogs. Fake group and individual DM transport confirmed feedback transitions. No real recipient was contacted.

Intentional constraints: dense star/more controls retain at least 24px web targets to honour the requested 44px donor row density; primary send and mobile header controls are 44px or larger. Existing paste handlers sanitize caption text and split pasted donor name/number; they do not prevent pasting. Private phone searches are not placed in shareable URLs. Actual Android keyboard/hardware and assistive-technology certification require physical-device testing; viewport and production handler checks are not a claim of that certification. Very long answers and short landscape screens retain normal scrolling instead of clipping information.

Sources used: installed UI UX Pro Max, Anthropic Frontend Design, and the current [Vercel Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md). Skill-generated marketing/scholarly recommendations were rejected as off-topic. No new runtime UI framework or external font/CDN dependency was added.

