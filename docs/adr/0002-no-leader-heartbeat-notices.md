# No leader heartbeat or stall notices; silence is console telemetry

Agent Teams removed the silence watchdog that used to notify the leader when a working teammate produced no model output (30-minute general window, 5-minute provider-hang tier). The roster and detail views keep the same silence, spawn-age, and usage data as passive console telemetry, marked "stalled" after `PI_TEAMMATE_STALL_SILENCE_MS` (default 5 minutes). A teammate that dies — including a provider hang that kills the child — still delivers one terminal crash diagnostic through the standard close path; the leader decides recovery from that report alone.

## Context

The watchdog inserted mid-task health messages into the leader's context and asked it to choose between waiting, steering, or shutting down. Steering cannot recover a request hung inside the provider, so the "steer again" option was dead advice, and the notice interrupted focused leader work to demand an ops decision the runtime had already classified. Zero-output hangs without a process death now simply stay visible in the console until the leader or user acts; the machine no longer escalates them.

## Decision

Silence never wakes or interrupts the leader. Observation lives in the `/agent-teams` console. Failure reaches the leader only as a terminal outcome (close-path diagnostic or the worker's own failed report). Termination remains leader- or user-initiated; no threshold may kill a teammate.

## Consequences

- A hung-but-alive child can wait indefinitely; humans discover it through the roster instead of a push notification. This is accepted: an automatic mid-task prompt cost more (interrupted leader turns, dead-advice options) than the delayed discovery.
- Removing the watchdog is hard to reverse casually because tests and guidance now forbid leader-directed heartbeat notices; reintroducing any automatic leader notification requires revisiting this ADR.
