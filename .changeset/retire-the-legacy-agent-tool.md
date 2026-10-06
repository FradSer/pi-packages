---
"@fradser/pi-subagents": minor
"@fradser/pi-agent-teams": minor
---

Remove the `agent` tool, its six-action API, its selection branches and its
uppercase receipt. The four intent tools `agent_start`, `agent_input`,
`agent_stop` and `agent_list` are the only child tool surface: `agent_inspect` is
retired with it, because a roster read plus the delivered Session Result already
answers every question the per-child inspection existed for, and a tool the model
can call repeatedly is a tool it will call repeatedly instead of waiting.
A recorded branch whose selection named `agent` receives the intent family on its
next session start. No user data moves, no migration runs on discovery or start,
and no compatibility adapter remains.

Rename the shared executor to `executeChildIntent` and name its operations after
the intent operations. The published coordinator seam keeps its authority, so
`@fradser/pi-agent-teams` behaviour is unchanged apart from calling the renamed
executor.

Every child result now paints one collapsed row. A single-child row reads
`[tool] label · @name · status`, names the child once, and does not repeat a
state word the label already carries. The authored prompt or steer headline stays
on the row. A roster subject has no state, so `agent_list` reads
`[agent] listed · @children · N of M`. Every other fact is expansion detail, and
a moved line is dropped when the detail list already carries it.

This is a breaking tool-surface change for recorded `agent` scripts in these
pre-1.0 packages. Anything that parsed the legacy `AGENT ·`, `GRANT ·` or
`RESULT ·` lines must read the structured `details` instead. Definitions,
Memory, storage, result delivery and child lifetime are unchanged.