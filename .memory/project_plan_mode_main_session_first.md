---
name: plan-mode-main-session-first
description: /plan plans in the main session first; worker research is explicit and wall-clock worker timeouts are not used
type: project
---

## Why

Plan mode should not pay the cost or complexity of spawning one or many worker processes before the main session understands the request. Simple tasks can be planned directly, while complex tasks may benefit from independent worker research only after the main session's plan and an explicit user choice.

## How to apply

- `/plan <request>` enters read-only mode and sends a planning follow-up to the current session; it does not start `pi-kit` workers immediately.
- The main session writes and presents the plan first, including whether additional research is useful.
- The plan review menu offers direct implementation and an explicit worker-research action. Worker research receives the existing plan as context and is optional.
- `runPiWorker` has no wall-clock timeout or `timedOut` result. Abort and process shutdown remain the cancellation mechanisms; termination grace periods are only for cleanup after cancellation.

## Related

[[project_teammate_autonomous_and_tui]] [[project_pi_kit_internal_dependency]]
