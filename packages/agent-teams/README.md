# Agent Teams Pi Package

Multi-agent team system for Pi — mailbox-based communication, task management, and team-leader orchestration.

**Version**: 0.2.0
**Display Name**: Agent Teams

## What This Package Does

Transforms Pi into a multi-agent team platform. Register teammates with different roles, communicate via mailboxes, assign and track tasks, and let a team-leader orchestrate the work.

### Extension

The extension (`src/index.ts`) registers the orchestration tools and the `/teammate` command:

| Tool / Command | Description |
|---|---|
| `teammate_register` | Register a teammate with a worker, reviewer, specialist, or observer role |
| `teammate_configure` | Update an existing teammate's description, prompt, model, or tools |
| `teammate_list` | List all registered teammates |
| `teammate_remove` | Remove an idle teammate and its mailbox |
| `teammate_message` | Send a message; workers address a peer or `agent`, leaders may use `to="all"` with a role filter |
| `teammate_inbox` | Read the caller's inbox; main-session results enter the current conversation |
| `teammate_create_task` | Create and assign a task with optional blockedBy dependency IDs |
| `teammate_list_tasks` | List tasks filtered by status or assignee |
| `teammate_start_task` | Start a ready assigned task as an autonomous child Pi process; returns immediately |
| `teammate_wait` | Explicitly wait for task runs and collect their results |
| `teammate_cancel_task` | Cancel a running task (SIGTERM the worker) |
| `teammate_cleanup` | Prune terminal tasks after their outcomes are synthesized |
| `/teammate` | Open the full-screen team console |

Spawned workers receive only `teammate_message`, `teammate_inbox`, and `teammate_report`. `teammate_report` is bound to the worker's current task run; it cannot update another task.

### Team UI: passive widget + full-screen console

No global key interception — pi's model selector, history and dialogs always
work. The teammate UI is:

- **Widget (display only)** above the prompt editor: one colored row per
  teammate (name, `(teammate)` label, animated task status / `○ idle`). Passive —
  it never touches your keys.
- **`/teammate` full-screen console**: `↑`/`↓` select a teammate, `Enter` open
  its full page with task sections + mailbox transcript, `r` inline reply,
  `Esc` back/close, `x` stop a running worker, `q` close.

**Direct communication**: use `teammate_message` everywhere. The main session
addresses a registered teammate; a spawned teammate addresses another teammate
or `agent` to reach the main session. Call `teammate_inbox` in the main session
to return worker messages in the current conversation. The TUI remains focused
on team/task status and does not duplicate mailbox alerts.

### Roles

| Role | Description |
|---|---|
| `worker` | Executor — performs assigned tasks |
| `reviewer` | Code/content reviewer |
| `specialist` | Domain expert |
| `observer` | Read-only, monitors activity |

The current Pi session is always the team leader. `team-leader` is not a registerable role.

## Structure

```
agent-teams/
├── package.json              — Pi package manifest (declares the orchestration extension)
├── README.md                 — This file
├── src/
│   ├── index.ts              — Extension entry point (orchestration tools + /teammate + guidance injection)
│   ├── state.ts              — State management (mailbox, tasks, registry, dependencies, liveness)
│   ├── types.ts              — TypeScript types and typebox schemas
│   ├── spawner.ts            — Child Pi process spawner (autonomous guardian-loop workers) 
│   ├── statefile.ts          — Shared state file (parent ↔ worker mailbox/task board sync)
│   └── worktree.ts           — Git worktree isolation for parallel workers
├── .memory/
│   ├── MEMORY.md             — Memory index
│   └── openai_teammate_api_reference.md  — OpenAI API reference (kept for reference)
└── tests/
    └── test_teammate_package.py  — Package E2E tests
```

## Usage

### 1. Install

```bash
pi install /path/to/pi-packages/packages/agent-teams
```

### 2. Reload

Run `/reload` in Pi to activate the extension. The teammate guidance is automatically injected into the system prompt on every turn.

