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
npx tsc --noEmit -p packages/recap/tsconfig.json
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/recap pack --dry-run
```

## Style and Architecture

Use strict ESM TypeScript and shared `@fradser/pi-kit` model, spinner, theme,
and text helpers. Recap generation is asynchronous and in-process through
Pi's model registry: preserve deduplication, cancellation, the 30-second
abort timeout, and stale-session error handling. Keep summaries single-line
and capped at 120 characters. Persist changed recaps with `pi.appendEntry`
and best-effort directory-session synchronization. Widgets and menus are TUI
only; headless sessions and commands must not start generation. Keep the
recap widget above the editor and preserve its native-spinner alignment.

## Testing and Release

Update `features/recap.feature` before behavior changes, then add regression
coverage under `tests/` for persistence, startup restoration, prompt cleanup,
configuration, cancellation, and headless behavior. The manifest ships
`index.ts`, `extensions`, `features`, and `README.md`; it excludes tests. The
release script includes `@fradser/pi-recap`; use the repository Changeset and
Conventional Commit conventions for published changes and verify the pack
contents before release.
