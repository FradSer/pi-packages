---
"@fradser/pi-tasks": minor
---

The completion checks gained a read side: a caller can ask what blocks a completion instead of only finding out by failing one.

`update_task status=completed` refuses and names the blocker, which is the write side. A model that split a task into n and just finished one has the other question — which of the rest can be marked done *now* — and answering it by attempting each completion is n refusals to learn n facts the board already holds.

- **Every task carries `blockedBy`**: the ids among its `dependsOn` that are not completed. `dependsOn` says what the edges are; this says which of them are unfinished, which is otherwise a comparison against a list made by hand. Absent when nothing is blocking it.
- **`list_tasks` takes `ready`**: the tasks that could be completed right now — an attempt on the record (in progress, or pending under a recovery hold a dead holder left) with every declared dependency completed. It is the mirror of `claimable`, which answers what can be started; the two together are what makes a batch of n recoverable without a refused completion per task.

Both are pure functions of state the store already holds, and the declared output schema says so, so a codemode script reads the same thing a model does. A task nobody has touched is not completable however finished its dependencies are: there is no attempt to accept.

Verified in `packages/tasks/tests/` (85 passed) and through the tool surface in a live Pi 1.0.0 session: a four-task split with one finished returned exactly the newly-unblocked dependent from `list_tasks {ready: true}`, while every task in the full list named what was still unfinished.
