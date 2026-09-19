# 02 — Launch a Hosted Pi on the desk from the Mac

**What to build:** From the Mac, a Console launches a Hosted Pi on the desk: the durable receipt exists before the turn starts, the identity comes back immediately, and the session reports itself as running. Invalid requests are refused without running anything.

**Blocked by:** 01 — Connect as a Console and list the desk's Hosted Pi sessions.

**Status:** ready-for-agent

- [ ] The Pi host is rewritten rather than reused. It creates, runs, and disposes a session per request today, so holding one live session across turns, subscribing to its events, accepting a further prompt, and keeping a slot past one turn are new work. Admission, the durable receipt written before execution, the host-wide cap, the no-automatic-retry rule, and the no-replay-after-restart rule carry over.
- [ ] An accepted launch returns its durable identity before execution starts, and the receipt is written before the turn starts.
- [ ] An identical retry with the same identity returns the existing Hosted Pi; a different prompt or project with that identity is refused.
- [ ] Refusals run nothing: a project outside every configured development root, an empty, oversized, or invalid-UTF-8 prompt, the host-wide cap already reached, and a project overlapping a live session.
- [ ] A project that is deleted, or a development root that changes, while a Hosted Pi is alive has defined behavior and its own scenario.
- [ ] A host restart marks a Hosted Pi that was running as interrupted, never replays its prompt, and leaves its session log readable so a later attach can still show what happened.
- [ ] Mac side: a launch fast path on the console command and one assistant-facing tool, both returning the identity immediately.
- [ ] Scenarios pinned: the desk hosts a new Hosted Pi; a launch outside the configured roots is refused; a launch with an invalid prompt is refused; a Hosted Pi is idempotent by identity; intake rules are unchanged apart from slot ownership; a host restart never replays work.