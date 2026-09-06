# 04 — Agent Capability Memory Abstraction

**What to build:** Isolated Agent Memory stored in each Agent's dedicated directory. Captures reusable capabilities, methods, and operating patterns via versioned Memory Proposals and serial merging, while strictly keeping project facts and history inside Project Memory.

**Blocked by:** 03 — Cross-Project Persistent Identity & Specialization

**Status:** completed

- [x] Dedicated per-Agent memory directory `~/.pi/agent/agents/memory/<agentName>/`
- [x] Memory Proposals submitted by Work Sessions undergo serial reduction and conflict check
- [x] Project-specific facts and identifiers are rejected from Agent Memory
- [x] Reusable methods from Agent Memory load into cross-project sessions without leaking source project facts
