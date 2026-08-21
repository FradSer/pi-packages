---
name: monitor-display-pattern
description: Background monitor UI uses exactly one compact started tool row and one terminal event message row
type: project
---

## Why

The monitor start tool previously duplicated visible status rows because Pi renders tool-call and tool-result slots separately. The settled KISS design makes the lifecycle explicit and avoids repeating the same event.

## How to apply

- `monitor_start.renderCall` returns an empty `Container`.
- `monitor_start` uses `renderShell: "self"`; `renderResult()` renders exactly one startup row: `[monitor] started · <description>`. This single-owner rule prevents Pi's call/result lifecycle from duplicating the startup row.
- `monitor_start.execute()` returns empty `content`, structured `details`, and `terminate: true`.
- The asynchronous terminal result is sent once through `pi.sendMessage` and rendered by `registerMessageRenderer("monitor-result")` as `[monitor] event · <description> (<configured expand key> to expand)`.
- Agent teams reuse the same lifecycle abstraction for startup (`[agent] started · ...`), while teammate reports keep their semantic message label (`[message] from @teammate`), without an extra `[agent] event` prefix.
- Shared label formatting belongs in `@fradser/pi-kit` as `formatToolEventLabel(kind, description, tool?)` and `formatAgentMessagePrefix(direction, count?)`; consumer packages depend on pi-kit via `workspace:*`.
- Do not add a second startup custom message, polling tool, widget, or non-empty `renderResult` for monitor start.

## Related

[[pi-kit-internal-dependency]] [[monitor-optimization]] [[pi-package-conventions]]
