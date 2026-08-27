---
name: monitor-display-pattern
description: background monitor UI owns one compact started row and one terminal event row
type: project
---

## How to apply

monitor_start suppresses the default call row and renders exactly one startup row through its result. The asynchronous terminal result is sent once through the native message channel and rendered as one event row. Do not add a second startup message, polling tool, widget, or non-empty monitor-start result.

Agent Teams startup rows use the user-approved subject order `[agent] @<name> started · <assignment>`; this is specific to teammate startup and does not change the general event-label contract.

Synchronous listing tools use the terminal-event visual language rather than a started-row title: format the event label through pi-kit, use the configured expand-key hint, and render structured details through the native custom-message box. Shared event-label formatting belongs in @fradser/pi-kit.