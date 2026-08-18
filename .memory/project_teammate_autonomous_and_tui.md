---
name: teammate-autonomous-and-tui
description: Agent Teams (packages/agent-teams) — run-centric: declarative agent files, single-call DAG dispatch, bounded child-process nodes, one-way leader inbox reports, session-wide worker cap, per-spawn identity validation
type: project
---

`packages/agent-teams` is a run-centric multi-agent system: the Pi session is the leader; agents are declarative Markdown files; each run is a dependency-aware task graph dispatched in one call, where each node is a bounded child Pi process and a session-wide cap limits total workers to 8.

**Why:**
The teammate-registry model (runtime `teammate_register`/`create_task`/`start_task` ceremony, session-scoped identities, read receipts) was replaced after a design review. The ceremony critique: a one-off delegation cost 4 tool calls (list/register/create/start), identities were session-ephemeral so registration cost was paid per session, and competitor packages proved single-call DAG dispatch + declarative markdown agents. The later simplification removed the remaining half-channels: workers report only to the leader, upstream DAG results replace peer delivery, and live run status is not injected into every system prompt.

**How to apply:**
1. **Agents are declarative files** (`src/agents.ts`): frontmatter `name`/`description`/`tools`/`model` (inline `#` comments stripped), body = role prompt. Discovery precedence per name: project `.pi/agents/` > user `~/.pi/agent/agents/` > bundled `agents/`. Bundled: worker/reviewer/specialist/observer.
2. **Single-call DAG dispatch** (`teammate_run`): `tasks` with `id`/`agent`/`prompt`/`paths`/`access` (default read)/`dependsOn`/`model`/`timeoutMs`, plus `concurrency` (default 4), `worktree`, `background`, `timeoutMs`, `summarize`, and `summaryAgent`. Validates duplicate ids, unknown dependsOn, cycles, and bad paths before any spawn. Root nodes start immediately; `scheduleRun` auto-starts dependents on completion; write nodes with overlapping paths are deferred across all runs in the session unless worktree-isolated (`findSharedWorkspaceWriteConflict`). A session-wide cap of 8 workers applies across runs.
3. **Leader tools (3)**: `teammate_run`, `teammate_cancel` (run or node-level cancel; SIGTERM→SIGKILL), and `teammate_retry` (retries failed/cancelled nodes without re-running completed ones). There is no leader message, status, wait, inbox, or cleanup tool.
4. **Worker protocol (1 capability tool)**: worker-only `teammate_message` has `subject`/`body`/optional `status` and always reports to the leader. Per-spawn identity: `PI_TEAMMATE_WORKER_NAME` = `runId:nodeId`, `PI_TEAMMATE_SPAWN_ID` = fresh UUID; stale-spawn events are rejected. Reports enter one leader inbox; there are no peer mailboxes, worker inboxes, or leader broadcasts. Upstream DAG results are injected into downstream prompts (`=== UPSTREAM HANDOFF ===`).
5. **Outcomes and persistence**: workers report progress/final deliverables, but the harness creates one canonical terminal result after child close. Reported completion plus harness shutdown remains completed; failed nodes cancel transitive pending dependents. State snapshots are dirty-gated and written as leader-owned debug artifacts; worker task argument temp directories are removed after close or spawn error.
6. **UI**: passive widget (display-only) + `/teammate` full-screen console (owns input via `ctx.ui.custom`, no global interception) — rows are nodes, detail = node lifecycle and leader reports, live activity streams tool calls and thinking deltas, SGR mouse-wheel scrolling.
7. **Testing**: BDD in `features/agent-teams.feature`, package tests in `tests/test_teammate_package.py` including node-eval runtime tests of state.ts/spawner.ts; typecheck via `npx tsc --noEmit --strict ... src/*.ts`.

**Related:** [[pi-cli-print-json-usage]] [[no-global-input-interception]] [[pi-kitty-csi-u-keys]] [[pi-custom-component-rendering]] [[pi-package-conventions]]
