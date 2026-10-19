# Goal working context

## Current work

A goal has one requirement text: its objective. The verification contract is deleted, not
repositioned. `GoalRecord` has no `verificationContract`, neither Goal tool accepts
`verification_contract`, `goalBody`/`get_goal` print the objective alone, `prompt.ts` has no
`verificationContractBlock` and no contract part in `policyKey`/`policyChars`, `check.ts` builds its
prompt from the objective, the claim and the observations, and `core.ts` compares objective, evidence
window, status and generation when it decides whether a verdict is stale. `applyRevision` moves the
objective and the evidence window together, so the observations collected under the old requirement
stay inadmissible. A legacy record keeps its objective and drops the field during normalization,
pinned by `goal_store.mts` and by `goal_completion.mts`; the reasoning is in
`.changeset/goal-objective-only.md`. `goal_native_live.py` now asserts the settled frame carries no
`Completion conditions` block, so the deletion cannot come back unnoticed. Both tools also declare their
parameters and refuse a call carrying anything else (`undeclaredKeys` in `tools.ts`, with
`CREATE_GOAL_PARAMS`/`UPDATE_GOAL_PARAMS` as the declared sets): a stale schema is refused as an
unapplied update rather than having the removed field dropped silently from a revision that lands, and
the injected-budget case in `goal_simplified.mts` now pins that refusal instead of an ignored
`token_budget`.

A `/goal <text>` request is the user's own turn, and `settled` now says so explicitly. The command
delivers the request as a custom message, so `events.ts` used to see role `custom` and never mark the
run user-initiated: a model that only recorded the objective in that run produced no tool receipt,
hit the `!performedWork` stop and paused the goal with `No effective work was recorded. Use /goal
resume to continue.` before any work ran — the exact wait the user reported. `events.ts` now treats
the `goal-procedure` message as that user turn, and `GoalScheduler.settled` takes `userInitiated` and
skips the no-work stop for it, so the request earns exactly one real run; the run after it is judged
normally, so an unproductive turn cannot hold the loop open. `goalBody` also stopped appending
`Tokens used:`, which is a record field, not a transcript line. Reasoning is in
`.changeset/goal-request-run-continuation.md`; the pinned contract is the `/goal` scenario in
`goal_simplified.mts` and the scripted native probe `goal_native_request_continuation.py`.

