# Acceptance-condition trace against current source

Date: 2026-10-07. Scope: `packages/continual-learning` working tree, read from source,
not from the handoff document.

Focused check: `uv run --no-project --python /opt/homebrew/bin/python3 python -m pytest
packages/continual-learning/tests/test_jev_learning.py
packages/continual-learning/tests/test_empty_memory_routing.py
packages/continual-learning/tests/test_incremental_learning.py
packages/continual-learning/tests/test_independent_memory_partition.py
packages/continual-learning/tests/test_memory_final_verification_transaction.py
packages/continual-learning/tests/test_learning_efficiency.py
packages/continual-learning/tests/test_jev_memory_relations.py
packages/continual-learning/tests/test_jev_cited_evidence.py
packages/continual-learning/tests/test_jev_deadline_research.py -q`
Result: **105 passed in 55.99 s, exit 0.**

The `.feature` files record scenarios. They are named below as the recorded scenario.
The passing check is the pytest test in the same row.

## Condition trace

### 1. Separate directions for durable knowledge and behavioral constraints; Memory metadata is scored

- Source: `extensions/jev-learning.ts:670` asks "Does the evidence contain established
  durable knowledge or a lasting user preference?" and `:673` asks "Does the user evidence
  establish a lasting behavioral restriction or verification requirement?". The two answers
  are separate keys, so both can be true at once. Metadata relevance is scored per entry at
  `:676` with `related_${i}` = "How relevant is this existing Memory metadata to the evidence?".
- Scenario: `features/jev-learning.feature`.
- Passing checks: `test_jev_learning.py::test_jev_directions_relationships_and_failures`,
  `test_jev_learning.py::test_adjacent_relevance_levels_share_one_decision_and_semantic_content_excludes_bookkeeping`,
  `test_incremental_learning.py::test_selector_uses_metadata_only_accepts_all_related_and_writes_each_body_once`,
  `test_learning_efficiency.py::test_equivalent_durable_prohibitions_route_to_memory_and_harness`.
- Verdict: holds.

### 2. Empty index routes straight through; unavailable Jev falls back to the existing selector

- Source: `extensions/incremental-learning.ts:552` sets diagnostic
  `"empty Memory index; parent-routed explicit evidence"`. `extensions/jev-learning.ts:442`
  returns `reason: apiKey ? "unavailable" : "missing-key"` with no client call, and
  `:438` sets `status: fallback` for selection. The production constructor at
  `extensions/inject-memory.ts:1763` passes no flags, so `enabled` is false without config.
- Scenario: `features/incremental-learning.feature`, `features/composed-memory-partition.feature`.
- Passing checks: `test_empty_memory_routing.py::test_empty_memory_routes_explicit_evidence_without_model_and_preserves_dossier`,
  `test_jev_learning.py::test_selector_fallback_and_empty_index_do_not_send_jev_or_drop_memory`,
  `test_incremental_learning.py::test_empty_selection_keeps_memory_enabled_and_builds_empty_scope`.
- Verdict: holds.

### 3. Structural and frozen-verbatim-citation checks precede every judgment

- Source: `extensions/jev-learning.ts:208` `citedMemoryEvidence` and `:217` build the cited
  index set before any question; `:220` `citedHarnessEvidence`; windows are cut at `:241`
  and returned at `:262`; the judge uses the prepared windows at `:710`. Fully cited
  creations are noted at `:763` as already having passed parent permission and privacy.
- Scenario: `features/jev-citation-generation.feature`.
- Passing checks: `test_jev_cited_evidence.py::test_cited_memory_requires_complete_bounded_review`,
  `test_jev_cited_evidence.py::test_cited_memory_preflights_uncited_privacy_citations_and_bounds`,
  `test_jev_cited_evidence.py::test_cited_review_freezes_every_request_before_first_transport`,
  `test_jev_cited_evidence.py::test_verbatim_harness_explanation_keeps_authority_and_scope_checks`.
- Verdict: holds.

### 4. Independent judgments run in parallel; body-dependent judgments wait

