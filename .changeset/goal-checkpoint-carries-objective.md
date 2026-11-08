---
"@fradser/pi-goal": patch
---

An automatic continuation no longer starts from an empty custom message.

The 2026-11-04 `jev-duplex-analysis-and-data` archive records a durable goal
created mid-session whose next three checkpoint runs each produced an empty
assistant message, ending in `3 consecutive runs produced nothing new. Use /goal
resume to continue.` The checkpoint body was empty and the run's assembled
system prompt predated the goal's creation, so the model received neither the
objective nor the work policy for those runs.

`checkpointBody` now renders the cached policy, the escaped untrusted objective
block, the live no-new-work streak and the in-flight-work note, and both
continuation paths (the idle timer and the settlement boundary) deliver that
body with the checkpoint. The checkpoint stays hidden from the transcript;
claim, dispatch, acceptance and the three-run limit are unchanged. `settings()`
falls back to the core's project root when no run context is bound yet, so a
timer delivery needs no non-null assertion.

Two Given/When/Then regressions pin the delivered and boundary-started body, the
live streak and hidden display, and the escaping of a hostile objective; the
feature contract was regenerated from observed assertions. Goal pytest, both
typechecks, pack, all five native Pi CLI/PTY probes, the isolated Docker
acceptance (Pi 1.4.0, 33 pytest cases and the full probe set) and the workspace
quality gate pass. An independent read-only review found no new blocking defect.
The first Docker attempt failed on a network-interrupted bun download and the
retry succeeded; no real-model or archived-session replay was run.
