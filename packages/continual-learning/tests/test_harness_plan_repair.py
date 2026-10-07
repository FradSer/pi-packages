"""One bounded repair of a rejected Harness plan.

Three live pipeline runs failed on three different planner defects — a missing
plan, a negative case matching its own rule, and a case list of strings — so
this is a recoverable authoring mistake seen repeatedly, not random noise. The
repair is handed the exact errors and the rejected plan and may change nothing
else: identity, evidence, and the authoritative selected scope still have to
survive revalidation.
"""

from __future__ import annotations

from pathlib import Path

from support import run_bun_script

HARNESS = Path(__file__).with_name("harness-repair-harness.ts")


def run(scenario: str) -> dict:
    return run_bun_script(HARNESS, scenario)


def test_a_rejected_plan_gets_one_repair_attempt_and_is_applied() -> None:
    value = run("repaired")
    assert value["repairRequested"] is True, value
    # Initial plan plus exactly one repair. A second retry would be unbounded
    # spend on a child that is already failing to hold the contract.
    assert value["spawned"] == 2, value
    assert value["ok"] is True, value
    assert value["operations"] == 1, value


def test_a_repair_that_is_still_invalid_fails_the_phase() -> None:
    value = run("repair-also-fails")
    assert value["repairRequested"] is True, value
    assert value["spawned"] == 2, value
    assert value["ok"] is False, value
    # The diagnostic names the real defect, so the failure is actionable rather
    # than a bare "rejected".
    assert "must remain unmatched" in value["detail"], value


def test_the_repair_is_bounded_to_one_attempt() -> None:
    for scenario in ("repaired", "repair-also-fails"):
        assert run(scenario)["spawned"] == 2, (scenario, run(scenario))


def test_repair_worker_keeps_the_captured_consolidation_model() -> None:
    value = run("repair-model")
    assert value["ok"] is True, value
    assert value["spawned"] == 2, value
    assert value["modelArgs"] == ["provider/frozen", "provider/frozen"], value


def test_missing_output_recovery_keeps_the_captured_consolidation_model() -> None:
    value = run("missing-model")
    assert value["ok"] is True, value
    assert value["spawned"] == 2, value
    assert value["modelArgs"] == ["provider/frozen", "provider/frozen"], value


def test_missing_structured_output_gets_one_bounded_recovery() -> None:
    value = run("missing-output")
    assert value["repairRequested"] is True, value
    assert value["spawned"] == 2, value
    assert value["ok"] is True, value
    assert value["operations"] == 1, value
    assert value["modelArgs"] == ["(default)", "(default)"], value
    assert value["usage"] == {"input": 3, "output": 3, "cacheRead": 3, "cacheWrite": 0, "totalTokens": 6, "cost": 0.03}, value
    assert value["repairContainsRawOutput"] is False, value
    assert [attempt["attempt"] for attempt in value["attempts"]] == [0, 1], value
    assert [attempt["outcome"] for attempt in value["attempts"]] == ["rejected", "noop"], value


def test_missing_output_twice_stops_after_one_recovery() -> None:
    value = run("missing-twice")
    assert value["repairRequested"] is True, value
    assert value["spawned"] == 2, value
    assert value["ok"] is False, value
    assert [attempt["outcome"] for attempt in value["attempts"]] == ["rejected", "rejected"], value


def test_missing_output_recovered_with_invalid_plan_gets_no_second_repair() -> None:
    value = run("missing-invalid")
    assert value["repairRequested"] is True, value
    assert value["spawned"] == 2, value
    assert value["ok"] is False, value
    assert "must remain unmatched" in value["detail"], value
    assert [attempt["outcome"] for attempt in value["attempts"]] == ["rejected", "rejected"], value


def test_foreign_or_ambiguous_plans_never_trigger_recovery() -> None:
    for scenario in ("foreign-plan", "ambiguous-plan"):
        value = run(scenario)
        assert value["repairRequested"] is False, (scenario, value)
        assert value["spawned"] == 1, (scenario, value)
        assert value["ok"] is False, (scenario, value)


