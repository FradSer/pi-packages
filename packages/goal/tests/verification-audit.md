# Goal audit verification, second round

Runtime fingerprint: `ed1a58fbafb5434933e5bd58d71a67c1e0c0556a113eb176b445ef8a78fb2702`.
Algorithm: SHA256 over a sorted listing of `packages/goal/src/*.ts`, one line per file as SHA256, two spaces,
repo-relative path, newline. `packages/goal` is tracked (48 files); `git diff HEAD -- packages/goal` is the real
baseline.

Two independent scoped reviews ran against the first candidate. The first returned Standards FAIL, Spec PASS.
The second returned REWORK on both axes and found two production defects the first round missed. Both are fixed
here with RED regressions, together with the cleanup and the three weakened hygiene tests.

## First-round corrections

1. Ghost import. `tests/goal_store.mts` imported `taskIndex` from `src/record.ts`, which never exported it. Root
   cause: `tsconfig.json` included only `src/**/*.ts`, so no harness was type checked, and tsx erases an unused
   named import at runtime. Added `tsconfig.tests.json` covering `src` and `tests` plus a regression; its first
   run reported 14 further harness type defects, all fixed.
2. Dead settings. `autoSelectSingleGoal` survived removal of automatic adoption; `thinkingLevel` and its
   orphaned `thinkingLevels()` survived the single-command surface. Removed. Older settings files carrying
   `autoSelectSingleGoal` remain harmless, asserted in the session harness.
3. Restored test semantics. `const claimed = scheduler.claim()` in the scheduling harness had been deleted as
   apparently unused, but it consumes one authorized dispatch. Restored with a comment.
4. Zero-reader exports removed: `MAX_PROMPT_FRAGMENT_CHARS`, `goalPrompt`, `staleCheckpointPrompt`,
   `unfocusedPrompt`, `writeGlobalSettings`, `removeProjectSettings`, `projectHistory`.

## Second-round corrections

5. `goal_claimed` never reached the ledger. `scheduler.ts` built the `ledger` array inline in the options object
   passed to `host.apply`; that object literal is evaluated before `mutate` runs, so `authorization` was still
   undefined and every successful claim supplied `[]`. `store.apply` reads `spec.ledger` only after `mutate`
   returns, so the fix collects the event inside `mutate` into an array declared beforehand. Regression: "a
   successful claim is recorded in the ledger".
6. A `null` record crashed the pool scan. `store.readGoal` read `.version` off the parsed value without
   confirming it was an object, so one `null` record threw a `TypeError` and hid every valid sibling.
   Regression: "one malformed record does not hide the valid ones".
7. The cross-process race barrier never synchronized. The parent passed epoch milliseconds as a string and the
   worker called `Date.parse` on it, which is `NaN`, so `Date.now() < NaN` was false and the writers overlapped
   only by accident. The worker now parses a number and throws on an unusable value rather than silently
   disabling the barrier.
8. Three hygiene regressions were weaker than they claimed and are rewritten: the export scan now covers
   `export {}` barrels and `export type/interface`, ignores comments and prose as readers, and fails when it
   scans nothing; the command scan reads every `src/*.ts`; the import scan accepts single quotes and covers the
   `.ts` fixtures; the settings scan requires a reader that names the setting on a settings object. A separate
   regression proves every named export of `src/index.ts` is reachable from the package entry.
9. Dead surface removed after the strengthened scan: `CheckpointDetails`, `PersistedGoalRecord`,
   `GoalLedgerEventType`, `checkpointTriggerPrompt`, `escapeXmlAttribute`, `CHECKPOINT_TRIGGER_MAX_CHARS`, the
   `budgetReached`/`GOAL_SECTIONS`/`encodeCursor` barrels, thirteen named exports of `src/index.ts` the package
   entry could not import, `openGoals`, `unfocus`, `markInterrupted`, `emptyGoal`, and two `void` reads that
   kept unused names alive.
