---
name: agent-teams-persistent-agents
description: Agent Teams redesign uses cross-project persistent Agents, isolated Work Sessions, capability-only Agent Memory, a minimal delegation tool, and shared role-independent communication
type: project
---

## Why

The redesigned Agent Teams object is an Agent, not a session-bound teammate process. An Agent can work across projects. User Agent Definitions establish the durable identity; project definitions specialize the same named Agent without creating a project-owned identity. Unknown names create Temporary Agents, which can be promoted automatically after the leader judges their first result high-quality from evidence, verification, and reuse value.

## How to apply

- One Agent may hold several Work Items concurrently, but every Assignment Attempt runs in an isolated Work Session with its own Pi session, Process Incarnation, prompt context, tools, and temporary state.
- All work sources—person, Routine, external event, or Agent handoff—create the same Work Item. Handoff transfers ownership only after the target Work Session accepts.
- Persisted Agents own Agent Memory in their own dedicated folder. It records reusable capabilities, methods, judgment criteria, preferences, and operating patterns, including lessons abstracted from project work. Ownership follows content and applicability, not where the lesson was learned; Temporary Agents have no Agent Memory.
- Project facts, concrete decisions, and history remain in the project's existing Project Memory. A reusable lesson may separately become Agent Memory without moving or copying the project record. Preserve the lesson's assumptions and limits; anonymizing a local decision alone does not make it general. Never create per-project subfolders inside Agent Memory or automatically load raw project evidence across projects.
- Concurrent Work Sessions only submit versioned, evidence-backed Memory Proposals; an Agent-level serial reducer merges capability-focused proposals. Low-risk preferences may auto-merge after evidence, while high-risk rules require human approval.
- `agent({ name, prompt?, work? })` is the delegation/work-control interface. `agent_event({ message, to?, status? })` is the shared communication interface for Leader ↔ Worker and Agent ↔ Agent, never exclusive to a role or user/project scope. Sender identity comes from runtime binding; a Leader binds to its Pi session without needing a Worker Assignment Attempt. Keep `to` for explicit addressing; omit it only with one unambiguous bound reply route. Shared messaging does not grant state-transition authority. Execution tools and advanced transitions remain separately authorized and progressively available.
- Agent Definitions request capability intent. Each Work Item starts with the minimum effective tools and may progressively load additional policy-authorized capabilities.
- Every Work Session receives its own Computer Lease; local worktrees, isolated browsers, and cloud computers are adapters. User access follows Status → Preview → Takeover, with Agent writes paused during takeover.
- A persistent background broker/daemon is explicitly out of scope. Routines may create Work Items only while the current Agent Teams runtime is available; do not claim cross-session autonomous execution.
- Notify the user only for an Attention Request or an important final result. This must not suppress required worker results to the leader; Presence, leader delivery, and human notifications are separate concerns.
- Before implementation, close the cross-runtime storage and message-correlation contracts: a process-local serial reducer is not globally serial, atomic rename is not mutual exclusion, and an Agent name alone does not identify a reply's Work Session. See `packages/agent-teams/DESIGN-REVIEW.md` for the design gaps, not implemented guarantees.

## Related

[[project_teammate_autonomous_and_tui]]
[[project_continual_learning_autonomous_consolidation]]
[[project_pi_package_conventions]]