def test_post_plan_snapshot_failure_marks_pending_attempt_failed() -> None:
    value = run("snapshot-missing")
    assert value["ok"] is False, value
    assert value["spawned"] == 1, value
    assert value["attempts"][-1]["outcome"] == "failed", value


def test_recovery_child_cancellation_is_not_reported_as_transport_failure() -> None:
    value = run("missing-recovery-cancel")
    assert value["ok"] is False, value
    assert value["spawned"] == 2, value
    assert value["attempts"][-1]["outcome"] == "cancelled", value
    assert value["usage"]["input"] == 3, value
    assert value["attempts"][-1]["usage"]["input"] == 2, value


def test_initial_timeout_keeps_usage_from_the_terminated_child() -> None:
    value = run("initial-timeout")
    assert value["ok"] is False, value
    assert value["attempts"][-1]["outcome"] == "failed", value
    assert value["usage"] == {"input": 1, "output": 1, "cacheRead": 1, "cacheWrite": 0, "totalTokens": 2, "cost": 0.01}, value


def test_recovery_timeout_keeps_prior_and_recovery_usage_once() -> None:
    value = run("recovery-timeout")
    assert value["ok"] is False, value
    assert value["spawned"] == 2, value
    assert value["usage"] == {"input": 3, "output": 3, "cacheRead": 3, "cacheWrite": 0, "totalTokens": 6, "cost": 0.03}, value
    assert [attempt["usage"]["input"] for attempt in value["attempts"]] == [1, 2], value


def test_stdout_limit_keeps_usage_from_the_bounded_prefix() -> None:
    value = run("stdout-limit")
    assert value["ok"] is False, value
    assert "stdout exceeded" in value["detail"], value
    assert value["usage"] == {"input": 1, "output": 1, "cacheRead": 1, "cacheWrite": 0, "totalTokens": 2, "cost": 0.01}, value


def test_null_exit_signal_while_current_is_failed_not_cancelled() -> None:
    value = run("crash-null")
    assert value["ok"] is False, value
    assert "cancelled" not in value["detail"].lower(), value
    assert value["attempts"][-1]["outcome"] == "failed", value


def test_invalid_optional_noop_report_is_discarded_without_model_repair() -> None:
    value = run("noop-report")
    assert value["repairRequested"] is False
    assert value["spawned"] == 1
    assert value["ok"] is True
    assert value["operations"] == 0
    assert [attempt["outcome"] for attempt in value["attempts"]] == ["noop"]


def test_semantic_feedback_gets_one_frozen_read_only_repair_and_revalidation() -> None:
    value = run('semantic-repaired')
    assert value['semanticCalls'] == value['spawned'] == 2
    assert value['semanticDecision'] == 'allow' and value['ok']
    assert not value['targetExists']
    assert [a['outcome'] for a in value['attempts']] == ['proposed', 'noop']
    assert [a['jev']['reason'] for a in value['attempts']] == ['uncertain', 'supported']


def test_unknown_service_and_exhausted_repair_budget_keep_proposal() -> None:
    for scenario, spawned in [('semantic-unavailable', 1), ('semantic-off', 1), ('semantic-exhausted', 2), ('semantic-still', 2), ('semantic-empty', 2)]:
        value = run(scenario)
        assert value['ok'] and value['semanticDecision'] == 'propose', value
        assert value['spawned'] == spawned and not value['targetExists'], value
        assert value['directApply']['outcome'] == 'rejected', value
    value = run('semantic-tamper')
    assert not value['ok'] and not value['targetExists']
    assert value['semanticCalls'] == 1


def test_semantic_cancellation_stops_before_repair_and_apply() -> None:
    value = run('semantic-cancel')
    assert not value['ok'] and value['spawned'] == value['semanticCalls'] == 1
    assert not value['targetExists']
    assert value['attempts'][-1]['outcome'] == 'cancelled'
    assert value['attempts'][-1]['jev']['inputTokens'] == 10
    assert value['attempts'][-1]['jev']['estimatedCostUsd'] == 0.00000042