- Source: parallel batches use `Promise.all` at `extensions/jev-learning.ts:462`, `:573`,
  `:626`, and `:846`. Body-dependent work is ordered after the relation step in
  `extensions/inject-memory.ts:1543` (relations telemetry) and `:1547` (readiness telemetry).
- Scenario: `features/jev-memory-relations.feature`, `features/jev-composed-readiness-research.feature`.
- Passing checks: `test_jev_memory_relations.py::test_relation_transport_handles_every_original_pair_with_bounded_concurrency`,
  `test_jev_memory_relations.py::test_existing_memory_checklist_is_required_and_its_body_remains_bound`,
  `test_jev_learning.py::test_parallel_batch_never_accepts_mixed_versions_or_invalid_late_answers`.
- Verdict: holds.

### 5. Explicit Memory requirement is always handled; low confidence is neither dropped nor allowed to change Harness

- Source: `extensions/inject-memory.ts:7` states that `/memory <request>` learns explicit
  Memory; `:1921` states that an explicit request always reaches selection but does not
  force it; `:2346` keeps an explicit Memory request from changing Harness or AGENTS.md.
  Low confidence maps to `uncertain` in the reason union at `extensions/jev-learning.ts:28`
  and to a repair attempt at `extensions/inject-memory.ts:1582`.
- Scenario: `features/manual-memory-request.feature`.
- Passing checks: `test_jev_learning.py::test_parent_checks_precede_jev_and_explicit_memory_is_never_silently_dropped`,
  `test_learning_efficiency.py::test_automatic_screen_keeps_explicit_knowledge_and_validation_opportunities`,
  `test_learning_efficiency.py::test_manual_selector_decline_survives_tool_only_signals`.
- Verdict: holds.

### 6. Uncertainty, timeout, and unavailability never release a constraint; the reason is kept and the code falls back or proposes

- Source: `extensions/jev-learning.ts:28` carries the reasons `uncertain`, `unavailable`,
  `timeout`, `cancelled`; `:438` returns `status: propose` for non-selection stages and
  `:506` maps `APITimeoutError` to `timeout` and other errors to `unavailable`; `:431`
  sets `maxRetries: 0` so no hidden retry invents a result.
- Scenario: `features/jev-deadline-research.feature`, `features/learning-recovery.feature`.
- Passing checks: `test_jev_learning.py::test_http_failures_keep_only_trusted_status_and_preserve_proposal`,
  `test_jev_learning.py::test_finite_git_proof_never_bypasses_semantic_holds_or_service_failure`,
  `test_jev_memory_relations.py::test_partial_service_failure_keeps_lower_bound_usage_and_returns_no_proof`,
  `test_jev_memory_relations.py::test_relation_timeout_and_inflight_cancellation_return_no_proof`,
  `test_incremental_learning.py::test_selector_timeout_is_cancelled_without_dossier_or_fallback`.
- Verdict: holds. The retained on-arm run is a live example: a transport failure produced
  `unavailable` rather than a released constraint, and no Memory was written.
- Gap: the parent receipt for that same failure records no reason. See gap A below.

### 7. Parent keeps write authority, transactions, and freshness checks; Jev never writes, reclassifies privacy, or bypasses Harness

- Source: `extensions/independent-memory-partition.ts:13` returns
  `writeAuthorized: false` (also `:15`, `:56`), and `extensions/jev-memory-readiness.ts:21`
  does the same. The memory attempt is recorded only by the parent at
  `extensions/inject-memory.ts:1714`. Freshness is proved by
  `assertSemanticInputsFrozen()` and the `selectedSourceDigest` hash block at
  `extensions/inject-memory.ts:1938`. Final verification sits inside the rollback
  transaction in `extensions/consolidation-run.ts` and is exercised by
  `features/memory-final-verification-transaction.feature`.
- Scenario: `features/independent-memory-native-parent.feature`,
  `features/memory-final-verification-transaction.feature`.
