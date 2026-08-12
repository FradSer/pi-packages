# Teammate Pi Package

Multi-agent team system for Pi — mailbox-based communication, task management, and team-leader orchestration.

**Version**: 0.2.0
**Display Name**: Teammate

## What This Package Does

Transforms Pi into a multi-agent team platform. Register teammates with different roles, communicate via mailboxes, assign and track tasks, and let a team-leader orchestrate the work.

### Extension

The extension (`src/index.ts`) registers 10 tools and 1 command:

| Tool / Command | Description |
|---|---|
| `teammate_register` | Register a new teammate agent with a name, role, and description |
| `teammate_list` | List all registered teammates |
| `teammate_send` | Send a message to a teammate's mailbox |
| `teammate_read_mailbox` | Read messages from a teammate's mailbox |
| `teammate_assign_task` | Assign a task to a teammate (team-leader only) |
| `teammate_list_tasks` | List tasks filtered by status or assignee |
| `teammate_update_task` | Update task status (in_progress, completed, failed, cancelled) |
| `teammate_broadcast` | Broadcast a message to all teammates (team-leader only) |
| `teammate_task_deps` | Wire task dependencies (blocks / blockedBy) on the board |
| `teammate_spawn` | Spawn a real child Pi process as a teammate to execute a task |
| `/teammate-status` | Show teammate system status summary |

### Roles

| Role | Description |
|---|---|
| `team-leader` | Orchestrator — assigns tasks, broadcasts messages, coordinates work |
| `worker` | Executor — performs assigned tasks |
| `reviewer` | Code/content reviewer |
| `specialist` | Domain expert |
| `observer` | Read-only, monitors activity |

### Skill

A reference skill `using-teammate` is also included, documenting the OpenAI Teammate / Workspace Agents API surface.

## Structure

```
teammate/
├── package.json              — Pi package manifest (declares extension + skills)
├── README.md                 — This file
├── src/
│   ├── index.ts              — Extension entry point (10 tools + 1 command + before_agent_start injection)
│   ├── state.ts              — State management (mailbox, tasks, registry, dependencies, liveness)
│   ├── types.ts              — TypeScript types and typebox schemas
│   ├── spawner.ts            — Child Pi process spawner (real worker execution)
│   └── worktree.ts           — Git worktree isolation for parallel workers
├── skills/
│   └── using-teammate/
│       └── SKILL.md          — Pi extension tool usage guide (/skill:using-teammate)
├── .memory/
│   ├── MEMORY.md             — Memory index
│   └── openai_teammate_api_reference.md  — OpenAI API reference (kept for reference)
└── tests/
    └── test_teammate_package.py  — Package E2E tests
```

## Usage

### 1. Install

```bash
pi install /path/to/pi-packages/packages/teammate
```

### 2. Reload

Run `/reload` in Pi to activate the extension. The teammate guidance is automatically injected into the system prompt on every turn.

### 2. Register teammates

In your conversation with Pi, ask:

> Register a team-leader called "alice" who coordinates the team
> Register a worker called "bob" who implements code changes
> Register a reviewer called "charlie" who reviews pull requests

### 3. Assign tasks (team-leader)

> Alice, assign a task to bob to implement user authentication

### 4. Communicate via mailboxes

> Send a message to bob: "Please start on the auth module, the task is in your list"

### 5. Update task progress

> Bob, update task task_1 to in_progress
> Bob, mark task task_1 as completed with result: "Implemented JWT auth in src/auth.ts"

### 6. Broadcast

> Broadcast to all workers: "Please use the new auth library v2.0"

### 7. Wire task dependencies

> Wire task_2 to be blocked by task_1

### 8. Spawn a real worker

> Bob, spawn task_1 now

This launches a real child Pi process running `pi --print --no-session --model <model> Task: <description>` in the project directory. The worker executes the task with its own context; on exit the task is marked completed (stdout as result) or failed (stderr as error).

### 9. Worktree isolation for parallel workers

> Bob and charlie, spawn task_2 and task_3 with worktree isolation

Workers run on their own git branch under `.pi/worktrees/`; the diff is captured into the task result and the worktree is cleaned up afterwards.

### 10. Timeout and cost visibility

> Bob, spawn task_1 with a 5 minute timeout

Workers are killed after `timeoutMs` (default 30 min) if they hang. Token/cost usage is parsed from the worker's JSON output and shown on the task, so the leader sees exactly what each worker spent.

## State Persistence

The teammate system state (teammates, mailboxes, tasks) is persisted as session entries, so it survives session restarts and `/resume` operations.

## License

MIT.