10. Docs corrected: the duplicated `scheduler.ts` comment, two JSDoc blocks on one `store.ts` method, the
    `events.ts` header that credited notification-only `agent_settled`, the `paths.ts` docstring that described
    revision calculation, and the two same-named `MAX_OBJECTIVE_CHARS` constants, now `MAX_OBJECTIVE_CHARS`
    (storage) and `MAX_PROMPT_OBJECTIVE_CHARS` (prompt block).
11. One reviewer finding was dismissed with evidence: `ledger.ts` `?? "pool"` looked unreachable, but
    `goal_unfocused` carries `goalId: string | null`, so the pool file is reachable and the fallback stays.

## RED before GREEN, and mutation evidence

Every fix above has an observed RED regression before it and a green suite after. Reproduced mutations on the
real tree, each restored byte-for-byte with an identical source fingerprint:

- null-record guard removed: RED
- claim-ledger push removed: RED
- dead `autoSelectSingleGoal` reintroduced: RED
- unreachable `export type { GoalRecord }` reintroduced: RED
- dead barrel `export { budgetReached }` reintroduced: RED
- single-quoted ghost import added to `goal_thread.mts`: RED

The last three were run after a hole in the owner's own export scan was found this way. Every mutation restored
its file byte-for-byte; the runtime fingerprint was identical before and after each run.

Earlier-round mutations (dead settings, ghost import, removed claim line) are in `red-evidence-current.md`.
An earlier attempt at mutation evidence mutated a temporary copy while pointing the regression at repository
tests; those tests resolve their own package path, so a copy is invisible to them and that claim was withdrawn.

12. Round-three self-found defects. After dispatching the round-three review, reading `src/index.ts` directly
    found `export type { GoalRecord } from "./record.ts";` unreachable from the package entry for the same reason
    as the other twelve, and the owner-written entry-surface regression had missed it because its regex
    `^export\s*\{` does not match `export type {`. The line was removed and the regex now accepts the optional
    `type` form. Reintroducing it makes the regression RED.
13. A third hole in the export scan, found by mutation rather than by reading. Reintroducing
    `export { budgetReached };` in `prompt.ts` stayed green: the scan counted the name's occurrences anywhere,
    and `scheduler.ts` and `core.ts` import `budgetReached` from `record.ts`, so a barrel with no consumer looked
    alive. Barrel re-exports are now judged only by a consumer importing the name *from that module*. This is
    the third time an owner-written check passed while a real defect survived, and each was found by mutating the
    tree rather than by trusting the check.

## Round five: P2, P3, hygiene and cleanup all fixed

17. P2, `tools.ts` history section, fixed. `get_goal(section="history")` computed a page and dropped its
    `page.cursor`, so the events past the first page were unreachable through the tool's own documented input. The
    result now states the continuation, or that history ended. Regression: "a long history hands back the cursor
    that continues it", which drives the registered tool directly and asserts on its returned `content[0].text`.
    Two earlier attempts were reverted rather than left half-wired, because the session harness never routes tool
    output to `outcome.prompt` and a second attempt corrupted the trailing async IIFE. A history only pages past
    pi-kit's 256 KiB batch bound, so the seed is 1,200 wide events.
18. P3, `check.ts` parser with `core.ts` refusal accounting, fixed. A nonempty answer carrying no verdict marker
    parsed as a plain refusal, so three unparseable answers consumed the whole three-attempt allowance and paused
    a goal that had never been judged. `parseCheckVerdict` now reports `valid`, true only when the final line is
    MET or NOT MET, and `runCompletionCheck` turns an invalid answer into an error, which the accounting does not
    count. Regression added to the existing parser scenario; its two `deepEqual` assertions were extended with the
    new field, which is a documented contract change rather than a weakened expectation.
20. Cleanup done: the write-only `store.ts` cache, its empty `invalidate()`, its call in `core.ts`, and the
    pipeline comments that described it are removed; the orphaned continuation-marker doc in `prompt.ts` is gone;
    the `record.ts` comment claiming an unknown phase reads as `ready` now describes the actual `idle` fallback and
    why it is the safe reading.

    Correction to an earlier record in this file. It dismissed the reviewer's
    `writePrompt` finding as wrong, on the grounds that `tools.ts:341` sets
    `writePrompt`. That was a false premise: the method and the
    `GoalMutationSpec.writePrompt` option are different members, and the option
    never calls the method. `GoalStore.writePrompt()` had no caller anywhere in
    packages/goal and has been removed. The reviewer was right and the earlier
    dismissal was wrong.

