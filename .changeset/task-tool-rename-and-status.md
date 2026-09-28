---
"@fradser/pi-tasks": minor
"@fradser/pi-agent-teams": minor
"@fradser/pi-kit": minor
---

Rename the two Agent Teams tools and the board status they expose.

- `work` is now `task`. The package was already `@fradser/pi-tasks` and the internal type was already `BoardTask`, so `work` was the only name in the set contradicting the other two. It is also a mass noun, which forced a model reading `work` plus an `action` parameter to decide whether the tool performs work or registers work items.
- `agent_event` is now `message`. Its parameters were `to`, `message`, and `intent`, its renderer already displayed it as a message, and the name implied lifecycle authority the tool does not have.
- The board status `claimed` is now `in_progress`. The old name described an authority a caller had to be granted; a Task has no declared owner, so moving a Task into progress is the act of taking it. User-facing wording follows: an already-claimed Task is reported as already in progress.

`@fradser/pi-kit` gains a runtime coordination registry, `registerCoordination` / `resolveCoordination` / `clearCoordination`, so separately-loaded extensions can exchange capabilities at runtime without importing one another. Values are stored as `unknown` so kit keeps naming no consumer type.

No action, parameter, or result shape changes; only names. Migration: a model that says `work` or `agent_event` gets an unknown-tool error, and any pinned tool list naming them must be updated.
