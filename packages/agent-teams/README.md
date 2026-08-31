# Agent Teams Pi Package

Claude-Code-style collaborative agent teams for Pi: named resident teammates, a shared local task board with self-claim, and direct peer-to-peer messaging.

**Display Name**: Agent Teams

## What This Package Does

The team leader (your Pi session) spawns named teammates as long-lived child Pi processes in RPC mode. Each teammate has an isolated context, a peer inbox, and access to a shared task board. The harness—not the leader model—polls for activity: it drains leader reports, routes peer mail, applies task claims and submissions, judges verify prompts with fresh one-shot reviewers, and wakes idle teammates only when work or mail exists.

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
model: provider/model       # optional; "inherit" = the leader's current model at spawn time
verify: review prompt       # optional role-default gate; a fresh reviewer answers VERDICT: PASS/FAIL
worktree: true              # optional role-default Git isolation
---
Review the assigned scope for exploitable security problems. Do not edit files.
```

Teammate model resolution at spawn time, in precedence order: an explicit
`provider/model` pin wins; `inherit` pins the leader session's current model;
without a pin, the unified teammate model set from `/agent-teams` (press `m`
in the roster page for a type-to-filter picker) applies to this session;
otherwise Pi picks its own default.

Discovery precedence per name (later overrides earlier): user < project <
project-local, with generated session roles filling only the names no file
defines. A re-spawn that supplies an explicit inline definition replaces a
previously generated session role of the same name; definition files are never
overwritten by inline input.

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
  prompt: "Review the auth middleware",
  resources: ["packages/api/auth"]
})

teammate_spawn({ name: "backend", agent: "worker" })
```

