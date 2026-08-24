# Agent Teams Pi Package

Claude-Code-style collaborative agent teams for Pi: named resident teammates, a shared local task board with self-claim, and direct peer-to-peer messaging.

**Display Name**: Agent Teams

## What This Package Does

The team leader (your Pi session) spawns named teammates as long-lived child Pi processes in RPC mode. Each teammate has an isolated context, a peer inbox, and access to a shared task board. The harness—not the leader model—polls for activity: it drains leader reports, routes peer mail, applies task claims and submissions, runs deterministic verify gates, and wakes idle teammates only when work or mail exists.

The message surface is deliberately singular: `send_message` is the only messaging primitive. Workers report with `to: "leader"`; teammates address peers by name; the leader addresses teammates by name. The routing implementation varies by destination (outbox, inbox, or control stream), but callers use one schema.

## Install

```bash
pi install /path/to/pi-packages/packages/agent-teams
```

Then run `/reload` in Pi.

## Agents Are Declarative Files

Agent definitions are Markdown files with frontmatter; the body is the role prompt.

```markdown
---
name: isolated-security-auditor
description: Read-only security reviewer in an isolated worktree
tools: read,bash
model: provider/model       # optional
verify: npm test            # optional role-default completion gate
worktree: true              # optional role-default Git isolation
---
Review the assigned scope for exploitable security problems. Do not edit files.
```

Discovery precedence per name (later overrides earlier):

There are no built-in roles. When a needed role has no definition, the
leader creates it in memory for the current session: it derives the definition
from the task using the abstract role reference in `references/agent-roles.md`
(definition anatomy, archetype axes, invariants), registers it, and then spawns.
The role is not written to disk or reused in a later session unless the user
explicitly requests persistence; only then may the leader set `definition.persist`
and choose a project or project-local scope.

| Scope | Location | Git semantics |
|---|---|---|
| user | `~/.pi/agent/agents/*.md` | system-level, never committed |
| project | `<cwd>/.pi/agents/<name>.md` | **git-managed** — commit for the team |
| project-local | `<cwd>/.pi/agents/<name>.local.md` | **local** — personal override, gitignore by convention |
| session | in-memory registry | **ephemeral** — disappears at session start, no source file |

A teammate definition is just a Markdown file you own. Shared roles live in `.pi/agents/<name>.md`; a personal tweak to that exact role is `<name>.local.md` in the SAME directory — same teammate name, local scope wins, and discovery deduplicates the pair into one entry (never two). `resolveAgent` reports each definition's `scope` and `gitManaged`; guidance lists both so the leader knows provenance.

## Build a Team

```text
teammate_spawn({
  name: "security",
  agent: "reviewer",
  prompt: "Review the auth middleware"
})

teammate_spawn({ name: "backend", agent: "worker" })
```

- Spawn has exactly three parameters: `name`, `agent`, and optional kickoff `prompt`.
- Without a kickoff prompt, the teammate idles until messaged or until claimable work appears.
- Teammates stay alive between tasks and consume no model tokens while idle.
- A session-wide cap of 8 living teammates applies.
- An agent declaring `worktree: true` gets its own Git worktree; its diff is captured at shutdown.
- `teammate_shutdown({ name })` stops one teammate and releases its claimed task back to the board.

## Coordinate Through One Message Primitive and the Board

```text
send_message({
  to: "security",
  message: "Please challenge the backend finding against the current middleware."
})

task_create({
  subject: "Fix auth middleware findings",
  description: "Address the confirmed security findings in packages/api/src/auth.ts",
  dependsOn: ["t_1"],
  verify: "npm test"
})
```

`send_message` has one schema everywhere:

```text
send_message({ to, message, status? })
```

- Worker report: `to: "leader"`; use optional `status: "completed" | "failed"` for a terminal report.
- Peer mail: `to: "<teammate-name>"`; `status` is invalid.
- Leader steering or direct assignment: `to: "<teammate-name>"`; a working recipient gets a control-stream steer, an idle recipient wakes with the message.
- The first non-empty line of `message` becomes the console title.
- Peer traffic never enters the leader model context; inspect it in `/agent-teams` instead.

