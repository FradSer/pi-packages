---
"@fradser/pi-subagents": patch
---

Reset authoritative completion evidence on each new assistant message, including
content-event fallback for transports without message_start, so an unfinished
later message cannot inherit a previous successful stop. Normalize stop reasons
to bounded protocol tokens at parsing, result delivery and rendering boundaries.