def test_snapshot_changes_during_semantics_or_before_apply_never_write() -> None:
    value = run('semantic-judge-tamper')
    assert not value['ok'] and not value['targetExists']
    assert value['semanticCalls'] == 2
    value = run('semantic-apply-tamper')
    assert value['ok'] and value['directApply']['outcome'] == 'rejected'
    assert not value['targetExists']


def test_optional_report_cannot_discard_valid_rules_or_consume_repair_slot() -> None:
    value = run('report-only')
    assert value['ok'] and value['operations'] == 1, value
    assert value['spawned'] == 1 and not value['repairRequested'], value


def test_semantic_repair_keeps_normalized_plan_when_optional_report_is_invalid() -> None:
    value = run('semantic-report')
    assert value['ok'] and value['semanticDecision'] == 'allow', value
    assert value['spawned'] == value['semanticCalls'] == 2
    assert not value['hasReport'], value


def test_smaller_semantic_repair_retains_exact_omitted_candidate_and_evidence() -> None:
    value = run('semantic-pruned')
    assert value['ok'] and value['semanticDecision'] == 'allow'
    assert value['operations'] == 1 and value['spawned'] == value['semanticCalls'] == 2
    assert value['repairCanOmitUnsupported']
    deferred = value['deferredPlan']
    assert len(deferred['operations']) == len(deferred['evidence']) == 1
    assert deferred['operations'][0]['rule']['id'] == 'no-obsolete-compiler'
    assert deferred['evidence'][0]['index'] == 0
    assert deferred['evidence'][0]['quote'] == 'Never run the retired compiler through bash'
    assert value['storedProposals'] == [deferred]
    assert not value['targetExists']
    held = run('semantic-pruned-still')
    assert held['semanticDecision'] == 'propose' and held['directApply']['outcome'] == 'rejected'
    assert held['deferredPlan']['operations'][0]['rule']['id'] == 'no-obsolete-compiler'
    assert held['storedProposals'] == [held['deferredPlan']]


def test_semantic_repair_cannot_replace_a_rule_identity() -> None:
    value = run('semantic-pruned-foreign')
    assert value['ok'] and value['semanticDecision'] == 'propose'
    assert value['operations'] == 2 and value['semanticCalls'] == 1
    assert value['directApply']['outcome'] == 'rejected' and not value['targetExists']


def test_semantic_repair_cannot_shorten_a_retained_original_quote() -> None:
    value = run('semantic-pruned-requoted')
    assert value['ok'] and value['semanticDecision'] == 'propose'
    assert value['operations'] == 2 and value['semanticCalls'] == 1
    assert value['directApply']['outcome'] == 'rejected' and not value['targetExists']
    assert not value.get('deferredPlan') and not value['storedProposals']


def test_semantic_scope_repair_requests_quote_safe_command_matching() -> None:
    value = run('semantic-still')
    assert value['repairAddressesQuoteScope'] and value['receivedFailureHints']
    assert value['spawned'] == value['semanticCalls'] == 2
    assert value['semanticDecision'] == 'propose'
    assert value['directApply']['outcome'] == 'rejected' and not value['targetExists']


def test_parent_validation_rejections_explain_the_stop_without_candidate_text() -> None:
    # Given initial and repaired rules that fail their executable cases,
    # when the phase stops, both receipt attempts retain controlled reasons.
    value = run('repair-also-fails')
    assert not value['ok'] and value['spawned'] == 2
    for attempt in value['attempts']:
        assert attempt['diagnostic'].startswith('Parent Harness validation: fixtures=')
        assert 'retired-compiler' not in attempt['diagnostic']
    semantic = run('semantic-invalid-cases')
    assert semantic['semanticDecision'] == 'propose'
    assert 'fixtures=' in semantic['attempts'][-1]['diagnostic']
    assert semantic['directApply']['outcome'] == 'rejected' and not semantic['targetExists']


def test_semantic_scope_comes_from_frozen_parent_identity_on_both_attempts() -> None:
    # Given a generated rule and a repair, When the parent invokes semantics,
    # Then both calls receive the frozen cwd/run/scope/evidence binding.
    value = run('semantic-repaired')
    assert value['boundScopeChecks'] == [True, True]
    assert value['semanticDecision'] == 'allow'
    assert not value['targetExists']
