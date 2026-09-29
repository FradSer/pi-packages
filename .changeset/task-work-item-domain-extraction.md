---
"@fradser/pi-agent-teams": patch
---

The task board domain moved out to a new workspace package, `@fradser/pi-tasks`, which now owns the `task` tool and the board container outright.

This step alone changed no behaviour. The tool surface changed later, in the same 1.0.0 release: see `three-package-split.md`. `/agent-teams` is unchanged.

**What moved**

`@fradser/pi-tasks` now owns the data model (`BoardTask`, `TaskStatus`, `TaskIntent`, `WORK_RUNTIME_VERSION`), the pure graph and resource rules (`taskIdFromSubject`, `normalizeResources`, `canonicalDependency`, `canonicalDependencies`, `hasDependencyCycle`, `resourcesConflict`), and durable board persistence (`tasksRoot`, `boardDir`, `boardFilePath`, `claimsDir`, `submissionsDir`, `readBoardFile`, `writeBoardFile`, `createTaskIntent`, `takeTaskIntent`, `INTENT_PUBLISH_GRACE_MS`).

What stays here is the stateful half: the in-memory board container and its transitions in `state.ts`, the roster, peer mail, the verification gate, and both `work` tool slices. Those need the `ChildHost` / `WorkStore` seam before they can move.

**Two duplications removed**

`worker.ts` carried its own private copy of `resourcesConflict` with a wider signature than the leader's. Both now call the one implementation in `@fradser/pi-tasks`, so a worker and the leader cannot disagree about whether two leases conflict.

`sessionKey` moved to `@fradser/pi-kit`, because the board directory and the teammate runtime directory are scoped by the same key and two packages must agree on which session a directory belongs to.

**Deliberate changes**

- Operator-visible board errors now say `Work snapshot` instead of `Agent Teams Work snapshot`. `@fradser/pi-tasks` owns the file and may be installed without the team runtime, so naming Agent Teams would be wrong. `test_snapshot_version.py` was updated to the corrected wording; the version numbers and the refusal to treat an unreadable board as empty are unchanged.
- `TaskStatus` became a plain TypeScript union. The previous TypeBox construction existed only to be converted straight back into a type with `Static<>`, and no tool parameter ever used the runtime value. This keeps `@fradser/pi-tasks` free of a typebox peer.
- `WORK_RUNTIME_VERSION` keeps the value `2`, inherited from `TEAM_RUNTIME_VERSION`, so boards written before the extraction still load. `TEAM_RUNTIME_VERSION` remains for this package's own runtime snapshot; the two files now version independently, which is correct since their schemas are independent.
- `canonicalDependencies` and `hasDependencyCycle` became public. They were private to `state.ts`; a board-only consumer of `@fradser/pi-tasks` needs the same cycle refusal the leader applies at creation.

**Publishing order**

`@fradser/pi-tasks` must reach the registry before this package can publish, because the packed manifest now depends on it at an exact version. It is listed after `@fradser/pi-subagents` and before `@fradser/pi-agent-teams` in `PUBLISH_SCOPE`, and `test_publish_allowlist_orders_split_layers_before_their_consumer` pins that ordering. Its first release needs the interactive bootstrap and npm trust setup, not a Changesets bump.
