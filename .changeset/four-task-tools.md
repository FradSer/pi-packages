---
"@fradser/pi-tasks": minor
"@fradser/pi-agent-teams": minor
---

Four tools, one noun. The task board is now `create_task` / `get_task` / `list_tasks` / `update_task` — the same shape as `create_goal` and `get_goal` beside it — and the three names for one thing are gone.

**The surface**

`@fradser/pi-tasks` used to register a single `task` tool with an `action` parameter. It now registers four tools, one per operation. The decomposition follows Claude Code's task tools for one reason that matters more than the resemblance: a position in the lifecycle is reachable by exactly one call, and a refusal can name the call that earned it.

The names are not Claude Code's. They follow this workspace: verb first, the noun as the object, snake_case — `create_task` beside `create_goal`, `get_task` beside `get_goal`. A PascalCase name imported from another product reads as someone else's vocabulary in a session where every other tool here is snake_case.

- `create_task` records what must be done, and takes `supersedes`, which replaces an obsolete task atomically and re-points every dependent at the replacement.
- `get_task` reads one task in full, including the structured brief a successor needs. `list_tasks` is bounded and leaves the brief out, so this is how a brief is read; without it a handoff is written for nobody. It accepts an `id` and nothing else.
- `list_tasks` reports the state a model would otherwise have to infer: who holds each task, whether a recovery hold is set, what it depends on. A pending task that must not be taken is otherwise indistinguishable from one that may.
- `update_task` is the fat one — status, content, brief — the same division Claude Code uses, where one declaration covers four operations rather than four declarations competing for the prompt.

**Breaking**

- The `task` tool and its `action` parameter are gone. A caller that used `action: "create"` uses `create_task`; `action: "list"` uses `list_tasks`; `action: "take"`, `action: "complete"` and `action: "reopen"` all become `update_task` with `status: "in_progress" | "completed" | "pending"`.
- `BoardTask` is now `Task`. It is re-exported from `@fradser/pi-agent-teams`, so a consumer of that package's types sees the new name.
- The store and file symbols lost the board prefix: `loadBoard` → `loadTasks`, `clearBoard` → `clearTasks`, `boardDiagnostic` → `storeNotice`, `configureBoardStore` → `configureTaskStore`, `isBoardStoreClaimed` → `isTaskStoreClaimed`, `onBoardChanged` → `onTasksChanged`, `BoardStoreHooks` → `TaskStoreHooks`, `boardFilePath` → `tasksFilePath`, `readBoardFile` → `readTasksFile`, `writeBoardFile` → `writeTasksFile`, and `WORK_RUNTIME_VERSION` → `TASKS_FILE_VERSION`.
- The task file is `tasks.json`. It is still **read** as `board.json`, so a task recorded by an earlier install is picked up rather than orphaned, and a session that loaded the pre-rename file says so. Writes only ever go to `tasks.json`.
- `TASK_CAPABILITY_TOOLS` lists the four names, so a spawner granting a capability has to be updated. A grant of `"task"` now matches nothing.

**What did not change, deliberately**

- No delete. Claude Code removes a todo with `status: "deleted"`; this package's contract is that a task carrying a result, a dependency or a completed attempt is real work, and real work is returned to pending rather than erased.
- A completion still needs an explicit `outcome`. Collapsing it into `status: "completed"` alone would let a completion be a field assignment rather than a judgement with evidence, which is what the old `complete` action existed to prevent.
- `dependsOn` is not mutable through `update_task`. Supersession re-points dependencies, atomically and cycle-checked, which is the mechanism this package already pins.
- `status` is refused by name when it is outside the three routes, instead of falling through to the content branch where a caller would be told it had supplied nothing to change.

**Verification**

`python3 -m pytest packages/tasks/tests/ -q` (71 passed), `packages/agent-teams/tests/` (280 passed), `pnpm typecheck`, and the tool-parameter schema fixture. Driven live on Pi 1.0.0 as well: a throwaway extension called all four registered tools through `ctx.executeTool` for twenty-seven steps of a full lifecycle — create, get, list with each filter and cap, take, twice-take, a brief written twice, read back, every refusal a caller can earn, failure and recovery, completion, double completion, reopen, an unmet dependency, a supersession, and an unknown field. Seventeen accepted, ten refused, and the supersession reached the file with the brief intact.
