# Shared-draft E2E versus one-review repair

Given the same eight frozen tasks and each task's prior no-plugin draft,
when two fresh Docker Pi sessions independently receive that exact draft,
then compare independent strict completion and incremental post-draft cost.
No new drafts, outcome-based substitutions or hidden-grader feedback are allowed.
The user explicitly selected all eight pairs on 2026-10-09.

- Model: cli-proxy/opencode/deepseek-v4.1-flash, high thinking; Pi 1.0.4.
- Each workflow shares 1200 seconds and 80 inference requests across its initial
  verification/review and repair. Setup and final independent grading are
  reported separately. Alternate arm order by original sample index.
- E2E: first execute the real packed plugin's executeE2EVerify API inside the
  disposable Docker project, using the fixed authorized adapter and offline
  deterministic checks. This requires no model request. Then DeepSeek repairs
  using actual bounded diagnostics, with only E2E activated in native Pi.
  Additional native verification calls are retained and counted separately.
- Review: one read-only DeepSeek review phase (at most 300 seconds; no edit,
  shell or E2E tools), followed by DeepSeek repair. Review inspections may require
  multiple inference requests. No second reviewer. An incomplete review remains
  explicitly incomplete; it is not excluded because it is unsuccessful.
- Both repair agents may run public tests. Neither sees oracle patches, task IDs,
  hidden tests, old hidden outcomes or the other workflow's findings.
- A tool-start alone is not completed verification. Distinguish initial plugin
  execution, fresh proof, repair execution, and post-repair verification.
- Stage handoff kills and acknowledges all prior-stage sandbox descendants,
  including detached test processes, before repair starts. Shared deadlines include
  this cleanup. Remote provider cancellation and billing remain unverified.
- Frozen public commands are regression checks, not full requirement coverage.
  Their feasibility limits, including Ruff under emulation, remain disclosed.
- Primary completion: unchanged independent official strict grader. Also report
  failure-to-pass repairs, pass-to-fail regressions, unscored timeouts and known
  public/hidden scope mismatches. Test counts are diagnostic, not a percentage
  of all requirements. This reused exploratory sample is not held-out evidence.
- Cost: incremental requests, input/output/cache tokens, Pi-estimated USD,
  initial/repair elapsed time and public-test time. Initial draft cost is shared
  and shown separately. Price estimates are not verified account bills; missing
  prices and interrupted request usage remain unknown, not zero.
- Pin prior image digests and draft hashes. Validate original image HEAD before
  applying a draft; retain the original baseline for final full-patch capture.
  Empty drafts are valid starts. Both workflows' captured starting patches must
  match before any comparative claim.
- Never rerun a completed valid model attempt for a better result. Infrastructure
  invalid starts are retained; all wasted known cost is separately reported.
