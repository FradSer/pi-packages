# @fradser/pi-agent-teams

## 0.8.1

### Patch Changes

- Updated dependencies
  - @fradser/pi-kit@0.4.1

## 0.8.0

### Minor Changes

- dcf3806: Deliver every teammate report to the leader: intermediate send_message(to="leader") reports now reach the leader as their own follow-up turn instead of parking in the console-only mailbox, and queued reports are never coalesced — one message, one leader turn, in arrival order, with an authored-at timestamp in the envelope. Leader-relevant harness events ride the same channel: clean-shutdown summaries, worktree diff notices (bounded preview plus branch retrieval command), and verify-gate escalations; task outcome notices and operational diagnostics stay console-log only to avoid double reporting. Worktree cleanup now commits remaining work onto the kept branch before removing the directory — previously the branch deletion destroyed uncommitted captured work — while failed-spawn teardown still deletes the empty branch. Worker guidance rations messages by value instead of throttling: every leader-bound message costs a full turn, bare status pings are forbidden.
- 953f548: Two-tier stall watchdog: a working teammate silent since spawn with zero lifetime model output and no running tool — the provider-hang signature — is flagged after five minutes (`PI_TEAMMATE_SILENT_STALL_MS`, 0 disables) instead of the general thirty-minute window. Stall notices carry silence duration, spawn age, and lifetime token/cost diagnostics, and the zero-output notice names shutdown plus respawn as the effective remedy since steering cannot unstick an in-flight request. Streaming usage is now persisted to the roster, making zero-token hangs visible before shutdown.
- 9a80d93: Fixes from the first live analysis of the stall watchdog and tool-grant work, plus the delivery-gap root cause it surfaced: a spawned teammate runs its kickoff turn immediately, so marking prompt-less spawns idle at birth mislabeled an actively-running turn as idle — queued leader messages were then delivered into that running turn and lost (the teammate kept reporting "board empty" until a steer landed). Status now stays "starting" until real stream events arrive and flows starting→working→idle from stream truth. The provider-hang classifier now keys on recognized stream activity (text/thinking/toolcall/tool events) instead of usage totals — providers that omit usage after real output are no longer misclassified, and an empty message_end artifact never counts; usage stays diagnostics. The grant is flushed to both rosters before the kickoff is written, and historical spawn renders read persisted details only so name reuse cannot display another incarnation's allowlist.
- ab0feb8: Spawn surfaces now expose each teammate's effective tool allowlist: `teammate_spawn` records the granted tools in the roster before the first wake, the spawn result line and console detail name them, and a role derived inline without a `tools` field visibly shows its narrow capability-only grant. Leader guidance now requires matching definition tools to the assignment — file-inspecting work needs explicit `read`/`bash` — and prescribes shutdown-plus-respawn instead of steering when capabilities are missing. This prevents workers from burning turns discovering they cannot execute their kickoff.
- a7fbc11: Agent teams: `model: inherit` resolves to the leader session's current model at spawn time, and `/agent-teams` gains a type-to-filter picker (`m` in the roster page) that sets a session-wide teammate model — precedence: role pin > inherit > team default > Pi default. Task/role `verify` gates are now review prompts judged by a fresh one-shot reviewer answering `VERDICT: PASS/FAIL` instead of shell commands.

### Patch Changes

- dcf3806: Dispatch the first teammate report to Pi's native follow-up queue even while the leader is active, rather than holding it in Agent Teams until the complete leader run settles. Later reports remain FIFO-serialized until the dispatched report settles.
- dcf3806: Keep requested teammate shutdowns in the tool lifecycle and console instead of emitting misleading agent-message follow-ups, and use an explicit harness-event envelope for lifecycle diagnostics that do wake the leader.
- fde16ae: The leader's send_message no longer rejects a stray `status` field with "status is reserved for worker reports to=leader". The shared message schema exposes `status` to leaders too, and leader models occasionally copy it from worker report patterns — which hard-failed the call and blocked teammate delivery (observed live in hud-playground). A stray status on a leader-sent message is now ignored with a one-line corrective note appended to the tool result, and the leader tool description no longer mentions `status` at all. Worker-side semantics are unchanged: status is still honored only for reports addressed to "leader".
- fde16ae: Clarify message routing truth: active control-stream writes render as `steered`, inbox/outbox and wake-up paths render as `queued`, and neither outcome implies recipient processing. Stall diagnostics now render independently as teammate health events instead of message suffixes.
- fde16ae: Route every Agent Teams tool transcript renderer through pi-kit's shared started/event lifecycle abstraction, including worker task and messaging tools, with common width truncation, expansion, and error-row behavior.
- dcf3806: Reject non-finite teammate report timestamps and keep malformed metadata from interrupting follow-up delivery.
- dcf3806: End the current worker turn after a terminal leader report, and suppress subsequent reports until a new wake-up while preserving distinct intermediate reports and assignment boundaries.
- fde16ae: Clarify task creation handoff: `task_create` now reports that it never spawns teammates, identifies the current session board, immediately offers newly-created work to existing idle teammates, and explains how pending work proceeds when no teammate is available.
- dcf3806: Preserve the configured expand hint for lifecycle tool rows when a result has structured details but an empty visible content body, such as teammate_spawn's `{ started: true }` result. The title truncates before the hint so `ctrl+o to expand` remains visible within the available TUI width.
- dcf3806: Fix a crash when lifecycle tool rows render with pi's class-based Theme: extracting `theme.bg` into a local and calling it unbound lost the receiver, so any teammate/worktree tool result row threw `TypeError: Cannot read properties of undefined (reading 'bgColors')` (uncaughtException exiting pi). Lifecycle renderers now call theme methods through their receiver, with class-based-theme regression coverage. Unify the report-row visual language in pi-kit: every lifecycle row and collapsed teammate-message row share one full-width `customMessageBg` band (blank band row above/below, one-column inset), a `customMessageLabel`-colored bold `[tool] label ·` prefix, and per-teammate accent colors from pi-kit's stable palette applied to @name segments. Teammate report rows render `[message] from @name · <key> to expand` through the shared `renderAgentMessageBand` abstraction instead of their private Box, and agent startup rows use the explicit `[agent] @name started · task` shape. Remove the hard 80-character task-name cap so lifecycle rows truncate only at the actual terminal width; fixed session panels keep an explicit local width bound. Truncated band rows no longer lose the band background: truncating a styled row injects a full SGR reset (\x1b[0m) before the ellipsis that also cleared the customMessageBg, so pi-kit now re-applies the background immediately after every reset — the ellipsis and trailing padding keep the same band color as the preceding text.
- Updated dependencies [fde16ae]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [dcf3806]
- Updated dependencies [a7fbc11]
  - @fradser/pi-kit@0.4.0

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
