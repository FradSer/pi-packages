# Goal working context

## Current work

Audit of `packages/goal` against its own written contracts, and the fixes it produced.
The earlier work in this thread (the visible `[goal] requesting` row and the one-line
check row) is recorded in `.changeset/goal-request-row-visibility.md`.

## Audit inventory

Each entry names what was read and the verdict. Every `src/` module was read in full; the
documented surfaces were cross-checked against every emit and write site.

- `paths.ts` — path safety (`isInside`, `safeGoalId`, the placement refusal) is called
  before every write. Fixed: the module comment described an append-only ledger that no
  longer exists, `goalPromptPath` described a live prose file, and the placement refusal
  still spoke of ledger appends.
- `record.ts` — normalization drops unsafe values to safe defaults, budget helpers, elapsed
  format. Fixed: an orphaned comment documented a removed next-action field. The legacy
  `activePath` field is preserved on read and is no longer fabricated.
- `store.ts` — one writer, lock ownership guard, stale takeover, release under the same lock,
  legacy files untouched. Fixed: `readGoalFromDisk` was byte-identical to `readGoal` under a
  comment claiming a distinction; `readPrompt` returned the record objective, not a prose
  file, and is now `readObjective`.
- `scheduler.ts` — arm and claim are separate, identity and generation are re-checked under
  the lock, a claim is spent once and never replayed. No defect. The delivery-failure path
  had no test, so two scenarios were added.
- `prompt.ts` — bounded and escaped blocks, stable policy with volatile counters, cache
  accounting. Fixed: `statusLabel` was exported with no reader.
- `check.ts` — tool-less child, final-line marker only, every truncation stated. Fixed:
  `attempts`, `advice` and `stopped` were never set or read, and one comment described
  attempt accounting that the retired refusal-count design owned.
- `evidence.ts` — bounded and redacted observations, edit projection, monitor and review
  attribution. `research_goal` stays excluded as a retired tool, now with a comment. No defect.
- `core.ts` — focus and owner rules, the activation handshake, budget accounting, the turn
  stop guard. Fixed: `currentTurnSeq` and `focusedId` had no reader.
- `tools.ts` — three tools, argument validation, the stop guard, paging. Fixed: the
  `applyRevision` comment and the revision guard comment described a removed refusal
  count and a dead prose file; two exports had no external reader.
- `commands.ts` — management verbs, request queueing, activation only on accepted delivery.
  No defect after the earlier row fix.
- `procedure.ts` — one row per request, gated on renderer availability, body model-only. No
  defect after the earlier row fix.
- `events.ts` — handler order is the runtime; checkpoint messages stay hidden and are accepted
  once; usage is attributed to the goal that ran. No defect.
- `dashboard.ts` — one line below the editor, no tag, widget reused across refreshes. No
  defect after the earlier check-row fix.
- `settings.ts` — layer order, per-field sanitizing, environment last, refusal on save. Fixed:
  two path helpers were exported with no external reader.
- `index.ts` — installer wiring only. No defect.
- `AGENTS.md`, `TUI.zh-CN.md`, `README.md` — every rule and trigger table entry was matched to
  the code that produces it. No open defect; three sentences were corrected across this thread.
- `features/goal.feature` — every scenario traced to a harness run; new scenarios were
  regenerated from observed assertions. Two clause-only duplicates were removed: the same
  rules are executed and recorded under `Goal native sessions: /goal hands the model a seed
  instead of creating one` and `Simplified thread Goal lifecycle: Given a loaded Goal
  extension When tools register Then only three Goal tools exist`.
- `features/monitor-evidence.feature` — the readable form of eight monitor-evidence rules.
  Their clauses carry no predicates and no harness runs them by name; every rule is executed
  and recorded under its own scenario name in the `Goal monitor evidence` block of
  `goal.feature`, and the file now says so at its head.
- `goal_native_frames.py`, `goal_native_live.py`, `goal_native_tui.py` — the shared terminal
  decoder, the frame assertions (`assert_progress_frame`, `assert_request_frame`,
  `assert_settled_frame`) and the process-group teardown. No defect.
- `goal_native_completion.py` — the scripted full-path acceptance: completion, refusal, empty,
  error, blocked, long-requirement and cancellation cases. No defect.
- `goal_native_request_row.py` — the composed-screen proof that one `/goal <request>` paints
  one `[goal] requesting` row with the typed words and no request body. No defect.
- `goal_native_revision.py` — asserts the current revision contract: one goal revised in
  place, contract kept, pursuing again, no archive and no ledger. No defect.
