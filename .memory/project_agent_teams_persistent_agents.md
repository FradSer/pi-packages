---
name: agent-teams-final-surface
description: Final Agent Teams public coordination surface
type: project
---

Agent Teams uses only `agent`, `work`, and `agent_event`; `/agent-teams` is the
human management surface. `agent` actions are delegate/start/inspect/stop with
incarnation-bound session handles. `work` owns Work lifecycle. `agent_event` is
communication-only (`inform`/`request`). Legacy lifecycle, task, and message
tools are absent. Incompatible persisted runtime snapshots fail explicitly.