## Final verification chain

Superseded. This chain ran on `ed1a58fb…` after the `checkProgress.detail` and duplicated `ledgerPath` removals:

- `python3 -m pytest packages/goal/tests/ -q`: 21 passed.
- goal source `tsc`: passed. goal tests `tsc`: passed.
- root `pnpm typecheck`: passed.
- `pnpm --dir packages/goal pack --dry-run`: passed.
- `pnpm check:install`: passed.
- native preflight rejection, native PTY lifecycle, native CLI/TUI completion: all passed.
- no fixture process remained.

Earlier chains also passed: `monitor_0d3d04a0` (50.6s) on `94052869…` and `monitor_ddd9bbc8` (46.1s) on
`6ba241f6…`.

## Corrections to earlier claims

An earlier revision of this file stated that `packages/goal` is untracked local work. It is not. It also
stated that the `scheduler.claim()` line was deleted as unused and later restored; it existed at HEAD and this
change replaced it with a checked claim and a comment. Both errors came from writing the review brief on an
unchecked premise.

14. Two remaining low-severity findings closed after that chain: `checkProgress.detail` was declared and never
    assigned or read, and `readGoalHistoryPage` recomputed `ledgerPath(...)` in both branches while `file` was
    already in scope. Both were removed; neither had a behavioral effect.

## Round four: P1 authorization race fixed

15. A claim could consume authorization on a goal that had already stopped. `claim()` judged status,
    `autoContinue`, ownership and budget before taking the store lock, while the locked mutation rechecked only
    generation and claimed/running phase. A writer that stopped the goal in that window still received
    `used=1`, `phase=claimed` and a `goal_claimed` ledger entry. Reproduced standalone as
    `{"claimed":true,"used":1,"phase":"claimed","status":"budget_limited","goalClaimedEvents":1}`, then
    promoted to the scenario "a goal stopped after the pre-lock read claims nothing". Fix: rejudge the
    preconditions inside the locked mutation and refuse with `GoalStopped`. Verified both ways: with the fix
    the scenario passes, with the fix deleted it fails returning `run: 1`.
16. A secondary defect surfaced by the new regression: on refusal the scheduler called `focused()`, which can
    answer from the pre-lock snapshot, so a `budget_limited` goal was overwritten to `paused` and lost its own
    reason for stopping. The refusal path now reads through `host.readFocused()` after the lock is released, and
    the scenario asserts the goal keeps `budget_limited`.

## Known open findings, not yet fixed

17. P2, `tools.ts` history section: `get_goal(section="history")` takes a cursor and never returns
    `page.cursor`. The store computes it; the tool drops it. Two attempts to write a RED regression failed and
    were reverted rather than left half-wired: the session harness never surfaces tool output to `outcome.prompt`,
    so an assertion there cannot discriminate, and a second attempt to drive the registered tool directly corrupted
    the trailing async IIFE in `goal_session.mts`. The working approach is to assert on the tool's own
    `content[0].text` via `registerGoalTools` with a `core` double, added outside that IIFE. A history only pages
    past pi-kit's 256 KiB batch bound, so a seed needs roughly 1,200 wide events.
18. P3, `check.ts` parser with `core.ts` refusal accounting: nonempty checker output carrying no verdict marker
    is accepted as a *valid* explicit final refusal, so three malformed outputs consume the whole three-refusal
    budget and pause the goal. The unmet sentence is discarded too. The contract says three *valid* refusals.