Only the leader creates tasks. Idle teammates self-claim pending tasks whose dependencies are met. A task-level `verify` command overrides the claiming agent's frontmatter `verify`; zero exit completes the task, while failure returns stderr to the claimer for fix-and-resubmit.

## Tools

| Tool / command | Side | Description |
|---|---|---|
| `teammate_spawn(name, agent, prompt?)` | Leader | Start one named resident teammate; model/worktree come from agent frontmatter |
| `teammate_shutdown(name)` | Leader | Stop one teammate and release its claimed work |
| `send_message(to, message, status?)` | Both | The only messaging primitive; `to: "leader"` is reserved for worker reports |
| `task_create(subject, description?, dependsOn?, verify?)` | Leader | Add a shared board task |
| `task_list()` | Both | One shared board-view definition; leader view also includes the roster |
| `task_claim(taskId?)` | Worker | Atomically self-claim a pending, unblocked task |
| `task_submit(taskId, status, result?)` | Worker | Submit a claimed task outcome; completion passes through verify |
| `/agent-teams` | User | Management console: session teammates, persistent agent roles, board, details, shutdown |

That is **7 unique tool names**. There are no `teammate_run`, `teammate_fanout`, `teammate_cancel`, `teammate_retry`, or `teammate_message` tools.

## Reliability Protocol

- **Per-spawn identity validation**: every leader report must match the teammate's current spawn id; stale callbacks and events cannot affect a replacement with the same name.
- **Sent means written**: peer `send_message` succeeds only after the recipient inbox write succeeds. The harness owns delivery into a recipient turn.
- **One writer per state file**: only the leader process writes runtime and board snapshots (atomic tmp+rename). Workers append leader reports to their outbox, peer mail to recipient inboxes, and task intent via exclusive-create marker files.
- **Completion is gated, not self-reported**: a task completes only after its effective verify gate passes when one exists; no gate means the submission itself completes it.
- **No caps, heartbeat only**: teammates run without turn-count or duration ceilings. The harness heartbeat tracks silence per working teammate and — after 30 minutes without any RPC output (`PI_TEAMMATE_STALL_NOTICE_MS`, 0 disables) — sends the leader one actionable notice per silence episode. The notice is the last automatic action: continuing, steering, shutting down, or respawning a context-carrying successor belongs to the leader alone. Any output or prompt delivery re-arms it, and steering a silent teammate warns that delivery is uncertain.
- **Failure semantics**: an unexpected crash marks the teammate stopped, reports a diagnostic, and releases its claimed tasks.

## State and Sessions

Runtime state lives in `~/.pi/agent/teammate/<sessionKey>/` and dies with the session (`state.json`, report outboxes, peer inboxes, roster). The task board lives in `~/.pi/agent/tasks/<sessionKey>/board.json` and persists for later inspection; nothing auto-deletes it. Claims held by dead teammates return to pending on reload.

## Structure

```
agent-teams/
├── index.ts              — package-root extension entry point
├── references/           — role templates consulted when generating new agents
├── src/
│   ├── index.ts          — composition root and session lifecycle
│   ├── tools.ts          — leader tools and /agent-teams command
│   ├── worker.ts         — worker tools plus the shared task_list registration
│   ├── team-machine.ts   — resident lifecycle, mail routing, intents, verify, wake-ups
│   ├── state.ts          — roster, board, leader inbox state machine
│   ├── spawner.ts        — resident RPC process spawner (uncapped sequences)
│   ├── agents.ts         — agent discovery and frontmatter parsing
│   ├── statefile.ts      — runtime/board/mail IO and marker-file intents
│   ├── ui.ts             — passive widget and /agent-teams management console
│   ├── guidance.ts       — static leader and worker protocols
│   └── follow-up-queue.ts — serialized automatic report delivery
├── features/             — BDD contract
└── tests/                — package tests
```

## License

MIT
