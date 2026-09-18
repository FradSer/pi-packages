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
- Carry a single-line Work subject with the complete brief retained as the Work description