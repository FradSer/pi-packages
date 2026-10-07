---
"@fradser/pi-subagents": patch
---

Show a running child above the editor when the extension was loaded into a session that never fired a session start.

Both halves of the activity area were installed by `session_start`. An extension loaded or reloaded into a running session never sees one, so the roster observer was never armed and the live context was never adopted: a child could start, work and settle while the above-editor row never appeared, and its settlement never reached the participant registry. The observer is now armed once for the life of the runtime and re-armed idempotently by whatever session start does arrive, and the live context is adopted from `tool_call`, which the host fires before it executes the tool — so the context is in place before the child that call starts is registered.

Reload Pi for this to take effect in a session that is already open.
