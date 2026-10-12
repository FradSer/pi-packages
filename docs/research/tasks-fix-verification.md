# Tasks fix verification

## Candidate

Baseline: `8c827980`.
Scoped file hashes: @tasks-fix-candidate.json.
Raw manifest SHA256: `bdcb298a1d69f45239876b95d2c7c0aeb786ebc628e5da2c0a2abcf8a21a6f4a`.
The initial review candidate is retained in @tasks-fix-candidate-initial.json.

## Checks

- Final combined Tasks and Agent Teams suites: 475 passed in 498.67 seconds.
- The combined run includes the gate-verdict and correction-input regressions.
- Typecheck passed after the final correction.
- Tasks and Agent Teams packed manifests passed dry-run inspection.
- `git diff --check` passed.
- Isolated real Pi print checks run in the Tasks suite with a deterministic provider.
- Final native PTY run: `/tmp/tasks-complete-handoff-final`.
  It uses 120x40, 48x24 and 48x12 in the same live session.
  Captures retain raw terminal bytes, interactions, events and reconstructed screen text.
  Waiting starts collapsed. Ctrl+O reveals current blocker, handoff, original plan and history.
- Independent final review: Standards PASS, Spec PASS; all 24 candidate file hashes match.
- Independent checks: final correction tests 4 passed; prior focused checks 28 passed.
- The reviewer inspected native captures. The parent owns the full suite and PTY execution evidence.
- Gate-pass verdict forwarding and rejected-submission input recovery are corrected.
  The final combined run verifies the declared gate without withdrawing it.
- Expanded handoff now includes candidate and prior findings.
- The last manifest refresh changes only the correction regression hash; production source remains unchanged.

## Test expectation change

`evidenceHistory` belongs in explicit detail results, not list summaries.
The existing schema test now excludes this detailed field when comparing summary fields.
The assertion still checks exact schema field agreement.

## Compatibility

The library retains its documented direct acceptance path for externally verified blocked work.
The public model-facing update tool requires recovery before successful blocked delivery.
The tool preserves result bytes rather than trimming their boundary whitespace.
Explicit outstanding lists replace current work. Historical findings remain additive.

## Limitations

The installation audit reports eleven missing workspace packages, including Agent Teams.
Tasks is configured. No settings or dependency installation changed.
Standard pnpm commands trigger an unsolicited dependency check; verification disables that check only.
No remote machine operations, paid provider calls, publication or commits occurred.
Native deterministic acceptance does not prove real-model judgment or accessibility.
The current user session has not reloaded the changed renderer.
