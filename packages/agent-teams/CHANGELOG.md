# @fradser/pi-agent-teams

## 0.7.0

### Minor Changes

- d37028f: Unify collapsible event rows on the shared pi-kit expand hint and fix the teammate shutdown label: `teammate_shutdown` now renders one `[agent] event · @name shut down` row (previously mislabeled as a monitor event) whose collapsed line appends the same dim ` · <configured key> to expand` hint as teammate report rows, with the shutdown details (exit code, released tasks, usage) revealed behind expansion. `formatExpandHint` moves the hint language into `@fradser/pi-kit`, replacing the hand-rolled variants in agent-teams, monitor, and utils. Leader `send_message` adopts the same single-row lifecycle pattern: the call slot renders nothing and one `[message] to @name · steered|queued` row carries only the synchronous routing outcome, replacing the duplicated call-plus-sentence transcript rows. Teammate stall health renders independently as an `[agent] event` rather than decorating a message row. `task_create` gets the same treatment with a `[board] created · <subject>` row; all leader tool renderers now key failures off pi's render-context `isError` flag instead of the result object. A teammate's completion entry ("Teammate @name finished.") is announced once per spawn incarnation: reports now carry the spawn identity, so repeated terminal-status messages from one resident render as ordinary report rows instead of duplicate finished lines, while a respawned teammate of the same name announces again.

### Patch Changes

- 82b8e8b: Honor multi-line YAML tool lists in agent frontmatter and make unfinalized teammate reports self-finalize before escalating. `parseFrontmatter` now parses dash-list `tools:` blocks — flush-left or indented items, interleaved blank/comment lines, no-space `-item` entries — which previously collapsed silently into an empty execution allowlist. When a teammate's sequence ends while its last leader-bound report lacks terminal status, the machine drains outboxes before deciding, sends one inbox finalize request per spawn incarnation instructing `status="completed"`/`status="failed"`, escalates to the leader reminder only on a second miss, cleans up nudge bookkeeping on every shutdown path, and the worker-side `send_message` result reminds when a leader-bound message carries no terminal status.
- Updated dependencies [d37028f]
  - @fradser/pi-kit@0.3.0

## 0.6.0

### Minor Changes

- 7ad11b4: Rebuild Agent Teams as a Claude-Code-style collaborative organization layer: named resident teammates (long-lived RPC child processes), a shared task board with atomic self-claim and verify-gated completion, and direct peer-to-peer inbox messaging. The former DAG API (`teammate_run`, `teammate_fanout`, `teammate_cancel`, `teammate_retry`) remains removed. Simplify the new team surface to seven unique tool names: `send_message(to, message, status?)` is the one messaging primitive for worker reports, peer mail, and leader steering; `task_list` is shared by both sides; and `teammate_spawn` now accepts only name, agent, and optional prompt, with model/worktree moved to declarative agent frontmatter.
  Agent definitions gain a fourth scope for custom teammates: inside `.pi/agents/`, a `<name>.local.md` file declares a personal project-local override that stays out of version control, while `<name>.md` remains the git-managed team-shared layer; same-name pairs deduplicate into one definition with local winning. Precedence is project-local > project > user > bundled, and `resolveAgent` exposes each definition's scope and gitManaged flag so guidance and tooling can show provenance.
- 7ad11b4: Add an output-silence heartbeat for resident teammates. A teammate wedged mid-turn (for example, blocked forever in a provider request) never accumulates assistant turns and produces no RPC output, so nothing could alert anyone while the roster showed "working" indefinitely. The harness poll now tracks `lastOutputAt`: after 30 minutes without any output (`PI_TEAMMATE_STALL_NOTICE_MS`, 0 disables) the leader receives one actionable notice per silence episode naming the teammate and its recovery options. The notice is the last automatic action — continuing, steering, shutting down, or respawning a context-carrying successor belongs to the leader alone. Any stream activity or prompt delivery re-arms the watchdog. The health notice states that steer delivery may be uncertain without changing the message-routing result, and the widget, console roster, and detail views show how long a working teammate has been silent.
- acbadc7: Adopt full teammate autonomy as the package constitution: the harness detects and notifies, the leader model decides — no configuration may automatically terminate a working teammate. Remove the per-wake-up turn budget (the former 100-assistant-turn ceiling that silently killed long sequences) and do not ship any duration-based auto-reclaim. Turn counts and silence durations remain visible as telemetry and heartbeat signals; the stall notice is informational and names the recovery options (keep waiting, steer again, shut down, or respawn a successor whose prompt composes context from the original kickoff, mailbox reports, board claims, and the console detail transcript). Leader guidance gains a "recover, never punish" section teaching this workflow.

### Patch Changes

- 1503fdb: Use `teammate_message` for teammate completion and run notifications instead of the legacy `teammate-update` custom message type.
- Updated dependencies [50c45ff]
- Updated dependencies [7ad11b4]
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
