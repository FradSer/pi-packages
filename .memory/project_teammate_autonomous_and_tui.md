---
name: teammate-autonomous-and-tui
description: Agent Teams — declarative agent files, run-scoped DAG task dispatch, leader-owned state, nonblocking execution, and passive widget + /teammate console
type: project
---

`packages/agent-teams` provides multi-agent orchestration for Pi: the current Pi session is the team leader and sole `state.json` writer. Agents are declarative Markdown definitions; tasks are dispatched as dependency-aware DAG runs via `teammate_run`. Child Pi processes run autonomously and emit append-only events to per-run outboxes under `~/.pi/agent/teammate/<sessionKey>/events/`.

**Why:**
Earlier versions used runtime teammate registration (`teammate_register`/`teammate_configure`) and manual sleep-polling; the TUI panel used global key interception and broke pi's model selector. The redesign replaced runtime registration with declarative agent files (`.pi/agents` > `~/.pi/agent/agents` > bundled), introduced single-call DAG dispatch (`teammate_run`), and moved all interactive UI into a full-screen console that owns input.

**How to apply:**
1. **Declarative agents**: Agents live in Markdown files with frontmatter (`name`, `description`, `tools`, optional `model`) and a role prompt body. Discovery precedence per name: project `.pi/agents` > user `~/.pi/agent/agents` > bundled `packages/agent-teams/agents/*.md` (`worker`, `reviewer`, `specialist`, `observer`). `teammate_status` lists available agents.
2. **DAG task runs (`teammate_run`)**: Dispatch a complete task graph in one call. Each task declares `id`, `agent`, `prompt`, `paths`, `access` (`read` default, `write` explicit), optional `dependsOn`, `model`, and `timeoutMs`. Root nodes start immediately; downstream nodes auto-start when dependencies complete. Foreground (default) gathers results in the tool call; `background=true` returns the run ID immediately and delivers one follow-up on completion.
3. **Leader-owned state + worker outboxes** (`src/statefile.ts`): Parent atomically publishes `state.json` before spawn and after leader updates. Each spawn receives a fresh `runId` and per-run JSONL outbox. `applyWorkerEvents()` drains complete records, validates worker identity, run ownership, recipient, and event shape before applying state changes in leader memory.
4. **Coordination & isolation**: Paths define coordination scope, not permanent locks. Overlapping read tasks run concurrently; overlapping shared-workspace writes are blocked at start unless `worktree=true` is set (which runs the worker in `.pi/worktrees/teammate-<taskId>`).
5. **Worker capabilities**: Child processes running in worker mode register only `teammate_message`, `teammate_inbox`, and `teammate_report`. They execute one bounded task run, record plan/progress/blockers to the leader mailbox, report the outcome, and exit. Normal exit code `0` is required for success; signal termination, timeout, or non-zero exit fail the node and cancel downstream dependents.
6. **Cost accounting**: Worker usage (tokens and cost) is parsed from child JSONL stream `message_end` events into run node metadata — see [[pi-cli-print-json-usage]].
7. **Leader tool surface**: Leader tools are `teammate_run`, `teammate_status`, `teammate_wait`, `teammate_cancel`, `teammate_cleanup`, `teammate_message`, and `teammate_inbox`. `teammate_wait` is the explicit barrier for background runs; `teammate_cancel` stops active workers via SIGTERM/SIGKILL escalation; `teammate_cleanup` prunes terminal runs.
8. **TUI (no global key interception)**: Passive `setWidget` above the editor displays team/run status with a braille spinner. `/teammate` opens a full-screen console (`ctx.ui.custom`, owns input) styled matching `@packages/btw` (top/bottom borders, accent header, dim shortcuts footer). Supports ↑/↓ navigation, Enter open run/node, `r` reply, `x` stop, Esc back/close. Viewport wrapping wraps source lines to fit terminal width.
9. **Lifecycle & cleanup**: Worker identities and runs are ephemeral to the session. On session start, state initializes empty; on session shutdown, live children are terminated before temporary directories are removed.

**Related:** [[pi-cli-print-json-usage]] [[no-global-input-interception]] [[pi-kitty-csi-u-keys]] [[pi-custom-component-rendering]] [[pi-package-conventions]]
