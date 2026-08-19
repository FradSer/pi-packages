# @fradser/pi-agent-teams

## 0.5.2

### Patch Changes

- a1b37a0: Remove the `Console: /teammate` navigation hint from the `[teammate-update]` run summary follow-up message. The console affordance stays in the live widget, but the completion message no longer prompts the user to open the console.
- Standardize runtime package entry points on package-root `index.ts` modules. The monitor status is also rendered through Pi's native footer so it appears below the directory and usage lines.
- Updated dependencies
  - @fradser/pi-kit@0.1.1

## 0.5.1

### Patch Changes

- 3c88ab4: Introduce `@fradser/pi-kit` as the shared internal runtime package and remove duplicated TUI, message, and model-selection helpers across consumers:
  
  - Spinner frames/interval (`PI_SPINNER_FRAMES`, `PI_SPINNER_INTERVAL_MS`) come from pi-kit in agent-teams, memory, recap, and vision.
  - The overlay/console theme style language (`createPiThemeStyle`) comes from pi-kit in btw and agent-teams; `BtwOverlayStyle` aliases `PiThemeStyle`.
  - Message text extraction (`extractTextContent`) comes from pi-kit in btw, recap, vision, utils, and agent-teams.
  - Model selection (`parseModelRef`, `modelRef`, `modelLabel`, `sortModels`, `selectModelFromMenu`, `enterModelFromInput`) comes from pi-kit in memory, recap, and vision.
  - monitor's hand-rolled escape-key check now uses pi-tui's `matchesKey(data, Key.escape)`.
  
  Also fixes a packaging/loading bug in `@fradser/pi-memory`: `config.ts` moved into `extensions/` (it was outside the shipped `files` and the directory-glob the extension loader used), and the `pi.extensions` entry now points at `./extensions/inject-memory.ts` so pi loads exactly the factory file and treats `config.ts` as a helper module.

## 0.5.0

### Minor Changes

- f4fccb1: Republish all published package versions through GitHub CI to align with current release flow and regenerate their release metadata after version comparison.

## 0.4.0

### Minor Changes

- f3b5cd7: Run-centric redesign: declarative agent files + single-call DAG dispatch.
  
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
