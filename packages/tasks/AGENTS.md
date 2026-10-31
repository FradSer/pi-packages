# Tasks Package Guidelines

`packages/tasks/` publishes `@fradser/pi-tasks`. Package-root `index.ts` re-exports
`src/index.ts`. `src/tool.ts` registers the four public tools, `src/store.ts`
owns atomic state transitions and dependency validation, `src/persist.ts`
manages directory-scoped storage under `<agentDir>/tasks/`, and `src/rows.ts`
implements pi-kit lifecycle rendering. BDD contracts live in `features/`;
executable tests live in `tests/`.

## Commands

Run focused tests from the repository root:

```bash
python3 -m pytest packages/tasks/tests/ -q
pnpm --dir packages/tasks pack --dry-run
sh packages/tasks/tests/tasks_docker.sh
```

## Structure and Invariants

- **Passive Store**: Tasks is an explicit, passive work list. Open tasks do not
  trigger turns, and a recorded verification verdict does not run a test command.
  No capability injection, settlement instructions, or model continuation remains.
- **Tool Surface**: Exactly four tools: `create_task`, `get_task`, `list_tasks`,
  and `update_task`. No child process reaches these tools; subagents cannot take
  or complete tasks, and the leader session records outcomes from reports.
- **State Machine**:
  - `pending`: Unstarted or reopened work. Prerequisites must complete before entry to `in_progress`.
  - `in_progress`: Held attempt by derived caller.
  - `blocked`: Work awaiting resolution or investigation; requires a `reason`.
  - `cancelled`: Abandoned unfinished work; leaves the active board while preserving its record.
  - `completed`: Requires `outcome=success` with evidence and passing verification verdict (`verdict=pass`). An `outcome=failed` verdict retains failure evidence and returns the task to `blocked`.
  - `pending` (reopen): Reopening completed work withdraws conclusions and transitions dependent tasks to `blocked`.
- **Rendering & Display**: All tool outputs follow pi-kit `[tasks]` lifecycle
  style. Every row is collapsed by default showing `[tasks] <action> · <title>`
  with native expansion hints. Headlines wrap across terminal widths without
  truncation; the wrapped body reveals full descriptions, dependencies, and
  evidence via Ctrl+O or row action.

## Task References

- Read @README.md for the complete tool schemas, query pagination, and replacement semantics.
- Read @CONTEXT.md for historical architecture decisions and export-removal boundaries.
- Read @TUI.zh-CN.md when changing TUI presentation or expansion behavior.
