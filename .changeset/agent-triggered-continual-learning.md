---
"pi-continual-learning": minor
---

Split learning triggers into independent `autoSettledLearning` and
`autoContinualLearning` settings (both off by default) and retire `autoMemory`.
When enabled, the parent registers `learn_current_memory`, a no-parameter tool
that lets the agent request current-task Memory learning once before its final
answer. The request carries no content: the parent freezes the task evidence and
applies the configured `automaticPhases.memory` policy, so `apply` writes only
validated changes, `propose` saves them for review, and `off` refuses. The settled
learner skips Memory for a task the agent already processed while still handling
Harness and AGENTS.md.

All user-level configuration now lives in one file,
`<agent-dir>/continual-learning.json`: the learning model (`model` as
`provider/model` or `{provider, model}`), the two learning triggers, phase
policies, AGENTS.md budget, Jev and the capability flags. `/memory model` and the
settings menu merge into it and preserve every other section. The legacy
`<agent-dir>/memory.json` pair and `<agent-dir>/memory/settings.json` learning
fields remain readable as fallbacks for existing installs; nothing writes them.

Learning also preflights the model against the no-extensions view used by planner
children. An extension-registered session or configured model now blocks with an
actionable `/memory model` message before any worker spawns, instead of failing
the selector with `Model not found`.
