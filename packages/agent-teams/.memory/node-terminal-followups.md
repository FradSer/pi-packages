---
name: node-terminal-followups
description: Background Agent Teams runs notify the main session after each non-summary teammate reaches a terminal outcome, with completion shown separately from the agent report and no automatic run summary
type: project
---

## Why

The leader needs incremental results while independent teammates are still working. Waiting for the run-level settle message hides completed work and delays downstream attention. Setup failures must use the same delivery contract as child-process failures.

## How to apply

- `run-machine.ts` sends one node follow-up for each non-summary node in a background run when it reports `completed`/`failed`, when its child process reaches a terminal outcome, or when pre-spawn setup fails (agent/state-file/worktree setup).
- `Node.nodeFollowUpSent` prevents duplicate follow-ups when a worker report is followed by process-close finalization; retry clears the marker.
- The node follow-up uses the worker's full terminal report/body and does not stop remaining teammates.
- Run settlement remains internal to leader state and foreground (`background=false`) runs continue to return their result inline, but background settlement does not enqueue a separate run-summary follow-up.
- The transport content contains only `<agent-message from="<agent>">` plus the worker's full body. The completion notice is rendered separately as `Teammate @<agent> finished.` and is never embedded in the report content.
- Worker turn budgets default to 100 assistant turns as a high safety cap; explicit lower budgets remain available for deliberately bounded tasks.
