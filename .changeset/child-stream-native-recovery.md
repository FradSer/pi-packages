---
"@fradser/pi-subagents": patch
"@fradser/pi-agent-teams": patch
---

Classify a known premature provider stream closure for Pi's native retry policy.
Use its configured retry budget, backoff and cancellation in the same child input sequence.
Preserve partial output and original diagnostics. Disabled or exhausted retry still reports unanswered.
