# Repository Guidelines

## Project Structure

`packages/plan-mode/` publishes `@fradser/pi-plan-mode`. The package-root
`index.ts` re-exports `src/index.ts`, which owns `/plan` commands, plan-mode
state, prompt injection, model switching, and TUI widgets. `src/config.ts`
persists the dedicated model settings; `src/plan-worker.ts` runs read-only
explore workers and the plan writer; `src/plan-overlay.ts` renders the review
action menu. BDD contracts are in `features/plan-mode.feature`; executable
checks are in `tests/test_plan_mode.py`.

## Commands

Run focused tests and package type checking from the repository root:

```bash
python3 -m pytest packages/plan-mode/tests/ -q
pnpm exec tsc --noEmit --allowImportingTsExtensions -p packages/plan-mode/tsconfig.json
pnpm --dir packages/plan-mode pack --dry-run
```

## Style and Architecture

`/plan <prompt>` starts in the main session; worker research begins only when
the plan marks it required. Open review after `agent_settled` without awaiting
session-replacing UI inside the lifecycle hook; catch asynchronous review
failures and release the re-entry guard.

Plan mode must remain read-only: only the session-specific plan file may be written, bash is limited
to the explicit safe command set and read-only Git subcommands, and explore
workers receive only `read`, `grep`, `find`, and `ls`. Child workers use
`--no-extensions` and must not gain wall-clock timeout behavior; the host owns
the plan-file write. Keep the persistent indicator below the editor, worker
status above it, and review actions within the overlay viewport.

## Testing Guidelines

`features/plan-mode.feature` and `tests/test_plan_mode.py` cover read-only
command parsing, worker diagnostics, CLI arguments, automatic review, and
session-replacement deadlocks. The bash allowlist is a command guard, not an OS
sandbox; keep tests for unsafe stages in chains/pipelines. Pack checks must
include `index.ts`, `src`, and `README.md`.
