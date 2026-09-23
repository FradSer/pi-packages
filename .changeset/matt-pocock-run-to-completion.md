---
"pi-matt-pocock": patch
---

Keep a multi-step workflow running to completion instead of breaking off partway.

The active-workflow guidance told the agent to "yield with the workflow still active" whenever
only teammate results remained outstanding, so any long task stopped at the first checkpoint it
could justify. It now says to drive the current procedure to its end in this turn and not to end
the turn to ask whether to continue, and it reserves yielding for work that genuinely depends on
an external actor, an unreachable teammate result, or exhausted context. Completion is still
gated on applicable verification and returned blocking reviews.

A workflow step also no longer re-delivers procedure bodies the session has already been shown.
Every transition re-sent the active procedure's whole dependency closure — the `implement`
bundle is 14.5 KiB of `implement` + `bdd` + `tdd` — so repeated transitions spent the context the
work itself needed and ended long tasks for want of room rather than want of work. Each
procedure is now delivered once per session and a transition carries only the newly active one,
while a session restore still re-delivers the full context because a restore is a context
boundary.