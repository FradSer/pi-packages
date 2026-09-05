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
pnpm --dir packages/monitor pack --dry-run
```

## Style and Architecture

Keep monitor captures and command output untrusted; never let raw output become system instructions.

- **Result-Contract Monitoring (`monitor_start`)**: Requires a machine-verifiable `result_pattern` (regex with named captures or JSON extraction), optional `failure_pattern`, and `timeout_ms`. Keep output bounds in `src/monitor.ts`: 10 KiB displayed lines, 64 KiB fragments, 2,000 lines/256 KiB retained logs, and 100 lines/32 KiB terminal tails.
- **Execution Duality**:
  - *Interactive mode*: Starts the detached process group, returns a compact started result, sets `terminate: true` to end the turn, and delivers exactly one terminal `monitor-result` message (`triggerTurn: true`).
  - *Non-interactive mode (`print`/`json`)*: Waits synchronously inside `monitor_start` and returns the terminal report directly.
- **Progressive Tool Disclosure**: `monitor_stop` is registered but activated via `pi.setActiveTools()` only while at least one monitor is running.
- **UI**: Use `ctx.ui.custom` for the `/monitor` output-viewing console and Pi footer for active monitor counts. Provide monitor usage guidance through the system prompt without intercepting or modifying native `bash` calls. Do not add polling tools or skills.

## Testing Guidelines

`features/monitor.feature` and `tests/test_monitor_package.py` cover terminal
matching, timeout, print/JSON completion, diagnostic bounds, and process-group
cleanup. Exercise zero-exit-without-match (`result_missing`) and descendants
that ignore SIGTERM; shutdown must still escalate to SIGKILL. The package
ships `index.ts`, `src`, and `README.md`.
