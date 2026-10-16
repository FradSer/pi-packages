---
"@fradser/pi-loop": minor
---

Run a count-bounded request that names no cadence.

`/loop 输入3次Hi` and `/loop --times 3 Hi` were refused with "The request names no
cadence". A run count bounds the loop, so nothing about that plan is undetermined:
the loop now takes the shortest permitted tick and repeats as soon as each
repetition settles, and a tick that arrives while a repetition is still running is
skipped rather than queued. The start notice says the cadence was assumed, so a
defaulted cadence is never silent.

The count is scheduling metadata wherever it appears, so it leaves the message:
`/loop 输入3次Hi` repeats `输入Hi`. A count-only segment already left it, and a
count phrase inside a segment now leaves it too.

A request that names neither a cadence nor a count is still refused. Nothing
bounds it, and a guessed cadence could repeat an unbounded loop for the life of
the session.
