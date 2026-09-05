# Repository Guidelines

## Structure

`index.ts` re-exports the extension in `src/index.ts`. The command registration and wiring are in `src/index.ts`; `context.ts` builds a compact recent-session excerpt, `spawner.ts` launches and parses the read-only child Pi process, and `overlay.ts` owns the interactive multi-turn popup. BDD scenarios are in `features/btw.feature`, with executable Python checks in `tests/`.

## Commands

From the repository root:

```bash
python3 -m pytest packages/btw/tests/ -q
pnpm exec tsc --noEmit -p packages/btw/tsconfig.json
pnpm --dir packages/btw pack --dry-run
```

## Style and architecture

Keep command, context, process, and UI responsibilities separated. `/btw` must remain a TUI-only `ctx.ui.custom` overlay that owns its input and never writes to session history. The child runs with `--print --mode json --no-session`, allows only `read`, `grep`, `find`, and `ls`, and explicitly excludes `bash`, `edit`, and `write`. Preserve prompt-file cleanup after close and launch errors, bounded output, abort/termination handling, compact context limits, and follow-up history. The popup covers the editor: preserve `margin: { bottom: 0 }` in
`src/index.ts`, the 40% answer-body cap, and multi-turn input focus.

## Testing Guidelines

`features/btw.feature` and `tests/` cover bounded context, child JSONL parsing,
usage aggregation, follow-up history, popup geometry, and cancellation cleanup.
Verify that no side-thread messages enter the main session. Packed resources
include `.memory` alongside `index.ts`, `src`, and `README.md`.