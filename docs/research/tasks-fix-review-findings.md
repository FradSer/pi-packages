# Independent review findings

## Initial candidate

Baseline: `8c827980`.
Manifest: @tasks-fix-candidate-initial.json.
The reviewer confirmed all 23 initial hashes.
Standards: REWORK. Spec: REWORK.

## Findings to retain for recheck

1. Refused submission correction is not reachable through resident input.
   Rejected pending records still freeze input and queue rejection feedback.
   Initial tests inject a corrected marker after observing denied authorization.
   Correction must prove feedback delivery and authorized correction input.
2. Prior successful result disappears after reopen and later failure.
   Parent reproduced this. The correction retains task.result in evidence history.
   A public-tool regression now preserves exact body bytes.
3. Expanded waiting omits handoff candidate and priorFindings.
   Both fields must remain visible in native expansion.

## Newly exposed integration issue

The implementation child reported missing gate-pass verdict forwarding.
The correction must keep the declared gate in place and record the accepted pass.
No test may withdraw the gate merely to obtain success.

## Final verdict

Raw manifest SHA256: `bdcb298a1d69f45239876b95d2c7c0aeb786ebc628e5da2c0a2abcf8a21a6f4a`.
All 24 file hashes match. Standards PASS. Spec PASS.
The reviewer confirms all retained findings are resolved.
Independent final correction tests: 4 passed. Prior focused tests: 28 passed.
No remaining concrete blockers.

## Recheck scope

Validate current hashes in @tasks-fix-candidate.json before reviewing.
Keep prior findings separate from the current verdict.
Check both Standards and Spec, with attempted refutation before PASS.
No source edits, dependency installation, user settings changes or paid calls.
