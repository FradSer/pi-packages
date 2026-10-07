# Verification provenance repair

The initial real-project prompt previously described the command as a settled
verified fact before running it. In the reused yocto learning session, both test
invocations were `pnpm test 2>&1 | tail -40`. Their native results displayed seven
and eight passing tests, but contained no original process exit code or details.
A non-error result for a pipeline cannot alone establish the test process exit.
A local reproduction confirms `false | tail -40` returns zero while standalone
`false` returns one. This is a defect in experimental provenance, not evidence
that the test actually failed or that Jev's judgment was necessarily correct.

The workflow now requests a standalone invocation and describes verification
as conditional on the resulting observation. It records a separate
`learningCommandNativeSuccess` check using the existing exact call/result links
and conservative command matcher. A successful independent check after learning
does not replace the frozen learner evidence. The new acceptance assertion runs
after Memory, recall and Harness observations, retaining separate phase results.
Private preferences, no-push authority, project tasks, model and quality gates
remain unchanged. Production extension prompts and policy are unchanged.

Historical reports and frozen labels remain intact. Interpret their positive
labels as declared benchmark expectations. For the reused pipeline case, a
hold cannot independently demonstrate an incorrect semantic judgment when
success provenance was unavailable. Later successful independent tests prove
the checkout's behavior, not what the learner could observe at its decision.
Do not retroactively relabel the raw corpus, count a hold as a new success, or
claim Jev improves quality based on this repair.

Acceptance scenarios: standalone successful native call is recognized; a
pipeline, echo, failed result or unavailable result cannot satisfy verification.
RED: one missing-helper failure and one passing existing matcher regression.
GREEN: 23 focused workflow/cohort/native checks passed in 0.23 seconds.
Independent review: 41 related checks passed. Full package suite: 1078 passed in
424.01 seconds; TypeScript, nineteen packed workspace manifests, target dry pack
and diff checks passed.

Next actual-project comparison must preserve this stricter execution provenance
in both off/on arms, retain any missing-provenance failure, and compare useful
knowledge, mistaken learning, constraint behavior, cost and duration. Improving
the benchmark is a prerequisite for credible measurement, not goal completion.

The new six-arm experiment is live at
`/Users/FradSer/.cache/pi-continual-learning/docker/20261007T025657Z`.
The initial build attempt stopped before inference due to a registry EOF;
pulling the same official uv 0.8.22 image restored the build. A read-only interim
check of the first project confirms one exact standalone `pnpm test` call with
its successful linked native result. Final Memory, Harness and recall outcomes
are pending; this is provenance evidence only, not quality improvement.
