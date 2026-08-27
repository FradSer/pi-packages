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
npx tsc --noEmit -p packages/plan-mode/tsconfig.json
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/plan-mode pack --dry-run
```

## Style and Architecture

Use ESM TypeScript with the package's strict, no-emit configuration and reuse
`@fradser/pi-kit` for model, spinner, and theme helpers. Plan mode must remain
read-only: only the session-specific plan file may be written, bash is limited
to the explicit safe command set and read-only Git subcommands, and explore
workers receive only `read`, `grep`, `find`, and `ls`. Child workers use
`--no-extensions` and must not gain wall-clock timeout behavior; the host owns
the plan-file write. Keep the persistent indicator below the editor, worker
status above it, and review actions within the overlay viewport.

## Testing and Release

Update the relevant `.feature` scenario before behavior changes, then add
coverage under `tests/` for restrictions, worker diagnostics, CLI arguments,
and review behavior. The manifest ships `index.ts`, `src`, and `README.md`.
It is included in the `scripts/publish-release.mjs` allowlist and publishes
through the GitHub Actions Changesets workflow. Follow repository Changeset and
Conventional Commit conventions for release changes.
