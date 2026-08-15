---
name: teammate-autonomous-and-tui
description: Agent Teams (packages/agent-teams) — run-centric: declarative agent files, single-call DAG dispatch, bounded child-process nodes, best-effort mailbox, per-spawn identity validation
type: project
---

`packages/agent-teams` is a run-centric multi-agent system: the Pi session is the leader; agents are declarative Markdown files; each run is a dependency-aware task graph dispatched in one call, where each node is a bounded child Pi process.

**Why:**
The teammate-registry model (runtime `teammate_register`/`create_task`/`start_task` ceremony, session-scoped identities, read receipts) was replaced after a design review. The ceremony critique: a one-off delegation cost 4 tool calls (list/register/create/start), identities were session-ephemeral so registration cost was paid per session, and competitor packages (pi-maestro-teammate, pi-mesh) proved single-call DAG dispatch + declarative markdown agents. User decision (2026-08): replace (remove obsolete paths), keep runId validation, keep mailbox but best-effort, cut the read-receipt protocol, and make output compact with structured summary synthesis.

**How to apply:**
1. **Agents are declarative files** (`src/agents.ts`): frontmatter `name`/`description`/`tools`/`model` (inline `#` comments stripped), body = role prompt. Discovery precedence per name: project `.pi/agents/` > user `~/.pi/agent/agents/` > bundled `agents/`. Bundled agents: worker/reviewer/specialist/observer.
2. **Single-call DAG dispatch** (`teammate_run`): `tasks` with `id`/`agent`/`prompt`/`paths`/`access` (default read)/`dependsOn`/`model`/`timeoutMs`, plus `concurrency` (default 4), `worktree`, `background`, `foregroundTimeoutMs`, `timeoutMs`, `summarize`, and `summaryAgent`. Validates dup ids, unknown dependsOn, cycles, and bad paths before spawn. Root nodes start immediately; `scheduleRun` auto-starts dependents on completion; write nodes with overlapping paths are deferred unless worktree-isolated (`findSharedWorkspaceWriteConflict`, run-scoped).
3. **Leader tools (8)**: `teammate_run`, `teammate_status` (agents + run overview, or runId node detail), `teammate_wait` (gather barrier for runIds), `teammate_cancel` (run or `nodeId` node-level cancel; marks cancelled BEFORE terminating workers so settleRun cannot reclassify; SIGTERM→SIGKILL), `teammate_retry` (retries failed/cancelled nodes without re-running completed ones), `teammate_cleanup` (prunes terminal runs), `teammate_message` (to `runId:nodeId` or `all` + runId), `teammate_inbox`.
4. **Worker protocol** (3 tools): `teammate_message` (agent or peer node key, validated against snapshot), `teammate_inbox` (no receipts), `teammate_report` (bound to node). Per-spawn identity: `PI_TEAMMATE_WORKER_NAME` = `runId:nodeId`, `PI_TEAMMATE_RUN_ID` = fresh UUID; `applyWorkerEvents` rejects stale-spawn events. Mailbox is best-effort, idempotent by event id.
5. **Execution & timeouts**: Foreground gather detaches to background when `foregroundTimeoutMs` (default 5 min) is exceeded so the model turn is never hung; run-level `timeoutMs` fails the whole run past its cap; node-level `timeoutMs` bounds individual workers. Failed nodes cancel transitive pending dependents (`cancelBlockedDependents`) and fail the run. Worktree per node (`createWorktree(run.cwd, "${runId}-${nodeId}")`) isolates writes and captures git diff for review.
6. **Output conciseness**: Tool returns (`run`, `wait`, follow-ups) emit compact status summaries. Per-node rows are status-only without arbitrary truncation heuristics; `summarize: true` appends a `__summary` node (using `summaryAgent`, default `observer`) after all leaf nodes that synthesizes a final structured summary into `run.summary`.
7. **UI**: passive widget (display-only) + `/teammate` full-screen console (owns input via `ctx.ui.custom`, no global interception) — rows are nodes, detail = node conversation + spawn. Follows `@packages/btw` style language.
8. **Testing**: BDD in `features/teammate-status.feature`, 28 pytest cases (`tests/test_teammate_package.py`) including node-eval runtime tests of state.ts/spawner.ts; typecheck via `npx tsc --noEmit --strict ... src/*.ts`.

**Related:** [[pi-cli-print-json-usage]] [[no-global-input-interception]] [[pi-kitty-csi-u-keys]] [[pi-custom-component-rendering]] [[pi-package-conventions]]
