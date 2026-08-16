# Agent Teams Pi Package

Run-centric multi-agent system for Pi — declarative agents, single-call DAG dispatch, bounded child-process nodes with a best-effort mailbox.

**Display Name**: Agent Teams

## What This Package Does

Agents are declarative Markdown files (bundled, user, and project scopes). A run is a dependency-aware task graph dispatched in **one call**: root nodes start immediately, concurrency is bounded, overlapping shared-workspace writes are deferred (advisory coordination across all runs in the session) unless worktree-isolated, and downstream nodes auto-start when their dependencies complete. Each node is a bounded child Pi process with per-spawn identity validation.

## Install

```bash
pi install /path/to/pi-packages/packages/agent-teams
```

Then run `/reload` in Pi.

## Agents are declarative files

Agent definitions are Markdown files with frontmatter; the body is the worker's role prompt.

```markdown
---
name: security-auditor
description: Read-only security reviewer; use after security-sensitive edits
tools: read,bash
model: provider/model   # optional
---
Review the assigned scope for exploitable security problems. Do not edit files.
```

Discovery precedence per name: **project `.pi/agents/` > user `~/.pi/agent/agents/` > bundled package `agents/`**. Bundled agents: `worker`, `reviewer`, `specialist`, `observer`. List them with `teammate_status`.

## Dispatch a run in one call

```text
teammate_run({
  tasks: [
    { id: "inspect", agent: "reviewer", prompt: "Review the auth middleware", paths: ["packages/api/src"], access: "read" },
    { id: "fix", agent: "worker", prompt: "Apply the review findings", paths: ["packages/api"], access: "write", dependsOn: ["inspect"] },
    { id: "verify", agent: "reviewer", prompt: "Verify the fix", paths: ["packages/api"], access: "read", dependsOn: ["fix"] },
  ],
  concurrency: 2,
  worktree: false,
  background: true
})
```

- `access` defaults to `read`; declare `write` explicitly.
- `dependsOn` edges must form a DAG (duplicate ids, unknown references, and cycles are rejected before any worker starts).
- `worktree: true` runs every node in its own git worktree and captures each diff for integration review.
- `background` defaults to `true`: teammates always run in the background — the call returns the run id immediately, the model turn stays free, and one run-completion follow-up is delivered when the run settles. Pass `background=false` to block and gather inline (it detaches after 5 minutes so the turn is never hung).
- `timeoutMs` is a run-level hard cap: when exceeded, the run fails and live workers are terminated.
- Multi-node runs append a `__summary` node by default (`summarize=false` to skip). Single-task runs stay compact unless `summarize=true`.
- Completing a node hands its result to pending dependents (worker prompt + peer message). Workers may also message same-run peers.

## Tools

| Tool | Description |
|---|---|
| `teammate_run` | Dispatch a dependency-aware task graph in one call |
| `teammate_status` | List agents + run overview, or one run's node detail |
| `teammate_cancel` | Cancel a run, or one node (`nodeId`) while the rest continues |
| `teammate_retry` | Re-run only the failed/cancelled nodes of a settled run |
| `teammate_message` | Message the team leader or a node, or broadcast to a run (`to="all"`) |
| `/teammate` | Full-screen console: run/node status, node detail, sent messages, cancel node |

Best-effort snapshot mailbox: workers **send** via `teammate_message` (`team-leader` or a same-run peer) and submit outcomes via `teammate_report`. Delivery is validated and idempotent, but there are no read receipts and no delivery guarantees for worker-bound messages: a message addressed **to** a running worker (leader reply, peer handoff, broadcast) lands in the shared state snapshot, and the worker sees it only if it re-reads that snapshot, so treat worker-bound messages as best-effort. What *is* guaranteed is the DAG handoff — upstream results are injected into downstream prompts (`=== UPSTREAM HANDOFF ===`) by the scheduler.

## Reliability protocol

- **Per-spawn identity validation**: every worker event must match the node's current spawn id; stale events from an older process cannot affect a newer spawn.
- **Best-effort mailbox**: delivery is validated and idempotent (event ids), but no read receipts are exchanged and worker-bound messages are seen only if the worker re-reads the snapshot; read flags are leader-local.
- **One canonical terminal result per node**: built by the harness from node state + captured output after the child closes; a worker's `teammate_report` alone is not final delivery.
- **Advisory write-conflict coordination (session-wide)**: the scheduler never starts a shared-workspace write node while another shared-workspace write node with overlapping paths is running — checked across **all runs in the session**, not just the same run. This is scheduling-level coordination, not isolation.
- **`access`/`paths` are metadata, not enforcement**: they drive conflict scheduling and prompts; a worker's real capabilities come from its agent definition's `tools` list. A `read` node whose agent has `write`/`bash` tools can still write. Use `worktree: true` or a restricted agent tool list when you need actual isolation.
- **Failure semantics**: a failed node cancels its not-yet-started transitive dependents and fails the run; other nodes finish. Cancelling a run or node reports the outcome in the tool call itself — it does not fire an extra completion follow-up.

## State and sessions

State is session-scoped and dies with the session (`~/.pi/agent/teammate/<sessionKey>/`); runs do not survive restarts. `background: true` runs notify via one follow-up; worker messages and node outcomes are recorded in the leader transcript and visible in `/teammate` and `teammate_status`. Agents, by contrast, live in files and survive across sessions — that is the persistent layer.

## Structure

```
agent-teams/
├── package.json       — Pi package manifest
├── agents/            — bundled agent definitions (worker/reviewer/specialist/observer)
├── src/
│   ├── index.ts       — extension: tools, run scheduler, widget + /teammate console
│   ├── agents.ts      — declarative agent discovery (frontmatter parsing, scope precedence)
│   ├── state.ts       — runs/nodes state machine, mailbox, settlement
│   ├── spawner.ts     — child Pi worker spawner (JSON-mode, usage accounting)
│   ├── statefile.ts   — shared state file + worker outbox IO
│   ├── worktree.ts    — git worktree isolation
│   ├── console-viewport.ts — console viewport math (wrap, scroll clamp, ranges)
│   └── terminal.ts    — canonical per-node terminal result builder
├── features/          — BDD contract
└── tests/             — package E2E tests
```

## License

MIT
