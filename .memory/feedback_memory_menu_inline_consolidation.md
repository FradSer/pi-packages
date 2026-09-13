---
name: memory-menu-inline-consolidation
description: /memory manages automatic settled-task learning and explicit consolidation; completion requires parent validation
type: feedback
---

## Why

The `/memory` command manages model configuration, consolidation, instructions, memory-folder access, and automatic learning. The user's September 2026 design update requires the model to learn durable context and executable constraints without waiting for a memory command; this supersedes the earlier manual-only consolidation decision.

## How to apply

1. Keep the workflow exposed through `pi.registerCommand` and `ctx.ui.select`; do not reintroduce per-workflow skills or custom question tools.
2. With auto-memory enabled, `agent_settled` starts one parent-owned pipeline for completed user input. Coalesce pending tasks, ignore extension continuations as new triggers, freeze context before asynchronous work, and await receipts in headless runs. `/consolidate` and the menu remain explicit entry points.
3. The persisted toggle controls automatic learning. Existing memory indexes are injected independently; the main model does not bypass parent validation by writing memory files during ordinary task execution.
4. Resolve project instructions from the current project context, preferring `AGENTS.md` and falling back to `CLAUDE.md`.
5. A zero child exit code is insufficient. Completion requires a bounded structured plan, parent validation, and verified receipts; empty output is uncertain.

**Related:** [[pi-package-conventions]]