- `goal_native_rejection.mts` — the SDK-level preflight harness: a refused completion while a
  turn is settling must not activate an unrelated paused revision. It runs the real agent
  session and asserts `GOAL_NATIVE_REJECTION_OK`; it records no observations, so the contract
  guard skips it. No defect. `test_goal.py` now runs it, so it cannot rot unnoticed.
- retired probe — `goal_native_supersede.py` failed and asserted removed behaviour (an archive,
  `goal_cleared`/`superseded` ledger events, and `research.md`), and its fixture
  `goal_offline_fixture.ts` was a two-line re-export of the completion fixture, so the environment knobs the probe set had no effect. Those two files
  were removed; `goal_native_rejection.mts` above is a different, live harness.

## Review findings

An independent review found no blocking defect. Its non-blocking items are closed here.

- Deadness and behaviour-preservation claims were reproduced by `git grep` across the
  repository, and no missed caller was found. Its note that the sweep had not covered
  in-module-only type exports is accurate: the finding was about helper functions.
- The `nothing was replayed` assertion was vacuous, because the fixture threw before
  recording. Every checkpoint attempt is now counted before the refusal, and the test
  asserts exactly one attempt. Fixed sleeps became a bounded poll.
- The revision probe asserted a vacuous `no checking` and read its record before the pursuit
  assertion. It now rejects the real activity line and re-reads the record after the pursuit
  assertion, so the state under test is the state the screen reported.
- Further stale sentences were fixed in `tools.ts`, `paths.ts`, the labels of
  `goal_completion.mts` and `goal_store.mts`, and three scenario names.
- The request-row replay residual was listed in AGENTS.md but missing here; it is named
  under accepted limitations below.

## Second review

A second, narrow review then found one blocking inventory gap and four non-blocking items.
All are closed.

- Blocking: `features/monitor-evidence.feature` had no verdict, and the enforcing test could
  not see it because it hardcoded one file name. The inventory now names it, the hygiene test
  globs every `features/*.feature`, and the missing verdict was the failure that was
  reproduced before the fix.
- The native-probe section read as one broken sentence after the truncation repair. It is now
  one bullet per probe.
- The inventory check tested for a name anywhere in the document. It still does, but it now
  covers every feature file, and the guard refuses a short title that appears twice.
- The stated test count was stale by one; the suite printed 32 at that point and prints 33 now.
- Receipts: the dead-symbol ledger was a `/tmp` script. Its durable form is in the
  repository: `test_no_export_lacks_a_reader`, `test_removed_dead_surface_stays_removed` and
  the type check cover the removals on every run, and the ledger below records the
  HEAD-versus-now counts. That pin now covers the removed class members and interface
  fields too, not only the four names it started with: re-adding `focusedId` fails it with
  `/focusedId/ was removed as dead surface and is present again`, and `core.ts` came back
  byte-identical (SHA256 `7a91eaff...`). The HEAD tree was not re-run: the baseline of this audit printed
  `31 passed` before the fixes and the tree prints `32 passed` after them, the added test
  being the inventory guard.

Dead-symbol ledger: one scope for every symbol — `src`, `tests` and `features` — and the same
command over HEAD and the working tree. `readGoalFromDisk` 28 to 1, `readPrompt` 7 to 1 while
`readObjective` goes 0 to 7, `currentTurnSeq` 1 to 1, `focusedId` 1 to 1, exported
`statusLabel` 1 to 0, `void statusLabel` 1 to 0, `void repoRoot` 1 to 0, seven further helper
exports 1 to 0 each, `attempts`/`advice`/`stopped` 1 to 0 each, `goal.activePath =` 2 to 1.
A count that does not reach zero has exactly one remaining occurrence and it is not a reader:
the pin names `readGoalFromDisk`, `readPrompt`, `currentTurnSeq` and `focusedId` in order to
forbid their return, and `record.ts` keeps the legacy `activePath` preservation line.

## Contract-integrity guard

Every harness that records observations — all of them except `goal_native_rejection.mts` and the `goal_race_worker.mts` worker — now verifies
every `features/*.feature` file against the assertions that run actually observed: each
observed scenario must exist in some feature file with the same predicates in the same order
and whitespace collapsed, and a short title may not appear in two files. `test_goal.py` does
this inside the existing harness run, so it costs nothing extra. A harness whose source uses the
observer must produce at least one recorded scenario, so the guard cannot pass vacuously. It
has teeth: deleting one scenario block from a contract file fails the suite with `is in no
feature file`, and the file came back byte-identical; the receipt recorded here is the hash of
the file as it stands now, SHA256 `be0df346...`, so it can be checked against the artifact.

