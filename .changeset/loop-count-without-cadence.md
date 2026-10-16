---
"@fradser/pi-loop": minor
---

Run a count-bounded request that names no cadence.

`/loop 输入3次Hi` and `/loop --times 3 Hi` were refused with "The request names no
cadence". A run count bounds the loop, so nothing about that plan is undetermined:
the loop now defaults to a five-minute cadence, and a tick that arrives while a
repetition is still running is skipped rather than queued. The start notice says
the cadence was assumed, so a defaulted cadence is never silent.

The count is scheduling metadata wherever it appears, so it leaves the message:
`/loop 输入3次Hi` repeats `输入Hi`. A count-only segment already left it, and a
count phrase inside a segment now leaves it too.

An unnamed cadence is never a refusal, with or without a run count. `/loop
检查项目修改，总结` repeats every five minutes until you run `/loop stop` or its
stopping condition is met, and the start notice says the cadence was assumed.

The start line moves to the turn a repetition reaches. Every `/loop ...` arrives
as a user turn and the first repetition is queued behind that run, so a line sent
from the command landed ahead of the input you typed. The line is now injected at
the head of the next run, which is the run a repetition reaches. A start with no
cadence reaches it at its first repetition, five minutes later.
