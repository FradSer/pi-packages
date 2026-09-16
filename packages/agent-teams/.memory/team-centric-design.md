---
name: agent-teams-final-surface
description: Final Agent Teams public surface and lifecycle rules
type: project
---

**Why:** Agent Teams uses one explicit coordination surface so Work authority,
communication, and resident lifecycle cannot be confused.

**How to apply:**

1. Public model tools are `agent`, `work`, and `agent_event`; `/agent-teams`
is the human management surface.
2. `agent` uses strict `delegate`, `start`, `inspect`, and exact-session `stop`
actions. Session handles include the resident and spawn incarnation.
3. `work` owns create/list/assign/claim/submit/release/completed-only reopen/
supersede. Claim and submit are marker intents; the single-writer harness owns
acceptance and verification.
4. `agent_event` is communication-only with `inform` or `request`. It never
completes, releases, reopens, or reassigns Work.
5. Worker capability grants contain only `agent_event` and `work` plus requested
Pi built-ins. Verification freezes execution and archives deferred mail as Work
history.
6. Incompatible persisted runtime snapshots fail explicitly; no silent migration
or legacy-tool fallback is allowed.
