# Audited continuation of the two-pair coverage retest

Given the user explicitly resumed the interrupted two-task experiment,
when Ant Design's original review arm restores its captured partial code/tests,
then reuse the completed one-pass review and deduct all last-observed prior
requests and elapsed time from the shared 80-request/1200-second budget.
Reserve one additional request for interruption uncertainty. Do not reset the
budget or discard the original incremental costs.

The public coverage, native E2E workflow, strict graders and proof boundaries
remain as in POSTFIX-V2.md. This continuation uses the pipefail-corrected fixed
adapter for both arms; preserve the original adapter and interrupted receipts.
No hidden grading feedback was produced for the interrupted attempt or fed to
recovery. Prior final test processes were interrupted and are not completed proof.

- Ant review: recreate pinned original image, apply/capture the original shared
  seed, then reverse that seed and apply the full captured partial patch. Restore
  coverage.json. Supply completed original review and last public tool diagnostics;
  do not initiate another review. First run the fixed adapter on restored work.
- Other three arms: fresh normal V2 workflows from their original shared drafts.
- Combined cost includes old + new completed model usage. Last-observed request
  counts are lower bounds; interrupted usage/billing remain unknown. Report
  cumulative elapsed time separately from new recovery time.
- Recovery starts a fresh model context after an infrastructure interruption.
  Mark this asymmetry explicitly; this is exploratory evidence, not a clean
  held-out comparison. Independent strict grading still uses the same frozen
  grader, image and final full patch for both arms.
- Freeze every recovery input by hash. A complete original review, nonnegative
  remaining budgets, actual shared-start hash and actual Docker patch restoration
  are preconditions. Never silently restart an interrupted valid attempt.
- Run the bounded supervisor in a recorded process session so a lost tool waiter
  does not abandon an unbounded container. Explicit user stops still require
  terminating the recorded supervisor and its exact task-owned containers.
