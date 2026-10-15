# Goal working context

## Current work

Audit of `packages/goal` against its own written contracts and the fixes it produced. The two
TUI fixes it started from are recorded in `.changeset/goal-request-row-visibility.md`; the
audit itself, the contract guard and the Pi cohort move are in `.changeset/goal-audit-fixes.md`
and `.changeset/pi-core-cohort-1-2.md`. Older narrative lives in this file's git history.

## Audit inventory

Every `src/` module was read in full; the documented surfaces were matched to the code that
produces them. Fixed items are named in place.

- `paths.ts` — path safety runs before every write. Fixed: comments describing an append-only
  ledger, a live prose file and ledger appends.
- `record.ts` — normalization, budget helpers, elapsed format. Fixed: an orphaned comment for a
  removed next-action field. Legacy `activePath` is preserved on read, never fabricated.
- `store.ts` — one writer, lock ownership guard, release under the same lock. Fixed: a duplicate
  reader, the misleading `readPrompt` name (now `readObjective`) and the fabricated `activePath`.
- `scheduler.ts` — arm and claim are separate; a claim is spent once and never replayed. No
  defect; the delivery-failure path had no test, so two scenarios were added.
- `prompt.ts` — bounded, escaped, prefix-stable blocks. Fixed: `statusLabel` was exported with no
  reader.
- `check.ts` — tool-less child, final-line marker only. Fixed: three verdict fields that were
  never set or read, and their comment.
- `evidence.ts` — bounded, redacted observations. `research_goal` stays excluded as a retired
  tool, now with a comment. No defect.
- `core.ts` — focus and owner rules, activation handshake, budget accounting, stop guard. Fixed:
  `currentTurnSeq` and `focusedId` had no reader.
- `tools.ts` — three tools, validation, stop guard, paging. Fixed: comments describing a removed
  refusal count and a dead prose file; two exports with no external reader.
- `commands.ts`, `procedure.ts`, `dashboard.ts` — one request row, one check row, one footer line.
  No defect after the two TUI fixes above.
- `events.ts` — handler order is the runtime; checkpoint messages stay hidden and are accepted
  once. Fixed: `event.prompt` was read directly, which Pi 1.2.0 types as a union — see the
  cohort section.
- `settings.ts` — layer order, sanitizing, refusal on save. Fixed: two path helpers with no
  external reader.
- `index.ts` — installer wiring only. No defect.
- `AGENTS.md`, `TUI.zh-CN.md`, `README.md` — every rule and trigger entry matched to its emit
  site; the sentences that had drifted were corrected.
- `features/goal.feature` — every scenario traced to a harness run, regenerated from observed
  assertions; two clause-only duplicates removed. `features/monitor-evidence.feature` is the
  readable form of eight rules executed under the `Goal monitor evidence` names.
- `goal_native_frames.py`, `goal_native_live.py`, `goal_native_tui.py` — shared decoder, frame
  assertions, process-group teardown. No defect.
- `goal_native_completion.py` — the scripted full-path acceptance. No defect.
- `goal_native_request_row.py` — the composed-screen proof of the request row. No defect.
- `goal_native_revision.py` — the revision contract, replacing a stale probe that asserted
  removed archive, ledger and research behaviour. No defect.
- `goal_native_rejection.mts` — SDK-level preflight refusal; now driven by `test_goal.py`. No
  defect.

## Receipts

One command produced the receipts for every class of fix: the dead-surface pin reverted (pre-fix
run 1, `was removed as dead surface and is present again`), restored (`core.ts` SHA256
`7a91eaff...`) and re-run (1 passed); the contract guard reverted (pre-fix run 1, `is in no
feature file`), restored (`goal.feature` SHA256 `be0df346...`) and re-run; the symbol counts over
HEAD and the working tree; the suite and every check; and the guard, which runs inside every
harness run, so 0 missing and 0 drifted is the suite passing over the 173 scenarios the contract
file holds.

Dead-symbol ledger, one scope for every symbol (`src`, `tests`, `features`) and the same command
over HEAD and the working tree: `readGoalFromDisk` 28 to 1, `readPrompt` 7 to 1 while
`readObjective` goes 0 to 7, `currentTurnSeq` 1 to 1, `focusedId` 1 to 1, exported `statusLabel`
1 to 0, `void statusLabel` 1 to 0, `void repoRoot` 1 to 0, seven further helper exports 1 to 0
each, `attempts`/`advice`/`stopped` 1 to 0 each, `goal.activePath =` 2 to 1. A count that does
not reach zero has exactly one remaining occurrence and it is the pin that forbids the return, or
the legacy `activePath` preservation line.

## Contract-integrity guard

