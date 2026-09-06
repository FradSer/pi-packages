# 01 — Core Delegation Tracer Slice

**What to build:** The minimal end-to-end delegation loop. The leader calls `agent({ name, prompt })`, which creates a durable `WorkItem`, launches an isolated `WorkSession` process with a unique `AssignmentAttempt`, synchronously returns `Agent Presence`, and receives the final verified result.

**Blocked by:** None — can start immediately.

**Status:** completed

- [x] `agent({ name, prompt })` creates a Work Item in the work ledger
- [x] Launches an isolated child process with its own session context and attempt ID
- [x] Returns Agent Presence reflecting the active Work Session
- [x] Captures the terminal completion result and reports it back to the leader
