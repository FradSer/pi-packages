---
name: follow-up-queue
description: Agent Teams report delivery hands off immediately to Pi steering without internal serialization or post-run follow-up delays
type: project
---

## Why

Agent Teams previously routed worker reports through Pi's `followUp` channel and held subsequent reports in an internal `FollowUpQueue` until `agent_settled`. Because Pi does not deliver follow-ups while the leader is actively executing tool calls, active leader coordination loops delayed decision-useful worker reports until the entire task finished. Furthermore, every held report then started a separate leader turn, replaying obsolete progress after terminal completion was already known.

Worker execution is autonomous: repeated leader status queries or progress nagging do not alter worker execution and only delay incoming reports by keeping the leader turn busy. The correct pattern is:
1. Worker reports are handed off immediately to Pi's `steer` channel so they arrive at the next safe tool boundary when the leader is working, or wake the leader immediately when idle.
2. The leader assigns work once and sends messages during work only when newly discovered evidence, constraints, or decisions change the worker's assignment.

## How to apply

- `src/leader-reports.ts` defines envelopes and formatting; the internal `FollowUpQueue` is removed.
- `src/index.ts` hands reports directly to `leaderPi.sendMessage(..., { triggerTurn: true, deliverAs: "steer" })`.
- Working leaders receive reports at safe tool boundaries without interrupting in-flight tools; idle leaders wake immediately.
- `src/guidance.ts` instructs the leader: do not ask for progress reports or repeat existing instructions; send only newly discovered information that changes the worker's assignment.
- Silence is console telemetry only (`PI_TEAMMATE_STALL_SILENCE_MS` roster marker): the harness never sends the leader heartbeat or stall notices; provider hangs surface through the terminal close-path diagnostic (see `docs/adr/0002-no-leader-heartbeat-notices.md`).
- Verified by unit and integration tests including native Pi CLI execution (`tests/test_immediate_reports.py`).

## Related

[[feedback_no_sleep_waiting_for_teammates]]
[[project_agent_teams_persistent_agents]]
