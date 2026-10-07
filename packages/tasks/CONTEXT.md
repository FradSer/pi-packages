# Tasks working context

Read @README.md for the task interface and persistence contract.

## Current state

`packages/tasks` is one self-contained Pi package. Loading and writes use only
`tasks.json`. The old `board.json` file and its resolvers are retired and are not
loaded, copied, renamed, or deleted. Task file version stays 2.

Uncommitted on this tree: the discoverability and cost change
(`@../../.changeset/tasks-discoverable-and-cheap.md`), which follows the four
changesets that shipped with `e86a44f`. The four are committed; the retirement
baseline snapshot named in earlier revisions of this file is no longer needed.

## Why the tools were not used

Measured before the change, over 1152 session files under `~/.pi/agent/sessions`
(437 in this repo, 59 here since 2026-10-01): `create_task` ran 17 times in 7
sessions while `bash` ran 78178 times. The tools loaded and were exposed the whole
time. Four causes, in the order they mattered:

- **No per-turn presence.** The package bound five hooks, all of them either a
  lifecycle reset or the settle check. `pi-goal` injects a capability note from
  its `context` hook every turn, which is why goals are used; tasks had no
  equivalent.
- **A self-sealing reminder.** `src/stop-check.ts` returns early when no open task
  exists, so the reminder could sustain the habit and never start it. All 5
  sessions carrying `pi-tasks-status` are among the 7 that called `create_task`.
- **The wrong moment.** `agent_before_settle` fires after the model considers the
  work finished. A task record earns its value before the work starts.
- **A cost at delivery.** The checks refused an honest single-attempt completion,
  a mixed call discarded its content edits, and a misplaced context field was
  refused with `schema is false`.

## What the change does

- The trigger conditions live in two surfaces. `create_task` carries them in its
  snippet and its description, which are sent to the provider on every turn
  already. `src/presence.ts` adds one bounded note per request from the `context`
  hook, because a description cannot say when the situation calls for the tool: a
  session that never considers recording work never reads the description of the
  tool that would record it. The note carries no task state, so it is identical
  every turn and lands at a fixed index after the system message, which keeps each
  request a prefix of the last. `tests/test_discoverability.py` pins the note, its
  bound, its position, and that one source file defines it.
- A context-only write is not progress. The settlement snapshot no longer hashes
  `context`, because a brief is what a successor reads rather than a change to
  the work. Counting it bought another automatic continuation.
- `normalizeTaskContext` moves a handoff field written at the context level into
  `context.handoff`, and refuses a field no layer owns with a message naming the
  field and where the handoff fields belong.
- The nested schemas in `CONTEXT_PARAMS` are open for that reason: a closed one
  made the validator the author of the refusal, and its wording was `schema is
  false`. The top level stays closed, where the validator's wording is readable.
- `executeTaskUpdate` validates and records the content half before it reads the
  status half. A refused status keeps the edit and names the status change as the
  half to retry. A refused content edit records neither half.
- `checkCompletion` returns every unsatisfied check, and
  `completionRefusalReasons` joins their remedies into one message.
  `completionRequirements` names what a completion must carry, and the take path
  reports it.

## Decisions taken deliberately, not oversights

- **The exported `tasks` container.** `packages/agent-teams/src/state.ts` imports
  it as `storedTasks` and publishes it as its own snapshot state, and it owns the
  file there. The shared live container is the arrangement, not an accident.
- **The runtime verb section in `src/store.ts`.** `revertUndeliveredTake`,
  `acknowledgeSupersession`, `bindTask`, `failTasksHeldBy`, and `discardTask` are
  named for what happened and stay unreachable from the model tools.
- **`checkCompletion` returns an array.** Breaking for a library consumer, and
  nothing in this repository reads it outside `store.ts`. Naming one check at a
  time was the cost the change exists to remove.
- **The three-call state machine stays, with one route around it.** R5 asked for
  the single-attempt path to be removed or proven cheap. It is proven cheap
  instead: the take names the requirements, a refusal names every unmet check with
  its remedy, and one call after a refusal succeeds. The recorded creator is the
  route around the take, so a caller that records and finishes its own work pays
  two calls. Removing the take outright would delete the attempt record that
  `recovery_hold` rests on.
- **The child-process limit is documented, not worked around.** A child runs
  `pi --no-extensions`, so the four tools cannot reach it. A second task surface
  inside every child is a different package's problem.

## Verification

- `python3 -m pytest packages/tasks/tests/ -q` — 142 pass, 0 fail. Coverage
  added by this change: `tests/test_discoverability.py` (the trigger conditions in
  the tool surface, and that the package injects no message of its own), three
  context tests in `tests/test_work_context.py`, `tests/test_completion_cost.py`,
  and the rewritten mixed-call tests in `tests/test_task_contents.py`.
- `pnpm typecheck` passes.
- `pnpm --dir packages/tasks pack --dry-run` lists `index.ts`, all of `src/`, and
  `README.md`.
- `AGENTS.md` carries a Task Records section, which is where the tool trigger
  conditions are stated for a session that has not read this file.

## Open, not fixed here

A spawned child lost its private session directory twice while this change was
being delegated: the first run's JSONL tree was deleted mid-run, and the second
run's `--session-dir` was gone within 90 seconds of `spawner.ts` creating it, so
the child reported `ENOENT` with no usable answer. The child's file writes
survived both times, which is how the feature scenarios in this change exist. The
cause is outside `packages/tasks` and is not reproduced.
