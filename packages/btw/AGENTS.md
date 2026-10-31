# btw Package Guidelines

## Scope and structure

`/btw` answers side questions in a TUI overlay. It does not add messages to the main session.

- `src/index.ts` registers the command and connects the components.
- `src/context.ts` selects recent conversation text.
- `src/spawner.ts` runs the read-only Pi child and parses JSONL output.
- `src/overlay.ts` owns input, conversation turns, scrolling, and cancellation.
- `features/btw.feature` defines behavior. `tests/` verifies it through Python and TypeScript.

Read @README.md for usage. For UI changes, read the installed Pi `docs/tui.md`
and its applicable examples.

## Contracts

- Keep `/btw` TUI-only. Use `ctx.ui.custom` for input ownership.
- Do not write side questions or answers to the main session.
- Select four recent user or assistant text messages. Display them in chronological order.
- Limit context to 4000 characters, including the truncation marker. A zero limit returns an empty excerpt.
- Run the child with `--print --mode json --no-session --no-extensions`.
- Allow only `read`, `grep`, `find`, and `ls`. Exclude `bash`, `edit`, and `write`.
- Keep prompt files private. Remove them after child close or launch failure.
- Preserve stream limits, timeout diagnostics, and graceful termination before escalation.
- Keep the overlay bottom margin at zero. Cap the answer at 40% or the space remaining after measured controls.
- Support 20 columns and 8 rows with a compact layout. Preserve the composer and essential controls.
- Delegate host focus to the native input. Home and End edit the visible composer.
- Handle normalized mouse events. Cache invalidation must not stop active work.
- Include completed answers in follow-up history. Aggregate usage across completed turns.
- Cancel an initial turn by closing the overlay. Cancel a follow-up by restoring prior turns.
- Ignore results after cancellation or disposal. Keep the follow-up input active after a completed turn.
- Preserve the legacy `onSpawn`, `showAnswer`, and `showError` interface.

## Verification

Run these commands from the repository root:

```bash
python3 -m pytest packages/btw/tests/ -q
pnpm typecheck
pnpm exec tsc --noEmit -p packages/btw/tsconfig.json
pnpm --dir packages/btw pack --dry-run
```

Runtime changes also require installation checks and live `pi --print` verification.
Test overlay input and geometry interactively. Report any unavailable verification.

Prefer behavior tests over source-string checks. Reuse test setup and deterministic turn completion.
Keep lifecycle checks for child arguments, prompt cleanup, cancellation, and stream failures.
Verify packed resources against `package.json`; do not infer that optional directories exist.