- Passing checks: `test_independent_memory_partition.py::test_original_supported_indexes_are_partitioned_without_write_authority`,
  `test_independent_memory_partition.py::test_stale_missing_or_forged_checks_cannot_authorize_subset`,
  `test_jev_memory_relations.py::test_relation_observation_uses_frozen_question_and_never_grants_write_authority`,
  `test_memory_final_verification_transaction.py::test_final_verification_rejection_and_cancellation_roll_back_real_writes`,
  `test_independent_memory_parent_pipeline.py::test_preservation_failure_and_evidence_tamper_prevent_all_subset_writes`.
- Verdict: holds.

### 8. Receipts state direction, chosen Memory, stop or fallback reason, applied result, Jev latency, and version, with no sensitive verbatim

- Source: `extensions/learning-efficiency.ts:341` `buildLearningReceipt`; the field is a
  controlled parent diagnostic at `:28-29` ("never raw worker stderr or model output");
  validation at `:407`; rendering at `:455` and `${attempt.phase} reason` at `:467`. Jev
  latency and status arrive through the `jev` field written at
  `extensions/inject-memory.ts:1724`.
- Scenario: `features/learning-efficiency.feature`.
- Passing checks: `test_learning_efficiency.py::test_receipt_reports_result_and_cost`,
  `test_learning_efficiency.py::test_summary_marks_zero_provider_cost_with_nonzero_usage_unavailable`,
  `test_learning_efficiency.py::test_mixed_priced_and_unavailable_attempts_keep_cost_unavailable`,
  `test_jev_learning.py::test_all_candidate_failures_are_reported_without_partial_permission`.
- Verdict: partially holds. Direction, applied result, usage, cost, and version pass. The
  stop or fallback reason does not hold for a failed memory attempt without Jev telemetry.
  See gap A.

## Gaps

### Gap A — a failed memory attempt can record no stop or fallback reason

- Evidence: `extensions/inject-memory.ts:1714-1723` writes `diagnostic` only in the
  `...(jev ? { jev, diagnostic: \`Jev ${jev.status}: ${jev.reason}\` } : {})` branch. When
  the worker fails before any Jev judgment exists, no reason is written.
- Real example: the retained receipt in
  `~/.cache/pi-continual-learning/docker/20261007T025657Z/handoff-retained-yocto-queue-on/`
  has memory `outcome: failed`, `durationMs: 26984`, `operations: 0`, and no reason field.
- Requirement at risk: a receipt must state the stop or fallback reason.
- Also affected: `extensions/inject-memory.ts:1577`, `:1870`, `:1970` push `failed` attempts
  without a reason.
- Coverage gap: no test asserts that a failed memory attempt carries a controlled reason.
- Proposed fix: write a controlled reason for a failed attempt when Jev telemetry is absent,
  chosen from parent-visible state only, and never from worker stderr or model text.
- Status: **closed** in this session. `memoryStopReason(...)` is exported at
  `extensions/inject-memory.ts` (next to `plannerFailureReason`), with the fixed vocabulary
  `memory planner timed out`, `memory planner exceeded the output limit`, `memory planner
  model error`, `memory planner produced no usable plan`, `memory consolidation verification
  failed`. `memoryStopFlags` is set in three failure sites and the attempt push writes the
  reason when Jev telemetry is absent and the attempt outcome is `failed`.
- RED evidence: `test_inject_memory_extension.py::test_memory_stop_reason_is_a_fixed_vocabulary_without_worker_text`
  failed with `Export named 'memoryStopReason' not found` before the change.
- GREEN evidence: 58 passed in 15.37 s for `test_memory_gate_failure_labels.py` plus
  `test_inject_memory_extension.py`; the full package suite reported 1082 passed in 408.52 s;
  `pnpm typecheck` exit 0.
- Limit: the push-site condition is verified by typecheck, the full suite, and the new
  vocabulary test. No test drives a real failing worker through the parent pipeline in this
  selection, so the wiring is reviewed rather than executed end to end.

### Gap B — the runner gate does not distinguish a generator failure from a Jev judgment failure

