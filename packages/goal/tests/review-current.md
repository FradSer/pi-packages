# Frozen goal review candidate

## Scope and baseline

Review only `packages/goal`. The package is untracked local work, so `git diff HEAD` is not a task baseline.
Use the retained reviewer result on runtime fingerprint `13c7e4dc414f4c803815ae1dd68d3a606e28d0fb75cd3111261bb86ea6380194` as the correction baseline.
Do not review or change other workspace work. No commits or publication are authorized.

Current source fingerprint: `61a20fdd9e18ab1732c835e74dfd1d6c6f769e649c12a566c57b5a12f073d0db`.
Algorithm: sort `packages/goal/src/*.ts` paths; form one line per file as SHA256, two spaces, path, newline; SHA256 the listing.

## Prior findings and correction delta

- Native void-send preflight failure left activation intent. A later unrelated edit resumed paused work.
  Correction: busy/pending requests are refused; command stores only a pending exact prompt and owner.
  `before_agent_start` consumes it and grants activation only for a matching accepted request.
  Ordinary accepted prompts clear unmatched pending intent. Send throws, pause/clear, boundaries and settlement revoke it.
- An old explicit MET archived a resumed goal. Correction: `core.check()` also compares scheduler generation before returning acceptance.
- New user UI requirement: state appears below the input using pi-kit, elapsed uses whole minutes from `0m`.
  Correction: existing `createLiveActivityWidget` uses belowEditor; formatElapsed outputs integer total minutes.
- E2E process cleanup now escalates isolated process-group SIGTERM to SIGKILL and reaps before printing success.

## User contract

Only one slash command: `/goal`. Bare reads this thread. Exact pause/resume/clear manage it.
Other full multiline text preserves objective, completion conditions and scope; setting activates a successful accepted revision.
Fresh threads never adopt project goals. Same-thread restore preserves identity. View/tools/widget read fresh state.
Pause stops usage and automatic checks. Resume authorizes one dispatch. Stale checks cannot close or reauthorize newer runs.
Clear confirms and archives. No user goal deletion, publication, commit, or changes to other packages.
Full acceptance scenarios are in `features/goal.feature`.

## Evidence and safe checks

- Unit seam RED reproduced async rejected send and explicit-check generation bugs; both now GREEN.
- `node --import tsx packages/goal/tests/goal_native_rejection.mts` passes original native SDK no-model rejection.
- `python3 packages/goal/tests/goal_native_tui.py` passes native PTY busy rejection, unrelated edit staying paused,
  idle revision activation, once-only continuation, pause/clear, belowEditor factory and 0m rendered text, then process cleanup.
  Uses isolated project/agent directories and a local scripted provider, no authenticated calls.
- `python3 -m pytest packages/goal/tests/ -q`: 12 passed before final rerun.
- Goal tsc and root typecheck, pack dry-run and installation audit are safe read/check operations.

## Standards and Spec reports

Read repository AGENTS.md and package AGENTS.md. Check docs/memory if present for related pitfall/convention entries.
Return separate Standards and Spec verdicts. Before PASS, state strongest failure case and evidence refuting it.
Retain blockers with exact file lines and a reproduction. Do not edit or wait for remediation.

Standards heuristic baseline (judgement calls; project rules override): mysterious names, duplicated code, feature envy,
data clumps, primitive obsession, repeated switches, shotgun surgery, divergent change, speculative generality,
message chains, middle men, refused bequest. AI slop baseline: fabricated evidence via casts/suppressions,
evidence widening, defensive clutter, mock patching of own internals, vacuous names.
Inspect these in the correction delta; skip issues already enforced by tooling. Describe each axis in under400 words.

## Limits

No OS sandbox claim against concurrent directory replacement; failed creation can leave prose without active record.
Tool-less checker cannot independently inspect code/tests. Native fixtures deliberately control model response behavior;
external provider/model performance is not verified. Existing loaded user process requires reload for new extension code.
