---
"@fradser/pi-kit": minor
---

Pi-kit gains the shared worker-runtime primitives: the file and environment mechanics that every package spawning or running inside a child Pi process needs, and that the agent-teams split into subagents / task / agent-teams needs in more than one package.

**New exports**

- `readJsonlBatch(file, byteOffset, endOffset?, maxBytes?)` — incremental read of complete JSONL records after a byte offset. A truncated or recreated file restarts from zero so callers deduplicate by record id; an unterminated trailing record is left for the next read; a record larger than the batch cap is skipped with a diagnostic so one sender cannot block a drain; a missing file is empty rather than an error.
- `appendJsonlLine(file, value, { maxBytes?, label? })` — capped append that creates a private `0700` directory and writes `0600`, refusing an oversized record instead of truncating it.
- `writeJsonAtomic(file, value)` — atomic tmp-plus-rename replacement, leaving no temporary file behind.
- `createExclusiveJsonFile(dir, name, value, { maxBytes?, label? })` — the single-writer intent race. `wx` makes the temporary file unique to the process and `linkSync` fails with `EEXIST` when the destination exists, so exactly one racer among any number of concurrent processes returns true. The name is escaped with `safeFileName` so a caller-supplied value cannot escape the directory.
- `takeJsonIntent(dir, validate, { graceMs?, label? })` — drains the lowest-named intent. Malformed records are consumed and reported so one broken file cannot block the queue, but an unparseable record younger than the publish grace is retried, because destroying an in-flight intent would leave its author waiting forever.
- `readRequiredEnvBinding(names, env?)` — an all-or-nothing environment binding. Any absent or empty required name yields `undefined`, so a partially configured child is treated as "not a worker" rather than as a worker with missing fields. An empty string counts as missing: treating it as present would yield a binding whose paths silently resolve against the current directory.
- `safeFileName(name)`, plus `DEFAULT_JSONL_BATCH_BYTES`, `DEFAULT_JSONL_RECORD_BYTES`, `DEFAULT_INTENT_BYTES`, and `DEFAULT_INTENT_PUBLISH_GRACE_MS`.
- `sessionKey(sessionFile, cwd)` — the scope key for per-session state on disk. It derives from the session file when there is one and falls back to the working directory, so two leader processes holding the same session share one directory and two sessions in one project do not. Shared because `@fradser/pi-tasks`'s board directory and `@fradser/pi-agent-teams`' runtime directory must agree on which session a directory belongs to.

**Design notes**

Diagnostics and oversize errors take a `label`, so a consumer can adopt these without changing wording its own tests and operators already read. `agent-teams` passes `"Worker event"` and `"task intent"` to reproduce its existing strings exactly.

Domain validation, path layout, and coordination authority deliberately stay with the consumer: `takeJsonIntent` receives a validation callback rather than knowing any intent shape, and attempt-bound authority is not extracted here yet because both of its consumers are not visible until the split lands.

These stay inside `src/index.ts` rather than a sibling module. That file's single-module layout is a documented loader-compatibility invariant — a zero-internal-import module resolves identically under Node's native type stripping, tsx, pi's extension loader, and tsc with any moduleResolution — so adding `src/worker-runtime.ts` and re-exporting it would reintroduce exactly the relative-specifier edge case the invariant avoids. Two tests now pin the layout.

The section imports no Pi core package and no consumer package, keeping pi-kit's dependency-free manifest honest.

Contract: `packages/kit/features/worker-runtime.feature`. Tests: `packages/kit/tests/test_worker_runtime.py`, where the single-writer race is asserted against eight real concurrent processes rather than two sequential in-process calls.

No consumer is rewired yet; this is additive, so existing behaviour is unchanged.