`goal_live_context.mts` was converted to record its three scenarios. That bound two
clause-only scenarios in `goal.feature` to real assertions and added one scenario for the
custom-startup contract.

The guard exists because a hand-maintained copy was not enough. During this audit the file
silently lost its tail: it is 130 KB, the file reader caps at 50 KB, and a read-modify-write
round trip rewrote only the prefix. The file was restored from git, every intended edit was
replayed from the recorded observations, and the guard now catches exactly that class of loss.

## Receipts

One command produced the receipts for every class of fix, and its output is in the thread:
the dead-surface pin reverted (pre-fix run 1, `was removed as dead surface and is present
again`), restored (`core.ts` SHA256 `7a91eaff...`) and re-run (1 passed); the contract guard
reverted (pre-fix run 1, `is in no feature file`), restored (`goal.feature` SHA256
`be0df346...`) and re-run (13 passed then; `test_goal.py` collects 14 now); the symbol counts over HEAD and the working tree; the
suite and every check; and the contract guard, which runs on every harness run — 0 missing and
0 drifted is the suite passing — over the 173 scenarios the contract file now holds. The suite
is 33 tests because `goal_native_rejection.mts` is now driven by one of them.

## Verification

- `python3 -m pytest packages/goal/tests/ -q` -> 33 passed; the added tests are the inventory
  guard and the SDK-level preflight harness, and the contract-integrity check runs inside every
  harness test.
- `pnpm exec tsc --noEmit -p packages/goal/tsconfig.tests.json`, `pnpm typecheck`,
  `pnpm --dir packages/goal pack --dry-run` and `pnpm pack:check` (18 manifests) pass.
- Native: `goal_native_completion.py`, `goal_native_request_row.py` and
  `goal_native_revision.py` pass. The revision probe reproduces the whole route: create,
  stop for lack of work, `/goal <request>`, revise in place, pursue again.
- That probe needed a real fix of its own sampling: the authorised state lasts only while
  that run continues, so the probe reads the record between single terminal reads. The
  transition was confirmed with temporary instrumentation, which was removed.

## Accepted limitations

- A contended write locks the event loop: `Atomics.wait` in 20 ms steps, bounded by
  `LOCK_TIMEOUT_MS` (2 s). The store, the scheduler and the tool executors are synchronous by
  design, so removing the block is a restructure, not a fix. It triggers only when another
  writer holds the lock.
- Nothing covers the retired replacement design any more (a new goal absorbing a completed or
  capped one, with archive and research). It is not a contract, so no test asserts it.
- A session replayed without this renderer prints the whole request body through Pi's default
  custom-message rendering, because Pi persists `display`. The send-time check cannot cover
  replay; AGENTS.md states the residual and this audit leaves it accepted.
- An attempt to measure which branches the suite never runs was abandoned: the function names
  V8 reported could not be aligned with the TypeScript sources under tsx, so no finding rests
  on coverage numbers. Every dead-code finding rests on call sites and greps.
- Clause-only feature scenarios carry no predicates, so the guard cannot see them drift; the
  rules they state are guarded under the scenario names that do carry predicates.

## Commits and review

- `366d812b` `fix(goal): audit package against contracts` — the audit change.
- `3d03b7c9` `refactor(goal): clean unused variables in tests` — the Code Terrier finding below.
- Code Terrier round 1 (review `58abc864-af8d-4d44-aec8-b62e9757db76` of `HEAD~1...HEAD`) reported
  one low-severity finding: a stored-and-never-read `scheduler` local in
  `tests/goal_native_revision.py`. It was real and is fixed; the same scan found a second one
  (`module` in `tests/test_goal_hygiene.py`), also fixed. An AST scan of the goal tests now
  reports no stored-and-never-read local, the suite is green, and the revision probe passes.
- The continuation of that review was refused twice with HTTP 409:
  "review 58abc864-af8d-4d44-aec8-b62e9757db76 cannot run another round in its own session yet.
  No second review was submitted." The skill's rule is to report the refusal and stop, because a
  new submission for the same evidence is what the refusal exists to prevent, so no second
  review was submitted. The corrections above therefore rest on my own verification, not on a
  reviewed round.

## Closeout

Six review rounds ran. The last one states plainly that no blocking issue remains and that its
four remaining wording leftovers were fixed afterwards; the completion check accepted the
revised objective against the receipts above.

- No publish happened. `~/.pi/agent/settings.json` loads this package from the repository, so
  a Pi reload picks the fixes up.
