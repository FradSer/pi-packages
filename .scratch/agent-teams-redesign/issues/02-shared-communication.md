# 02 — Shared Bidirectional Communication

**What to build:** The unified `agent_event({ message, to?, status? })` tool for Leader ↔ Worker and Worker ↔ Peer communication. Enforces trusted sender binding from runtime context, precise reply routing for work context isolation across projects, and progressive status semantics.

**Blocked by:** 01 — Core Delegation Tracer Slice

**Status:** completed

- [x] `agent_event` registered for both leader and worker processes
- [x] Leader can send messages to a specific worker without needing a worker assignment attempt
- [x] Worker replies preserve originating Work Item context and reply route
- [x] Omitted `to` routes strictly to the unique bound reply route or fails explicitly