19. The owner's own hygiene test had a false positive it introduced plus several false negatives, all now repaired.
    The barrel reader expression `import\s*type?` did not mean an optional `type` keyword and expected a bare
    module name, so a genuinely consumed barrel failed; it now matches an optional `type` keyword and a
    `../src/`-prefixed path. The export scan ignored `export type { X }` outside `src/index.ts` and counted a name
    quoted inside a string literal as a reader; the settings scan accepted a comment as a reader. Comments and
    string/template literals are now stripped before anything is counted. The stricter scanner then found a real
    dead export the previous one missed: `export type { GoalSchedulerState }` in `scheduler.ts`, whose only
    consumer was its own re-export; removed, with the type import it kept alive.
    Mutation evidence, each run on the real tree and restored byte-for-byte with an identical fingerprint: a
    genuinely consumed barrel now PASSES, so the false positive is gone, while a dead barrel, a dead export named
    only in a string literal, and a dead setting with a comment-only reader all FAIL. Two earlier runs of mine were
    invalid mutations rather than test failures: an unused import tripped `tsc` (TS6133) instead of the scanner, and
    a comment naming `autoSelectSingleGoal` was inert because that field is no longer declared. The reviewer's real
    case declares the field and gives it only a comment as its reader, and that fails as intended.
20. Cleanup: the `store.ts` cache has only `set`/`delete`/`clear` and no reader; `writePrompt` has no caller;
    `prompt.ts:24-32` still documents the deleted cap and assertion; `record.ts:175-177` says the fallback is
    `ready` while the code uses `idle`.

Items 17 and 20 were confirmed by the round-three review and are now fixed as described above. Item 18 is the same
defect as the round-three P3 and is fixed. Item 19, the owner's own hygiene test, is repaired as described in
round five above.

`monitor_56342bbb` is the final acceptance chain on candidate `bc9948f4…` (after P1, P2, P3, the hygiene repair and the cleanup) and exited successfully in 44.6 seconds:

- `python3 -m pytest packages/goal/tests/ -q`: 21 passed.
- goal source `tsc`: passed. goal tests `tsc`: passed.
- root `pnpm typecheck`: passed.
- `pnpm --dir packages/goal pack --dry-run`: passed.
- `pnpm check:install`: passed.
- native preflight rejection, native PTY lifecycle, native CLI/TUI completion: all passed.
- no fixture process remained.

Mutation spot-checks on this candidate, each run against the real tree and restored byte-for-byte with an
identical fingerprint: the locked precondition recheck removed from the claim makes its scenario FAIL; the cursor
returned by the history tool removed makes its scenario FAIL; the verdict validity flag forced true makes the
parser scenario FAIL; a genuinely consumed barrel PASSES while a dead barrel, a dead export named only in a string
literal, and a dead setting with a comment-only reader all FAIL.

Earlier chains: `monitor_9124e6c3` (50.7s) on `064a75bd…`, `monitor_443ce926` (44.5s) on the hygiene repair,
`monitor_0d3d04a0` (50.6s) on `94052869…`, `monitor_ddd9bbc8` (46.1s) on `6ba241f6…`.

21. The gap the stricter scanner could not close, closed by pinning rather than by proving. A public class member
    with no caller is invisible to the export scan, which is the shape the removed `openGoals`, `unfocus`,
    `markInterrupted` and `emptyGoal` had. Two attempts at a general check were discarded: the first flagged five
    false positives because a two-space object literal has the same shape as a class body, the second tripped its
    own vacuity guard because the class-body regex matched nothing. A dedicated regression,
    `test_removed_dead_surface_stays_removed`, pins those four names instead. It is weaker than proving they were
    dead: it only fails if one of them returns. Mutation evidence, each restored byte-for-byte with an identical
    fingerprint: `get openGoals()` reintroduced into `core.ts` RED, `markInterrupted(goal)` reintroduced into
    `scheduler.ts` RED, baseline hygiene module 7 passed. The general limitation stands and is not claimed closed.

## Unrelated breakage found outside this package

