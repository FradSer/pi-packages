---
"@fradser/pi-tasks": minor
"@fradser/pi-agent-teams": minor
---

Make a recovery hold a first-class status, at the same level as in progress. `TASK_STATUSES` gains `recovery_hold`, and the `recoveryRequired` flag is gone from the record, from every projection, and from the model-facing text. `pending` now means never attempted, and only that.

A task that fails, that has its premise withdrawn by a reopen, or that is restored mid-attempt now sits in `recovery_hold` instead of `pending` under a flag. Taking from `recovery_hold` still needs a stated reason, and the refusal still names the state. A task row reads `recovery hold` in the status slot where it used to read `pending · recovery hold`, so a held task is no longer displayed as work that was never started.

`claimable` and `ready` answer from the status alone: a claimable task is `pending` with every dependency met, and a completable one is `in_progress` or `recovery_hold`. The paired flag checks those predicates used to carry are gone.

A task file written before this change restores correctly. A record with `pending` and `recoveryRequired: true` restores as `recovery_hold`, a record still in progress restores as `recovery_hold`, and the flag is never written back. The file format version is unchanged, because the reader normalizes both spellings rather than migrating the file.

This is a breaking library change for these pre-1.0 packages. Read `task.status === "recovery_hold"` where a record used `task.recoveryRequired`, and drop `recoveryRequired` from anything that stored it. Update `@fradser/pi-tasks` and `@fradser/pi-agent-teams` together. Task file format version 2, completion evidence, dependency rules, ownership, and recovery rules are unchanged.
