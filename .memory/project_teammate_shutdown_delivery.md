---
name: teammate-shutdown-delivery
description: Separate assignment completion, confirmed process closure, and native Pi report delivery.
type: project
---

## Why

A terminal report ends an assignment, not its resident process. Reports handed to Pi's steering queue can be consumed after shutdown. A termination timeout does not prove that the child is absent.

## How to apply

- Preserve distinct `missing`, `closed`, and `unconfirmed` termination outcomes. Unconfirmed close retains shutdown intent and task/resource ownership; new work is rejected until closure is resolved.
- Record confirmed-stop evidence by spawn incarnation, not teammate name, and retain it until runtime reset.
- Snapshot delivery at `message_start`, then share that snapshot with the TUI renderer and `message_end` persistence. Annotating only at `message_end` misses the initial custom-message renderer in the repository's Pi SDK. Preserve authored body/time; a stop after delivery starts must not retroactively mark a report late. An after-stop delivery is not worker activity or assignment reopening.
- Use assignment wording for terminal-report finish rows. Keep native Pi print and TUI delivery regressions alongside deterministic shutdown tests in `packages/agent-teams/tests/`.

**Related:** [[project_teammate_autonomous_and_tui]] [[pi-package-conventions]]
