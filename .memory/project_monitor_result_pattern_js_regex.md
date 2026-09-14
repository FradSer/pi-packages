---
description: monitor_start compiles result_pattern/failure_pattern as JavaScript regexes — Python (?P<name>...) is rejected before the monitor starts; use (?<name>...) or a plain sentinel
---

`@fradser/pi-monitor` validates `result_pattern` and `failure_pattern` by compiling them with `new RegExp(pattern)` in `packages/monitor/src/monitor.ts`, so the accepted dialect is JavaScript, not Python. An invalid pattern is rejected by `monitor_start` itself (`invalid <field>: Invalid regular expression: ...`) and no monitor is started.

## How to apply

- Never use Python group syntax. `EXIT:(?P<exit>\d+)` fails with `Invalid group`; the JavaScript forms are `(?<exit>\d+)` for a named capture or `(\d+)` for a numbered one, and a plain sentinel such as `EXIT:\d+` when no capture is needed.
- Gate a finite pipeline by echoing a terminal sentinel from the command and matching it: `python3 -m pytest packages/continual-learning/tests/ -q 2>&1; echo "EXIT:$?"` with `result_pattern: "EXIT:\\d+"` (and optionally `failure_pattern: "EXIT:[1-9][0-9]*"`) reported the run in one terminal result.
- Named captures are returned in `captures`; the documented repository examples already use the JavaScript form (`packages/monitor/README.md`, `result_pattern="__PI_MONITOR_RESULT__ (?<json>\\{.*\\})"`), so match them rather than inventing dialect-specific syntax.
