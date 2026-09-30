---
"@fradser/pi-subagents": minor
---

A standalone child returns its Session Result: its settled answer now reaches the main session.

`@fradser/pi-subagents` is installable on its own, and with only that package loaded a child's work never came back. The answer existed in exactly one place — the spawner's progress stream, where an `agent_settled` event becomes a final frame — and the standalone spawn passed no `onUpdate`, so it was discarded at the moment it existed. The `agent` tool's description promised the opposite: "Results arrive automatically: continue your own work or end the turn rather than polling." The gap survived review because every configuration in daily use had `@fradser/pi-agent-teams` installed, and that package's published host owns the spawn and delivers reports itself.

**What changed**

- One **Session Result** per settled turn, delivered as a custom message with a `followUp` delivery and a triggered turn. The child's final text is the body, verbatim, behind an `<agent-result from=… session=… turn=…>` envelope; structured fields go in the message details.
- The message renders as one pi-kit lifecycle row — `[agent] reported · @name` with the result's first line visible, the rest of the answer on expansion, and no session handle in the row. An ended Work Session paints on the error band: one visible line with an explicit `triggerTurn: false` and `deliverAs: "nextTurn"`, because recoverable execution is internal (ADR-0002) and a death is not a decision the Leader has to make. The explicit false matters — pi reads an *absent* `triggerTurn` as permission to steer the turn in flight.
- A settled child is listed as `idle` with its answer as `liveText`, a shutdown the Leader requested produces no death notice, and a delivery that fails records itself on the roster instead of vanishing.
- The spawner now reports a settle the moment it is parsed. It previously coalesced progress to one frame per stdout read, so a read carrying a settle *and* the next turn's start hid the settle completely — the exact failure this feature exists to remove.
- The roster records the child's live text on every frame and projects it, so a delivered result stays readable and the delivery decision is auditable from the roster.
- A published coordinator host suppresses execution-layer delivery, so installing both packages delivers each result once, exactly as today.
- The contract lives behind the entry that holds the session API: a tool's execution context has no `sendMessage`, so the library takes an injected sender and stays TUI-free. A consumer embedding the library directly still spawns, records, and inspects — without delivery, as before.

**Two defects a live session found, which no offline test could see**

- A real child settles **empty** before it settles with its answer. The first version treated that empty settle as the turn's result, armed the dedupe, and suppressed every real result for the life of the Work Session. The dedupe is now armed by the turn, and a textless settle neither delivers nor arms it.
- The standalone path handed the child its kickoff prompt **twice** — once as the spawn description, which the spawner writes to the control stream itself, and once through the resident-wake call. Every prompted start ran the same turn twice: twice the child's tokens, and twice the Leader's turns now that a settled turn is delivered. The prompt now travels once.

The first version of this feature passed its entire offline suite and delivered nothing to a real session.

**Vocabulary**

`Session Result` joins `CONTEXT.md` as a term owned by this package: the settled output of one Work Session turn, distinct from a Submission (which needs a Task and an Assignment Attempt a standalone spawn has neither of), from a Message (the team runtime's), and from Agent Presence (state, not result). ADR-0007 records why the execution layer delivers at all.

Contract: `features/session-result.feature`, ADR-0007, `docs/spec-standalone-session-result.md`.

**Verification**

- `tests/test_session_result.py` drives the real entry, the real tool, and the real delivery with only the child process mocked: a settle delivers verbatim with its provenance, an empty settle does not, an empty settle followed by the answer delivers exactly one result, every wake of a resident delivers, a hosted spawn delivers nothing, a child that dies produces one visible non-triggering line, a death that leaves a later turn unanswered is announced, a Leader-requested stop is not a death, a host with neither renderer nor session API still works, and the library barrel loads no pi-tui.
- `tests/coalesced-settle-fixture.ts` drives the real parser with a settle and the next turn in one stdout read, because a hand-written frame list cannot catch the parser dropping an event.
- Nine findings from an independent review of the first version are fixed: the ended notice steering an in-flight turn, two owners for a delivery failure, an unconsumed `sendMessage` promise, a roster frozen at `working`, a death that silenced a later turn, a Leader-requested stop painted as a death, a settle lost to read coalescing, notice text naming a call the tool refuses, and a README that contradicted the manifest.
- A live RPC session with only this package installed: the leader delegates, the Session Result arrives as a custom message, it enters the model's context, the next turn reads it, and exactly one result is delivered.
