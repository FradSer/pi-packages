---
"@fradser/pi-goal": patch
---

`/goal <text>` now asks the model to revise the focused goal instead of superseding it.

`goalRequest` told the model: form a NEW goal that carries the earlier objective forward, create it with `supersedes: true`, and do not revise the existing goal in place. That contradicted four other sources and disabled the path the command builds for itself.

**Why it mattered**

The command keys one activation token to the focused goal id, and only `update_goal` consumes it. When the delivered body forbade an in-place revision, a paused goal could not be revived through `/goal <text>`: the model superseded instead, the paused record was archived with `goal_cleared` / `superseded`, and the ledger never recorded the `goal_resumed` it owed. The busy path was worse, because the command had already revised in place and then told the model to replace the goal it had just revised. A live model had to disobey the instruction to reach the documented behaviour; the seeded unit tests never noticed, because they script the model's tool call rather than obeying the body.

**What changed**

- The seeded request keeps the existing objective, adds the new request to it, and revises that goal in place with `update_goal`. It names why: a revision is the only path the command can activate.
- `/goal <text>` never asks the model to supersede: the seeded body revises the focused goal in place, and new work after a finished goal follows an explicit clear.
- The research step still runs first when repository facts are missing; the final paragraph now says to record the objective with `update_goal` or `create_goal` rather than naming creation alone.
- `tests/goal_session.mts` pins the invariants: the body asks for `update_goal`, it does not forbid an in-place revision, and it never names `supersedes`.