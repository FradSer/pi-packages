# Agent Teams Pi Package

Run-centric multi-agent system for Pi — declarative agents, single-call DAG dispatch, bounded child-process nodes with a leader inbox and push-only node message transcripts.

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

Discovery precedence per name: **project `.pi/agents/` > user `~/.pi/agent/agents/` > bundled package `agents/`**. Bundled agents: `worker`, `reviewer`, `specialist`, `observer`. Available agents are dynamically injected into prompt guidance via `before_agent_start`.

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
- `background` defaults to `true`: teammates always run in the background — the call returns the run id immediately, the model turn stays free, and workers message `team-leader` (`teammate_message`) with their deliverables upon completion, delivered automatically as a follow-up turn. The team leader does not sleep or busy-wait while tasks execute. Pass `background=false` to block and gather inline (it detaches after 5 minutes so the turn is never hung).
- `timeoutMs` is a run-level hard cap: when exceeded, the run fails and live workers are terminated.
- Multi-node runs append a `__summary` node by default (`summarize=false` to skip). Single-task runs stay compact unless `summarize=true`.
- Completing a node hands its result to pending dependents through the spawned worker prompt. Workers may also send same-run peer messages for the leader transcript; peer inbox delivery is intentionally omitted.

## Tools

| Tool | Description |
|---|---|
| `teammate_run` | Dispatch a dependency-aware task graph in one call |
| `teammate_cancel` | Cancel a run, or one node (`nodeId`) while the rest continues |
| `teammate_retry` | Re-run only the failed/cancelled nodes of a settled run |
| `teammate_message` | Message the team leader or a node, or broadcast to a run (`to="all"`) |
| `/teammate` | Full-screen console: run/node status, node detail, sent messages, cancel node |

Message storage is deliberately narrow: worker reports and leader-bound messages go to one leader inbox; each node keeps a push-only `sentMessages` transcript for `/teammate`; leader replies and broadcasts go to the target node's `inboxMessages` in the shared snapshot. Worker-to-worker mailbox delivery is not performed. Workers can still address same-run peers for a validated transcript entry, but dependency results are delivered through the DAG prompt (`=== UPSTREAM HANDOFF ===`) when the dependent starts.

## Reliability protocol

- **Per-spawn identity validation**: every worker event must match the node's current spawn id; stale events from an older process cannot affect a newer spawn.
- **Narrow message storage**: worker event ids are validated and deduplicated; leader-bound reports use the leader inbox, node sent transcripts are push-only, and leader-to-worker messages are best-effort snapshot inbox entries. No read flags or receipts exist.
- **One canonical terminal result per node**: built by the harness from node state + captured output after the child closes; a worker's message with status alone is not final delivery.
- **Advisory write-conflict coordination (session-wide)**: the scheduler never starts a shared-workspace write node while another shared-workspace write node with overlapping paths is running — checked across **all runs in the session**, not just the same run. This is scheduling-level coordination, not isolation.
- **`access`/`paths` are metadata, not enforcement**: they drive conflict scheduling and prompts; a worker's real capabilities come from its agent definition's `tools` list. A `read` node whose agent has `write`/`bash` tools can still write. Use `worktree: true` or a restricted agent tool list when you need actual isolation.
- **Failure semantics**: a failed node cancels its not-yet-started transitive dependents and fails the run; other nodes finish. Cancelling a run or node reports the outcome in the tool call itself — it does not fire an extra completion follow-up.

## State and sessions

State is session-scoped and dies with the session (`~/.pi/agent/teammate/<sessionKey>/`); runs do not survive restarts. `background: true` runs notify via one follow-up; worker messages and node outcomes are recorded in the leader transcript and visible in `/teammate`. Agents, by contrast, live in files and survive across sessions — that is the persistent layer.

## Structure

```
agent-teams/
├── package.json       — Pi package manifest
├── agents/            — bundled agent definitions (worker/reviewer/specialist/observer)
├── src/
│   ├── index.ts       — extension: tools, run scheduler, widget + /teammate console
│   ├── agents.ts      — declarative agent discovery (frontmatter parsing, scope precedence)
│   ├── state.ts       — runs/nodes state machine, message storage, settlement
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
