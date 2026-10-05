# Tasks working context

Read @README.md for the task interface and persistence contract.

## Current state

`packages/tasks` is one self-contained Pi package. Loading and writes use only
`tasks.json`. The old `board.json` file and its resolvers are retired and are not
loaded, copied, renamed, or deleted. Task file version stays 2.

The tree is dirty and uncommitted. Four changesets ship together:

- `@../../.changeset/retire-task-board-runtime.md` — the retirement, reviewed.
  Standards PASS, Spec PASS, candidate
  `9fe82eeca789bad9bfea6c9c6dd6036316be22cebbf10327283b63bfb456db8c`.
- `@../../.changeset/tasks-one-claimable-rule.md` — one definition of claimable work.
- `@../../.changeset/tasks-one-refusal-shape.md` — one refusal shape. Breaking for
  tasks and agent-teams together.
- `@../../.changeset/tasks-settlement-and-completion-fixes.md` — the three fixes
  below.

The retirement baseline snapshot is at
`/var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/pi-tasks-retire-register-rfrzgz2o`.
A git diff against HEAD includes that earlier work, so it is not a review scope
on its own.

## Three settlement and completion fixes

- **Headless settlement prints.** The `waiting` and `paused` notices are transcript
  rows. `TaskStopCheck.check` now takes `hasUI` from the settle handler's
  `ExtensionContext` and returns `undefined` on a settlement that cannot continue
  when the session has no UI. A continuation result keeps its `custom_message` in
  every mode, because the model reads it on the next request. The passive-row
  contract lives in `tests/test_task_stop_check.py`; the live suite asserts
  non-empty stdout for `ignore`, `progress`, and `inspect-only`.
- **A stale holder is not a hold.** `completeTaskWithOutcome` applies the holder
  check only while `status === "in_progress"`. A restored pending task naming a
  departed holder completes through the fallback path, as `takeTask` accepts it.
  A task nobody ever took is still refused when the checks are on.
- **A failure clears its gate answer.** An `outcome: "failed"` completion clears
  `completionVerdict` and `completionGate`; the blocker stays as evidence.

Concurrent edits kept in the same files: the settlement summary row names the
work once with no task-id prefix (`src/stop-check.ts`), `index.ts` re-exports
`./src/stop-check.ts`, and the README and `features/task-stop-check.feature`
carry that wording.

## One definition of claimable work

- `claimableTasks()` is the only answer to "what can a caller take". The `list_tasks`
  filter and the settlement reminder both read it.
- Fixes a real divergence: the reminder's own copy required an unheld task, and a
  restored pending task still naming a departed holder is pending, so `takeTask`
  accepts it. The reminder under-reported available work.
- `resolveRecordKind` in `src/types.ts` names the restored-record classification
  next to `TASKS_FILE_VERSION`. Present-but-invalid is repaired to `task`,
  including `null`; only an absent value is inferred from the reserved namespace.

## One refusal shape

- Every refusal is `{ refusal, detail?, reason }`. `TaskRefusalPayload` is the
  payload; `refuse()` and `refuseClaim()` are the only two constructors and both
  delegate to one private builder.
- The success flag stays what each operation's domain calls it: `ok` for a task
  write, `applied` for a claim marker.
- `takeTask`'s `"unknown"` became `"unknown-task"`, so one fact has one code.
- Breaking. Consumers read `result.reason` where a result used `result.error`, and
  read `result.refusal` to branch on why. The sentences themselves are unchanged.

## Decisions taken deliberately, not oversights

- **The exported `tasks` container.** `packages/agent-teams/src/state.ts` imports
  it as `storedTasks` and publishes it as its own snapshot state, and it owns the
  file there. The shared live container is the arrangement, not an accident.
- **The runtime verb section in `src/store.ts`.** `revertUndeliveredTake`,
  `acknowledgeSupersession`, `bindTask`, `failTasksHeldBy`, and `discardTask` are
  named for what happened and stay unreachable from the model tools. Moving them
  is churn without behaviour.

## Verification

- `python3 -m pytest packages/tasks/tests/ -q` — 126 pass, 0 fail. The three new
  red-first tests and the headless passive-entry test are in this count.
- `python3 -m pytest packages/agent-teams/tests/ packages/subagents/tests/ -q`
  with `PI_TASK_HOLDER` and `PI_TEAMMATE_*` stripped — 300 + 583 pass, 0 fail.
  The resident session sets `PI_TASK_HOLDER`; two agent-teams fixtures copy
  `os.environ` and derive a non-main holder without the strip. That is an
  environment artifact of a resident run, not a code regression.
- `pnpm typecheck` passes. `pnpm --dir packages/tasks pack --dry-run` lists
  `index.ts`, all of `src/`, and `README.md`.
- Two timeout fixtures in agent-teams had budgets below the runtime's own
  30-second confirmation window; each finishes in about 31 seconds and reports ok,
  so their budgets moved to 50 seconds. No runtime timeout changed.

## Headless output: resolved

A `pi --print` run that ended with unfinished work printed nothing and exited 0:
the task check returned a result carrying a `custom_message` draft on the settle
that ended the run. The check returns no result there when the session has no UI
(`ctx.hasUI`), and the run prints its final assistant text. The stdout assertion
in `tests/test_task_stop_live.py` pins it; the E2E scenario `bundle` still
settles the task it created and says so at that step.

`packages/agent-teams/tests/test_bundle_ack.py` carries two earlier fixes, both
stale expectations in a file that was untracked and had never passed: it drove
the composed `agent` tool under the intent interface, where that tool is not
dispatchable, and it expected a surface named `task` when the tasks surface is
four tools.

Changes remain local and uncommitted. Reload Pi to pick up the reminder,
refusal, and settlement changes.