- Evidence: `tests/live_docker_projects.py:190` maps the message
  "No successful real Jev memory judgment" to `missing-supported-memory-judgment`. That
  gate fires when no candidate was generated at all, as in the retained run, because no
  candidate means no Jev judgment.
- Requirement at risk: the work must not treat a service failure, a missing Jev receipt, a
  candidate-generation failure, and an unexecuted probe as one kind of judgment error.
- Coverage gap: no test asserts a distinct label for a service or generator failure.
- Proposed fix: in the memory observation, derive the failure label from the receipt
  instead of the message alone, so a missing candidate records a distinct check such as
  `missing-candidate-generation`, while a real judged-and-unsupported candidate keeps
  `missing-supported-memory-judgment`. The arm must still fail; only the label changes.
- Status: **closed** in this session. The gate is now
  `memory_gate_failure(receipts, jev_mode)` in `tests/live_docker_projects.py`, and the
  checks map adds `memory-phase-stopped-before-candidate-review`,
  `missing-jev-review-for-applied-memory`, and `no-candidate-for-jev-review` next to the
  existing `missing-supported-memory-judgment`. Every case that failed before still fails;
  only the label is more specific.
- RED evidence: the three tests in `test_memory_gate_failure_labels.py` failed with
  `AttributeError: module 'live_docker_projects' has no attribute 'memory_gate_failure'`
  before the change.
- GREEN evidence: 58 passed in 15.37 s; full suite 1082 passed.

## Independent review of the gap fixes

A separate child with no implementation history reviewed the diff read-only. It
found two minor issues and two notes. All action already taken is recorded here.

| Finding | Severity | Action |
| --- | --- | --- |
| `memoryStopReason` could attach to an attempt recorded `rejected` when the structural repair sets its own attempt and the run then fails with no Jev telemetry. The attempt object could disagree with itself. | minor | Fixed. The outcome expression is now computed once as `attemptOutcome`, and the new exported `memoryAttemptDiagnostic({outcome, jev, stopReason})` returns the controlled reason only when that recorded outcome is `failed`. A test covers `failed`, `rejected`, `cancelled`, `applied`, `proposed`, and both Jev shapes. |
| The gate collected Jev telemetry across all phases, so a memory phase with no Jev review but a harness judgment reused the unsupported-judgment label. | minor | Fixed. The absent-candidate test now uses memory-stage Jev attempts only, so the label separates "no memory candidate reached review" from "a memory candidate was judged and unsupported". |
| No test coupled the push-site guard to the outcome expression. | minor | Fixed by the `memoryAttemptDiagnostic` test above. |
| Claimed `type(inputTokens) is int` was stricter than the old check. | note | No change. The original memory gate already used `type(...) is int`; the reviewer compared it with the harness gate's own predicate. |
| `realJevParticipation` is set only after the memory gate passes. | note | No change. The original code set the flag after its assert in the same way. |
| An `outputLimit` cause can be masked by a `modelError` cause at the planner-failure site. | note | Accepted as a limit. The receipt records one controlled reason, not a list. |

Verification after the review fixes: focused selection 75 passed in 16.10 s;
`pnpm typecheck` exit 0. The full suite is deferred until the running batch
finishes, because a CPU-heavy run during the batch could inflate the latency
measure of the arm in flight.

The running batch image was built before these review refinements. Its receipt
labels come from the earlier first-pass code. The refinements change evidence
presentation and the gate label, not the learning pipeline's decisions, so the
batch still measures the same Jev behavior. This limit is recorded for the
results file.

## Honest limits of this trace

- The trace covers code paths and their tests. It is not a quality measurement, and it is
  not evidence that Jev improves learning.
- The `.feature` files are cited as recorded scenarios. These `.feature` files are not all
  executed directly by this pytest selection; the passing check in each row is the named
  pytest test.
- Conditions 6 and 8 are proven for the paths the tests exercise, and Gap A is now closed
  for the receipt path.
- No default-off claim is made here for the composed and independent strategies beyond the
  constructor check noted in condition 2. That claim belongs to the net-benefit step.