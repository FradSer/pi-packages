---
"@fradser/pi-tasks": minor
"@fradser/pi-kit": minor
"@fradser/pi-subagents": minor
"@fradser/pi-agent-teams": patch
---

`@fradser/pi-tasks` now honours the boundary it claims, and a standalone install
is durable.

## The boundary is enforced, not asserted

The package documented that it knows nothing about processes, rosters, or peer
mail, and the test that claimed to enforce it only checked import specifiers and
four words. The source had meanwhile grown a `spawnId` comparison, `Leader`
comments, and a symbol key naming `@fradser/pi-subagents` — a coupling that
compiles, passes every behavioural test, and produces a wrong board.

**What moved out of `store.ts`.** The leader-half is gone: `createDirectWork`,
`discardDirectWork`, `reclaimDirectWork`, `reopenCompletedWork`, and
`releaseTasksOf` were process operations wearing domain names. What remains is the
board and its transitions, in Task and holder vocabulary.

**The seam is declared once.** The participant registry — shape and key — moved
into `@fradser/pi-kit`, which owns no consumer and is already a dependency of both
sides. It was previously a hand-written mirror in each package, and a mirror is
exactly how that stops matching: a renamed field showed up as a silently wrong
assignment. The registry interface also gained `current(holder, incarnation?)`,
so this package asks whether a participant can act instead of reading its liveness
and incarnation itself. `@fradser/pi-subagents` answers it from the roster, which
is the only layer that knows.

**The environment binding belongs to the board.** The tool read
`PI_TEAMMATE_WORKER_NAME` — another package's private variable. It now reads
`TASK_HOLDER_ENV`, which this package exports, and `@fradser/pi-agent-teams`
spells it by import. The old coupling was a rename away from silently turning every
participant's take into a take by the main session.

**The test now enforces the claim.** `test_the_package_imports_no_coordination_concept`
bans the runtime vocabulary across every source file, `test_the_package_names_no_sibling_package`
fails if a sibling package is named at all, and
`test_the_package_owns_its_own_environment_binding` pins the binding name.

## An installed-alone board survives a restart

The package claimed durable board persistence, and only a coordinator ever wrote
the file. Installed on its own, the board lived in memory and vanished with the
process; no test covered it, because the e2e only checked one create/take/complete
loop in a single process.

`src/extension.ts` now reads the board at session start and writes it after every
change when nothing else owns the store. A coordinator that claims the store keeps
sole ownership and this package stands down, so two writers on one file is not
reachable. A present-but-unreadable board is reported through
`boardDiagnostic()` and appears in `list`, and the process does not become the
writer for a file it failed to read.

## The row is a row

`taskRowSpec` was written, exported, and never supplied: the extension passed no
`renderResult`, so every real session got Pi's default rendering and the spec was
only reachable from a test. `src/rows.ts` now binds the geometry once through
pi-kit's `bindLifecycleRenderers` and the extension attaches it, matching how
`@fradser/pi-subagents` and every other tool in this workspace paint a row. This
is why `@earendil-works/pi-tui` is now a declared `*` peer.

## One function per behaviour, in Task vocabulary

`reopenCompletedWork` and `reopenTask` were the same transition under two names
and two vocabularies; the second is gone. The runtime-only transitions were renamed
for what happened rather than for the act: `revertInFlightAttempt` became
`revertUndeliveredTake` and now names its holder, `releaseTasksOf` became
`failTasksHeldBy`. `bindTask` and `discardTask` replace the direct-work trio, and
`BoardTask.deferredMessages` is gone: a peer message is a coordination record, and
the board states what must be done rather than what was said about it.

`BoardTask.errorMessage` is removed. Nothing ever wrote it, and the changeset
moving retained evidence to `result` had already made it vestigial.

## The per-Task context budget is enforced

`withinContextBudget` was exported and never called, so the budget that stopped a
long-lived Task from growing without limit was declared and never applied.
`setTaskContext` and `updateTask` now refuse a patch that would exceed it.

`createBoundWork` in `@fradser/pi-agent-teams` composes `createTask` with
`bindTask` and rolls the creation back on refusal, which is what the removed
`createDirectWork` did. `TaskIntent.worker` is now `TaskIntent.participant`, and
operator-visible board errors say "Task board" rather than "Work snapshot", which
already said "Work" for a package whose tool is `task`.

## Publishing

`@fradser/pi-tasks` and `@fradser/pi-kit` are unchanged in their published
contract; this release only adds to them. `@fradser/pi-tasks` still needs its
first interactive publish and npm trust setup before `@fradser/pi-agent-teams`
can release, per the ordering pinned in `PUBLISH_SCOPE`.
