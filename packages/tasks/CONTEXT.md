# Tasks working context

Read @README.md for the current interface and persistence contract.

## Current state

The user confirms passive Tasks and explicitly requests complete removal of retired compatibility code.

- The extension registers four tools and session persistence only.
- No capability injection, settlement instructions, automatic messages or model continuation remains.
- Deleted `src/stop-check.ts` and `src/presence.ts` and their package exports.
- Deleted the status renderer from `src/rows.ts` and its obsolete formatting tests.
- A regression test requires all retired public exports to be absent.
- The four tools, persistence, ownership, dependencies and completion evidence remain unchanged.
- The Changeset uses a minor release because the user authorizes removal of public exports.
- Saved session history remains untouched. Old persisted custom messages can still use the host fallback renderer.
  Source removal does not erase historical messages. No compatibility display or hiding implementation was added.

## Verification

- RED: export-removal regression identifies all ten retained exports before deletion.
- Tasks suite: 154 passed with `python3 -m pytest packages/tasks/tests -q`.
- `pnpm typecheck` and the Tasks package dry-run passed.
- The packed Tasks manifest excludes both deleted modules.
- `pnpm pack:check` validated all 18 packed manifests.
- `git diff --check` passed after removing a trailing blank line.
- Source search finds no retired status identifier or execution helpers in Tasks source or package entry.
- Actual isolated CLI tests stop with open tasks and use explicit list/get.
- Real isolated Pi PTY run passes expansion and same-component resize at 120x40, 48x24 and 48x12.
- Evidence: `/tmp/tasks-removed-status-native`; inspected restored composed screen.

## Independent review and limitations

- Fresh read-only review returns PASS for the final export-removal candidate.
- The reviewer independently confirms 154 tests, typecheck, package dry-run and no remaining consumers.
- The reviewer finds a stale package description; it now describes passive records and persistence.
- Package dry-run and scoped diff checks pass after that metadata correction.
- The earlier installation check fails for ten other missing packages, not Tasks.
- No settings changes, saved-session edits, commits or publication occurred.
- The current Pi session requires a reload to unload previous handlers.
- Offline evidence does not prove real-model task checking, physical themes or screen-reader behavior.
- Unrelated changes in other packages remain untouched.
