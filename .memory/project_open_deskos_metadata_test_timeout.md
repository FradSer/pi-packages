---
name: "project_open_deskos_metadata_test_timeout.md"
description: "pi-packages packages/open-deskos: the machine-session-discovery case 'metadata file and workspace traversal budgets…' writes MAX_METADATA_FILES (2048) + MAX_WORKSPACES (256) fixtures sequentially, failed at bun's 5s default under load ([5000.16ms], 2 of 3 runs) but passed alone; it now sets node:test { timeout: 20000 }, after which three full non-CL runs passed 169/0."
type: project
---
In `packages/open-deskos/tests/machine-session-discovery.test.mjs`, the case `metadata file and workspace traversal budgets stop reads before unbounded inventories` loops over `[[MAX_METADATA_FILES, true], [MAX_WORKSPACES, false]]` and writes `limit + 3` JSON fixtures sequentially via `put` (one shared workspace `w` for the file limit, one `w<index>` per file for the workspace limit) before asserting `checked === limit` and `sessions.length === 64`.

`packages/open-deskos/src/discovery.ts` exports `MAX_METADATA_FILES = 2048` and `MAX_WORKSPACES = 256`, so one pass of that case creates about 2,300 fixture files before `scanDirectorySessions` is called.

Observed 2026-11-04 under load: `(fail) metadata file and workspace traversal budgets stop reads before unbounded inventories [5000.16ms]` in two of three consecutive full non-CL runs, while that same test file run alone passed 3/3 (`23 pass`, `0 fail`).

The case now passes the node:test options object `{ timeout: 20000 }` as its second argument; bun `v1.4.1-canary.1` honored an explicit timeout option in a probe that passed after sleeping 6001.74ms, past the 5s default.

After the change, three consecutive non-CL runs of `bun test packages/impeccable/tests packages/open-deskos/tests packages/utils/tests/live-sessions*.test.ts` each reported `169 pass` / `0 fail`.

Why: the failing work is the sequential fixture volume against a ~5000ms runner default, while the case's own checks stayed `checked === limit` and `sessions.length === 64`. How to apply: when a bulk-fixture case in this repo times out near 5000ms inside a loaded suite but passes in isolation, give that case a per-test `{ timeout: ... }` option instead of relaxing its traversal assertions.