---
name: follow-up-queue
description: Agent Teams serializes automatic teammate reports through Pi custom-message follow-ups, including reports arriving while the leader is active
type: project
---

## Why

Pi accepts a custom `sendMessage(..., { triggerTurn: true, deliverAs: "followUp" })` while the leader is streaming and retains it in its native follow-up queue. Agent Teams must not add an idle-only gate that delays that handoff until the entire leader run settles. Doing so leaves reports in the package queue during a leader tool-call loop instead of at least making them visible to Pi's proper queue.

A native follow-up still runs only after the current tool/steering loop can naturally finish; it does not interrupt an in-flight tool or an unbounded leader loop. The leader guidance therefore forbids sleep-based polling, and urgent interruption needs an explicit steer/abort design rather than changing ordinary reports.

## How to apply

- `packages/agent-teams/src/follow-up-queue.ts` owns a FIFO report queue and one active dispatch.
- `pump()` dispatches the first pending report whether the leader is idle or active. Active leaders receive it through Pi's native `followUp` channel; idle leaders begin a new turn.
- Keep only one package dispatch active. `agent_settled` releases it and schedules the next pending report, preserving FIFO and one-report-per-leader-turn semantics.
- Match idle-started dispatches in `before_agent_start`/`agent_start`; a watchdog restores a dispatch when no start occurs. Active-run dispatches are already accepted by Pi's follow-up queue and wait for settlement.
- `sendMainSessionFollowUp` only enqueues. Do not call Pi's void `sendMessage` directly from worker completion paths.
- Teammate report discipline belongs at the report-sequence boundary: suppress duplicate bodies within one sequence and reopen reporting only after a new wake-up prompt; preserve distinct intermediate reports and never infer duplicates across assignments.
- Keep BDD coverage in `features/agent-teams.feature` and the busy-leader serialization regression in `tests/test_teammate_package.py`.
