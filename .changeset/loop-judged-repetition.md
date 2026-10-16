---
"@fradser/pi-loop": patch
---

Judge only the loop's own repetition, and drop the unused abort seam.

Every settled turn reaches the extension, so a turn the user started, or a turn
that was already running when a repetition was queued behind it, could end the
loop before its first repetition and spend a decision request on an answer that
was not the loop's result. `agent_end` now compares the run's last user message
with the pending injection, and `agent_settled` judges only a match. The behavior
matches `features/loop.feature` and the package README.

`src/decide.ts` no longer declares an abort signal, because none reaches it: Pi
1.2.0 reports `ctx.signal` to a hook inside a turn, and `undefined` inside an
extension command and at the settle boundary. The client's timeout bounds each
request. Read `packages/loop/AGENTS.md`.

The package guidance also records why the start notice uses `triggerTurn: false`
instead of the root guidance's `deliverAs: "followUp"` and `triggerTurn: true`:
a triggered turn at the start would inject a model turn the user did not ask for.
