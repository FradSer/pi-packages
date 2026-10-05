---
"@fradser/pi-subagents": patch
---

Retain native final-message stop reasons, errors and tool-call evidence, and
report empty, failed, truncated or missing final answers as explicit unanswered
follow-ups rather than blank success envelopes. Preserve original output, bound
provider diagnostics, render an error-band row and expose the outcome in roster
readbacks while leaving the resident IDLE for explicit subsequent input.
