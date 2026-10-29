# Private Donor Hub

Open **Donors** from the studio header. All, Important, Donated and Not donated are filters over one persistent private directory. Name filtering happens locally for immediate results; private-number searches stay on the server. Changing tabs clears the search. Responses contain opaque IDs and no phone field; the server alone resolves IDs for sending. Add accepts an arbitrary saved label and an international number or Pakistani 03 number. Pasting both into either field fills the two fields. Delete is recoverable with Undo. Changing donation status/amount is bookkeeping, not a deduction from the case balance. Edits appear immediately and writes for each donor are serialized so older replies cannot reverse newer choices.

Use **Add donor → Import verified contacts** to import an exported `records` JSON file through the authenticated app. It skips the connected owner's account and normalizes duplicates, preserves existing statuses/notes, and does not send messages. Do not add private exports to GitHub. Group membership alone does not prove a donation; imported records start Not donated.

Chat examples:

- `add donor Ali 03001234567`
- `make Ali important`
- `mark Ali donated 2000`
- `remove donor Ali`
- `send to important donors with 2 minutes gap`
- `send to all donors with 90 seconds gap`
- `stop donor DMs`

Complex owner instructions can use the validated `donor_action` model tool. Contact data/notes cannot grant action permission. Names/numbers supplied for additions must come from the current owner instruction. The Donors page supports exact selection when names collide. Unclear greeting names use Brother; clearly recognized female personal names use Sister. This is conservative validation, not universal name recognition.

Explicit donor batches snapshot up to 20 recipients, put Important first and attach the saved poster by default. The gap picker accepts 1–10 minutes, defaults to 4 minutes and suggests 3–5. The first DM starts immediately; subsequent DMs wait the selected gap after confirmation. Prior confirmed sends do not exclude someone from a new deliberate batch. Opt-outs, blocked/uncertain recipients, own-account exclusion and the global 50/day cap remain enforced. A failed or uncertain dispatch stops the batch; a restart marks an unfinished batch Interrupted and never automatically replays it. Progress/receipts remain stored. Free hosting can sleep; it cannot guarantee uninterrupted batch execution.

The **Messages** tab holds 20 distinct editable captions (10 shown initially), using the same saved case facts, amount and payment details. Each batch snapshots one variant per recipient. Changing the saved DM regenerates the bank to avoid stale case facts. This is wording variation, not a guarantee against WhatsApp restrictions. It does not change the saved group caption. Persistent connections, batched receipt reads and cached private donor records reduce repeated database work.

`Hold DMs`, `pause personal messages` and the donor Stop button pause personal DMs only. Group Auto and group timers remain unchanged. `Hold everything` still stops both. Older private-send callbacks are rejected after a newer personal pause instruction.

Change the campaign image in **Settings → Change poster**, or the message tools menu. Image uploads are converted to JPEG, previewed, then saved to the existing private cloud store. Existing captions are preserved. Poster replacement is blocked during active sends to avoid mixed-image batches. No medical claims, poster text or remaining-amount text inside the image are automatically edited.

Validation: Python regression tests, nine Node UI suites, JavaScript/Python syntax checks, and desktop/mobile browser checks against fake WhatsApp. No real WhatsApp recipient was contacted for testing. The prior abandoned `reply_view` local experiment is not part of this release.
# Individual manual sending

Each donor-row DM click is an explicit immediate send, including previously sent or uncertain recipients. The button remains available after confirmation. This path bypasses the old-recipient check and the inter-DM cooldown only for that manual click, never for bulk/Auto jobs. It retains opt-outs, blocked numbers, the own-account exclusion, and real connection checks (donor sends have no daily cap). Identical request IDs never dispatch twice; a new deliberate click has a new request ID. An in-flight WhatsApp request must finish before another dispatch can use the transport. Network/provider time is not an artificial cooldown and success is never guaranteed or fabricated. A manual success restarts the active donor batch's gap. The header sums saved amounts of active records marked Donated, independently of search filters, and excludes deleted records; it does not infer receipts or alter the case balance.


