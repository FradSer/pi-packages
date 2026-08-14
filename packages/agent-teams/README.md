# Agent Teams Pi Package

Multi-agent team system for Pi — reusable current-session teammates, bounded task runs, and team-leader orchestration.

**Version**: 0.2.0
**Display Name**: Agent Teams

## What This Package Does

Transforms Pi into a current-session multi-agent task system. Reuse compatible idle teammates, run each task in a bounded child process, communicate proactively with the leader, retain terminal task results for synthesis, and let the team leader orchestrate the work.

### Extension

The extension (`src/index.ts`) registers the orchestration tools and the `/teammate` command:

| Tool / Command | Description |
|---|---|
| `teammate_register` | Reuse a compatible idle teammate when available, otherwise register one with a worker, reviewer, specialist, or observer role |
| `teammate_configure` | Update an existing teammate's description, prompt, model, or tools |
| `teammate_list` | List all registered teammates |
| `teammate_remove` | Remove an idle teammate and its mailbox |
| `teammate_message` | Send a message; workers address a peer or `agent`, leaders may use `to="all"` with a role filter |
| `teammate_inbox` | Read the caller's inbox; main-session results enter the current conversation |
| `teammate_create_task` | Create and assign a task with repo-relative paths, read/write access, and optional blockedBy dependency IDs |
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
│   ├── spawner.ts            — Child Pi process spawner (one-task workers)
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

The current Pi session is always the team leader; do not register a `team-leader` teammate. Before registering, inspect the idle team and reuse a compatible role/model/tool configuration whenever possible. Register a new teammate only when its capability or role prompt materially differs. Each teammate needs:

- a concise name;
- one focused role (`worker`, `reviewer`, `specialist`, or `observer`);
- a short responsibility summary;
- a reusable prompt describing the role, method, boundaries, deliverable, and completion criteria;
- only the tools it actually needs.

Example prompt for a reviewer:

> Review the assigned diff for correctness and regressions. Read the relevant tests first. Do not edit files. Report only confirmed findings with severity, evidence, exact paths, and a minimal fix recommendation. State what you checked when no issue is found.

### 3. Decompose and create tasks

Create one task per observable outcome with `teammate_create_task`. Each task declares one or more repository-relative paths plus an access mode: `read` or `write` (default). Paths are coordination context, not permanent exclusive locks. Do not use globs, absolute paths, parent traversal, or duplicate paths.

Put the complete handoff in the task description:

- goal and relevant context;
- ordered procedure;
- inputs and constraints;
- exact deliverable and location;
- verification command or acceptance criteria;
- what to do when blocked.

Declare artifact dependencies at creation time with `blockedBy` (a list of task IDs that must complete first). Use it whenever a later task needs a concrete earlier artifact or decision. Dependencies are immutable after creation; there is no public mutation tool. Keep titles short (`Audit auth refresh`, `Implement login form`, `Review API diff`) and put detail in descriptions.

### 4. Run independent work in parallel

Start independent tasks in the same turn. Every `teammate_start_task` returns immediately. Read-only tasks may overlap. The extension blocks overlapping `write` tasks only when they would run concurrently in the shared workspace:

```text
teammate_start_task taskId="task_1"
teammate_start_task taskId="task_2"
teammate_start_task taskId="task_3"
```

Continue coordinating while workers run. Call `teammate_wait taskIds=["task_1", "task_2", "task_3"]` only when their final outcomes are needed. Dependent tasks (declared with `blockedBy` at creation) receive a `Task unblocked` inbox message when all blockers complete. Do not serialize independent work.

### 5. Communicate and synthesize

Use `teammate_message` for every handoff, blocker, decision, or broadcast. A worker proactively records its plan, material progress, blockers, and changed assumptions in the `agent` mailbox. These intermediate messages do **not** interrupt the main session; the leader reads them with `teammate_inbox` only when needed and may send targeted replies with `teammate_message`. The worker's terminal `teammate_report` carries its final summary. After the child closes, the harness—not the prompt—builds one canonical terminal result from task state and captured stdout/stderr, records it in the agent mailbox, and injects it into the main session as the single follow-up update. This keeps the leader focused on dispatch and final synthesis. Worker messages remain leader-validated append-only outbox events; the TUI intentionally shows only team/task status.

After `teammate_wait`, inspect the files and evidence, reconcile conflicting results, run verification yourself, and provide one synthesized answer. A worker's claim is not proof until its deliverable and tests are checked.

### 6. Isolation, failures, and cleanup

Shared-workspace overlapping writes are blocked at task start. To deliberately explore overlapping write approaches, start the second task with `isolation="worktree"`, then review and integrate its captured diff. Treat failed, timed-out, cancelled, or missing tasks explicitly; retry a settled failed task with `teammate_start_task retry=true`, which gives the same idle teammate a fresh run identity. Cancel a running task with `teammate_cancel_task`. An idle teammate stays available for five minutes by default and is retired only when it has no assigned/running work and no unread messages. Terminal task results remain available until the leader synthesizes them; then use `teammate_cleanup` to prune those task records.

## Current-Session State and Concurrency

The team leader is the only writer of the transient shared state file for the current session. Every spawned worker receives a fresh `runId`, reads that file, and emits append-only events through the unified `teammate_message`, `teammate_inbox`, and `teammate_report` worker capabilities. The leader validates the sender, run identity, recipient, task ownership, and event shape before applying an event, so an old worker run cannot update a later run, and one worker cannot overwrite another worker's message, revert a read receipt, or update another teammate's task. Completed runs write their final board before their per-run outbox and replay metadata are compacted.

A child running in worker mode registers only three identity-bound capabilities (`teammate_message`, `teammate_inbox`, and status reporting); it never registers team lifecycle, UI, task-board, or spawn tools. It executes one bounded task run within its recorded paths, messages the leader at plan/progress/blocker milestones, reports its final outcome, and exits. Its idle teammate identity can be reused for later current-session work. The parent harness owns final delivery to the main session, including workers that exit, fail, time out, or never report a terminal result. This is a reliable collaboration protocol, not an OS security sandbox: workers still run with the user's local permissions. A normal exit code of `0` is the only successful process outcome; signal termination, timeout, and non-zero exit fail the task.

Teams do not persist across session starts or `/resume`: every session begins with an empty team. On shutdown, live workers are terminated and observed before the shared state directory is deleted, then the in-memory board is cleared. Pending-task self-claim is intentionally not available until a cross-process claim lock exists; atomic snapshot writes alone are not a safe claim protocol. Plan approval and task-completion hooks likewise remain future work until their state transitions and quality-gate semantics are designed end to end.

## License

MIT.