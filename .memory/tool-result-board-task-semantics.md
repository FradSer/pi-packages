---
name: tool-result-board-task-semantics
description: Root guidance standardizes clustered Agent Teams board/task tool results and lifecycle rows
 type: project
---

## Why

Agent Teams tool output previously mixed board context, task state, roster data, and next actions in repeated prose. This made both model reasoning and transcript scanning less reliable. The stable domain model is board as the current-session coordination container and task as one work item within it.

## How to apply

Model successful tool results as clustered semantic groups: coordination context, summary, work items, ownership, routing, validation, next action, and participants. Mention the context once, avoid repeating state across prose and lists, and keep item rows limited to identity, lifecycle state, subject, ownership, and blocking relationships. Distinguish synchronous effects from queued intents and verification-pending outcomes; never claim a later transition before the responsible harness applies it. Keep collapsed TUI rows compact through the shared pi-kit started/event lifecycle abstraction and place grouped details behind expansion.

## Related

[[pi-package-conventions]]
