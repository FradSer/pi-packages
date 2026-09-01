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

Use ESM TypeScript and strict repository settings. Keep monitor captures and command output untrusted; never let raw output become system instructions.

- **Result-Contract Monitoring (`monitor_start`)**: Requires a machine-verifiable `result_pattern` (regex with named captures or JSON extraction), optional `failure_pattern`, and `timeout_ms`. Raw output is captured out of LLM context into a bounded buffer (10 KiB line limit, 1000 lines burst, 1 MiB stderr limit).
- **Execution Duality**:
  - *Interactive mode*: Starts the detached process group, returns a compact started result (`[monitor] started · <desc>`), sets `terminate: true` to end the turn, and delivers exactly one terminal `monitor-result` message (`triggerTurn: true`).
  - *Non-interactive mode (`print`/`json`)*: Waits synchronously inside `monitor_start` and returns the terminal report directly.
- **Progressive Tool Disclosure**: `monitor_stop` is registered but activated via `pi.setActiveTools()` only while at least one monitor is running.
- **UI & Guardrails**: Use `ctx.ui.custom` for the `/monitor` output-viewing console and Pi footer for active monitor counts. Use `tool_call` guardrail to advise `monitor_start` for blocking bash commands. Do not add polling tools or skills. Reuse `@fradser/pi-kit` lifecycle renderers.

## Testing and Release

Update `features/monitor.feature` before behavior changes, then add regression
coverage under `tests/`. Verify package contents with the dry-run command. The
manifest ships only `index.ts`, `src`, and `README.md`; published behavior or
manifest changes should follow the repository Changeset and Conventional
Commit conventions. The release script currently includes `@fradser/pi-monitor`.
