---
"@fradser/pi-agent-teams": patch
---

Dispatch the first teammate report to Pi's native follow-up queue even while the leader is active, rather than holding it in Agent Teams until the complete leader run settles. Later reports remain FIFO-serialized until the dispatched report settles.
