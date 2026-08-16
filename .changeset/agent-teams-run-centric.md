---
"@fradser/pi-agent-teams": minor
---

Run-centric redesign: declarative agent files + single-call DAG dispatch.

Breaking tool-surface change (replaces the teammate-registry model):

- New: `teammate_run` dispatches a dependency-aware task graph in one call
  (tasks with `dependsOn`, per-node `access`/`model`/`timeoutMs`, `concurrency`,
  `worktree`, `background`). Root nodes start immediately; downstream nodes
  auto-start when dependencies complete; overlapping shared-workspace writes
  are deferred unless worktree-isolated.
- New leader tools (5): `teammate_run` (dispatches a dependency-aware task
  graph in one call), `teammate_status` (agents + run overview, or run/node
  detail), `teammate_cancel` (cancel a run or one node while the rest
  continues), `teammate_retry` (re-run failed/cancelled nodes),
  `teammate_message` (message team leader, a node, or broadcast).
- Worker capability tools (2): `teammate_message` (message `team-leader` or a
  same-run peer) and `teammate_report` (submit progress or final deliverable).
- Removed: `teammate_wait` (replaced by automatic completion follow-ups and
  inline gather), `teammate_cleanup`, `teammate_inbox`, and the legacy
  registry tools (`teammate_register`, `teammate_list`, `teammate_configure`,
  `teammate_remove`, `teammate_create_task`, `teammate_list_tasks`,
  `teammate_start_task`, `teammate_cancel_task`).
- Agents are now declarative Markdown files (bundled `agents/`, user
  `~/.pi/agent/agents/`, project `.pi/agents/`; project > user > bundled).
- Mailbox is a best-effort snapshot: workers send via `teammate_message` and
  `teammate_report`. Incoming messages are delivered into the shared state
  snapshot; DAG handoffs inject upstream results into downstream prompts
  (`=== UPSTREAM HANDOFF ===`).
- Advisory write-conflict coordination spans all runs in the session:
  overlapping shared-workspace write nodes are deferred unless worktree-isolated.
- Full-screen `/teammate` console with live activity stream and mouse-wheel scrolling.
- Worker protocol kept: per-spawn identity validation, one canonical terminal
  result per node, SIGTERM->SIGKILL cancellation.
