---
name: memory-menu-inline-consolidation
description: /memory menu and manual background consolidation workflow; consolidation is user-triggered and completion requires evidence
 type: feedback
---

## Why

The @fradser/pi-memory `/memory` command uses a native Pi menu for model configuration, consolidation, instructions, memory-folder access, and the auto-memory toggle. Consolidation is an explicit user action and must not be triggered automatically by context thresholds or settled-agent events.

## How to apply

1. Keep the workflow exposed through `pi.registerCommand` and `ctx.ui.select`; do not reintroduce per-workflow skills or custom question tools.
2. `/consolidate` and the menu action start a single-flight parent-owned consolidation transaction. The parent validates the structured plan, applies only selected operations, rebuilds indexes, checks the safe mirror, and writes the receipt.
3. Auto-memory guidance is controlled by the persisted toggle. Existing project memories are injected independently of that toggle.
4. Resolve project instructions from the current project context, preferring `AGENTS.md` and falling back to `CLAUDE.md`.
5. Do not treat a child process exit code of zero as proof of consolidation. Completion requires evidence such as tool activity, validator execution, or a structured consolidation report; empty output must be reported as uncertain.

**Related:** [[pi-package-conventions]]