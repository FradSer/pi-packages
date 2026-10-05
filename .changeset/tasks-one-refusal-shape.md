---
"@fradser/pi-tasks": minor
"@fradser/pi-agent-teams": minor
---

Return one refusal shape from every task-store operation. A refusal is now `{ refusal, detail?, reason }`: a machine code from one closed set for a caller to branch on, the task, holder, or prerequisite it is about, and the sentence a caller or a model reads.

Before this change the store returned the same sentence under five different shapes: `error` from a creation, `reason` from an edit, a completion, a reopen, and a bind, `refusal` with a `detail` from a take, and `error` again from a marker path. Only a take could be branched on without reading prose. The success flag is unchanged: `ok` for a task write and `applied` for a claim marker.

This is a breaking library change for these pre-1.0 packages. Read `result.reason` where a result used `result.error`, and read `result.refusal` to branch on why. Every refusal word in the sentences themselves is unchanged, no rule about what may be done changed, and the four model-facing tools still report the same text. Update `@fradser/pi-tasks` and `@fradser/pi-agent-teams` together.
