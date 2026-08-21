# Repository Guidelines

## Structure

`index.ts` re-exports the extension in `src/index.ts`. The command registration and wiring are in `src/index.ts`; `context.ts` builds a compact recent-session excerpt, `spawner.ts` launches and parses the read-only child Pi process, and `overlay.ts` owns the interactive multi-turn popup. BDD scenarios are in `features/btw.feature`, with executable Python checks in `tests/`.

## Commands

From the repository root, run `python3 -m pytest packages/btw/tests/ -q` for focused tests, `pnpm test` for the full suite, and `npx tsc --noEmit -p packages/btw/tsconfig.json` for the package’s strict typecheck. Use `pnpm --dir packages/btw pack --dry-run` to inspect the shipped extension files.

## Style and architecture

Use strict ESM TypeScript and keep the command, context, process, and UI responsibilities separated. `/btw` must remain a TUI-only `ctx.ui.custom` overlay that owns its input and never writes to session history. The child runs with `--print --mode json --no-session`, allows only `read`, `grep`, `find`, and `ls`, and explicitly excludes `bash`, `edit`, and `write`. Preserve prompt-file cleanup after close and launch errors, bounded output, abort/termination handling, compact context limits, and follow-up history. Use `@fradser/pi-kit` for shared theme and runtime helpers; follow its style callbacks and keyboard-scrolling patterns rather than global terminal listeners.

## Testing and release

Update `features/btw.feature` before behavior changes, then update `tests/` and run the focused suite. Keep `package.json` `pi.extensions`, peer dependencies, `files`, README, and changelog/release metadata aligned. This public Pi extension depends on `@fradser/pi-kit` through `workspace:*`; preserve that dependency direction and publish ordering.