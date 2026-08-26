---
"pi-continual-learning": minor
---

Rename the `/guardrails` command to `/harness`, and extend `/consolidate`
into a two-phase pipeline: after a verified memory consolidation, a second
read-only planner mines the same immutable session snapshot for tool-call
guardrail evidence (blocked calls, confirm outcomes, corrections) and applies
bounded policy/skillPrompt changes atomically to the personal project-local
layer only.
