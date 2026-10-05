---
"@fradser/pi-subagents": minor
"@fradser/pi-agent-teams": minor
---

Make disk agent.md the only durable identity declaration. Remove invocation
persistence/Memory/worktree switches and automatic identity creation. Every child
settles to IDLE and stays sendable until explicit stop or parent shutdown; temporary
contexts remain memory-only. Fold private Memory, scratch workspace and per-project
history into the Agent home, remove Git workspace/commit machinery, expose saved
offline identities separately, and provide explicit non-destructive legacy migration.
Provisioning and Memory updates share one locked atomic state mutation boundary
that preserves creation time and existing metadata. Confirmed parent shutdown
retires exact resident/host control closures without touching replacements or
unconfirmed execution.
