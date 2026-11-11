---
name: "project_tasks_waiting_snapshot.md"
description: "`@fradser/pi-tasks` emits `[tasks] waiting · N unfinished task(s)` at settlement when unfinished tasks remain but continuation is unavailable; blocked tasks add `recovery inspection required`, headless runs omit the passive row, and identical waiting snapshots are deduplicated."
type: project
---
`packages/tasks/src/stop-check.ts` implements the unfinished-task reminder on `agent_before_settle`; it returns early unless the settlement outcome is `completed` and there is no abort, pending input, existing continuation, or pending message, and it treats non-`execution`, non-replaced tasks with status `pending`, `in_progress`, or `blocked` as open.

A task is runnable when it has no blocked dependencies and is either an unclaimed `pending` task or an `in_progress` task held by the current caller; automatic continuation also requires new effective tool work and fewer than three automatic continuations since real user input.

When continuation does not happen, the snapshot status is `waiting`; its reason joins any applicable `automatic continuation limit reached; user input required`, `no new effective work`, `no runnable task`, and the waiting reasons: blocked work contributes `recovery inspection required`, a foreign holder contributes `Other participant holds work`, unfinished dependencies contribute `unfinished dependencies`, and an unheld in-progress task contributes `missing task holder`.

The displayed subject is the remaining count followed by `unfinished task`, pluralized with `s` unless the count is 1, so one remaining task displays as `1 unfinished task`.

Blocked work waits for deliberate recovery, and the README states the harness does not clear blockers or infer authorization; `waiting` is the stop-check status, not a task status or user pause, and allowance exhaustion is also `waiting`.

With no UI, a waiting settlement returns `undefined` instead of a passive row; the README says this preserves the final `pi --print` answer, and identical waiting snapshots are deduplicated.

Repeated identical tool arguments and results, Task bookkeeping, and monitor polling do not count as new effective work, and extension-generated input does not reset the allowance.