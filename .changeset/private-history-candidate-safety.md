---
"@fradser/pi-subagents": patch
"@fradser/pi-agent-teams": patch
---

Reject linked or non-regular JSONL session-history candidates before provisioning
or spawning a resident. Both public standalone and hosted resume selection use
the same validation, with a second check at the shared spawn boundary.
