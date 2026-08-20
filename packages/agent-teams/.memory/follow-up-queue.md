---
name: follow-up-queue
description: Agent Teams serializes automatic teammate reports through Pi's void sendUserMessage API with lifecycle matching, retry backoff, and session invalidation
type: project
---

## Why

Pi's extension `sendUserMessage` API returns `void`; asynchronous preflight failures are routed to the runtime error handler rather than thrown to the caller. Concurrent automatic reports can also race Pi's prompt startup and produce `Agent is already processing a prompt`.

## How to apply

- `packages/agent-teams/src/follow-up-queue.ts` owns a FIFO report queue and one active dispatch.
- A dispatch is matched by its exact prompt in `before_agent_start`, confirmed by `agent_start`, and released only by the corresponding `agent_settled` path. Reports arriving during an active leader run remain queued.
- A watchdog restores a batch when no `agent_start` occurs; retries use bounded exponential backoff rather than a microtask spin.
- `reset()` increments a generation and clears timers, so delayed callbacks from an old session cannot deliver to a replacement session.
- Keep `sendMainSessionFollowUp` as a synchronous enqueue operation; do not call Pi's void API directly from worker completion paths.
