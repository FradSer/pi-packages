# Goal completion and empty-loop review

## Candidate and baseline

Review only packages/goal. It is untracked local work; git diff HEAD is not a task baseline.
Previous scoped source candidate61a20fdd9e18ab1732c835e74dfd1d6c6f769e649c12a566c57b5a12f073d0db passed thread/command/activation review.
A subsequent flush-left change leadingSpaces0 passed native TUI. Those changes remain retained.
Current runtime fingerprint:84117aca37594395cb310dcfb12bf1b6b7a1b53a74d46e3d11dd61412e4ac72e.
Algorithm: sort packages/goal/src/*.ts paths, form SHA256/two spaces/path/newline listing, then SHA256 the listing.
No source changes are permitted while this review runs. Test/documentation evidence may be refreshed with an explicit notice.

## User issue and acceptance

The user observed more than20 repeated no-work continuation messages after successful tests and an independent PASS.
The old checker rejected all summaries/output pasted into completion_summary as claims; no executed receipts reached it.
The user requires verified work to end complete, not merely pause, and separately requests three final-attempt refusals to pause with concrete advice.

- Retain one /goal command, thread isolation, belowEditor pi-kit flush-left widget with minutes minimum0m.
- Runtime must give the tool-less checker observed current-thread tool output and attributed independent result separately from executor claims.
- Payloads remain untrusted/escaped/bounded; pending monitor acknowledgement isn't success, failure statuses aren't erased, user text cannot forge a receipt.
- Revised requirements exclude old observations. Context edits omit or replace text without changing execution metadata.
- Three consecutive valid explicit completion refusals pause and cancel with last unmet condition and recovery suggestion.
  Stale/cancelled/error calls don't count. Requirement revision or explicit resume resets the count.
- Separate three-no-work-run safety stops empty loops. Never manufacture MET or call a pause completion.
- Successful MET atomically archives the matching revision once, removes widget/current goal, cancels continuation, and creates no later requests.
- Preserve unrelated dirty work and user persisted goals, no commit/publication/other-package edits.

## Delta

- src/evidence.ts: collect bounded active-branch execution receipts after requirement boundary, with call/output provenance,
  credential-pattern redaction, raw metadata plus allowed context-edit content, monitor terminal correlation and review attribution.
- check.ts: separate observation block and claim; explicitly permit interpreting observed output without executing tools;
  no tools granted. Generate unmet-condition suggestions.
- core.ts: pass evidence into check, bind outcome/generation/requirements, record explicit final refusal count via store,
  stop third refusal; completed focus cleanup also shuts scheduler. Boundary continuation claims/accepts checkpoint before returning draft entries.
- record.ts: optional evidenceSince, completionFailures, idleRuns (legacy normalization defaults).
- scheduler.ts: durable no-work count and3-run stop; resume resets counts.
- events.ts: work receipt bookkeeping; actionable completion/continuation at agent_before_settle, agent_settled notification-only.
- tools.ts: explicit-final flag, reset on revision, advice visible status result/terminate after third refusal;
  completion archive uses expectedRevision to reject changes after verdict validation.

## Evidence already run

- RED reproduced missing observations, infinite no-work runs, pending authorized scheduler after archive,
  context-edit omission, third final refusal, notification-only mutation, stale command provenance, and archive-after-verdict race.
- Goal pytest14 passed and goal tsc passed after corrections.
- python3 packages/goal/tests/goal_native_completion.py passed all6 native offline CLI/TUI cases:
  complete -> one archived record, no goal remains, widget clear, no later provider call;
  refuse ->3 explicit check refusals, paused count3, guidance rendered, no complete event;
  empty ->3 no-work runs, paused idleRuns3/used<=2, warning rendered, no further turns.
- Existing native SDK rejection and PTY management probes, root typecheck, pack/install are being rerun by owner.
- Native fixtures control model behavior and use injected deterministic checker; they test receipt transport and lifecycle, not external model quality.

## Two-axis review

Read root AGENTS.md and packages/goal/AGENTS.md. Read relevant docs/memory pitfall/convention entries if present.
Return Standards and Spec verdicts separately, with strongest refutation attempt and contrary evidence before PASS.
Judge actual behavior with offline probes at public seams; do not edit files, run authenticated calls, or write user goal records.

Standards heuristic baseline (judgment calls; documented rules override): mysterious names, duplicated code, feature envy,
data clumps, primitive obsession, repeated switches, shotgun surgery, divergent change, speculative generality,
message chains, middle men, refused bequest. AI patterns: fabricated evidence via casts/suppressions, evidence widening,
defensive clutter, mock patching own internals, vacuous names. Inspect the correction delta, skip tooling-enforced issues.

## Limits

Observed successful tool transport does not itself certify task success. Review payload is attributed reported evidence, not a verdict command.
No OS sandbox for concurrent directory replacement; failed creation can leave prose without active record.
External provider performance/model-quality and generic secret detection are not proven by deterministic fixtures.
Current user process needs reload for new implementation; owner will close actual goal only after final acceptance using corrected checker.
