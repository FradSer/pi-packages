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

Spawn a real child Pi process as the teammate to execute a task. The worker runs in non-interactive mode (`--print`) with the teammate's model and tool scope. The task must be ready (all `blockedBy` completed). On exit, the task is marked completed (stdout stored as result) or failed (stderr/error stored), and the teammate returns to `idle`.

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Teammate to spawn as the worker |
| `taskId` | yes | Task ID to execute in the child process |
| `isolation` | no | `worktree` runs the worker in a fresh git worktree (own branch, captured as a patch on completion, then removed); `none` (default) runs in the project directory |
| `timeoutMs` | no | Kill the worker after this many milliseconds (default: 1800000 = 30 min) |

## Command

- `/teammate-status` — Show teammate system status summary (number of teammates, tasks, unread messages).

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

Teammates registered with a `model` (and optional `tools`) can be spawned as real child Pi processes via `teammate_spawn`. The worker:

- Runs `pi --print --mode json --no-session [--model <model>] [--tools <tools>] Task: <description>` in the project cwd (or a fresh git worktree when `isolation: "worktree"`).
- Has its own model context and tool scope; it never sees the leader's conversation history.
- Reports completion by exiting 0 (stdout becomes the task result) or failure via non-zero exit (stderr becomes the error).
- Reports token/cost usage (parsed from JSON output) stored on the task and shown by `teammate_list_tasks`.
- Is killed after `timeoutMs` (default 30 min) if it hangs; the task is then marked failed with a timeout reason.
- With `isolation: "worktree"`, works on branch `teammate/<taskId>` under `.pi/worktrees/`; its diff is captured into the task result and the worktree is removed afterwards, so parallel workers never collide.
- Spawn info (pid, status, timestamps, usage) is stored on the task and shown by `teammate_list_tasks`.

## Liveness

Each teammate tracks `idle` / `running` status: `teammate_spawn` marks the teammate running (with its current task id); when the worker exits or fails to start, the teammate returns to `idle`. `teammate_list` shows the current status, so "registered" and "actually working" are always distinguishable.

## State Persistence

Teammate state (registrations, mailboxes, tasks) is persisted to session entries automatically. It survives `Ctrl+C`, `/resume`, and session restarts. No manual save is needed.

## Best Practices

1. Register a team-leader first — this role is required for `assign_task` and `broadcast`
2. Use `teammate_list` to check the team before assigning tasks
3. Workers should read their mailbox with `teammate_read_mailbox` after receiving a task notification
4. Use `teammate_list_tasks status="assigned"` to see pending work
5. Always provide a `result` when completing a task so the team-leader knows what was done
6. Wire dependencies with `teammate_task_deps` before spawning so blocked tasks fail fast
7. Give workers a `model` at registration so `teammate_spawn` can run them with the right model
8. Use `isolation: "worktree"` when spawning parallel workers that write files, so they never collide on the working tree
9. Set `timeoutMs` on long-running or risky tasks so a hung worker is killed and the task fails with a clear reason