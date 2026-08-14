# Monitor Pi Package

Result-contract background monitoring for Pi. Run a non-interactive command,
keep noisy progress output outside the model context, and wake the agent once
with a structured terminal result.

## Why result contracts

Raw build, deploy, test, and server logs contain far more progress text than an
agent needs. Streaming those lines into the conversation repeatedly consumes
context and can trigger unnecessary model turns.

`@fradser/pi-monitor` requires the caller to define success before starting the
command. It scans both stdout and stderr in the background. Progress output is
retained in a bounded log buffer but is not sent to the model. The monitor emits
one terminal result when:

- `result_pattern` matches: `success`
- `failure_pattern` matches: `failure`
- the command exits non-zero: `failure`
- the command exits zero without matching: `result_missing`
- the timeout expires: `timeout`

### Tools and command

| Tool / Command | Description |
|---|---|
| `monitor_start` | Run a command and wait for a declared success or failure result |
| `monitor_read` | Read a bounded tail of raw output on demand |
| `monitor_list` | List active result monitors and their contracts |
| `monitor_stop` | Stop one or all active monitors without emitting a result |
| `/monitor` | Inspect active and recent monitors and their retained output |

## Installation

```bash
pi install npm:@fradser/pi-monitor
# or from this repository:
pi install /path/to/pi-packages/packages/monitor
```

## Preferred usage: JSON sentinel

When the command can be wrapped, print a unique sentinel containing JSON:

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

Start the monitor with named `json` captures:

```text
monitor_start
  command="<wrapped command>"
  description="test suite result"
  result_pattern="__PI_MONITOR_RESULT__ (?<json>\\{.*\\})"
  failure_pattern="__PI_MONITOR_FAILURE__ (?<json>\\{.*\\})"
```

A successful result wakes the agent once:

```json
{
  "status": "success",
  "matched": "__PI_MONITOR_RESULT__ {\"status\":\"success\"}",
  "captures": {
    "json": "{\"status\":\"success\"}"
  },
  "result": {
    "status": "success"
  }
}
```

## Matching existing command output

For commands that already print a stable terminal line, use a result regex with
named captures:

```text
monitor_start
  command="pnpm dev"
  description="development server"
  result_pattern="Ready on (?<url>https?://\\S+)"
  failure_pattern="(?:EADDRINUSE|FATAL|Failed to start):? (?<reason>.*)"
  timeout_ms=120000
```

Avoid broad patterns such as `success|error|ready`. A result pattern is a
terminal contract, not a general log filter.

## Diagnostics

Ordinary output never triggers background model turns. If a terminal result is
`failure`, `timeout`, or `result_missing`, inspect the retained log explicitly:

```text
monitor_read monitor_id="monitor_1" tail_lines=100
```

Output is labelled by source:

```text
[stdout] compiling application
[stderr] connection refused
```

The retained history and every read are bounded:

- individual displayed line: 10 KiB
- unterminated input fragment: 64 KiB
- retained output: 2,000 lines and 256 KiB per monitor
- `monitor_read`: 500 lines and 64 KiB maximum
- recently finished monitor history: 20 monitors

## Result semantics

- Both stdout and stderr are scanned for `result_pattern` and `failure_pattern`.
- The first terminal match wins and stops the process group.
- Named regex captures are returned in `captures`.
- A named capture called `json` is parsed into `result` when it contains valid
  JSON no larger than 32 KiB.
- Completion waits for the child process `close` event so unterminated final
  output can still satisfy the contract.
- Non-persistent monitors time out after five minutes by default, with a maximum
  of one hour. `persistent=true` disables the timeout.
- All active monitors are stopped on session shutdown.

Consult `/skill:using-monitor` for the agent-facing usage procedure.
