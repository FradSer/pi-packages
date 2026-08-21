# Repository Guidelines

## Project Structure

`packages/keyboard/` publishes `pi-keyboard`, whose package-root `index.ts`
re-exports the extension in `src/index.ts`. Hardware behavior is split across
`src/config.ts` (persisted settings), `driver.ts` (the `via-rgb` executable),
`protocol.ts` (VIA RAW HID packets), `state-machine.ts` (lifecycle state and
transitions), `global-sessions.ts`, and `types.ts`. BDD contracts live in
`features/keyboard.feature`; executable package checks are in
`tests/test_keyboard_package.py`.

## Commands

Run focused tests with:

```bash
python3 -m pytest packages/keyboard/tests/ -q
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/keyboard pack --dry-run
```

There is no separate build step; Pi loads the TypeScript extension directly.

## Style and Architecture

Use ESM TypeScript and preserve the stable state names (`idle`, `unread_chat`,
`thinking`, `need_approval`, `error`) and zones (`all`, `matrix`, `underglow`).
Keep Pi lifecycle wiring and `/keyboard` handling in `src/index.ts`; keep HID
packet construction and external CLI execution in their dedicated modules.
The state machine must keep user aborts distinct from fatal errors, deduplicate
unchanged states, and retain graceful behavior when hardware is unavailable.
The default configuration is in-memory (`saveToEeprom: false`), so transitions
must use `--no-save` unless explicitly configured otherwise.

## Testing and Release

Update `features/keyboard.feature` before changing behavior, then extend the
Python contract tests. Test state definitions, packet bytes, zones, lifecycle
transitions, session cleanup, hook registration, and no-save behavior. The
manifest ships `index.ts`, `src`, `features`, and both READMEs; keep those
entries aligned with implementation. Add a Changeset for published behavior or
manifest changes and follow the repository's Conventional Commit scopes.