Every harness that records observations — all of them except `goal_native_rejection.mts` and the
`goal_race_worker.mts` worker — verifies each observed scenario against every `features/*.feature`
file: same predicates, same order, whitespace collapsed, unique short titles, and a recording
harness that wrote nothing fails. It has teeth: deleting one scenario block fails the suite with
`is in no feature file`. It exists because a hand-maintained copy silently lost its tail: the file
is 130 KB while the file reader caps at 50 KB, so one read-modify-write rewrote only the prefix;
the file was restored from git and replayed from recorded observations.

## Host cohort moved to Pi 1.2.0

- The host gate validated against Pi 1.0.0, so it could not see 1.2.0 API changes; the Docker
  acceptance, which resolves the latest Pi, exposed one here: `src/events.ts` read `event.prompt`
  directly, and Pi 1.2.0 types `before_agent_start` as a union discriminated by run kind
  (`error TS2339`, observed in the container). The handler now tests for the prompt, which is
  correct against both shapes.
- Every `@earendil-works/pi-*` development requirement in the workspace is `^1.2.0`, the lockfile
  was refreshed, and the cohort test, its feature and the root README record 1.2.0. Peers stay
  `*` and no Pi package became a runtime dependency.
- Four further pins of the version were replaced by a derivation from the root requirement:
  `tests/e2e/support/harness.py`, `packages/agent-teams/tests/test_native_disk_identity.py`,
  `packages/matt-pocock/tests/test_pi_v1_resolution.py`,
  `packages/subagents/tests/native_support.py`.
- Two more defects the bump exposed, both fixed: the prompt-budget harness handed the measured
  hooks an event without `systemPromptOptions`, which the monitor guard rejects; and the
  agent-management type fixture allowed its type check only 60 seconds, which the repository type
  surface now exceeds under load.
- Reported, not changed: the continual-learning paid-study harnesses pin the Pi baseline on
  purpose to keep their cohorts comparable (`live_continuous_project_learning.py`,
  `live_harness_first_run.py`, `live_harness_repair_diagnostic.py`, `live_memory_citations.py`,
  `live_memory_maintenance.py`, `live_memory_retrieval.py`, `docker_experiment.py`). Moving them
  is a study-protocol decision for that package's owner.

## Docker isolation acceptance

`sh packages/goal/tests/goal_docker.sh` packs this tree and runs the whole goal acceptance in a
container with nothing else loaded: `node:24-bookworm-slim`, Pi resolved to the latest at run
time (1.2.0 in the recorded run), `PI_VERSION` to pin deliberately, only the Goal package in the
agent settings, `pi list` captured to prove it, the packed tarball hashes in the receipt, and the
package gate (`pytest packages/goal/tests/`) plus every PTY probe. Verified `GOAL_DOCKER_OK` with
33 passed and all probes green; kit stays a library dependency and is never a loaded package.

## Verification

- `python3 -m pytest packages/goal/tests/ -q` -> 33 passed; with `tests/test_pi_core_cohort.py`,
  35 passed.
- `pnpm exec tsc --noEmit -p packages/goal/tsconfig.tests.json`, `pnpm typecheck` (0 errors),
  `pnpm --dir packages/goal pack --dry-run` and `pnpm pack:check` (18 manifests) pass.
- Native: `goal_native_completion.py`, `goal_native_request_row.py` and `goal_native_revision.py`
  pass on the workspace Pi and inside the container.
- The repository suite was run in two halves for the cohort change: 2318 passed and 1 skipped,
  then 1602 passed with two load-sensitive native tests, both of which pass in isolation or after
  the timeout fix above.

## Accepted limitations

- A contended write locks the event loop: `Atomics.wait` in 20 ms steps, bounded by
  `LOCK_TIMEOUT_MS` (2 s). The store, scheduler and tool executors are synchronous by design, so
  removing the block is a restructure, not a fix.
- Nothing covers the retired replacement design any more (a new goal absorbing a completed or
  capped one, with archive and research). It is not a contract, so no test asserts it.
- A session replayed without this renderer prints the whole request body through Pi's default
  custom-message rendering, because Pi persists `display`; the send-time check cannot cover
  replay, and AGENTS.md states the residual.
- Clause-only feature scenarios carry no predicates, so the guard cannot see them drift; the
  rules they state are guarded under the scenario names that do carry predicates.
- V8 coverage could not be aligned with these sources under tsx, so no finding rests on coverage
  numbers; every dead-code finding rests on call sites and greps.

## Commits and review

Audit and test infrastructure: `366d812b`, `3d03b7c9`, `8f5ccb2a`, `1eb39a75`, `700eee80`,
`34187d40`, `213dcc63`. Code Terrier review `58abc864...` found one low-severity dead local, which
is fixed, and a continuation of that session was refused three times (HTTP 409); a fresh review of
the full change, `19021f95...`, finished with no findings. The cohort move is this commit.
