# 04 — Steer, cancel, and end an attached Hosted Pi

**What to build:** An attached Console redirects the work while it runs, aborts the running turn, and ends the session when it is done. Cancelling keeps the session; ending releases its slot while the receipt stays readable.

**Blocked by:** 03 — Attach and follow a Hosted Pi from a position.

**Status:** ready-for-agent

- [ ] A mid-turn instruction uses the SDK's own queue semantics: the prompt carries a streaming behavior that is required while a turn is streaming and ignored when the session is idle, so the Console steers the running turn instead of starting a second one.
- [ ] Cancel aborts the running turn and settles without disposing the session. The session keeps its identity and stays attachable, and the receipt records a cancellation rather than a success.
- [ ] End disposes the session and releases its slot, and the terminal receipt remains readable.
- [ ] Slot behavior is explicit: a live session holds a slot; an idle unattached Hosted Pi releases the project's overlap lock while still counting against the host-wide cap, and re-acquires the lock when it resumes.
- [ ] An abandoned Hosted Pi is released after a bounded idle period without replaying its prompt, and an operator can end it explicitly before that. Four abandoned sessions must never block all further work.
- [ ] A launch or cancel whose outcome never arrived is reconciled by identity and never retried automatically.
- [ ] States are distinguishable: alive-but-idle, cancelled, failed, and interrupted by a host restart are never conflated, and no unknown state is reported as running.
- [ ] Scenarios pinned: an attached Console can steer the running turn; a Console can cancel the running turn; a Console can end a Hosted Pi; an idle unattached session stops blocking its project; an abandoned session does not consume the desk forever; Hosted Pi states are distinguishable.