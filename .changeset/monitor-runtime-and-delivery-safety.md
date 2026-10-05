---
"@fradser/pi-monitor": patch
"@fradser/pi-goal": patch
---

Keep monitor deadlines responsive by evaluating JavaScript result contracts in
interruptible workers with bounded queues. Match unterminated tails independently
for stdout and stderr, preserve diagnostics on timeout and stop, and await process
group escalation and worker termination even after a monitor leaves the active list.
Natural shell completion also reclaims remaining descendants in its process group.

Return terminal results directly for mixed and nested Pi v1 tool batches; retain
one asynchronous terminal notification per monitor-only UI call. Correlate direct
and custom results with cross-instance unique monitor IDs, render synchronous
outcomes truthfully, and validate development against Pi v1.0 with its Node baseline.

Bound the monitor console by terminal dimensions, preserve selection, hide logs
until requested, and route paging keys through Pi's focused overlay API.
Goal completion evidence uses structured monitor status, ignores pending starts,
and correlates modern IDs while preserving historical counter-based records and
the chronological position of updated outcomes.

Honor append-only context edits when collecting goal evidence: omitted receipts
and assistant calls contribute no observations, replacements change only content,
and original role and terminal metadata remain authoritative. Retain raw receipt
coverage across compaction and preserve last-edit semantics.
