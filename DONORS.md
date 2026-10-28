# Private Donor Hub

Open **Donors** from the studio header. All, Important, Donated and Not donated are filters over one persistent private directory. Search runs on the server across saved names, notes and numbers. Responses contain opaque IDs and no phone field; the server alone resolves IDs for sending. Add accepts an arbitrary saved label and an international number or Pakistani 03 number. Pasting both into either field fills the two fields. Delete is recoverable with Undo. Changing donation status/amount is bookkeeping, not a deduction from the case balance.

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

Explicit donor batches snapshot the full saved DM and selected audience, put Important first and attach the saved poster by default. They honor the requested gap with the existing 60-second minimum, global custom-send 50/day cap, block/opt-out lists and both legacy receipt key formats. Already-contacted or uncertain recipients are skipped. A failed or uncertain dispatch stops the batch; a restart marks an unfinished batch Interrupted and never automatically replays it. Progress/receipts remain stored. Free hosting can sleep; it cannot guarantee uninterrupted batch execution.

Change the campaign image in **Settings → Change poster**, or the message tools menu. Image uploads are converted to JPEG, previewed, then saved to the existing private cloud store. Existing captions are preserved. Poster replacement is blocked during active sends to avoid mixed-image batches. No medical claims, poster text or remaining-amount text inside the image are automatically edited.

Validation: 250 Python tests (30 new registry/delivery/integration checks, including inherited registry cases), seven existing Node UI suites, JavaScript/Python syntax checks, and desktop/mobile browser checks against fake WhatsApp. No real WhatsApp recipient was contacted for testing. The prior abandoned `reply_view` local experiment is not part of this release.

