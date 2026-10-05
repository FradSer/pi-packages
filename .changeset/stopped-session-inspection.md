---
"@fradser/pi-subagents": patch
---

Allow read-only inspection of known stopped exact incarnations still retained on
the roster, including their bounded output and errors, without reviving them or
reporting a liveness failure. Unknown or replaced handles report no known session;
process controls continue to require a living exact incarnation. Sanitize and
bound error diagnostics on both inspection and listing without modifying the raw
roster record, with an explicit marker when the preview is truncated.
