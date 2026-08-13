---
name: using-teammate
description: >
  Use when working with the teammate extension — registering agents, mailbox
  communication, task assignment, broadcasting, and team workflows. Load this
  skill when the user asks about teammate setup, multi-agent coordination,
  task management, or the teammate tool APIs.
---

# Teammate Extension — Usage Guide

This skill documents the `@fradser/teammate` Pi extension: a multi-agent team system with mailbox-based communication, task management, and team-leader orchestration.

## Quick Start

```
1. Register a team-leader:
   teammate_register name="alice" role="team-leader" description="Project coordinator"

2. Register workers:
   teammate_register name="bob" role="worker" description="Full-stack developer"
   teammate_register name="charlie" role="reviewer" description="Code reviewer"

3. Assign tasks (team-leader):
   teammate_assign_task assignee="bob" title="Implement auth" description="Add JWT login/register"

4. Communicate via mailbox:
   teammate_send to="bob" subject="Priority" body="Start with login endpoint first"
   teammate_read_mailbox name="bob" unreadOnly=true

5. Track progress:
   teammate_update_task taskId="task_1" status="in_progress"
   teammate_update_task taskId="task_1" status="completed" result="Done in src/auth.ts"

6. Broadcast:
   teammate_broadcast subject="API change" body="Use v2 of auth library"

7. Wire task dependencies (optional):
   teammate_task_deps taskId="task_2" blockedBy=["task_1"]

8. Spawn a real worker for a ready task:
   teammate_spawn name="bob" taskId="task_1"
```

## Tools Reference

### teammate_register

Register a new teammate.

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique name for the teammate |
| `role` | yes | `team-leader`, `worker`, `reviewer`, `specialist`, or `observer` |
| `description` | yes | What this teammate is responsible for |
| `model` | no | Preferred model for this agent |
| `tools` | no | Allowed tools list |

### teammate_list

List all registered teammates with roles, descriptions, and unread message counts.

### teammate_send

Send a message to a teammate's mailbox.

| Field | Required | Description |
|-------|----------|-------------|
| `to` | yes | Recipient teammate name |
| `subject` | yes | Message subject |
| `body` | yes | Message body content |
| `taskId` | no | Optional associated task ID |

### teammate_read_mailbox

Read messages from a teammate's mailbox.

| Field | Default | Description |
|-------|---------|-------------|
| `name` | `"agent"` | Teammate name to read mailbox for |
| `markRead` | `true` | Mark messages as read after viewing |
| `unreadOnly` | `true` | Only show unread messages |

### teammate_assign_task

Assign a task to a teammate (team-leader only). The assignee receives a mailbox notification.

| Field | Required | Description |
|-------|----------|-------------|
| `assignee` | yes | Teammate to assign the task to |
| `title` | yes | Task title |
| `description` | yes | Detailed task description |

### teammate_list_tasks

List tasks, optionally filtered.

| Field | Description |
|-------|-------------|
| `status` | Filter by: `created`, `assigned`, `in_progress`, `completed`, `failed`, `cancelled` |
| `assignee` | Filter by assignee name |

### teammate_update_task

Update a task's status.

| Field | Required | Description |
|-------|----------|-------------|
| `taskId` | yes | ID of the task to update |
| `status` | yes | `in_progress`, `completed`, `failed`, or `cancelled` |
| `result` | no | Result/output (for completed tasks) |
| `errorMessage` | no | Error message (for failed tasks) |

### teammate_broadcast

Broadcast a message to all teammates (team-leader only). Can filter by role.

| Field | Required | Description |
|-------|----------|-------------|
| `subject` | yes | Broadcast subject |
| `body` | yes | Broadcast message body |
| `role` | no | Only send to teammates with this role |

### teammate_task_deps

Wire dependencies on the task board. A task cannot be spawned until every `blockedBy` task is completed or cancelled; inverse `blocks` edges are maintained automatically.

| Field | Required | Description |
|-------|----------|-------------|
| `taskId` | yes | Task ID to update dependencies for |
| `blocks` | no | Task IDs this task blocks |
| `blockedBy` | no | Task IDs that block this task |

### teammate_spawn

Spawn a real child Pi process as the teammate to execute a task — a **fully autonomous agent**. The worker processes the task, then watches its own mailbox via a shared state file and processes new messages until **it decides to close** (idle window, explicit stop, or work complete). `background=false` (default) BLOCKS until the worker closes itself and returns its final report — no polling; `background=true` fires and forgets and the worker keeps living until it chooses to stop. The task must be ready (all `blockedBy` completed). On the worker's own exit, the task is marked completed (worker report stored as result) or failed, and the teammate returns to `idle`.

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Teammate to spawn as the worker |
| `taskId` | yes | Task ID to execute in the child process |
| `isolation` | no | `worktree` runs the worker in a fresh git worktree (own branch, captured as a patch on completion, then removed); `none` (default) runs in the project directory |
| `background` | no | `false` (default): block until the worker autonomously closes and return its report. `true`: fire-and-forget; the worker watches its mailbox until it decides to close |
| `timeoutMs` | no | Hard wall-clock cap before the worker is killed (default: 1800000 = 30 min) |

## Commands

- `/teammate-status` — Show teammate system status summary (number of teammates, tasks, unread messages).

## Team UI: passive widget + full-screen console

The teammate UI has two parts — and it never touches pi's own keys (no global
input interception, so the model selector, prompt history and dialogs always
work):

- **Widget (display only)** — a few lines above the prompt editor show each
  teammate (colored name, `(teammate)` label, `● running task_x` / `○ idle`)
  plus a `N message(s) to you from teammates` alert when the leader inbox has
  unread messages. It is passive: it renders nothing and intercepts nothing.
