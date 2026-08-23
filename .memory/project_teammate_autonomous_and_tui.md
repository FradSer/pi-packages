---
name: teammate-autonomous-and-tui
description: Agent Teams uses named resident teammates, a shared task board, one-way worker reports, and a TUI console owned by ctx.ui.custom
type: project
---

`packages/agent-teams` is a resident teammate system. The Pi session is the leader; teammates are named long-lived RPC child processes backed by declarative Markdown agent definitions. The system does not use the former run-centric DAG or fanout tool model.

## Why

Resident teammates remain available between turns, consume no model tokens while idle, and can be steered or awakened by the harness. A shared board and explicit message protocol provide coordination without leader-side polling or peer traffic entering the leader model context.

## How to apply

1. Agent definitions resolve from project `.pi/agents`, user `~/.pi/agent/agents`, and bundled definitions. Project-local `.local.md` overrides take precedence over the matching project definition.
2. The leader tool surface is `teammate_spawn`, `teammate_shutdown`, `send_message`, `task_create`, and `task_list`. Worker capabilities add `task_claim` and `task_submit`; `send_message` is the unified reporting and peer-message primitive.
3. Teammates are capped at eight living workers per session. They have no turn-count or wall-clock termination cap. Silence is telemetry for a stall notice; the leader decides whether to wait, steer, shut down, or respawn.
4. Worker and leader state use one-writer atomic snapshots. Workers write outboxes, peer inboxes, and exclusive-create task intents. Per-spawn identity validation rejects stale callbacks and reports.
5. Task completion is gated by the effective task verify command, falling back to the agent role's verify command. Shutdown or crashes release claimed tasks, while the board persists for later inspection and runtime rosters do not.
6. The passive widget shows only working or starting teammates. `/agent-teams` opens the full-screen console through `ctx.ui.custom`; extensions must not use global terminal-input interception.
7. Keep BDD scenarios in `packages/agent-teams/features/agent-teams.feature` and executable coverage in `packages/agent-teams/tests/test_teammate_package.py`.

**Related:** [[pi-package-conventions]] [[no-global-input-interception]] [[pi-custom-component-rendering]]