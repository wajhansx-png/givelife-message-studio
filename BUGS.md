# GiveLife audit — bug inventory

Evidence: automated survey (41 screens × 11 viewports 320–1920, 7,853 control checks, `fake server`, dark theme) + the 13-screenshot PDF brief + Playwright specs. Safety: fake WhatsApp only, no real sends.
Status: FIXED (with regression test) / OPEN / UNVERIFIED (why).

## A. From the PDF (screenshot # → issue)
| # | Sev | Screen | Issue | Status / evidence |
|---|---|---|---|---|
| 1a | P0 | Group preview | Click outside an edit did not save | FIXED `group_preview_edit.spec` (edit → outside → reload keeps it) |
| 1b | P1 | Group preview | "Save Base Message" saved instantly, unclear | FIXED → "Save Base" + small modal (says honestly if versions are cleared) |
| 1c | P1 | Group preview | Big "Next version" button | FIXED → purple arrow on the card's right edge, ↻ generate icon |
| 1d | P1 | Group preview | Too many buttons | FIXED → rare tools under More (Poster, Manual, Generate, Replace) |
| 1e | P1 | Group preview | Rs. 17,000 unpaid vs Rs. 15,000 left | UNVERIFIED: both can be true (debt vs remaining); needs owner rule |
| 2/6 | P1 | Donors phone | Names collapse to 0 px when a follow-up line exists | FIXED earlier (`donor_names_followup.spec`) |
| 2/6 | P1 | Donors phone | Tabs broken mid-word at 320 | FIXED (fit on one row) |
| 2/6 | P1 | Donors phone | Follow-up checkbox between tabs and rows; expand icon floating | OPEN (checkbox moved off the tabs; full-screen icon move not done) |
| 3 | P1 | Donors desktop | Column alignment / header | OPEN |
| 4 | P1 | Donor row "…" | Escape did not close the menu; outside click unreliable; menu ran off the bottom of a 1280×800 screen | FIXED `donor_menus.spec` |
| 5 | P1 | DM progress | Long status text, chips, Hide on top, no outside-click/Escape close, chip not purple | FIXED `donor_menus.spec` ("Sending: 2 of 5 sent · 3 left", plan line, Hide last, purple chip) |
| 8 | P0/P1 | Send DMs modal | Tall form, duplicate gap controls, poster state stale after Cancel | FIXED `send_dm_modal.spec` (fits 320×568 without scrolling; presets + Custom; plain-English summary) |
| 9/13 | P0/P1 | DM Messages | Big repeated error, donor tabs above editor, many toolbar rows, big Next | OPEN |
| 10 | P2 | Donors More menu (phone) | Test DM + Poster toggle duplicated | FIXED (More = Bulk only; Test DM in Send DMs setup; poster switch syncs) |
| 11 | P1 | Main More menu / case select | Native select list covers UI | OPEN |
| 12 | P0/P1 | Reply modal | Tall, one audience, `Turn ON` target 16 px | OPEN |

## B. Found by the automated survey
| Sev | Screen | Issue | Status |
|---|---|---|---|
| P1 | Main/DM "More" menu @320 | Panel items clip off the right edge (8 elements) | OPEN |
| P2 | Auto replies @all | `#repEnabled` target under 24 px | OPEN (part of #12) |
| P2 | Main @320/360 | "More app options" label overflows | OPEN |
| P2 | Donor messages @320/360 | "Regenerate 20 versions" label overflows | OPEN |
| P2 | Send DMs @320 | "Custom" label overflowed | FIXED (nowrap grid) |
| P3 | Group preview (under overlay) | Main-page buttons reported "covered" | FALSE POSITIVE (hidden behind the full-screen preview) |
| P3 | `/mobile-preview` | Dev-only test page clips at phone widths | UNVERIFIED (developer tool, not the product) |

## C. Logic / backend (earlier in this work, all with tests)
FIXED: DM batch refused <20 versions; Generate-5 rejected Urdu/verse lines; 40-DM cap; 3-min server gap overriding the chosen gap; batch stopped on one bad recipient / unconfirmed send / WhatsApp blip; group jobs cancelled on one failed group; deploy left running batches stopped (auto-resume); AI rate limits not retried.
UNVERIFIED: real WhatsApp/AI behaviour; live site.

## D. Not yet covered (honest)
Click-through of every control (crawler built; full click run not completed, memory); Agents/Auto real actions; Notes; Case plan; Group finder; Urdu direction in every screen; keyboard/touch gestures on a real device.
