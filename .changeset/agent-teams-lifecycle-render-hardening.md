---
"@fradser/pi-agent-teams": patch
---

Harden agent lifecycle coordination, durable intent handling, and transcript presentation:
- Publish board intents atomically through a fully written temp file that is hard-linked into place, so a consumer can never observe or destroy a partial claim or submission record
- Retry an unparseable intent while it is younger than the publish grace instead of deleting it, so an in-flight intent cannot strand its author
- Archive and diagnose an unreadable persisted Work snapshot instead of silently continuing with an empty board
- Rotate a fully consumed oversized inbox instead of truncating it, so a concurrently appended peer message is never lost
- Abort an in-flight gate reviewer when a holding's authority is invalidated by release, stop, supersession, a new claim, or resumed owner execution
- Reject a late passing gate while teammate shutdown is pending
- Reject completed submissions during an unexpected-execution review park
- Report the residual write window when Work is released while its holder is still working
- Reconstruct the full brief — subject, description, criteria, and diagnostics — for an authorized verification revision
- Route steer and delivery feedback to an active teammate when the leader releases its Work
- Keep expanded agent delegate, inspect, and stop rows free of duplicated prompts, stale states, and retired activity
- Drop the expanded inspect row's state word, which repeated the row's own header and could contradict it
- State the coordination-only warning on delegate and start rows, matching the documented grant disclosure
- Write each snapshot artifact only when it changed, and throttle the forensic whole-state file while a teammate streams, instead of rewriting every artifact twice a second
- Bound the mailbox by total bytes as well as by message count, so long reports cannot grow the debug snapshot without limit
- Bound confirmed-stop and finish bookkeeping per session instead of accumulating one entry per incarnation
- Stop claiming the completion gate is read-only: its grant excludes edit and write, but a shell can still write
- Carry a single-line Work subject with the complete brief retained as the Work description