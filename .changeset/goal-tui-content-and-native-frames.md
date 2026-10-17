---
"@fradser/pi-goal": patch
"@fradser/pi-kit": patch
---

Preserve multiline goal results, preserve Markdown blank lines, and omit the redundant Goal prefix consistently in error rows. Token-capped goals now recommend clearing and starting a new goal rather than an unusable resume. Repair native terminal acceptance to decode complete repaint frames with a finite scripted provider, and document every TUI trigger.

Treat explicitly provided revision fields as decisions even when empty: an empty objective is rejected, and an empty revision still obeys decision exclusivity. Clarify that reason and completion_summary alone do not record an update.

Show settled Goal subjects and bodies in full with width-aware wrapping, preserve complete requirements in TUI while paging long model reads with content-bound cursors, unify summary and objective reads, constrain updates to mutually exclusive operations, and distinguish rejected updates from goal failure. Keep legacy blocked calls compatible, simplify final-refusal headlines, and reuse passive status widgets for repaint. Add opt-in fullSummary to pi-kit without changing existing consumers.