Root `pnpm typecheck` compiles `tsconfig.extensions.json`, which includes every extension, so it reports on
packages this audit does not own. On `bc9948f4…` it briefly failed with three errors in
`packages/continual-learning/extensions/inject-memory.ts:1435` and `:1873`: `readFile` and `MAX_MEMORY_BYTES`
undefined, and a `{}` assigned where a readonly array is expected. That file was uncommitted work in progress from
another session (`git status` showed it modified), it contains no reference to packages/goal, and this audit's
scope forbids editing code outside its own package, so it was reported rather than fixed. The other session
completed its edit and root `pnpm typecheck` returned to exit 0 with no change from this audit. Nothing in
packages/goal caused it: the package's own typechecks, its 22 tests, its pack dry-run, its installation audit and
its three native offline probes passed on the same candidate throughout.

## Final acceptance chain

`monitor_b7589f78` exited 0 in 42.6 seconds on `bc9948f4b0a31b30356072c62f97167bec0ebebe86c7753ad6b01c20658bd8df`,
with the goal-scoped checks first and root typecheck reported separately so a failure outside this package could
not be mistaken for one inside it:

- `python3 -m pytest packages/goal/tests/ -q`: 22 passed.
- goal source `tsc`: passed. goal tests `tsc`: passed.
- `pnpm --dir packages/goal pack --dry-run`: passed.
- `pnpm check:install`: passed.
- native preflight rejection, native PTY lifecycle, native CLI/TUI completion: all passed.
- root `pnpm typecheck`: exit 0, confirmed separately after the unrelated breakage cleared.
- runtime fingerprint asserted equal to `bc9948f4…`; no fixture process remained.

## Round six: reviewer findings closed

22. `acceptCheckpoint` authorization race, fixed. It validated identity, generation, dispatch and phase before
    taking the store lock, and its locked mutation only checked that a scheduler existed and set
    `phase=running`. A user pause landing in that window was therefore accepted: the record stayed
    `paused`/`autoContinue=false` while the dispatch advanced, `boundaryContinuation` returned `continue:true`,
    and the tool guard did not block work. The preconditions are now rejudged under the lock. Regression: "a
    checkpoint is refused after the goal is paused mid-flight".
23. Cross-owner pause, fixed. The claim refusal fallback checked the goal's status but not its ownership, so a
    losing claimant could pause a goal another session had resumed between its pre-lock read and locked claim.
    Ownership is now rechecked through `host.readFocused()` before pausing. Regression: "a losing claimant never
    pauses the goal another owner resumed"; without the guard it fails with `'paused' !== 'active'`.
24. Cursor regression strengthened. The old check asserted `/cursor=/`, which a fabricated cursor satisfies while
    repeating page one. It now walks the history: it extracts each cursor, re-calls the tool, asserts the cursor
    advances, that no event is served twice, that more than one page was needed, and that the last page states
    "End of history.", reaching all 1,201 events exactly once. The reviewer's own fabricated-cursor mutant now
    fails with "a cursor must advance, not repeat itself".
25. Malformed-child accounting covered end to end. The parser-level `valid` flag is unit tested, and
    "three malformed checker answers never spend a valid refusal" drives the real tool, core and store path: three
    error verdicts leave `completionFailures` at 0 and the goal `active`. Removing `!result.error` from the
    accounting in `core.ts` makes it fail with `3 !== 0`.
26. Dead `GoalStore.writePrompt()` removed, and this file's earlier dismissal of that finding corrected. The
    dismissal claimed `tools.ts:341` sets `writePrompt`, confusing the method with the unrelated
    `GoalMutationSpec.writePrompt` option, which never calls it. The reviewer was right.

`monitor_8fb741e0` is the acceptance chain for this candidate and exited 0 in 50.6 seconds on
`9b0be44b…`, after round six:

- `python3 -m pytest packages/goal/tests/ -q`: passed.
- goal source `tsc`: passed. goal tests `tsc`: passed.
- `pnpm --dir packages/goal pack --dry-run`: passed.
- `pnpm check:install`: passed.
- native preflight rejection, native PTY lifecycle, native CLI/TUI completion: all passed.
- root `pnpm typecheck`: reported separately so a failure outside this package cannot be read as one inside it.
- no fixture process remained.

