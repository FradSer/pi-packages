---
"@fradser/pi-goal": minor
---

A goal now has one requirement text: its objective. The verification contract is deleted rather than
repositioned, because two requirement texts meant the completion check judged one of them and the
model could read the other. `GoalRecord` has no `verificationContract`, `create_goal` and
`update_goal` expose no `verification_contract` parameter, `get_goal`/`/goal` and the `[goal] started` body print the objective alone, the run-start policy block
carries no second block, and the completion check receives the complete objective with the recorded
observations and nothing else. Both Goal tools refuse any parameter they do not declare, so a stale
schema from an older session is refused as an unapplied update instead of having the removed field
silently dropped from the revision it sent. A revision still moves the objective and the start of the evidence
window together, so observations collected under the old requirement stay inadmissible.

A record an earlier version wrote is tolerated rather than migrated: normalization drops its
`verificationContract` field and keeps the objective unchanged, so a goal stored under the old shape
reads, revises and completes as any other. `/goal <request>` now asks the model to preserve the
existing requirements inside the objective instead of naming a separate completion condition.