# @fradser/pi-monitor

Result-contract background monitoring for Pi. Run a non-interactive command,
keep noisy progress output outside the model context, and wake the agent once
with a structured terminal result.

## Why result contracts

Raw build, deploy, test, and server logs contain far more progress text than an
agent needs. Streaming those lines into the conversation repeatedly consumes
context and can trigger unnecessary model turns.

Use `monitor_start` for long-running commands. After it returns, the current
agent turn ends immediately. Do not sleep, poll, wait, or do follow-up work;
wait for the terminal result to wake the agent. Other tools and commands remain
available and are never blocked by the monitor. The terminal result automatically
wakes the agent once when:

- `result_pattern` matches: `success`
- `failure_pattern` matches: `failure`
- the command exits non-zero: `failure`
- the command exits zero without matching: `result_missing`

## Structure

```
monitor/
├── index.ts           — Package-root extension entry point
├── src/
│   ├── monitor.ts     — MonitorManager with bounded log/output/tail
│   ├── types.ts       — Parameter TypeBox schemas
│   └── index.ts       — Pi hooks, tool/command registration, widget
├── skills/using-monitor/SKILL.md
├── features/          — BDD contract
├── tests/             — Package E2E tests
└── README.md
```

### Tools and command

| Tool / Command | Description |
|---|---|
| `monitor_start` | Run a command and wait for a declared success or failure result |
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

A successful result wakes the agent once. In the transcript it is shown as a
compact monitor event; expand it to inspect the terminal fields:

```text
⏺ Monitor event: "test suite result"

status=success
elapsed=8.4s
result={"status":"success"}
```

The agent transport keeps the report in a Pi message envelope:

```text
<agent-message from="monitor">
[monitor monitor_1] test suite result
status=success
elapsed=8.4s
result={"status":"success"}
</agent-message>
```

The envelope and internal monitor label are hidden by the transcript renderer;
they are retained for the agent's context and structured message details.

## Matching existing command output

For commands that already print a stable terminal line, use a result regex with
named captures:

```text
monitor_start
  command="pnpm dev"
  description="development server"
  result_pattern="Ready on (?<url>https?://\\S+)"
  failure_pattern="(?:EADDRINUSE|FATAL|Failed to start):? (?<reason>.*)"
```

Avoid broad patterns such as `success|error|ready`. A result pattern is a
terminal contract, not a general log filter.

## Diagnostics

Ordinary output never triggers background model turns. When a terminal result is
`failure` or `result_missing`, the terminal notification already
includes a bounded tail of source-labelled output. There is no output-reading
or status-polling tool; wait for the one terminal notification instead of
calling another tool or sleeping and checking again.

A `running` monitor showing `0 retained, 0 dropped` while the source clearly
produced output usually means an intermediate filter is block-buffering: `grep`,
`sed`, and `awk` buffer when their stdout is a pipe, so lines stall until ~4 KB
accumulates or the process exits. Keep filter stages line-buffered (`grep
--line-buffered`, `sed -l`, `awk` with `fflush()`), or emit the terminal result
without a filter stage.

Output is labelled by source:

```text
[stdout] compiling application
[stderr] connection refused
```

The retained history and terminal diagnostic tail are bounded:

- individual displayed line: 10 KiB
- unterminated input fragment: 64 KiB
- retained output: 2,000 lines and 256 KiB per monitor
- terminal diagnostic tail: 100 lines and 32 KiB maximum
- recently finished monitor history: 20 monitors

## Result semantics

- Both stdout and stderr are scanned for `result_pattern` and `failure_pattern`.
- The first terminal match wins and stops the process group.
- Named regex captures are returned in `captures`.
- The monitor start tool returns a concise status containing the monitor id
  and description, then terminates the current turn.
- The model-facing terminal report uses the Pi agent-message envelope
  `<agent-message from="monitor">...</agent-message>` around compact
  `key=value` text. A named capture called `json` is parsed into `result` and
  emitted as compact JSON; complete structured data remains in message
  `details` for extensions/UI.
- A `json` capture is parsed when it contains valid JSON no larger than 32 KiB.
- Completion waits for the child process `close` event so unterminated final
  output can still satisfy the contract.
- Stopping a process group sends `SIGTERM`, then sends `SIGKILL` after a
  one-second grace period even if the shell child has already closed. The
  escalation timer keeps the session alive through that grace period, so
  descendants that ignore `SIGTERM` cannot outlive the monitor during shutdown.
- Monitor processes run until a terminal result, natural process exit, `monitor_stop`,
  or session shutdown. If a task needs a deadline, put it in the command itself
  (for example, `timeout 10m pnpm test`).
- All active monitors are stopped on session shutdown.

Consult `/skill:using-monitor` for the agent-facing usage procedure.
