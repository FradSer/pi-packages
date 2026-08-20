---
name: using-monitor
description: >
  Use when waiting for a background command, deploy, CI run, server startup,
  file watcher, or test result. The monitor requires a terminal result contract,
  keeps progress logs outside model context, and exposes one structured result.
---

# Monitor Extension Usage

Use `monitor_start` for long-running commands. After it returns, end the
current turn immediately. Do not sleep, poll, wait, or do follow-up work; wait
for the terminal result to wake the agent. Other tools and commands remain
available and are never blocked by the monitor.

## Tools

| Tool | Purpose |
|---|---|
| `monitor_start` | Start a command and wait for a declared terminal result |
| `monitor_stop` | Stop one or all active monitors without a result notification |

## Start with a result contract

`result_pattern` is required. `failure_pattern` is optional. Both scan stdout
and stderr.

```text
monitor_start
  command="pnpm dev"
  description="development server startup"
  result_pattern="Ready on (?<url>https?://\\S+)"
  failure_pattern="(?:FATAL|EADDRINUSE|Failed to start):? (?<reason>.*)"
```

The first terminal match stops the process and produces exactly one model
notification. Named regex groups become structured `captures`.

## Prefer a JSON sentinel

When the command can be wrapped, make the terminal result unambiguous:

```bash
sh -c '
  if pnpm test; then
    printf '\''__PI_MONITOR_RESULT__ {"status":"success"}\n'\''
  else
    code=$?
    printf '\''__PI_MONITOR_FAILURE__ {"status":"failure","exitCode":%s}\n'\'' "$code"
    exit "$code"
  fi
'
```

Wait for it with a named `json` capture:

```text
result_pattern="__PI_MONITOR_RESULT__ (?<json>\\{.*\\})"
failure_pattern="__PI_MONITOR_FAILURE__ (?<json>\\{.*\\})"
```

The `json` capture is parsed into the terminal result. Do not use broad patterns
such as `success|error|ready`; those are log filters, not reliable completion
contracts.

## Terminal statuses

- `success`: `result_pattern` matched.
- `failure`: `failure_pattern` matched, the process failed to spawn, or it exited
  with a non-zero code.
- `result_missing`: the process exited successfully without satisfying the
  declared result contract.

The monitor start tool returns a concise status with the monitor id and
description, then terminates the current turn. When the command reaches a
terminal state, the monitor sends one report with `triggerTurn: true`. Its
transport content uses the Pi agent-message envelope:

```text
<agent-message from="monitor">
[monitor monitor_1] test suite result
status=success
elapsed=8.4s
</agent-message>
```

The transcript renders the report as a concise monitor event, such as
`⏺ Monitor event: "test suite result"`; expanding it shows the terminal fields.
The report uses stable `key=value` fields and emits complex `result` data as one
compact JSON value. It also includes a bounded source-labelled diagnostic tail,
so ordinary stdout and stderr never create extra messages or turns and no
output-reading tool is needed. The terminal message automatically wakes the
agent once after the monitor reaches a terminal state.

## Downstream filters must stay line-buffered

The monitor consumes child stdout as it arrives, but an intermediate filter can
hold data back: `grep`, `sed`, and `awk` block-buffer when their stdout is a
pipe, so lines stall inside the filter until ~4 KB accumulates or the process
exits (verified on macOS BSD grep). A monitor watching such a pipeline can show
`0 retained, 0 dropped` for a long time even though the source already produced
output.

- Prefer commands that emit the terminal result directly, with no filter stage.
- If a filter stage is unavoidable, keep it line-buffered: `grep
  --line-buffered`, `sed -l`, or `awk '{ print ...; fflush() }'`.
- If the source script supports exclusion flags, use those instead of piping
  through `grep -v`.

## Diagnostics are included in the terminal result

After `failure` or `result_missing`, use the bounded diagnostic tail
already included in the terminal notification. Logs are source-labelled as
`[stdout]` and `[stderr]`; retained history and terminal diagnostics are bounded,
so output cannot grow without limit. Do not start another tool call to inspect
progress or poll a running monitor.

## Lifecycle

- Monitors run until a result matches, the process exits, `monitor_stop`, or session shutdown.
- If a task needs a deadline, put it in the command itself (for example, `timeout 10m pnpm test`).
- `monitor_stop` sends no terminal result notification. It sends the detached
  process group `SIGTERM`, then `SIGKILL` after a one-second grace period even
  if the shell child closed first. The grace timer keeps Pi alive through the
  escalation during session shutdown, so surviving descendants are cleaned up.
- `/monitor` shows active and recently finished monitors plus their bounded
  output without a global terminal-input listener.
- `monitor_start` is intentionally a one-shot contract: wait for its terminal
  notification instead of calling an output-reading or status-polling tool.
- All active process groups are stopped when the Pi session shuts down.