Mutation spot-checks on this candidate, each run against the real tree and restored byte-for-byte with an
identical fingerprint: removing the claim precondition recheck, the checkpoint precondition recheck, the ownership
recheck before pausing, the cursor continuation, the `!result.error` accounting condition, the parser validity
guard, and the scaling formatter each turn their regression RED. The reviewer's own fabricated-cursor mutant, which
satisfied the previous `/cursor=/` assertion, now fails with "a cursor must advance, not repeat itself".

## Round seven: panel retired, /goal revises in flight

27. `/goal` with a new objective while something else is in flight is no longer rejected outright. When the
    focused goal is actually being pursued (`status` active and `autoContinue`), the text is written as a
    revision and the loop continues on it; a paused goal has no work under way, so retyping must not silently
    rewrite it, and that case keeps the old rejection. Regression: `tests/goal_command.mts`, two scenarios
    driving the registered command handler through a minimal host double. Verified in both directions: with the
    fix the first scenario passes, and with the fix reverted it fails with the objective still the old one while
    the paused-goal scenario still passes. This harness is deliberately separate from `goal_session.mts`, whose
    session state is not safe to perturb from an added scenario; two attempts there caused seventeen unrelated
    failures and were reverted.
28. The expanded panel is gone. `renderDashboard` and `createDashboardOverlay` had no production caller: the
    `/goal` command renders a compact notification and never opens the overlay. Both were deleted with their test
    scenarios and the two `features/goal.feature` panel scenarios. The elapsed formatter contract was not lost
    with them: its test now asserts `formatElapsed` directly and still pins all twelve boundaries. Removing them
    also exposed and removed `DashboardOptions`, `DashboardFrame`, `bodyBudget`, `wrap`, an orphaned interface and
    the imports they left unused, which the hygiene scanner then confirmed by naming them.
29. The last user-visible goal id is gone: the "Could not pause" notification no longer prints it.

Receipts on this candidate: `PYTEST_EXIT=0` with 23 passed, goal source and tests `tsc` exit 0, pack dry-run exit
0, and the native rejection, TUI and completion probes all exit 0. Two failures are outside this package and were
reported rather than fixed, because the objective forbids editing other packages: root `pnpm typecheck` fails in
`packages/agent-teams/tests/tool-param-schema-fixture.ts`, and `pnpm check:install` reports `packages/utils` and
`packages/vision` not installed.

## Independent review of this round

Dispatched on fingerprint `9b0be44b…`, concurrently with the acceptance chain, which is read-only with respect to
this package. Four prior reviews each returned REWORK; their findings and fixes are items 22 to 26 above.
Verdict recorded when it returns.

## Unverified limitations

The hygiene regressions are static analysis. They assert structure, not runtime behavior, so a refactor that
preserves structure can still hide a behavior change. The export scan covers exported names only: a non-exported
private member with no caller, such as a class getter, is invisible to it, and the removal of such members
(`openGoals`, `unfocus`, `markInterrupted`, `emptyGoal`) rests on grep evidence, not on a regression. The native
probes use scripted offline providers, so external model quality and general provider behavior stay unverified.
The `store.ts` cache, which kept write-only entries with no reader, has been removed along with its empty
`invalidate()` and its call in `core.ts`; nothing in this package reads it. The `KNOWN_EVENT_TYPES` set still
duplicates the `GoalLedgerEvent` union by hand with no compile-time
link; that is a structural improvement outside this audit's dead-code scope. `KNOWLEDGE` of the cross-process
race barrier is by construction, not by assertion: the workers still might overlap for other reasons even with a
valid barrier. Historical RED-before-fix ordering and any prior publish/push/commit activity cannot be
established from this snapshot.

Four earlier review documents (`review-current.md`, `review-completion-current.md`,
`review-completion-correction.md`, `verification-current.md`) are tracked files from earlier sessions and were
deliberately left in place: they are not this task's artifacts, and removing another session's tracked evidence
is outside this audit's authority. They describe earlier candidates and are superseded by
`verification-audit.md`; a reader should treat them as history, not as current status.