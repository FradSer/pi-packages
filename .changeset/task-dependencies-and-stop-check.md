---
"@fradser/pi-tasks": minor
---

Make task dependencies the primary tool interface. Return unfinished task state to the model before normal settlement.

## Task tools

Remove `resources` from the four tool parameter schemas, task projections, tool descriptions, and transcript rows. Use `dependsOn` for prerequisites and `blockedBy` for unfinished prerequisites.

Independent tasks can run in parallel. Dependent tasks wait until all prerequisites complete. Stored resource fields and library helpers remain compatible with existing data and known consumers.

## Settlement check

Register an `agent_before_settle` handler. If unfinished work can proceed, append a bounded task snapshot to model context and request one continuation.

The snapshot includes task ids, status, holders, and unfinished dependencies. It directs the model to perform work before recording completion evidence. The harness never marks work completed.

Permit at most three automatic task continuations per real user input. Extension-generated input does not reset the allowance. Report unfinished work when the limit is reached.

Do not continue after cancellation or provider errors. Respect queued input and continuation already requested by another handler.

Return blocked or recovery-held work for one inspection continuation per task snapshot. A passive status row alone does not reach another model request. The model reads the task and checks whether recovery is safe and authorized before supplying a recovery reason. The harness never clears holds or transfers ownership itself.

After inspection, unchanged blockers receive a specific passive waiting message, not repeated automatic attempts. Inspection shares the same three-continuation allowance.

Preserve entries from earlier boundary handlers when appending the task message. Repair missing or non-string task ids using the persisted key under a recovery hold, so one malformed record cannot disable reminders for valid work.

Render one compact transcript row. Keep the full snapshot in model context, bounded to 20 tasks and 8 KiB.

## Verification

Test the real Pi lifecycle with a deterministic provider. Reproduce premature settlement after setting `in_progress`, then verify that the next model request receives task state and completes dependent work.

Also test a model that ignores reminders. Verify that only three additional requests run and unfinished task status remains unchanged.

Resume a real saved session containing an interrupted task. Verify that blocker inspection reaches the next provider request, checks the saved artifact, recovers with a reason, performs and reads back work, and completes the task.

Test an unresolved recovery blocker separately. Verify that inspection does not change its hold or retry it without resolving the blocker.
