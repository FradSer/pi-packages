---
"@fradser/pi-loop": minor
---

Add `/loop <request>`: repeat one message into a session as a real user turn.

`--every`, `--times`, `--until` and `--message` state a schedule explicitly and
call no model. `{{index}}`, `{{total}}`, `{{remaining}}`, `{{time}}` and
`{{date}}` expand per repetition. A free request is resolved by TypeSafe Jev
choices over candidates the extension builds: the listed interval, the run
limit, the request segment that states the stopping condition, and the text to
repeat. A natural-language stopping condition is judged by one closed noul
question after each settled turn, against an explicit threshold.

A tick whose previous injection has not settled is skipped and counted, so a slow
turn cannot queue prompts. A repetition that cannot be delivered is reported and
ends the loop, because the promise `pi.sendUserMessage` returns is observed
rather than discarded. `/loop stop` and session shutdown release the only
timer, and a stopped loop cannot restart.

Verified with deterministic module checks, a loopback decision endpoint covering
low confidence, unspecified cadence, unknown answers and rejected credentials,
and a native `pi` TUI run that delivered two scheduled injections as
`messageType: "user"` turns.
