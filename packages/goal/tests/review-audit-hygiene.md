# Goal audit and hygiene review

## Candidate and scope

Review only `packages/goal`. Its files are untracked local work, so `git diff HEAD` is not a baseline.
Current runtime fingerprint: `8368a916d35291ac9736b6c031e3a257eebfc90175354791afcf414895017095`.
Algorithm: SHA256 over a sorted listing of `src/*.ts`, one line per file as SHA256, two spaces, path, newline.
No source changes during this review. Test or documentation evidence may be refreshed with a notice.
Do not edit files, run authenticated model calls, or mutate real goal records. Other packages and unrelated
local changes are out of scope and must stay untouched.

## User request

Audit `packages/goal` end to end and fix every confirmed defect in the package itself.
Known candidates to confirm or dismiss: a ghost `taskIndex` import in `tests/goal_store.mts`, a duplicated
`notifyPi` call in the `/goal` command handler, a dead `autoSelectSingleGoal` setting still parsed and documented
after automatic adoption was removed, a package description promising task trees, stale `/goal-status` or
`goal-*` references in tests, features and docs, plus any tool, prompt, ledger, store or evidence defect a fresh
reader can reproduce. Every fix requires a failing regression first and a passing suite after. Dead code,
unused settings, duplicated lines and stale docs must be removed, not left in place.

Preserve existing behavior: the single `/goal` command, thread isolation, below-editor flush-left minute status,
observed completion evidence, checked-revision archive, and the three-refusal and no-work bounds.
No publish, push, commit, or commit-history rewrite.

## Confirmed findings and corrections

1. Ghost import. `tests/goal_store.mts` imported `taskIndex` from `src/record.ts`, which never exported it.
   Root cause: `packages/goal/tsconfig.json` only included `src/**/*.ts`, so no harness was ever type checked,
   and tsx erases an unused named import at runtime, so every suite still passed.
   Correction: added `tsconfig.tests.json` covering `src` and `tests`, a regression that runs it, and removed
   the dead import. The first run exposed 14 further type defects in harnesses, now all fixed.
2. Dead settings. `autoSelectSingleGoal` and `thinkingLevel` survived the removal of automatic adoption and the
   single-command surface: still declared, still parsed from files, still implying behavior the runtime no longer
   had. `thinkingLevels()` lost its only caller with the old settings command. All removed.
3. Broken test semantics. The scheduling harness line `const claimed = scheduler.claim()!` had been removed as
   "unused" during a cleanup, but that line consumes one authorized dispatch; without it the run count assertion
   failed. Restored with a comment stating why the claim is load-bearing.
4. Seven zero-reader exports left by repeated redesigns, now deleted: `MAX_PROMPT_FRAGMENT_CHARS`, `goalPrompt`,
   `staleCheckpointPrompt`, `unfocusedPrompt`, `writeGlobalSettings`, `removeProjectSettings`, `projectHistory`.
5. New regressions in `tests/test_goal_hygiene.py`: type check covers harnesses, every setting has a reader,
   every harness import resolves, no export lacks any reader, and exactly one command is registered with no
   stale `goal-*` reference in sources, features or docs.
6. Fixture typing. `setWidget` overloads, `JsonObject` tool arguments, an optional `handleInput`, and a typed
   model removal are now expressed precisely instead of relying on loose doubles.

## Verification performed by the owner

Every regression was observed RED before its fix, including the 5s subprocess timeout on unbounded evidence
collection, and mutation spot-checks reintroduce the dead setting and the ghost import to confirm the checks
still fail. Final `python3 -m pytest packages/goal/tests/ -q` reports 20 passed. Goal-specific `tsc`, the new
tests tsconfig, root `pnpm typecheck`, pack dry-run, installation audit and the three native offline probes run
in a separate final chain whose result is reported with this review.

## Two-axis review

Read root `AGENTS.md` and `packages/goal/AGENTS.md`. Check `docs/memory` for related pitfall or convention files.
Return separate Standards and Spec verdicts. Before a PASS, state the strongest plausible failure and the
evidence that refutes it. Reproduce claims with offline probes at public seams; retain unaffected prior
evidence with explicit scope. Report blockers with exact file and line.

Standards heuristic baseline, always judgement calls where the repository documents otherwise: mysterious names,
duplicated code, feature envy, data clumps, primitive obsession, repeated switches, shotgun surgery, divergent
change, speculative generality, message chains, middle men, refused bequest. AI-slop patterns: fabricated
evidence through casts or suppressions, evidence widening, defensive clutter, mock-patching own internals,
vacuous names. Inspect the correction delta and the new hygiene tests in particular. Skip tooling-enforced issues.

## Spec focus

Verify that each removed item had no reachable reader: no user-visible `/goal-settings` input, no documented
setting, no tool behavior. Confirm `autoSelectSingleGoal` removal does not break existing settings files written
by older versions, which must remain harmless. Confirm the hygiene tests cannot pass vacuously, especially the
zero-reader export scan and the single-command scan, and that they fail when the corresponding defect returns.
Confirm behavior preservation for the single `/goal` command, thread isolation, status widget, completion
evidence, checked-revision archive, and the three-refusal and no-work bounds.

## Limits

The new hygiene tests are static analysis; they assert structure, not runtime behavior. The native probes use
scripted offline providers, so external model quality and general provider behavior stay unverified.
No claim is made about the earlier commit scope problem, which is outside this review.
