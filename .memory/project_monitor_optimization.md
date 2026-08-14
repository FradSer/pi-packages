---
name: monitor-optimization
description: pi-monitor bounds background-process output and waits for child stdio closure before cleanup
type: project
---

## Why

`@fradser/pi-monitor` runs long-lived shell commands inside the Pi session. Unbounded stderr, unterminated stdout lines, pending bursts, or premature process finalization can consume memory or lose the final output.

A separate product-quality issue is notification noise: every `onEvent` batch currently becomes a `pi.sendMessage(..., { deliverAs: "steer", triggerTurn: true })` custom message, and custom messages participate in LLM context. Batching and event caps bound transport volume but do not prevent repeated model turns or raw-log context accumulation.

## How to apply

- Use the child process `close` event rather than `exit`; it fires after piped stdio has closed.
- Keep `BATCH_WINDOW_MS` at 500ms and treat `MAX_EVENTS` as a safety circuit breaker, not a noise-control mechanism; increasing it increases the maximum possible model churn.
- The settled product direction is result-contract monitoring, not raw-log streaming: when starting a monitor, the model must declare a machine-verifiable terminal result (prefer a unique sentinel or a required result regex with captures) plus an optional failure condition. Capture ordinary output out of LLM context, scan incrementally, and expose exactly one structured terminal result (`success`, `failure`, `timeout`, or `result_missing`) with `triggerTurn: true`.
- Model-facing terminal content should be compact structured text rather than pretty-printed JSON: JSON remains useful for arbitrary nested result payloads and machine-facing metadata, but the current pretty JSON duplicates `captures` and parsed `result` and wastes context. Use stable `key=value` fields plus compact JSON only for the result payload; omit undefined fields and do not repeat the same data.
- Keep recent/full raw output behind a bounded explicit read path such as `monitor_read` for diagnostics; the `/monitor` TUI may display it without putting it into LLM context. Do not send progress batches into model context by default.
- Cap stdout lines at `MAX_LINE_LENGTH` (10 KiB), flush an unterminated line at `MAX_LINE_BUFFER` (64 KiB), and flush bursts at `MAX_PENDING_LINES` (1000).
- Cap captured stderr at `MAX_STDERR_BYTES` (1 MiB) and append `[stderr truncated]` to the final output when exceeded.
- Cap each notification at `MAX_PENDING_BYTES` (64 KiB) as well as `MAX_PENDING_LINES` (1000).
- Kill detached process groups with SIGTERM followed by a tracked, unref'd SIGKILL escalation timer; do not cancel that timer during immediate finalization after a kill request.
- Destroy stdout/stderr pipes during finalization and keep input handlers gated on `monitor.status === "running"`.

## Related

[[pi-package-conventions]]
