---
"pi-continual-learning": minor
---

Split learning triggers into independent `autoSettledLearning` and
`autoContinualLearning` settings (both off by default) and retire `autoMemory`.
When enabled, the parent registers `learn`, a no-parameter tool that lets the
agent request current-task Memory or Harness learning once before its final
answer. The request carries no content: the parent freezes the task evidence and
applies the configured `automaticPhases.memory` policy, so `apply` writes only
validated changes, `propose` saves them for review, and `off` refuses. The settled
learner skips Memory for a task the agent already processed while still handling
Harness and AGENTS.md.

All user-level configuration now lives in one file,
`<agent-dir>/continual-learning.json`: the learning model (`model` as
`provider/model` or `{provider, model}`), the two learning triggers, phase
policies, AGENTS.md budget, Jev and the capability flags. `/memory model` and the
settings menu merge into it and preserve every other section. The retired
`<agent-dir>/memory.json` pair and `<agent-dir>/memory/settings.json` learning
fields are neither read nor written; with no unified `model`, learning follows
the session model.

Learning also preflights the model against the no-extensions view used by planner
children. An extension-registered session or configured model now blocks with an
actionable `/memory model` message before any worker spawns, instead of failing
the selector with `Model not found`.


Agent-requested learning no longer treats replay-backlog bookkeeping as a
precondition: a malformed backlog or an unavailable replay reference now reports
the real learning outcome instead of failing with `learning was not started`.


All Memory is reviewable by default. `allowPrivateMemory` is removed from the
configuration schema, `createJevJudge`, the judge surface and the consent
helper, so agent-requested and settled learning no longer stop with
`private-memory-denied`. Frozen research source copies keep their historical
form.


Selector workers now default to off thinking; an empty worker decision falls
back to a bounded parent-routed minimal selection instead of failing the whole
learning run, while undecidable nonempty output stays a reported failure.
Agent-triggered results report a failure in any phase, not only Memory.


Coverage and body-review workers may wrap their JSON decision in a single
Markdown fence; the parent now parses it without relaxing the reject rules for
prose, extra objects or digest binding.
