# TOKEN-EFFICIENT CODING RULES

Goal: Minimize total token usage without sacrificing code quality, accuracy or security.

1. Search before reading. Open only relevant files, functions and line ranges.
2. Never scan the entire repository unless necessary.
3. Avoid rereading unchanged files or repeating successful commands.
4. Make minimal, targeted edits. Reuse existing code and components.
5. For bugs, identify the likely root cause before editing. Never blindly retry failed fixes.
6. Use short terminal outputs. Show relevant errors only; preserve full logs for deeper debugging.
7. Keep responses extremely concise. No unnecessary explanations, progress reports or repeated summaries.
8. For simple tasks, work directly. For complex tasks, use a brief plan before implementation.
9. Avoid unnecessary subagents, parallel agents and repeated research.
10. Run relevant tests once after changes. Rerun only when fixes or failures require it.
11. Keep project instructions short. Avoid duplicate instructions and unnecessary context.
12. Preserve important findings and decisions across long tasks without repeating full conversations.
13. Never rewrite working features or modify unrelated files.
14. Prefer efficient solutions over generating large amounts of new code.
15. Do not perform unnecessary Git operations, installations or dependency updates.
16. Finish with only: Changes made; Tests passed/failed; Remaining issues.
17. Never sacrifice correctness, security, necessary testing or functionality to save tokens.


Apply these rules automatically to every coding task.

# MAIN LINK
- Live site: Oracle, https://129-225-68-143.sslip.io. Render is suspended: never resume it while Oracle runs. Oracle's /health says `version: local`; check a deploy by comparing a served file (CRLF stripped) with main.
- `/` is the new design (same page as `/new`, built in `server.py` `reply_new_ui`). The previous page is saved unchanged at `/old` (`index.html`), not linked anywhere. Browser tests for the previous page use `/old`.

# GIKI PAGE (/giki) and GIKI 2 (/giki2)
- Giki 2 (`giki_line.Giki2Volunteers`, line `giki2`, More tile) is the same page and the same messages (share message, Timer, 2nd / 3rd shared with Giki) with its own people, batches and WhatsApp; routes `/giki2`, `/giki2/volunteers`, `/giki2/wa`; `server.GIKI_PAGES` maps page -> line.
- The Volunteers screen for the Giki list, with its own WhatsApp (a second device in the same gateway). Page: `server.py` `reply_giki_ui` + `giki.js` + `giki.css` (only loaded there); list, message, batch and timer: `giki_line.py`; the device (connect by code or QR, status, logout): `wa_lines.py`.
- A send for the Giki list carries `line: "giki"`; `send_custom` then runs inside `on_line()` and every gateway call uses `device()`. A line with no device sends nothing; it never falls back to the main WhatsApp. The launcher never takes a `giki-` device (or the Giki number) as the main one. Render wipes the disk on deploy; `gateway_registry.py` saves the gateway's device list (names to logins) in the DB and puts it back before the gateway starts, so the Giki link survives deploys.
- DM Case reads the Group msgs text at the click (with today's amount) and sends the PDF / video exactly when they are on for the group message. The Timer sheet (gap, batch, rest) is the Case page sheet and is what DM all uses.
- The owner's 42 Giki people are in `giki_numbers.md` and are added once, the first time the page opens (`GIKI_SEED_FILE=""` switches it off; previews and tests do). More people: + Add, Add many. DM all and DM Case = the case first, then the 2nd / 3rd messages, then the share message; Test sends it to the owner's own WhatsApp. Stop DMs -> Resume DMs (Giki page only: DM all again for the people still waiting, with today's case). A deploy carries list batches on by itself (`NAMES_AT_SEND`). Self-healing (Giki only, `DonorDelivery.peek` / `seen` -> `server.newest_sent` / `sent_after`): an unclear or failed answer is looked up in the chat (gateway history) before anything is resent; found = sent, not there = resent (3 tries), cannot tell = never twice. Ahmad test / Zain test (`giki_line.TEST_PEOPLE`, placeholder numbers) sit first and are delivered to the GiveLife test group as DMs. Stress harness for this lives outside the repo (fake gateway that fails / drops / loses sends). Tests: `tests/test_giki_line.py`, `tests/test_giki_server.py`, `tests/e2e/giki.spec.cjs`.

# RESPONSIVE UI RULES
- Layout fixes go in `responsive.css` (loaded last), one rule block per width band: <=299, <=359, <=380, <=899, >=900.
- Before finishing any UI change run `python tests/responsive_dashboard.py` (needs `tests/preview_fake.py --port 3003`), open `/dash`, press "Find errors": every screen and width must show no errors.

# DESIGN TASTE (owner's rules; from GiveLife_UIUX_Visual_Only_Dark_FIXED.pdf + owner requests)
- Do not ask the owner design questions: decide what is best and do it. For a new screen, show a mock image first.
- Phone: every often-used button sits in the bottom third (thumb zone); the most used is the biggest and lowest. Back in right-thumb reach.
- Most used = in front, never hidden in More: Send to GiveLife, Test group, Generate, English, Urdu + English, Trigger, Style fix, Copy, Edit, Giki 1, Giki 2. More (a bottom sheet) keeps only rare things.
- Simple: every button has a word (icon + word is fine). Icon alone only for ‹ › and the small Copy · Edit · Save base · ⋯ on the message. One Back per screen. No glow or box-shadow under buttons.
- Phone bottom bar: Notes, Message, Donors, Chat, More (icon above each word) + a small Giki 1 | Giki 2 row above it.
- Desktop left menu: Message, Case, Giki 1, Giki 2, Donors, Thank donors, Chat, Report, Notes, Settings, More; it stays beside Case, Donors, Chat, Report (Notes covers it).
- Message text 15px, fully readable, no scroll; on the phone a short message sits in the middle of its card (top to bottom).
- Send buttons one line each, about 42px, group name never overlapped. Send to GiveLife and Test group up front; other groups and Timer behind a click.
- Copy / Edit / Save base / ⋯ sit inside the message (bottom right) as small icons (about 34px), like the desktop home page.
- Show money left, tap to change. Auto ON/OFF easy to see without hiding the message.
- Tablet: message and send list side by side. Desktop: message and send buttons together.

# GRAPHIFY (use on every code task)
- First step of every code prompt: `graphify query "<question>"` or `graphify explain "<name>"`, then open only the files it names.
- No `graphify-out/graph.json` (it is git-ignored, so new sessions lack it): run `pip install -q graphifyy && graphify update .` first.
- After editing code: `graphify update .`. For one simple lookup, grep is fine.

# CASE PAGE (/new, Case tab)
- `case_run.py` + `/case-run` run the approved plan through the EXISTING engines (no sender of its own); `case-run.js` + the end of `new-ui.css` are the page. Tests: `tests/test_case_run.py`, `tests/e2e/case_run.spec.cjs`.
- No Start button: each row has one switch (ON = it sends). First ON asks once (summary + Start sending); a row joins a running case with `summary(key)` + `add_row`, and `row_op` pauses/starts one row alone.
- Saving a plan never sends. Start needs the summary token. One DM queue at a time. Never retry an uncertain send. A claim is not money until the owner confirms the amount.
