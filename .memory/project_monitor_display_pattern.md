---
name: monitor-display-pattern
description: Background monitor UI uses exactly one compact started tool row and one terminal event message row
type: project
---

## Why

The monitor start tool previously duplicated visible status rows because Pi renders tool-call and tool-result slots separately. The settled KISS design makes the lifecycle explicit and avoids repeating the same event.

## How to apply

- `monitor_start.renderCall` renders exactly one row: `[monitor] started · <description>`.
- `monitor_start` uses `renderShell: "self"` and an empty `renderResult()` (`new Container()`) so the initial tool result adds no visible row.
- `monitor_start.execute()` returns empty `content`, structured `details`, and `terminate: true`.
- The asynchronous terminal result is sent once through `pi.sendMessage` and rendered by `registerMessageRenderer("monitor-result")` as `[monitor] event · <description> (<configured expand key> to expand)`.
- Shared label formatting belongs in `@fradser/pi-kit` as `formatToolEventLabel(kind, description, tool?)`; consumer packages depend on pi-kit via `workspace:*`.
- Do not add a second startup custom message, polling tool, widget, or non-empty `renderResult` for monitor start.

## Related

[[pi-kit-internal-dependency]] [[monitor-optimization]] [[pi-package-conventions]]
