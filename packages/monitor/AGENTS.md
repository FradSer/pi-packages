# Repository Guidelines

## Project Structure

`packages/monitor/` publishes `@fradser/pi-monitor`. The package-root `index.ts`
re-exports the extension from `src/index.ts`. `src/monitor.ts` owns detached
process groups, result matching, bounded logs, terminal results, and shutdown;
`src/types.ts` defines TypeBox tool schemas. The extension registers
`monitor_start`, `monitor_stop`, `/monitor`, the prompt hook, and the native
footer/message renderers. BDD contracts are in `features/monitor.feature`, with
executable runtime checks in `tests/test_monitor_package.py`.

## Commands

Run focused tests from the repository root:

```bash
python3 -m pytest packages/monitor/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/monitor pack --dry-run
```

## Style and Architecture

Use ESM TypeScript and the existing strict repository settings. Keep monitor
fields, captures, commands, and output untrusted; never let terminal output
become instructions. Preserve the result-contract model: `result_pattern` is
required, progress does not wake the agent, and exactly one terminal result is
sent. Keep output limits and process-group SIGTERM/SIGKILL cleanup intact. Use
`ctx.ui.custom` for the interactive `/monitor` console and Pi's native footer
for status; do not add polling/output-reading tools or a package skill. Reuse
`@fradser/pi-kit` helpers rather than duplicating shared UI behavior.

## Testing and Release

Update `features/monitor.feature` before behavior changes, then add regression
coverage under `tests/`. Verify package contents with the dry-run command. The
manifest ships only `index.ts`, `src`, and `README.md`; published behavior or
manifest changes should follow the repository Changeset and Conventional
Commit conventions. The release script currently includes `@fradser/pi-monitor`.
