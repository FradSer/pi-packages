# Run-start injection repair

## Contract

The user requests all analogous injections use Pi 1.2 before_agent_start once per run.
Context injection must not use custom messages. Unrelated workflow history and authorization checkpoints remain in scope for preservation.
Additive instructions must not return a complete systemPrompt, because forced text can hide later structured contributions.
Custom startup has no prompt. It must not crash, invent a user request or erase pending authorization.

## Scope and ownership

- Context, Matt Pocock, Monitor, Plan Mode, Skill Router: structured contribution and absent-prompt boundaries.
- Agent Teams and Subagents: leader/worker guidance and agent Memory contribution.
- Continual Learning: Memory discovery and Harness guidance without custom injection, preserving actual read and guardrail provenance.
- Utils Sessions: peer recap contribution and absent-prompt boundary.
- Vision: absent-prompt startup only; image message transformation remains.
- Other history/image context transformations remain unchanged.

## Current verification

- Utils regression reproduces undefined.trim at custom startup before implementation.
- Sessions now contributes promptGuidelines and preserves the prior goal for custom startup.
- Utils suite: 135 passed and 74 subtests passed.
- All implementation reports arrived; no additive startup handler returns a full systemPrompt or custom message.
- Five-package combined suite passes 486 tests after a retained 180-second timeout; successful run takes 363 seconds.
- Agent Teams passes 303 tests; Subagents passes 585; Vision passes 18.
- Root typecheck and 18 packed manifests pass; configured Pi 1.2 composition tests pass.
- Memory full suite reports 22 failures, 1571 passes and one skip.
- Change-caused fixture failures and obsolete expectations are repaired; 33 affected tests pass.
- Frozen research failures are change-caused. HEAD planner bytes match the frozen expected hash and are retained in the historical fixture mapping; no manifest or frozen hash changes.
- The full Memory suite must run again after pending Harness repairs.
- Integration review finds guideline contributions disappear under customPrompt; affected packages are migrating to named sections with rendered-output regressions.
- Sessions uses an owned section and escapes prompt delimiters; 17 affected tests pass.
- Integration review is in flight.
- Memory security review reports three blocking Harness findings: incomplete config loses scoped guidance, old unscoped fallback can reactivate, and legacy skill guidance lacks invocation scope.
- All three Harness findings are repaired and independently closed: Standards PASS and Spec PASS for those repairs; 47 focused reviewer tests pass.
- Final Memory review: Standards PASS and Spec PASS; 66 focused reviewer tests pass with actual Pi 1.2 customPrompt builder coverage.
- Full Memory run: 1597 passed, one stale fixture failure. The fixture now includes sections; all 10 tests in that file pass.
- Final actual Pi 1.2 composition run passes at `/tmp/pi-native-run-start-final/native-run-start-gs9vidt5`.
- Five section-repaired package suites pass 486 tests; actual installed Pi 1.2 rendered composition passes five cases.
- Final Agent Teams suite passes 307 tests; Subagents passes 587.
- Sessions final section/escaping suite passes 17 tests; combined teams/subagents/Sessions targeted run passes 19.
- Final integration recheck resolves both functional and escaping findings, with no new defects.
- Reviewer verifies 28 targeted checks and source hashes matching the native manifest for Context, Matt Pocock and Monitor.
- Memory security review separately passes the final Memory/Harness candidate.
- Final root typecheck, packed manifests and diff checks pass.
- Memory escaping, no-custom delivery, actual-read nomination and unchanged guardrails pass the focused review.
- Final native Pi 1.2 no-custom composition acceptance passes for Goal, Memory, Harness, Context, Matt Pocock and Monitor, including user/custom startup and multiple tool rounds.
- Plan Mode, Skill Router, Teams, Subagents and Sessions have source review and rendered/handler tests, not new native acceptance.
- The Memory full-suite failure is closed by the corrected fixture and its ten passing tests; the nine-minute full suite was not repeated after that fixture-only edit.

## Limitations

- The current leader process continues to receive old Goal and Tasks runtime injections.
- A reload is required; isolated new processes do not prove this session loaded changes.
- Preserve pre-existing changes in Utils, Keyboard and Continual Learning.
- No settings changes, publication, commits, private-history edits or paid calls are authorized by this repair.
