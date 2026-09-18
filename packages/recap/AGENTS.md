# Repository Guidelines

## Project Structure

`packages/recap/` publishes `@fradser/pi-recap`. The package-root `index.ts`
re-exports `extensions/index.ts`. `extensions/index.ts` registers `/recap`,
lifecycle hooks, model/language menus, and the above-editor widget;
`extensions/config.ts` handles `recap.json` and environment overrides;
`extensions/recap.ts` extracts exchanges, builds prompts, cleans one-line
summaries, and calls the model registry. BDD contracts are in
`features/recap.feature`, with executable checks in `tests/test_recap_package.py`.

## Commands

Run focused tests and type checks from the repository root:

```bash
python3 -m pytest packages/recap/tests/ -q
pnpm exec tsc --noEmit --allowImportingTsExtensions -p packages/recap/tsconfig.json
pnpm --dir packages/recap pack --dry-run
```

## Style and Architecture

Recap generation is asynchronous and in-process through
Pi's model registry: preserve deduplication, cancellation, the 30-second
abort timeout, and stale-session error handling. Keep summaries single-line
and capped at 120 characters. Persist changed recaps with `pi.appendEntry`
and best-effort directory-session synchronization. Widgets and menus are TUI
only; headless sessions and commands must not start generation. Keep the
recap widget above the editor and preserve its native-spinner alignment. While
generation runs, the recap line is replaced by the identity-only `Recapping...`
activity row; never render the marker above a stale recap line.

## Testing Guidelines

`features/recap.feature` and `tests/test_recap_package.py` cover persistence,
startup restoration, prompt cleanup, configuration, cancellation, and headless
behavior. Verify first-prompt summaries describe requested work as planned,
not completed; unchanged recaps must not create new entries. The manifest
ships `index.ts`, `extensions`, `features`, and `README.md`, excluding tests.
