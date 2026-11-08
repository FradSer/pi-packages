---
"@fradser/pi-goal": patch
---

A stalled Goal no longer stops making progress, and a transient interruption no
longer cuts a working run short at an arbitrary point.

Three defects produced the reported "three chances" behaviour:

- Pi skips `agent_before_settle` on an aborted run, so the scheduler stayed
  `inRun`, leaked the previous run's `userRun` credit, and never re-armed. The
  runtime now closes the run at `agent_settled` (which Pi fires in a `finally`
  for every run, with an `aborted` flag) and drops that credit. An explicit abort
  keeps the goal open without silently starting another model turn; a host
  anomaly that skips the boundary without an abort re-arms through the ordinary
  store write. Only a real failed run stops at once. Restore and shutdown now
  reset the armed decision, denial, window streak, wait and pending timer, and a
  stale timer can no longer dedupe out a later delivery.
- A quiet turn honestly waiting on an in-flight bounded child, steer or monitor
  had no tool receipt, so it spent one of the three no-new-work chances. The
  goal then stopped at `Goal waiting` exactly when the result was about to arrive.
  A living child of this project (checked by live pid and matching cwd) now
  holds the window for a bounded wait — a stale, foreign or hung child cannot
  spin the loop forever. Only a result whose wait this thread actually observed
  counts as new work, so another session's child cannot revive this Goal.
  A completed result re-arms only a stop the runtime itself wrote. A user's own
  turn with new work does the same. Neither lifts a user pause, a blocker, a
  provider-failure stop, a spent allowance or a finished goal.
- A queued message made `boundaryContinuation()` discard the armed decision via
  `takeover()` with no re-arm. The armed decision now survives for the idle timer
  to deliver after the message settles. A refused checkpoint's `denied` flag no
  longer poisons the next run.

The model-facing policy now says to finish the started work unit before ending a
turn, to treat waiting on a bounded child as a legitimate turn, and to call the
completion check in the run where the objective's conditions were verified. The
run-start counters show the live no-new-work streak (`2/3`) instead of only the
constant limit, so the last chance is no longer a surprise.

Eighteen BDD regressions cover the aborted run, the leaked user credit, report-only
turns waiting on delegated work, a queued steer preserving its decision, a
refused checkpoint not poisoning the next run, a stalled goal resuming on the
user's new work, and the safety boundaries: stale/foreign/hung children cannot
hold the window (with the idle timer actually delivering), an unobserved foreign
result cannot count as this Goal's work, restore starts a fresh window, a stale
timer cannot dedupe out a fresh delivery, a user pause and a provider-failure
stop cannot be lifted by new work, and `maxAutonomousRuns=0` cannot be re-armed.
The dormant
`goal_completion.mts` subagent scenario had pinned the stall as correct; its
expected result is updated to the new requirement. `test_goal_hygiene.py` now
runs `bun x tsc`, matching the workspace's package manager.

Verification: 33 pytest tests (66 simplified + 36 scheduling harness scenarios),
`bun x tsc --noEmit -p tsconfig.tests.json`, root `bun run typecheck`,
`bun run pack:check` (21 manifests), `bun pm pack` (including the new
`src/inflight.ts`), and all five native Pi CLI/PTY probes pass.
