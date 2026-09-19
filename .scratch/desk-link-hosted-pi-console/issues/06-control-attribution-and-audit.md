# 06 — Show Control Attribution on the desk and record control audit

**What to build:** A Hosted Pi driven by a Console is visible as such on the desk, with the driving machine named, for as long as that control exists. Local touch and keyboard keep working, and the receipt records who drove the session.

**Blocked by:** 03 — Attach and follow a Hosted Pi from a position.

**Status:** ready-for-agent

- [ ] The desk's session validator, its summary arithmetic, and its live-status set accept the Hosted Pi states. The desk's session vocabulary is being changed while this is written, so re-read the validator, the summary arithmetic, and the live-status set instead of trusting an enumeration. Today an unknown status is coerced to running, which would make a failed or interrupted Hosted Pi either fail the whole snapshot or read as working.
- [ ] Control provenance is its own field and renders in exactly one place: the overview header, where data-source provenance already lives. It never appears in the session detail, which states session facts only.
- [ ] A Hosted Pi carries an explicit marker so the surface cannot present it as a report-only session, whose semantics are inspect-only.
- [ ] Attribution names the driving machine and session identity, lives exactly as long as the held control connection, clears when that connection ends, and has a defined lifetime across a Desk Link Service restart.
- [ ] The Hosted Pi receipt records the controlling identity, so audit survives the Console disconnecting.
- [ ] Local touch and keyboard keep working exactly as they do without a Console attached, and a Console never takes local driving authority away.
- [ ] No new page, widget, or state-bar element is introduced, and diagnostics stay command-only.
- [ ] Scenarios pinned: the desk states its Control Attribution; local input keeps working under Hosted Pi control; control is attributed for audit.