# 03 — Cross-Project Persistent Identity & Specialization

**What to build:** Persistent Agent definitions where user-scoped definitions provide global cross-project identity and project-scoped definitions specialize behavior. Unknown names run as Temporary Agents and can be promoted to user scope after verified high-quality execution.

**Blocked by:** 01 — Core Delegation Tracer Slice, 02 — Shared Bidirectional Communication

**Status:** completed

- [x] User Agent definitions in `~/.pi/agent/agents/<name>.md` resolve across projects
- [x] Project definitions in `<project>/.pi/agents/<name>.md` specialize the same named Agent
- [x] Unregistered names spawn as Temporary Agents without Agent Memory
- [x] Successful verified outcomes enable leader-evaluated promotion to user Agent definition
