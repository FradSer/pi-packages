# Agent Teams Pi Package

Run-centric multi-agent system for Pi: declarative agents, single-call DAG dispatch, bounded child-process nodes, and one-way worker messages to the leader.

**Display Name**: Agent Teams

## What This Package Does

Agents are declarative Markdown files (bundled, user, and project scopes). A run is a dependency-aware task graph dispatched in **one call**: root nodes start immediately, concurrency is bounded, and downstream nodes auto-start when their dependencies complete. Multiple teammates may operate on the same paths concurrently and coordinate through `teammate_message`. Each node is a bounded child Pi process with per-spawn identity validation.

`paths` and `access` are scheduling and prompt metadata. `paths` identifies the repository-relative area included in the worker prompt; `access` declares read or write intent. They do not enforce filesystem permissions or provide true read/write isolation. Multiple teammates may operate on the same paths concurrently and coordinate through `teammate_message`; `worktree: true` provides Git worktree separation when needed. There is no OS or container sandbox. A worker's actual capabilities come from the `tools` list in its resolved agent definition.

## Install

```bash
pi install /path/to/pi-packages/packages/agent-teams
```

Then run `/reload` in Pi.

## Agents Are Declarative Files

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

Discovery precedence per name: **project `.pi/agents/` > user `~/.pi/agent/agents/` > bundled package `agents/`**. Bundled agents: `worker`, `reviewer`, `specialist`, `observer`. Available agents are dynamically injected into prompt guidance via `before_agent_start`.

## Dispatch a Run in One Call

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

- `access` defaults to `read`; declare `write` explicitly. This is scheduling and prompt metadata, not a capability boundary.
- `dependsOn` edges must form a DAG (duplicate ids, unknown references, and cycles are rejected before any worker starts).
- `worktree: true` runs every node in its own Git worktree and captures each diff for integration review. It does not create an OS or container sandbox.
- `background` defaults to `true`: teammates run in the background, the call returns the run id immediately, and each teammate's terminal outcome sends its full deliverable in an immediate follow-up while the remaining teammates continue. A final run-completion follow-up is sent after all nodes settle. Pass `background=false` to gather inline; a long gather detaches to the background so the model turn is not left hanging.
- `turnBudget` is the optional per-node maximum assistant-turn budget and defaults to a high safety cap of 100 turns. There is no run-level or node-level wall-clock deadline field.
- A session-wide cap of 8 worker processes applies in addition to each run's `concurrency` limit.
- Multi-node runs append a `__summary` node by default (`summarize=false` to skip). Single-task runs stay compact unless `summarize=true`.
- Completing a node hands its result to pending dependents through the spawned worker prompt. Workers receive only the context supplied by their task, including the DAG handoff.

## Tools

| Tool | Description |
|---|---|
| `teammate_run` | Dispatch a dependency-aware task graph in one call |
| `teammate_fanout` | Leader-only bounded fanout from a completed node's structured array output |
| `teammate_message` | Worker capability for one-way progress and final deliverables to the leader; leader-side runtime steering for a running RPC worker |
| `teammate_cancel` | Cancel a run, or one node (`nodeId`) while the rest continues |
| `teammate_retry` | Re-run only the failed or cancelled nodes of a settled run |
| `/teammate` | Full-screen console: run/node lifecycle, node detail, worker messages, and node cancellation |

The worker-side `teammate_message` accepts a subject, body, optional lifecycle status, and optional structured data. It always delivers to the team leader. The leader-side operation uses the same tool name only to steer a running RPC worker; it does not create a mailbox.

Messaging is deliberately one-way: workers append validated messages to their own outbox, and the leader drains them into one leader inbox. Dependency results are delivered through the DAG prompt (`=== UPSTREAM HANDOFF ===`) when the dependent starts.

## Reliability Protocol

- **Per-spawn identity validation**: every worker event must match the node's current spawn id; stale events from an older process cannot affect a newer spawn.
- **One-way message storage**: worker event ids and per-spawn identities are validated and deduplicated; every accepted message lands in the single leader inbox. The harness does not maintain read receipts or per-worker inbound state.
- **One canonical terminal result per node**: built by the harness from node state and captured output after the child closes; a worker message alone is not final delivery.
- **Concurrent same-path execution**: teammates that share paths run in parallel and coordinate through `teammate_message` (e.g. announcing intent, negotiating file ownership). `worktree: true` is opt-in for Git-level isolation, not scheduling enforcement.
- **Metadata is not enforcement**: `access` and `paths` drive conflict scheduling and prompt context. A worker whose agent definition has write-capable tools can still write even when a node declares `access: "read"`. Use a restricted agent tool list for capability limits, and use `worktree: true` for Git tree separation.
- **Failure semantics**: a failed node cancels its not-yet-started transitive dependents and fails the run; other nodes finish. Cancelling a run or node returns the outcome in the tool call itself.

## State and Sessions

State is session-scoped and dies with the session (`~/.pi/agent/teammate/<sessionKey>/`); runs do not survive restarts. Background runs notify through automatic follow-ups; worker messages and node outcomes are recorded in the leader transcript and visible in `/teammate`. Agents, by contrast, live in files and survive across sessions: they are the persistent layer.

## Structure

```
agent-teams/
├── index.ts           — package-root extension entry point
├── package.json       — Pi package manifest
├── agents/            — bundled agent definitions (worker/reviewer/specialist/observer)
├── src/
│   ├── index.ts       — composition root: Pi hooks and session lifecycle
│   ├── tools.ts       — leader tools and /teammate command registration
│   ├── run-machine.ts — DAG scheduler, worker lifecycle, persistence, session cap
│   ├── ui.ts          — passive widget and /teammate console
│   ├── worker.ts      — worker identity binding and message capability
│   ├── guidance.ts    — static leader/worker protocol guidance
│   ├── agents.ts      — declarative agent discovery (frontmatter parsing, scope precedence)
│   ├── state.ts       — runs/nodes state machine, leader inbox, dirty tracking
│   ├── spawner.ts     — child Pi worker spawner (JSON-mode, usage accounting)
│   ├── statefile.ts   — leader snapshot + worker outbox IO
│   ├── worktree.ts    — Git worktree isolation
│   ├── console-viewport.ts — console viewport math (wrap, scroll clamp, ranges)
│   └── terminal.ts    — canonical per-node terminal result builder
├── features/          — BDD contract
└── tests/             — package E2E tests
```

## License

MIT
