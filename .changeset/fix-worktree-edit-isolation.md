---
"@fradser/pi-utils": patch
---

Apply worktree transitions only after the old agent run settles, block competing tool calls while switching, and resume the task through the new worktree session context. Prevent stale absolute edit/write paths from modifying another checkout. Require Pi 0.85.1 or newer for expanded command dispatch.
