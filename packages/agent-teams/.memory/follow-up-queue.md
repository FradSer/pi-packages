---
name: follow-up-queue
description: Agent Teams hands teammate reports immediately to Pi's steering channel without an internal serialized follow-up queue
type: project
---

## Why

Using `deliverAs: "followUp"` delayed teammate reports until the entire leader tool-calling turn finished, and an internal serialized queue holding subsequent reports until `agent_settled` meant multiple reports backlogged during active leader work and then flooded the leader across subsequent turns. Additionally, worker reports need to arrive promptly when the leader is working, at the next safe tool boundary, rather than waiting for the entire run to settle.

## How to apply

- `packages/agent-teams/src/leader-reports.ts` provides report types, envelopes, and display grouping; the internal `FollowUpQueue` is removed.
- Reports from `team-machine.ts` are handed directly to `leaderPi.sendMessage(..., { triggerTurn: true, deliverAs: "steer" })`.
- Working leaders receive reports at the next safe tool boundary without interrupting in-flight tools; idle leaders wake immediately.
- The leader guidance emphasizes that workers execute assignments autonomously without progress nagging; leader steering is reserved for newly discovered information that affects the worker's assignment.
- Silence is console telemetry only; no heartbeat or stall notices reach the leader. Provider hangs surface through the terminal close-path diagnostic (repo ADR 0002).
- Keep BDD coverage in `features/agent-teams.feature` and native delivery regressions in `tests/test_immediate_reports.py`.
