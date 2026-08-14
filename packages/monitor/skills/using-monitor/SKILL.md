---
name: using-monitor
description: >
  Use when waiting for a background command, deploy, CI run, server startup,
  file watcher, or test result. The monitor requires a terminal result contract,
  keeps progress logs outside model context, and exposes one structured result.
---

# Monitor Extension Usage

Use `monitor_start` instead of shell sleep-polling loops when a command takes an
unknown amount of time. Define the terminal result before starting the monitor.
Progress output is captured silently; it does not wake the model.

## Tools

| Tool | Purpose |
|---|---|
| `monitor_start` | Start a command and wait for a declared terminal result |
| `monitor_read` | Read bounded raw output when diagnostics are necessary |
| `monitor_list` | List active monitors and their result contracts |
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
- `timeout`: the timeout expired before either pattern matched.
- `result_missing`: the process exited successfully without satisfying the
  declared result contract.

The monitor sends one compact plain-text terminal message with `triggerTurn:
true`. It uses stable `key=value` fields and emits complex `result` data as one
compact JSON value. Ordinary stdout and stderr never create messages or turns.

## Diagnose only when needed

After `failure`, `timeout`, or `result_missing`, inspect retained output:

```text
monitor_read monitor_id="monitor_1" tail_lines=100
```

Logs are source-labelled as `[stdout]` and `[stderr]`. Reads and retained history
are bounded, so diagnostic output cannot grow without limit. Do not call
`monitor_read` after a successful structured result unless the result is
insufficient.

## Lifecycle

- Default timeout: five minutes; maximum: one hour.
- `persistent=true`: wait until matched, stopped, or session shutdown.
- `monitor_stop` sends no terminal result notification. It sends the detached
  process group `SIGTERM`, then `SIGKILL` after a one-second grace period even
  if the shell child closed first. The grace timer keeps Pi alive through the
  escalation during session shutdown, so surviving descendants are cleaned up.
- `/monitor` shows active and recently finished monitors plus their bounded
  output without a global terminal-input listener.
- All active process groups are stopped when the Pi session shuts down.