- **`/teammate` full-screen console** — type `/teammate` to open it. The
  console owns input, so navigation keys are safe in here:

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move the selection between the inbox row and teammates |
| `Enter` | Open the selected row: the leader inbox, or a teammate's full page |
| `r` | In a teammate page: start an inline reply (type + `Enter` send, `Esc` cancel) |
| `Esc` | In a list: close the console / in a page: back to the list |
| `x` | Stop the selected teammate's running worker hard (SIGKILL) |
| `q` | Close the console |

A teammate's page shows special sections — unread messages, assigned tasks
(with the full spawn lifecycle and worker output) — then the mailbox transcript.
The leader inbox (Enter on the alert row) shows messages teammates sent you;
viewing consumes them.

**Live visibility**: while a worker runs, its mid-run updates (progress messages
to the leader, task-result writes) are polled from the shared state file every
~5s and merged into the board — the leader inbox alert lights up live instead of
only after the worker closes. The console uses the same popup style as `/btw`
(borders, accent header, dim footer hints).

**Leader inbox**: teammates can message your window by writing to
`mailboxes["agent"]` (autonomous workers are told to post milestone/blocker
updates there). When such messages arrive, the panel shows a selectable
`N message(s) to you from teammates` row — Enter opens the full-screen inbox.
`teammate_read_mailbox name="agent"` also reads it.

Management actions remain available as tools: `teammate_remove` (unregister + delete mailbox), `teammate_cleanup` (prune finished tasks / remove one), `teammate_reset` (wipe the board).

## Team Workflow Patterns

### Standard workflow

```
team-leader → assign_task → worker → in_progress → completed/failed
                                                      ↓
                                              reviewer reviews
```

### Multi-worker parallel

```
team-leader → assign_task to worker-a
            → assign_task to worker-b (parallel)
            → broadcast to workers: "status update please"
```

### Review pipeline

```
team-leader → assign_task "Implement feature" to worker
worker      → update_task to completed
team-leader → assign_task "Review PR" to reviewer
            → send message to reviewer with PR link
reviewer    → update_task to completed/failed
```

### Dependency-gated pipeline

```
team-leader → assign_task "Setup" to worker-a
            → assign_task "Build" to worker-b
            → teammate_task_deps taskId="build-task" blockedBy=["setup-task"]
            → teammate_spawn name="worker-a" taskId="setup-task"   # runs now
            → teammate_spawn name="worker-b" taskId="build-task"   # rejected until setup completes
```

## Real Worker Execution

Teammates registered with a `model` (and optional `tools`) can be spawned as real child Pi processes via `teammate_spawn`. Change a teammate's model anytime with `teammate_update_model name=<teammate> model=<pattern>` — it applies to the next spawn (a running worker keeps its starting model); no need to remove/re-register. The worker is a **fully autonomous agent**:

- Runs `pi --print --mode json --no-session [--model <model>] [--tools <tools>]` with a guardian-loop prompt.
- **Watches its own mailbox**: a shared state file (`~/.pi/agent/teammate/<session>/state.json`) is published before spawn; the worker reads `mailboxes[<name>]`, processes every new message, posts replies back into the file, and updates its assigned task's status/result.
- **Decides when to close**: it exits on its own when the task is done + an idle window passes, an explicit stop message arrives, or it judges nothing else is coming — not when a one-shot task script finishes. A hard `timeoutMs` (default 30 min) remains as the safety cap.
- Has its own model context and tool scope; it never sees the leader's conversation history. `bash` is auto-appended to the tool allowlist for polling the state file.
- **Default `background=false` BLOCKS until the worker closes itself** and returns its final report — the leader never sleep-polls. `background=true` fires and forgets: the worker keeps watching its mailbox until it decides to stop; check `teammate_list_tasks` later for the outcome.
- Reports token/cost usage (parsed from JSON output) stored on the task and shown by `teammate_list_tasks`.
- With `isolation: "worktree"`, works on branch `teammate/<taskId>` under `.pi/worktrees/`; its diff is captured into the task result and the worktree is removed afterwards, so parallel workers never collide.
- When the worker closes, the parent merges anything the worker wrote to the shared file (replies, task updates) back into the board.

## Liveness

Each teammate tracks `idle` / `running` status: `teammate_spawn` marks the teammate running (with its current task id); when the worker exits or fails to start, the teammate returns to `idle`. `teammate_list` shows the current status, so "registered" and "actually working" are always distinguishable.

## State Persistence

Teammate state (registrations, mailboxes, tasks) is persisted to session entries automatically. It survives `Ctrl+C`, `/resume`, and session restarts. No manual save is needed.

## Best Practices

1. The team leader is the current main session — never register a `team-leader` teammate (it is rejected); `assign_task` and `broadcast` are always available to you
2. Use `teammate_list` to check the team before assigning tasks
3. Workers should read their mailbox with `teammate_read_mailbox` after receiving a task notification
4. Use `teammate_list_tasks status="assigned"` to see pending work
5. Always provide a `result` when completing a task so the team-leader knows what was done
6. Wire dependencies with `teammate_task_deps` before spawning so blocked tasks fail fast
7. Give workers a `model` at registration so `teammate_spawn` can run them with the right model
8. Use `isolation: "worktree"` when spawning parallel workers that write files, so they never collide on the working tree
9. Set `timeoutMs` on long-running or risky tasks so a hung worker is killed and the task fails with a clear reason
10. Use the default blocking spawn when you want the outcome in one call; use `background=true` when the worker should keep living and watch its mailbox afterwards