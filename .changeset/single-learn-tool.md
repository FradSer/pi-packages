---
"pi-continual-learning": major
---

Replace the `learn_current_memory` model-facing tool with a single zero-argument
`learn` tool. This is a breaking change with no alias, no compatibility layer
and no recorded-branch migration.

The one tool covers two explicit request families: organizing/remembering
Memory ("整理记忆", "记住这个", "remember this") and authoring a lasting Harness
rule ("以后禁止 npm", "纠正旧规则"). The model passes no intent, type, content,
path or file; the parent freezes the task evidence and routes the request. A
Harness request opens the existing guarded `/harness` procedure and returns an
honest `authoring-started` outcome. The follow-up turn may use the new declared
`harness_write` tool, whose required `cases` field survives strict tool-schema
sampling; the parent validates positive and negative fixtures, confirms, writes
atomically with readback, and records a receipt plus an undoable history row.
The existing two-step `harness_preview` path remains available. Memory requests
keep the existing Memory-only pipeline, receipts and undo.

The parent classification reads one real user entry. The consolidation
pipeline's evidence screen (`screenLearningEntries`) and the frozen historical
proofs are unchanged; planner-child structured-output flags and the
`learning_read` evidence marker remain. See ADR-0014.
