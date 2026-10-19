---
"@fradser/pi-goal": patch
---

A `/goal <text>` request now counts as the user's own turn. The command delivers the request as a
custom message, so the run it starts was never marked user-initiated: a model that only recorded the
objective in that run produced no tool receipt, and the goal paused itself with `No effective work was
recorded. Use /goal resume to continue.` before any work happened. The runtime now recognises the
`goal-procedure` message as that user turn, and settlement lets a user-initiated run pass the
no-effective-work stop, so the request earns exactly one real run. The run after it is judged
normally, so one unproductive turn cannot hold the loop open, and three runs that change nothing
still stop it.

Goal transcript rows also stop repeating `Tokens used: <n>`. Usage stays recorded on the goal and
reported in the run-start counters; the `[goal] started`, `[goal] updated` and `/goal` status rows
carry the objective and any stop reason alone.