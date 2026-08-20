---
name: node-terminal-followups
description: Background Agent Teams runs notify the main session after each non-summary teammate reaches a terminal outcome, including pre-spawn setup failures, then send a separate run summary when all nodes settle
type: project
---

## Why

The leader needs incremental results while independent teammates are still working. Waiting for the run-level settle message hides completed work and delays downstream attention. Setup failures must use the same delivery contract as child-process failures.

## How to apply

- `run-machine.ts` sends one node follow-up for each non-summary node in a background run when it reports `completed`/`failed`, when its child process reaches a terminal outcome, or when pre-spawn setup fails (agent/state-file/worktree setup).
- `Node.nodeFollowUpSent` prevents duplicate follow-ups when a worker report is followed by process-close finalization; retry clears the marker.
- The node follow-up uses the worker's full terminal report/body and does not stop remaining teammates.
- The existing run-settled follow-up remains separate and is sent once after all nodes settle; foreground (`background=false`) runs continue to return their result inline without automatic node follow-ups.
- Worker turn budgets default to 100 assistant turns as a high safety cap; explicit lower budgets remain available for deliberately bounded tasks.
