---
"@fradser/pi-goal": minor
---

A goal no longer has a budget, and no way to get one. The concept is deleted rather than repositioned:
`GoalRecord` has no `tokenBudget`, `budgetReached`, `remainingBudget` and the cap-stop helpers are
gone, nothing in the runtime stops, refuses a resume, refuses a revision or narrows the tool surface
because a number got large, the run-start prompt no longer prints a token limit or a remaining budget,
and the `/goal budget` verb added in this cycle is removed again before release. Usage is still
recorded and reported — main-model and completion-check tokens are attributed to the goal, including a
cancelled or superseded check for the same open goal — but usage is a report, not a gate.

A goal is bounded by its work. Automatic continuation still stops after three consecutive runs that
change nothing observable (unseen successful `edit` or `write` counts as progress; reading, searching,
fetching, commands and delegated child work explore), and `maxAutonomousRuns` remains the only
optional ceiling, unset by default. A record an earlier version wrote is tolerated rather than
migrated: a `budget_limited` status reads as `paused`, its `tokenBudget` field is dropped by
normalization, and the goal resumes and completes normally, so a goal that an old cap had stopped is
no longer stuck. `create_goal` exposes no budget parameter, so a model cannot reintroduce a limit
nobody asked for.