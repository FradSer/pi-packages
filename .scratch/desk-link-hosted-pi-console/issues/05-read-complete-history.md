# 05 — Read a Hosted Pi's complete history on demand

**What to build:** The live view stops hiding detail. A Console reads a Hosted Pi's complete history and complete tool results on demand, from a position, paged and bounded, while what enters its own session context stays bounded.

**Blocked by:** 04 — Steer, cancel, and end an attached Hosted Pi.

**Status:** ready-for-agent

- [ ] History is the Hosted Pi's own Pi session log under the host's session directory. This work adds no archive, and the durable receipt's bounded response is not presented as history.
- [ ] A read takes a position and is paged and bounded per request, using the same coordinate as the live stream so the two cannot disagree.
- [ ] A read never truncates silently: reaching a bound yields an explicit continuation rather than a shortened answer presented as complete.
- [ ] What enters the driving session's own context stays a bounded tail plus the terminal result of a turn, delivered as a follow-up message so it becomes part of that conversation. Each time a turn reaches a terminal outcome its result is delivered; the Hosted Pi may keep running afterwards.
- [ ] The console surface can page through history while attached, and reading history never changes the Hosted Pi's state.
- [ ] Scenarios pinned: a complete history and complete tool results are readable on demand; only a bounded tail and the terminal result enter the Console's own context.
