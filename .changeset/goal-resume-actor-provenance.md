---
"@fradser/pi-goal": patch
---

`goal_resumed` records which actor lifted the pause.

`scheduler.resume` hard-coded `reason: "user"` on every resume, while `goal_paused` had carried an actor since the beginning. A resume activated by a revision under an accepted `/goal <text>` request therefore reported that the user typed `/goal resume`, which nobody did. Two facts were written as one, so a durable history could not tell a user action from a runtime one.

**What changed**

- `resume(goal, settings, reason)` takes the actor. The `/goal resume` command in `commands.ts` passes `user`; `activateRequestedRevision` passes `revision`.
- The parameter is required rather than defaulted, so a future caller has to name the actor instead of inheriting the wrong one.
- The new `ResumeReason` type in `record.ts` is the closed set. The ledger event field stays a `string`, because an older line, or a hand-written one, carries whatever text it carried and the reader must keep ignoring it. `goal_store.mts` proves that tolerance with values this runtime never writes.
- `tests/goal_thread.mts` pins both actors: the accepted-request revision records `revision`, the management verb records `user`.