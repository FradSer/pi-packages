---
name: attempt-bound-authority
description: Worker communication and submissions bind to the started Assignment Attempt; failed Work is recovery-held instead of silently re-claimable
type: project
---

## Why

A real session exposed four coupled lifecycle defects. After a worker was superseded or stopped, its cancelled attempts kept emitting cancellation acknowledgements into a settled assignment; the `work` tool was hidden for a retained superseded holder, so it could not acknowledge cancellation at all and its resource lease stayed stranded. Turns that had started under one Assignment Attempt adopted a newly assigned `assignmentId` from the live roster, so an old turn could send or submit as replacement Work. A failed Work Item returned to the board as plainly `pending`, so idle residents were repeatedly re-delegated the same doomed work while the leader treated the failure as already handled. Nonterminal reports from retired attempts also kept acting as current leader instructions.

## How to apply

- `packages/agent-teams/src/worker.ts` binds a turn at `message_start`: `assignmentId`/`taskId` come from the delivered assignment marker, and `authorize()` rejects any call whose roster entry names a different attempt, Work Item, or incarnation. Reads match on `spawnId` as well as name so a replacement resident cannot lend authority.
- A bound, living, same-spawn roster entry with no assignment clears the binding for that turn: a retried attempt must not dead-end an ordinary peer/board wake.
- `send`, `queueWorkClaim`, and `queueWorkSubmission` all pass the same authority; a terminal outcome or closed assignment rejects further sends, claims, and submissions. A retained superseded holder keeps exactly one failed cancellation acknowledgement.
- `packages/agent-teams/src/state.ts` marks failed, crash-released, or stop-released Work `recoveryRequired`, which excludes it from `claimableTasks()` and wake notices; only an explicit leader `work assign` clears it. A harness start failure that never reached the worker stays ordinarily claimable.
- `packages/agent-teams/src/index.ts` keeps a retired attempt's nonterminal report in session history but removes it from the provider projection, because Pi cannot retract an already-queued steer.
- Keep BDD coverage in `features/worker-attempt-lifecycle.feature`, `features/session-history-regressions.feature`, and `features/historical-report-delivery.feature`; regressions live in `tests/test_worker_attempt_lifecycle.py`, `tests/test_session_history_regressions.py`, and `tests/test_historical_report_delivery.py`.
- Guidance states the contract in two sentences; `tests/test_prompt_budget.py` ceilings for `tmActiveLeader`/`tmWorker` were raised deliberately with that change.