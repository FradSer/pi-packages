# Agent Teams Pi Package

Run-centric multi-agent system for Pi — declarative agents, single-call DAG dispatch, bounded child-process nodes with a best-effort mailbox.

**Version**: 0.3.0
**Display Name**: Agent Teams

## What This Package Does

Agents are declarative Markdown files (bundled, user, and project scopes). A run is a dependency-aware task graph dispatched in **one call**: root nodes start immediately, concurrency is bounded, overlapping shared-workspace writes are blocked unless worktree-isolated, and downstream nodes auto-start when their dependencies complete. Each node is a bounded child Pi process with per-spawn identity validation.

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
  background: false
})
```

- `access` defaults to `read`; declare `write` explicitly.
- `dependsOn` edges must form a DAG (duplicate ids, unknown references, and cycles are rejected before any worker starts).
- `worktree: true` runs every node in its own git worktree and captures each diff for integration review.
- `background: false` (default) gathers node results in the tool call; `foregroundTimeoutMs` (default 5 min) detaches a still-running run to background so the model turn is never hung. `background: true` returns the run id immediately and delivers one run-completion follow-up.
- `timeoutMs` is a run-level hard cap: when exceeded, the run fails and live workers are terminated.
- `summarize: true` appends a `__summary` node after every leaf node that reads all results and synthesizes one final run summary (use for multi-node runs); tool returns show it instead of per-node output. Without it, returns list node statuses only — detail lives in `teammate_status runId` and `teammate_inbox`.

## Tools

| Tool | Description |
|---|---|
| `teammate_run` | Dispatch a dependency-aware task graph in one call (`timeoutMs` run cap, `foregroundTimeoutMs` detach cap) |
| `teammate_status` | List agents + run overview, or one run's node detail |
| `teammate_wait` | Explicit gather barrier for background runs |
| `teammate_cancel` | Cancel a run, or one node (`nodeId`) while the rest continues |
| `teammate_retry` | Re-run only the failed/cancelled nodes of a settled run |
| `teammate_cleanup` | Prune terminal runs after their results are synthesized |
| `teammate_message` | Message a node (`runId:nodeId`) or broadcast to a run (`to="all"`) |
| `teammate_inbox` | Read the main session's mailbox (`unreadOnly`) |
| `/teammate` | Full-screen console: run/node status, node detail, live worker text, stop |

Spawned workers receive only `teammate_message` (to `agent` only), `teammate_inbox`, and `teammate_report` — identity-bound to their node.

## Reliability protocol

- **Per-spawn identity validation**: every worker event must match the node's current spawn id; stale events from an older process cannot affect a newer spawn.
- **Best-effort mailbox**: delivery is validated and idempotent (event ids), but no read receipts are exchanged; read flags are leader-local.
- **One canonical terminal result per node**: built by the harness from node state + captured output after the child closes; a worker's `teammate_report` alone is not final delivery.
- **Write conflict protection**: two write nodes with overlapping paths never run concurrently in the shared workspace unless worktree-isolated.
- **Failure semantics**: a failed node cancels its not-yet-started transitive dependents and fails the run; other nodes finish.

## State and sessions

State is session-scoped and dies with the session (`~/.pi/agent/teammate/<sessionKey>/`); runs do not survive restarts. `background: true` runs notify via one follow-up; intermediate worker messages stay in the mailbox until you read them with `teammate_inbox`. Agents, by contrast, live in files and survive across sessions — that is the persistent layer.

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
│   └── terminal.ts    — canonical per-node terminal result builder
├── features/          — BDD contract
└── tests/             — package E2E tests
```

## License

MIT
