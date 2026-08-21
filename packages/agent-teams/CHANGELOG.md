# @fradser/pi-agent-teams

## 0.5.3

### Patch Changes

- 1503fdb: Use `teammate_message` for teammate completion and run notifications instead of the legacy `teammate-update` custom message type.
- Updated dependencies [50c45ff]
  - @fradser/pi-kit@0.2.0

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
  
  - `teammate_run` dispatches a dependency-aware task graph in one call. Tasks support `dependsOn`, per-node `access`/`model`/`turnBudget`, `concurrency`, `worktree`, and `background`; root nodes start immediately, downstream nodes auto-start when dependencies complete, and overlapping shared-workspace writes are deferred through advisory scheduling coordination.
  - The leader surface is `teammate_run`, `teammate_fanout`, `teammate_message` (for steering a running RPC worker), `teammate_cancel`, and `teammate_retry`.
  - The worker capability is `teammate_message` (progress, blockers, and final deliverables to the leader). There is no peer delivery, worker inbox, leader broadcast, or separate worker report capability.
  - Removed: `teammate_wait` (replaced by automatic completion follow-ups and inline gather), `teammate_cleanup`, `teammate_inbox`, and the legacy registry tools (`teammate_register`, `teammate_list`, `teammate_configure`, `teammate_remove`, `teammate_create_task`, `teammate_list_tasks`, `teammate_start_task`, `teammate_cancel_task`).
  - Agents are now declarative Markdown files (bundled `agents/`, user `~/.pi/agent/agents/`, project `.pi/agents/`; project > user > bundled).
  - Messages are validated through per-worker append-only outboxes and collected in one leader inbox; DAG handoffs inject upstream results into downstream prompts (`=== UPSTREAM HANDOFF ===`).
  - Advisory write-conflict coordination spans all runs in the session: overlapping shared-workspace write nodes are deferred unless worktree-isolated. `paths` and `access` are scheduling and prompt metadata, not filesystem permissions; there is no OS or container sandbox and no true read/write enforcement.
  - Full-screen `/teammate` console with live activity stream and mouse-wheel scrolling.
  - Worker protocol keeps per-spawn identity validation, one canonical terminal result per node, SIGTERM->SIGKILL cancellation.

## 0.3.0

### Minor Changes

- e16cd3f: Run-centric redesign: declarative agent files + single-call DAG dispatch.
  
  Breaking tool-surface change (replaces the teammate-registry model):
  
  - `teammate_run` dispatches a dependency-aware task graph in one call with `dependsOn`, per-node `access`/`model`/`turnBudget`, `concurrency`, `worktree`, and `background`. Root nodes start immediately; downstream nodes auto-start after dependencies complete; overlapping shared-workspace writes are deferred through advisory scheduling coordination.
  - Automatic completion follow-ups for background runs, bounded inline gather, `teammate_fanout`, `teammate_cancel`, `teammate_retry`, and leader-side RPC steering through `teammate_message` provide the run lifecycle surface.
  - Removed: `teammate_register`, `teammate_list`, `teammate_configure`, `teammate_remove`, `teammate_create_task`, `teammate_list_tasks`, `teammate_start_task`, and `teammate_cancel_task`.
  - Agents are now declarative Markdown files (bundled `agents/`, user `~/.pi/agent/agents/`, project `.pi/agents/`; project > user > bundled).
  - Read-receipt protocol removed: messages have no read flags or receipt events.
  - Workers use the worker-only `teammate_message` capability for progress and final deliverables. Messages have one destination: the leader's inbox; there are no peer mailboxes, worker inboxes, leader broadcasts, or separate report capability. DAG prompt handoffs provide upstream results to dependent workers.
  - `paths` and `access` coordinate scheduling and prompt context only. Shared-workspace protection is advisory write/write coordination; it is not true read/write enforcement and does not provide an OS or container sandbox.
  - Worker protocol keeps per-spawn identity validation, one leader inbox, one canonical terminal result per node, SIGTERM->SIGKILL cancellation.
