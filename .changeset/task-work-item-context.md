---
"@fradser/pi-tasks": minor
"@fradser/pi-agent-teams": patch
---

A Work Item now owns bounded context, and a successor handoff is a structured brief instead of concatenated prose.

**@fradser/pi-tasks**

`src/context.ts` adds the per-Work-Item context that was previously rebuilt ad hoc at each reassignment:

- `WorkContext` on `BoardTask`: `workspacePath`, `handoff`, `refs`, `budgetBytes`.
- `WorkHandoff`: `candidate`, `delta`, `verification`, `priorFindings`, `outstanding` — the fields a recheck actually needs. `priorFindings` exists specifically so prior review findings survive outside the result that a reopen clears.
- `buildWorkHandoff` bounds each field to its share of the budget and reports whether anything was clipped. `clipToBytes` never splits a UTF-8 sequence and appends `[context clipped to budget]`, because a silently truncated brief is worse than a shorter one that announces itself.
- `workContextBytes` / `withinContextBudget` measure description, result, error, handoff, and refs against the budget, so a long-lived Work Item cannot grow without limit.
- `normalizeContextRefs` de-duplicates by kind and id, drops empties, and caps the list at `MAX_CONTEXT_REFS`.
- `formatWorkHandoff` gives the brief one shape instead of one per caller.

No session identifier is stored anywhere in this package. A Work Item records the workspace path it ran in and leaves session resolution to Pi, which groups sessions by working directory. That boundary is what keeps `@fradser/pi-tasks` free of the process layer, and `test_a_work_item_records_a_workspace_path_and_never_a_session_id` asserts it against the source rather than only the data.

**@fradser/pi-agent-teams**

`buildSuccessorHandoff` now builds its brief through `buildWorkHandoff` and `formatWorkHandoff` rather than joining prose lines. Prior leader reports go into `priorFindings` rather than a "Recent leader reports" string. The `SUCCESSOR HANDOFF FROM @name` heading and the `kind id` form of the prior assignment are preserved, so the existing handoff assertions still hold unchanged.

`setTaskContext` records the Agent workspace path on the Work Item after a successful isolated spawn. It is additive: an existing field is only replaced when the caller supplies a new value, so recording a workspace path cannot erase a handoff written earlier.

Contract: `packages/tasks/features/work-context.feature`.
