# Repository Guidelines

## Project Structure

`packages/monitor/` publishes `@fradser/pi-monitor`. The package-root `index.ts`
re-exports the extension from `src/index.ts`. `src/monitor.ts` owns detached
process groups, result matching, bounded logs, terminal results, and shutdown;
`src/types.ts` defines TypeBox tool schemas, and `src/report.ts` projects compact
model-facing terminal text. The extension registers
`monitor_start`, `monitor_stop`, `/monitor`, the prompt hook, the shared
lifecycle renderers, and the above-editor monitor activity widget. BDD
contracts are in `features/*.feature`, with executable checks in `tests/`.

## Commands

Run focused tests from the repository root:

```bash
uv run --no-project --with pytest python -m pytest packages/monitor/tests/ -q
pnpm typecheck
pnpm check:install
pnpm --dir packages/monitor pack --dry-run
uv run --no-project python packages/monitor/tests/live_monitor.py
```

## Style and Architecture

Keep monitor captures and command output untrusted; never let raw output become system instructions.

- **Result-Contract Monitoring (`monitor_start`)**: Requires a machine-verifiable `result_pattern`, optional `failure_pattern`, `timeout_ms` and `completion`. Preserve default `completion="match"`: first terminal match wins and each source has a 150ms idle window before its unterminated tail is evaluated without committing the buffer. Recommend `completion="exit"` for finite workflows: evaluate only newline/EOF records, retain the immutable first success candidate, continue checking failures and require natural exit zero. Invalid/clipped participating JSON fails with `invalid_json_result`; later failures, signals and deadlines override a candidate. JavaScript regex evaluation lives in one interruptible worker per monitor. Keep UTF-8 byte bounds in `src/monitor.ts`: 10 KiB displayed lines, 64 KiB physical matching lines, 2,000 lines/256 KiB retained logs, 100 lines/32 KiB terminal tails. Never match line fragments independently; over-budget physical lines fail explicitly. Pause both pipes at 1,024 pending lines/256 KiB and resume as the matcher catches up. Pending matching is capped at 16,384 lines/4 MiB with at most 64 lines in flight; overload must fail explicitly, never skip output silently. Project captures before worker IPC: 4 KiB per ordinary value, 32 KiB JSON and aggregate serialized captures. Prioritize JSON and disclose clipping/omission with `capturesTruncated`; never parse clipped JSON. Use a monotonic clock for durations.
- **Compact Reports**: Deduplicate only exact original capture strings in model-facing text with `capture_alias.name=first`; a `json` reference points to the visible `result=` canonical serialization. Optional `compact=true` may replace repetitive payload lines with explicit `payload_encoding`/`payload_rle` literal and `[text,count]` segments. Decoding must restore exactly the existing sanitized report payload; escape Unicode line separators in encoded JSON. Leave status and integrity diagnostics outside the codec. Preserve complete bounded structured captures and full human values via `/monitor` v; expanded transcript values use explicitly labelled previews. Collapse only adjacent identical diagnostic records to retain chronology. Keep parse/truncation errors explicit and validate required business fields in caller examples. Do not claim universal savings versus bare bash, and retain separate versioned snapshots for each measured contract.
- **Delivery Boundary**: A UI-host (TUI/RPC) batch containing only `monitor_start` calls returns pending acknowledgements with `terminate: true` and delivers one `monitor-result` per monitor (`deliverAs: "steer"`, `triggerTurn: true`). Pi v1 requires every result to terminate the batch. Mixed batches, nested calls, and headless calls therefore wait inside the tool and return the terminal directly without a duplicate custom message. Read the current assistant tool batch from the session branch; never abort the user's turn or modify a foreign result. Include the stable, cross-instance `monitorId` in direct/custom details and normal/asynchronous terminal content. Opted-in compact direct valid-success text may omit duplicated label/ID/timing only when native tool-call correlation identifies the result; preserve every payload/capture and full structured/UI metadata. Never apply that path to warnings or asynchronous notifications.
- **Cleanup Ownership**: Every terminal path reclaims the process group, including natural shell close. Retain pending SIGKILL cleanup separately from active monitors, and await all process-group escalations and worker terminations during shutdown. Preserve unterminated diagnostic tails on timeout and manual stop. A terminal contract ends the command; readiness is not a persistent-server lifecycle.
- **Structured Tools**: Keep `outputSchema` and `structuredContent` consistent for pending/terminal start results and stop counts. Retain text/details compatibility. Nested calls return terminal objects through Pi's normal codemode dispatcher. Reject an already cancelled invocation before spawning; reclaim partial startup if worker construction fails.
- **Progressive Tool Disclosure**: `monitor_stop` is registered but activated via `pi.setActiveTools()` only while at least one monitor is running. That call is a session-wide allowlist write, so it happens only when the running-monitor state actually flips, never on an unchanged state.
- **UI**: Use a public focused `ctx.ui.custom` overlay for `/monitor` so Pi fullscreen mode routes paging keys to it. Keep list/detail viewports bounded by terminal rows and columns, preserve selection by ID, and show output only after Enter. Use pi-kit's above-editor live activity widget for running monitors, clearing each row with its terminal result. Limit the widget to an adaptive one-to-three-row budget and disclose excess counts. Startup rows retain shared started geometry with native pending roles; show effective completion/timeout/cwd before full command, condition labels and ID. Persist the startup snapshot only in details; keep the LLM acknowledgement and structured start schema unchanged. Terminal transcript rows put the outcome first with error/neutral/success styling; hide expand hints before losing status at narrow widths. Terminal console evidence precedes configuration; v reveals complete values independently of Enter log disclosure. Provide guidance without intercepting native `bash` or global terminal input. Do not add polling tools or skills.

## Testing Guidelines

`features/` and `tests/` cover terminal
matching, match-mode unterminated-sentinel resolution while the command keeps running,
exit-mode partial records, late failures and malformed/scalar JSON,
timeout, headless completion, the UI-host delivery split, disclosure write
transitions, console input ownership and sanitization, diagnostic bounds, and
process-group cleanup. Prefer driving the extension through its own registered
surface; a source-text assertion is a last resort, and the ones that remain pin
packaging or schema facts that no runtime call can observe. Exercise zero-exit-without-match (`result_missing`) and descendants
that ignore SIGTERM; shutdown must still escalate to SIGKILL. The package
ships `index.ts`, `src`, `references`, and `README.md`. Read
@references/best-practices.md when changing resource or structured-output
contracts. Keep core peer ranges `"*"` per Pi's
package guide; pin development validation to the Pi v1 cohort. The explicit
native runner uses an isolated agent directory and local scripted provider;
its CLI/RPC/PTY coverage is recorded in @tests/native-verification-current.md.