### 2. Define teammates

The current Pi session is always the team leader; do not register a `team-leader` teammate. Create a small, stable worker team. Each teammate needs:

- a concise name;
- one focused role (`worker`, `reviewer`, `specialist`, or `observer`);
- a short responsibility summary;
- a reusable prompt describing the role, method, boundaries, deliverable, and completion criteria;
- only the tools it actually needs.

Example prompt for a reviewer:

> Review the assigned diff for correctness and regressions. Read the relevant tests first. Do not edit files. Report only confirmed findings with severity, evidence, exact paths, and a minimal fix recommendation. State what you checked when no issue is found.

### 3. Decompose and create tasks

Create one task per observable outcome with `teammate_create_task`. Put the complete handoff in the task description:

- goal and relevant context;
- paths, inputs, and constraints;
- ordered procedure;
- files the worker may and may not change;
- exact deliverable and location;
- verification command or acceptance criteria;
- what to do when blocked.

Declare artifact dependencies at creation time with `blockedBy` (a list of task IDs that must complete first). Dependencies are immutable after creation; there is no public mutation tool. Keep titles short (`Audit auth refresh`, `Implement login form`, `Review API diff`) and put detail in descriptions.

### 4. Run independent work in parallel

Start independent tasks in the same turn. Every `teammate_start_task` returns immediately:

```text
teammate_start_task taskId="task_1"
teammate_start_task taskId="task_2"
teammate_start_task taskId="task_3"
```

Continue coordinating while workers run. Call `teammate_wait taskIds=["task_1", "task_2", "task_3"]` only when their final outcomes are needed. Dependent tasks (declared with `blockedBy` at creation) receive a `Task unblocked` inbox message when all blockers complete. Do not serialize independent work.

### 5. Communicate and synthesize

Use `teammate_message` for every handoff, blocker, decision, or broadcast. In the main session, target a registered teammate, or use `to="all"` with an optional role filter. In a worker, target one peer or `agent` to message the main session. Call `teammate_inbox` to read your messages; in the main session its result enters the current conversation. Worker messages remain leader-validated append-only outbox events; the TUI intentionally shows only team/task status.

After `teammate_wait`, inspect the files and evidence, reconcile conflicting results, run verification yourself, and provide one synthesized answer. A worker's claim is not proof until its deliverable and tests are checked.

### 6. Isolation, failures, and cleanup

Use `isolation="worktree"` when parallel workers might edit overlapping files. Treat failed, timed-out, cancelled, or missing tasks explicitly. Retry failed tasks with `teammate_start_task retry=true`. Cancel a running task with `teammate_cancel_task`. Keep finished tasks until their results are synthesized, then use `teammate_cleanup`.

## State Persistence and Concurrency

The team leader is the only writer of the session state snapshot. Every spawned worker receives a fresh `runId`, reads that snapshot, and emits append-only events through the unified `teammate_message`, `teammate_inbox`, and `teammate_report` worker capabilities. The leader validates the sender, run identity, recipient, task ownership, and event shape before applying an event, so an old worker run cannot update a later run, and one worker cannot overwrite another worker's message, revert a read receipt, or update another teammate's task. Completed runs publish their final state before their per-run outbox and replay metadata are compacted.

A child running in worker mode registers only three identity-bound capabilities (`teammate_message`, `teammate_inbox`, and status reporting); it never registers team lifecycle, UI, task-board, or spawn tools. This is a reliable collaboration protocol, not an OS security sandbox: workers still run with the user's local permissions. A normal exit code of `0` is the only successful process outcome; signal termination, timeout, and non-zero exit fail the task.

The teammate system state (teammates, mailboxes, tasks) is persisted as session entries, so it survives session restarts and `/resume` operations. Pending-task self-claim is intentionally not available until a cross-process claim lock exists; atomic snapshot writes alone are not a safe claim protocol. Plan approval and task-completion hooks likewise remain future work until their state transitions and quality-gate semantics are designed end to end.

## License

MIT.