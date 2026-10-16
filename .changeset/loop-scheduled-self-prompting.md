---
"@fradser/pi-loop": minor
---

Add `/loop <request>`: repeat one message into a session as a real user turn.

`--every`, `--times`, `--until` and `--message` state a schedule explicitly and
call no model. `{{index}}`, `{{total}}`, `{{remaining}}`, `{{time}}` and
`{{date}}` expand per repetition. A free request is resolved by TypeSafe Jev
choices over candidates the extension builds: the listed interval, the run
limit, the request segment that states the stopping condition, and the text to
repeat. A segment that only states a repetition count is the run limit, never a
stopping condition. A natural-language stopping condition is judged by one closed
noul question after each settled turn, against an explicit threshold.

A tick whose previous injection has not settled is skipped and counted, so a slow
turn cannot queue prompts. A delivery the host refuses is reported and ends the
loop. `/loop stop` and session shutdown release the only timer, and a stopped loop
cannot restart.

Verified with deterministic module checks, a loopback decision endpoint covering
low confidence, unspecified cadence, unknown answers and rejected credentials,
and a native `pi` TUI run that delivered two scheduled injections as
`messageType: "user"` turns. Measured against the live service on twelve labelled
requests, all four questions resolved correctly and an eight-hour five-minute loop
with a stopping condition costs about $0.02; read the package README for the
numbers and for what stays unverified.
