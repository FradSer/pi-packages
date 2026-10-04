# Completion review correction

## Candidate

Read the retained baseline brief: @packages/goal/tests/review-completion-current.md.
Original REWORK source fingerprint:84117aca37594395cb310dcfb12bf1b6b7a1b53a74d46e3d11dd61412e4ac72e.
Corrected source fingerprint:3f8d5e6e01ef0c0abf3538d3487329a6ed3d00cacd36fa8881dc56ae17c13110.
The df010203096d2ff86038f65f21421da27f42e17163371e80e138351b01f06b2a candidate received Standards PASS and Spec PASS for all original corrections.
Intermediate ef066cb8aa54e530a98e9a960baa3e2494034b2e0c31459c31fd5d9157591b83 closed the original blockers but failed computational bounds.
Algorithm: SHA256 of sorted src/*.ts checksum listing (SHA256/two spaces/path/newline).
No runtime changes during review. Package scope only; do not edit or run authenticated model calls.

## Original report retained

Standards REWORK: quoted JSON credential fields escaped the redactor; monitor/review labels lacked bounds and redaction.
Spec REWORK: monitor terminals lost launch input and matched/output fields; launch-before-revision terminals became fresh.
Loop archive used the newer revision and omitted evidenceSince after verdict validation.
Identical requirement rewrites reset final refusals. Pending monitor acknowledgements reset no-work counter.
Review verified overlap abort behavior and six native E2E cases but these did not close the blockers.

## Correction delta

- Every evidence label, input, and output passes redaction and separate bounds. JSON assignment syntax is covered.
- Collector tracks original call entry ID/time/input through monitor acknowledgement to terminal.
  Unique launch ID or description links a terminal. Old launches are excluded, ambiguous/unlinked success stays reported.
  Known terminal matched/output/exitCode metadata is included unless output has a context edit, which wins completely.
- completeCheckedGoal centralizes both archive paths with the original expectedRevision; loop checks evidenceSince and stale verdict.
- Only actual objective/contract changes reset evidenceSince/completionFailures; identical writes preserve them.
- noteWork ignores pending monitor_start and monitor_stop; only successful terminal monitor_start counts completed work.
- Regression tests reproduced RED for all original failures before these changes.

## Retained computational-bound finding

Intermediate review Standards/Spec REWORK: redaction lacked a field-start boundary and retried the credential pattern at each alphabetic position.
Independent 5k/10k/20k/40k descriptions cost41/163/665/2620ms;100k exceeded15s.
Owner added a subprocess regression at collectGoalEvidence with100k safe label plus10k output. It failed with TimeoutExpired5s before correction.
The only new runtime correction adds a word-boundary anchor to the credential-field regex.
JSON/quoted/unquoted assignments and label/output redaction remain covered; the new public-seam timeout regression passes.
Owner current goal pytest15 passed, monitor evidence tests2 passed in0.30s, goal tsc passed.
No user goal record was changed by these checks.

## Final legacy review transport correction

Read-only inspection of the actual current branch shows independent review deliveries use agent-teams-report.
The modern-only collector omitted those receipts. A public collector regression failed before the correction.
The sole runtime delta adds a legacy custom-message branch gated by origin=agent, status=completed,
finished=true, string agent and spawnId. It returns attributed reported data, not automatic PASS.
Harness-origin notices are excluded; bounded redaction and context edits apply unchanged.
New source fingerprint is above. No other production code changed after the df010... independent PASS.

## Acceptance and verification

Full confirmed user contract and limits remain in original brief and features/goal.feature.
Parent pytest14 and goal tsc pass. Native CLI/TUI completion/refuse/empty plus prior management/rejection tests will be rerun.
The test of unlinked custom success was changed to reported to implement launch provenance, not to erase failing outcomes.
Parent will finish actual goal only after fresh verified output and independent no-blocker acceptance.

## Review instructions

Validate fingerprint first. Independently rerun original probes and adjacent public-seam tests.
Return separate Standards and Spec verdicts with attempted refutation and evidence before PASS.
Review only correction delta plus its interactions; retain unaffected previous evidence with explicit scope.
If new blockers exist, return promptly without editing or waiting for repairs.
Safe checks: pytest packages/goal/tests, goal tsc, native rejection m ts, goal_native_tui.py, goal_native_completion.py.
These native probes use isolated directories and an offline provider. User goals must not be changed.
