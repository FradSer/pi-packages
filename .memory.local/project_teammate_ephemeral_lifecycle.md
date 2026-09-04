---
name: teammate-ephemeral-lifecycle
description: Agent Teams identities are reusable within one session, then actively expire after a clean idle TTL
type: project
---

## Why

The user clarified that a `Teammate` should not become durable session baggage, but immediate disposal after each task is too strict. A bounded worker process should finish one task run; the idle teammate identity remains available for compatible follow-up work, then is actively retired once it is truly expired.

## How to apply

1. A child worker process is one bounded task run: it reports plan, material progress/blockers, and terminal result to the leader, then exits. Its `Teammate` identity remains idle and reusable in the current session.
2. Prefer reusing an **idle teammate with the exact same role prompt, role, model, and tools**. If the responsibilities materially differ, register a distinct teammate; use `teammate_configure` deliberately rather than silently overwriting a role.
3. Default idle TTL is five minutes. Retire a teammate only when it is idle, has no assigned/in-progress task, has no unread inbox messages, and has exceeded the TTL. `0` is reserved for disabling automatic expiry internally. Manual remove remains an early cleanup action.
4. Preserve task results until explicit task cleanup. On `session_start`, initialize an empty team; on `session_shutdown`, terminate live children before deleting the shared directory and clear the board.
5. Paths are coordination scope, not permanent locks: overlapping read tasks may run together. Concurrent overlapping writes in a shared workspace are blocked at task start; deliberately parallel write experiments require `isolation: "worktree"` plus leader integration review.
6. Worker messages addressed to `agent` are delivered to the main session as follow-up updates. Terminal report, final summary, and close fallback are deduplicated so one run triggers one terminal update.

## Related

[[teammate-autonomous-and-tui]] [[pi-package-conventions]]
