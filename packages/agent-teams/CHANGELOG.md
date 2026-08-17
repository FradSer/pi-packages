# @fradser/pi-agent-teams

## 0.3.0

### Minor Changes

- e16cd3f: Run-centric redesign: declarative agent files + single-call DAG dispatch.
  
  Breaking tool-surface change (replaces the teammate-registry model):
  
  - New: `teammate_run` dispatches a dependency-aware task graph in one call
    (tasks with `dependsOn`, per-node `access`/`model`/`timeoutMs`, `concurrency`,
    `worktree`, `background`). Root nodes start immediately; downstream nodes
    auto-start when dependencies complete; overlapping shared-workspace writes
    are deferred unless worktree-isolated.
  - New: automatic completion follow-ups for background runs, foreground
    gather with bounded detachment, `teammate_cancel`, `teammate_retry`, and
    `teammate_message`.
  - Removed: `teammate_register`, `teammate_list`, `teammate_configure`,
    `teammate_remove`, `teammate_create_task`, `teammate_list_tasks`,
    `teammate_start_task`, `teammate_cancel_task`.
  - Agents are now declarative Markdown files (bundled `agents/`, user
    `~/.pi/agent/agents/`, project `.pi/agents/`; project > user > bundled).
  - Read-receipt protocol removed: messages have no read flags or receipt events.
  - Worker protocol kept: per-spawn identity validation, `teammate_message`
    capability, one leader inbox, per-node leader inbox entries, push-only node
    sent transcripts, DAG prompt handoffs, one canonical terminal result per
    node, SIGTERM->SIGKILL cancellation.