Automatic continuation bounds itself by the work a run does. Progress is a workspace change: only an
unseen successful `edit` or `write` earns the next run, and three consecutive runs that change
nothing pause the goal with `3 consecutive runs changed nothing observable. Use /goal resume to
continue.` The change memory lives in `GoalCore.changedWork` and `GoalScheduler.noChangeRuns`; it is
session-scoped, deliberately not cleared by a requirements revision (a re-worded objective must not
reset the loop's only bound), reset by a user resume, and a user-initiated run counts as a fresh
opportunity rather than as a no-change run. There is no budget concept at all. `GoalStatus` has no
capped state, `GoalRecord` has no `tokenBudget`, and no path stops, refuses or resumes on a number:
usage is recorded and reported, and the three-run no-change window is the loop's bound with
`maxAutonomousRuns` as the only optional ceiling. A cap-era record is tolerated rather than migrated: a
`budget_limited` status reads as `paused`, and a `tokenBudget` field is dropped by normalization, so a
goal that stopped under a cap resumes and completes normally. Docs and features no longer describe a
cap; reasoning is in `.changeset/goal-no-change-loop-bound.md`.

Goal state moved out of the working tree. It now lives at
`~/.pi/agent/goals/<project key>/<id>/record.json`, keyed by a readable Memory-style project name
plus a digest of the canonical path, and completion or clear writes the terminal `complete` status
instead of deleting the record. The change and its reasoning are in
`.changeset/goal-agent-dir-state.md`; the previous
work, the audit against the written contracts and the Pi 1.2.0 cohort move, is in
`.changeset/goal-audit-fixes.md` and `.changeset/pi-core-cohort-1-2.md`. Older narrative lives in
this file's git history.

## Audit inventory

Every `src/` module was read in full; the documented surfaces were matched to the code that
produces them. Fixed items are named in place.

- `paths.ts` — path safety runs before every write. Now owns placement too: the agent-directory
  goals root, the readable project key (Memory-style words plus a short digest of the canonical
  path, so punctuation-colliding paths never share a directory, cut to fit when a path is too long
  for one name) and the legacy project-relative paths that keep a goal stored by an earlier version
  readable. Fixed earlier: comments describing an append-only ledger, a live prose file and ledger
  appends. The placement refusal was removed with the project-relative layout it protected.
- `record.ts` — normalization, elapsed format. Fixed: an orphaned comment for a
  removed next-action field. Legacy `activePath` is preserved on read, never fabricated.
- `store.ts` — one writer, lock ownership guard, every write under the same lock. Creation seeds
  its own usage counters, so the run that created a goal is never charged to it. One record can
  now live in either layout, so the store locates the record before locking and mutates it where
  it lives; nothing is migrated and nothing is deleted. Fixed earlier: a duplicate reader, the
  misleading `readPrompt` name (now `readObjective`) and the fabricated `activePath`.
- `scheduler.ts` — arm and claim are separate; a claim is spent once and never replayed, and the
  no-change window (`NO_CHANGE_RUN_LIMIT`) is what stops a loop that keeps exploring. The delivery
  failure path had no test, so two scenarios were added. Fixed: `settled` stopped a user-initiated
  run with no tool receipt, which ended a goal in the turn that created it.
- `prompt.ts` — bounded, escaped, prefix-stable blocks. Fixed: `statusLabel` was exported with no
  reader.
- `check.ts` — tool-less child, final-line marker only. Fixed: three verdict fields that were
  never set or read, and their comment.
- `evidence.ts` — bounded, redacted observations. `research_goal` stays excluded as a retired
  tool, now with a comment. No defect.
- `core.ts` — focus and owner rules, activation handshake, usage accounting, stop guard, and the
  change memory the loop's bound reads. Fixed:
  `currentTurnSeq` and `focusedId` had no reader.
- `tools.ts` — three tools, validation, stop guard, paging. Fixed: comments describing a removed
  refusal count and a dead prose file; two exports with no external reader. Fixed: `goalBody`
  repeated `Tokens used:` on every creation, revision and status row.
- `commands.ts`, `procedure.ts`, `dashboard.ts` — one request row, one check row, one footer line.
  `/goal clear` now writes the terminal `complete` status with `stopReason: "user"` instead of
  releasing the record. No other TUI defect after the two request-row and check-row fixes.
- `events.ts` — handler order is the runtime; checkpoint messages stay hidden and are accepted
  once. Fixed: `event.prompt` was read directly, which Pi 1.2.0 types as a union — see the
  cohort section. Fixed: the `goal-procedure` request message was not recognised as the user's own
  turn, so a create-only request run stopped the goal.
- `settings.ts` — layer order, sanitizing, no refusal on save. The project override now sits next
  to that project's goals under the agent directory, and the legacy project-relative override is
  read first so an existing preference keeps applying. Fixed earlier: two path helpers with no
  external reader.
- `index.ts` — installer wiring only. No defect.
- `AGENTS.md`, `TUI.zh-CN.md`, `README.md` — every rule and trigger entry matched to its emit
  site; the sentences that had drifted were corrected.
- `features/goal.feature` — every scenario traced to a harness run, regenerated from observed
  assertions; two clause-only duplicates removed. `features/monitor-evidence.feature` is the
  readable form of eight rules executed under the `Goal monitor evidence` names.
- `goal_native_frames.py`, `goal_native_live.py`, `goal_native_tui.py` — shared decoder, frame
  assertions, process-group teardown. No defect.
- `isolated-agent.mts` — every harness that builds a store or runs the extension redirects
  `PI_CODING_AGENT_DIR` to a throwaway directory first, because goal state now lives there. The
  native probes read records by globbing `<agent>/goals/*/*/record.json` instead of rebuilding the
  project key.
- `goal_native_completion.py` — the scripted full-path acceptance. No defect.
- `goal_native_request_row.py` — the composed-screen proof of the request row. No defect.
- `goal_native_request_continuation.py` — the composed-screen proof that a create-only `/goal`
  request keeps pursuing and runs its continuation. No defect.
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
- Native: `goal_native_completion.py`, `goal_native_request_row.py`, `goal_native_revision.py`
  and `goal_native_request_continuation.py` pass on the workspace Pi and inside the container. The
  last one is the reproduction of the reported wait: reverting the `events.ts` recognition makes it
  fail with `No effective work was recorded. Use /goal resume to continue.` on a real CLI screen,
  and restoring the line makes it pass.
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

## Independent review of the state move

A fresh agent read the diff and the changed files, ran the suite, the two type checks and three
scratch probes, and found seven issues. Fixed here, with the same review's sound verdicts kept
below them.

- Kept records were still writable by accounting paths that guard on existence, not status: a late
  charge could revive a completed goal. Completion is now terminal in the store
  itself — a write may only keep `complete` — and the accounting writers (`chargeUsage`, the check
  charge, the `message_end` attribution) skip a finished goal instead of being refused. A check
  that returns after another session completed the goal is reported stale, not charged.
- `projectScopeKey` resolved only the whole path, so a path whose directory disappeared fell back to
  a lexical spelling and the key changed under a stored goal. The deepest existing ancestor is
  resolved now and the rest appended. Boundary: a project reached through a symbolic link that is
  later removed keeps the spelling it is passed as; a session started there runs in the resolved
  directory, so both sides use the resolved key.
- `safeGoalId("..")` returned `..`, so a dot-only id addressed a file above the project's goals
  root. Writes were already refused; reads are now impossible too, and `readRecordFile` checks
  containment in the goal root as well as the symlink walk.
- `readPool` marked an id seen before reading it, so an unreadable current record hid a readable
  legacy one; `locate` accepted any file while `readGoal` demanded a readable one, so a mutation
  could lock the wrong layout. Both now decide on the readable record. `focus` refuses a completed
  goal, which its own `goal` getter already treated as absent.
- Docs that claimed nothing is ever written into the working tree now say a new goal is not.

Sound per the same review: stale-lock takeover and the displaced-writer guard; project separation by
the digest (only a 32-bit collision remains); separator traversal and symlink rejection; readers of a
retained completed record (`core.goal`, restore, tool surface, dashboard, scheduler); harness
isolation; and the removed placement refusal, which nests nothing because the project root no
longer contributes path segments. A mixed-version window is recorded in the changeset.