- Spawn accepts `name`, `agent`, an optional kickoff `prompt`, optional `resources`, and optional `handoffFrom`. Resources are stable path-like tags used to prevent overlapping mutating assignments; they are advisory to the filesystem but enforced by the task/assignment state machine.
- A kickoff creates one direct assignment. After its terminal report, that worker cannot claim board work until the leader explicitly sends `reopen: true` with a distinct next assignment.
- `handoffFrom` builds a successor kickoff from the predecessor's latest assignment, board claim, and recent leader reports; it never silently transfers a board claim.
- Without a kickoff prompt, the teammate idles until messaged or until eligible claimable work appears.
- Teammates stay alive between tasks and consume no model tokens while idle.
- A session-wide cap of 8 living teammates applies.
- An agent declaring `worktree: true` gets its own Git worktree; at shutdown its changes are committed onto the worktree branch, the directory is removed, and the branch is kept so captured work stays retrievable (`git diff <base>..<branch>`).
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
  resources: ["packages/api/auth"],
  supersedes: ["old-auth-patch"],
  verify: "Every scenario in features/gallery.feature holds in the built gallery; no horizontal overflow at 400px."
})
```

`send_message` has one schema everywhere:

```text
send_message({ to, message, status? })
```

- Worker report: `to: "leader"`; use optional `status: "completed" | "failed"` for a terminal report. Every accepted leader-bound report — intermediate or terminal — enters Pi's follow-up queue as its own turn, even while the leader is active; Pi processes it when the current run can naturally end. After the first accepted terminal report in a wake-up sequence, later reports are suppressed until a new wake-up; distinct intermediate reports, including identical bodies before terminal status, remain deliverable, and the same content is not suppressed across assignments. For bounded reviewer assignments, put findings, the recommendation, verification evidence, and remaining risks in one concise terminal report. Use earlier reports only for genuinely new blockers, plan-changing facts, or evidence that changes the conclusion; do not send a separate status-only assignment-complete message or repeat unchanged findings. A terminal report ends the current worker turn. After a terminal report, report to the leader again only for a new assignment or decision-useful fact.
- Harness lifecycle events use a separate `<harness-event>` envelope. A requested `teammate_shutdown` stays in the tool lifecycle row and console mailbox; it does not start a leader follow-up turn. Unexpected stops and actionable harness events may still wake the leader.
- Peer mail: `to: "<teammate-name>"`; `status` is invalid.
- Leader steering or direct assignment: `to: "<teammate-name>"`; the synchronous routing result is `steered` only when the active control stream accepts the message, otherwise `queued` while the harness owns delivery on the next wake-up.
- Peer mail and reports to the leader are written to an inbox or outbox first, so their synchronous routing result is `queued`; none of these labels claims the recipient has read, understood, or processed the message.
- Teammate health is reported separately as an `[agent] event` such as `@name stalled · silent 5m`; health never appears as a message-routing suffix.
- The first non-empty line of `message` becomes the console title.
- Peer traffic never enters the leader model context; inspect it in `/agent-teams` instead.

Only the leader creates tasks. `task_create` adds pending work to the current session's board; it never spawns a teammate. An idle teammate receives a board notice only when it owns no assignment and the task's resources do not overlap another active assignment. A worker that claims a task owns it until `task_submit` completes or releases it; a terminal leader report alone never completes a board task or authorizes more claims. `supersedes` marks obsolete pending/claimed tasks as `superseded`, retargets pending downstream dependencies to the replacement, and permanently removes obsolete work from notices, claims, and completion. A live holder retains its resource lock until it acknowledges cancellation with `task_submit(status="failed")` or stops; a resumed board clears dead holders. With no living teammates, the result explicitly tells the leader to call `teammate_spawn`; with no eligible idle recipient, the task remains pending until the leader creates/opens a compatible assignment. Boards are session-keyed, so a task created in another Pi session is not automatically imported into the current session. A task-level `verify` prompt overrides the claiming agent's frontmatter `verify`. The harness runs it as a fresh one-shot reviewer: explicit `VERDICT: PASS` completes; explicit `VERDICT: FAIL - <reasons>` returns findings to the claimer. A missing verdict is **inconclusive**: the harness requests one verdict-only clarification, then escalates without counting it as a verification failure. Write acceptance criteria a reviewer can check, not shell commands.

## Tools

| Tool / command | Side | Description |
|---|---|---|
| `teammate_spawn(name, agent, prompt?, resources?, handoffFrom?)` | Leader | Start one named resident teammate; model/worktree come from agent frontmatter |
| `teammate_shutdown(name)` | Leader | Stop one teammate and release its claimed work |
| `send_message(to, message, reopen?, resources?, status?)` | Both | The only messaging primitive; `to: "leader"` is reserved for worker reports |
| `task_create(subject, description?, dependsOn?, verify?, resources?, supersedes?)` | Leader | Add a resource-scoped shared board task |
| `task_list()` | Both | One shared board-view definition; leader view also includes the roster |
| `task_claim(taskId?)` | Worker | Atomically self-claim a pending, unblocked task |
| `task_submit(taskId, status, result?)` | Worker | Submit a claimed task outcome; completion passes through verify |
| `/agent-teams` | User | Management console: session teammates, persistent agent roles, board, details, shutdown |

That is **7 unique tool names**. There are no `teammate_run`, `teammate_fanout`, `teammate_cancel`, `teammate_retry`, or `teammate_message` tools.

## Reliability Protocol

- **Per-spawn identity validation**: every leader report must match the teammate's current spawn id; stale callbacks and events cannot affect a replacement with the same name.
- **Queued means written**: peer `send_message` succeeds only after the recipient inbox write succeeds. The harness still owns delivery into a recipient turn; only an accepted active control-stream steer is labeled `steered`.
- **One writer per state file**: only the leader process writes runtime and board snapshots (atomic tmp+rename). Workers append leader reports to their outbox, peer mail to recipient inboxes, and task intent via exclusive-create marker files.
- **One assignment at a time**: direct assignments and board claims are mutually exclusive. A terminal direct report closes that assignment until an explicit `reopen`; a board claim stays open until `task_submit`.
- **Resource-safe board work**: overlapping path-like resource tags cannot run concurrently. Superseded tasks stay visible for audit but cannot be claimed, completed, or re-noticed.
- **Completion is gated, not self-reported**: a task completes only after its effective verify gate passes when one exists; no gate means the submission itself completes it. Explicit FAIL twice parks the task with its holder and escalates once. Missing verdict text is inconclusive, gets one clarification, then escalates without incrementing the failure count.
- **No caps, heartbeat only**: teammates run without turn-count or duration ceilings. The harness heartbeat tracks silence per working teammate and — after 30 minutes without any RPC output (`PI_TEAMMATE_STALL_NOTICE_MS`, 0 disables) — sends the leader one actionable health event per silence episode. The notice is the last automatic action: continuing, steering, shutting down, or respawning a context-carrying successor belongs to the leader alone. Any output or prompt delivery re-arms it. Health events carry diagnostics separately from message routing: silence duration, spawn age, and lifetime token/cost usage. A teammate with zero lifetime model output and no tool running gets flagged much earlier (5 minutes, `PI_TEAMMATE_SILENT_STALL_MS`, 0 disables): an in-flight request stuck on the provider will not recover by steering, so that notice names shutdown plus respawn as the effective remedy.
- **One-shot board notices**: an idle teammate is told about a claimable task exactly once; declined tasks never re-wake it, and released tasks re-arm. Notices are paced at least five minutes apart per teammate (`PI_TEAMMATE_NOTICE_PACE_MS` overrides in milliseconds).
- **One end-of-life line per teammate**: the first terminal report of a spawn incarnation renders the finish entry; shutting that incarnation down afterwards adds no second event row. Requested shutdown is process cleanup only, not proof of assignment completion; wait for the worker's terminal status report when possible. After the first accepted terminal report, later reports are suppressed until a new assignment prompt; distinct intermediate reports remain deliverable.
- **Failure semantics**: an unexpected crash marks the teammate stopped, reports a diagnostic, and releases its claimed tasks.

## State and Sessions

Runtime state lives in `~/.pi/agent/teammate/<sessionKey>/` and dies with the session (`state.json`, report outboxes, peer inboxes, roster). The task board lives in `~/.pi/agent/tasks/<sessionKey>/board.json` and persists for later inspection; nothing auto-deletes it. The board key is derived from the Pi session file (or cwd when no session file exists), so a fresh session with a different session file does not import another session's tasks automatically; resume the same board directory to continue them. Claims held by dead teammates return to pending on reload.

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
