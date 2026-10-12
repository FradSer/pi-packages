# Tasks working context

Read @README.md for the task interface and persistence contract.

## Current work

Follow-ups from a review of the real task records: id stabilization, exit semantics,
subject guidance, a long-subject fixture, dependency guidance, and now a smaller tool
surface with a subject limit so creating a task is light.

## Changes

- `src/graph.ts`: derived ids stop at a word boundary and disambiguate with `-1`, `-2`.
- `cancelled` is a fifth terminal status with a required reason; `reopenTask` returns it to pending.
- `src/tool.ts`: `update_task status=cancelled`, `cancelReason` projection and row line.
- `src/tool.ts`: `MAX_TASK_SUBJECT_LENGTH = 60`; `create_task` and `update_task` refuse a
  longer subject with a message pointing at `description`. The store stays permissive.
- `src/tool.ts`: the four tool descriptions and every parameter description were trimmed,
  and `description`/`verify` are documented as optional. Surface: 7482 -> 6044 characters.
- `tests/task-stop-live-fixture.ts`: the long-subject case uses a 60-character subject.
- Agent Teams reports cancelled counts; its long-subject fixture seeds through the store.

## Verification

- Tasks suite: 177 passed (`python3 -m pytest packages/tasks/tests -q`).
- Agent Teams consumer suite: 302 passed (`python3 -m pytest packages/agent-teams/tests -q`).
- Typecheck passed with `pnpm --config.verify-deps-before-run=false typecheck`.
- Repository packed-manifest check passed for 18 packages; `git diff --check` clean.
- Native waiting frames: 12 captures in `/tmp/tasks-compact-native`.
- Surface measurement: `create_task 622+642`, `get_task 221+184`, `list_tasks 226+712`,
  `update_task 903+2534` characters (description + parameter schema).

## Limitations and next checks

- The subject limit is model-facing only; stored records may be longer and still render whole.
- The id stays the creation handle after a rename; renames are not tracked.
- A cancelled prerequisite still blocks its dependents.
- Matt Pocock, Goal and Impeccable test runs fail in this workspace on missing `tsx` or an
  unverified dependency tree; that is an environment gap, not this change.
- A reload is needed before a running Pi session loads the updated tools and renderer.