"""Keep the live Memory gate label separated by cause.

A stopped candidate phase, an applied Memory without a Jev judgment, an absent
candidate, and a judged-but-unsupported candidate are different evidence
classes. The live runner must not report them as one kind of Jev error.
"""

from __future__ import annotations

import live_docker_projects as workflow


def receipt(*attempts: dict) -> list[dict]:
    return [{"kind": "learning-pipeline-receipt", "version": 1, "attempts": list(attempts)}]


SUPPORTED_JEV = {
    "stage": "memory",
    "status": "decided",
    "reason": "supported",
    "model": "jev-1.13.0",
    "inputTokens": 12,
}
UNSUPPORTED_JEV = {
    "stage": "memory",
    "status": "decided",
    "reason": "unsupported",
    "model": "jev-1.13.0",
    "inputTokens": 12,
}

CASES = [
    (
        "stopped-memory-phase",
        receipt({"phase": "memory", "attempt": 0, "outcome": "failed", "durationMs": 1, "operations": 0}),
        "Memory phase stopped before any candidate reached Jev semantic review",
        "memory-phase-stopped-before-candidate-review",
    ),
    (
        "applied-without-judgment",
        receipt({"phase": "memory", "attempt": 0, "outcome": "applied", "durationMs": 1, "operations": 1}),
        "Memory was applied without a Jev judgment",
        "missing-jev-review-for-applied-memory",
    ),
    (
        "no-candidate",
        receipt({"phase": "memory", "attempt": 0, "outcome": "noop", "durationMs": 1, "operations": 0}),
        "No candidate reached Jev semantic review",
        "no-candidate-for-jev-review",
    ),
    (
        "harness-telemetry-only",
        receipt(
            {"phase": "memory", "attempt": 0, "outcome": "proposed", "durationMs": 1, "operations": 0},
            {"phase": "harness", "attempt": 0, "outcome": "applied", "durationMs": 1, "operations": 1,
             "jev": {**SUPPORTED_JEV, "stage": "harness"}},
        ),
        "No candidate reached Jev semantic review",
        "no-candidate-for-jev-review",
    ),
    (
        "judged-but-unsupported",
        receipt({"phase": "memory", "attempt": 0, "outcome": "rejected", "durationMs": 1, "operations": 0, "jev": UNSUPPORTED_JEV}),
        "No successful real Jev memory judgment",
        "missing-supported-memory-judgment",
    ),
    (
        "jev-memory-review-unavailable",
        receipt({"phase": "memory", "attempt": 0, "outcome": "proposed", "durationMs": 1, "operations": 0,
                 "jev": {"stage": "memory", "status": "propose", "reason": "unavailable",
                         "model": "jev-1.13.0", "requestCount": 4, "completedRequests": 1}}),
        "Jev memory review was unavailable or incomplete",
        "jev-memory-review-unavailable",
    ),
    (
        "jev-memory-review-refused-preflight",
        receipt({"phase": "memory", "attempt": 0, "outcome": "proposed", "durationMs": 1, "operations": 0,
                 "jev": {"stage": "memory", "status": "propose", "reason": "sensitive",
                         "model": "jev-1.13.0"}}),
        "Jev memory review was refused by a preflight guard",
        "jev-memory-review-refused-preflight",
    ),
]


def test_gate_labels_each_stop_cause_distinctly() -> None:
    # Given a Memory outcome class, When the gate labels it for Jev mode "on",
    # Then the label names that class and never reuses another class's label.
    for name, receipts, expected, _check in CASES:
        assert workflow.memory_gate_failure(receipts, "on") == expected, name
    labels = [workflow.memory_gate_failure(receipts, "on") for _, receipts, _, _ in CASES]
    # Seven rows carry six cause classes: the no-candidate row and the
    # harness-telemetry-only row share one label on purpose. Every other class
    # keeps its own label, so a preflight refusal or a service failure never
    # reads as a semantic hold.
    assert len(set(labels)) == 6, labels
    assert labels[2] == labels[3] == "No candidate reached Jev semantic review", labels


def test_observed_failed_check_uses_the_specific_label() -> None:
    # Given a stopped Memory phase, When isolated effects are collected,
    # Then the recorded failedCheck names the stopped phase, not a Jev judgment.
    for name, receipts, expected, check in CASES:
        report: dict = {"checks": {}}

        def memory() -> None:
            failure = workflow.memory_gate_failure(receipts, "on")
            assert failure is not None
            raise AssertionError(failure)

        try:
            workflow.observe_learning_effects(report, memory, lambda: None, lambda: None)
        except AssertionError as error:
            assert "Learning effect acceptance failed: memory" in str(error), name
        assert report["phaseObservations"]["memory"]["failedCheck"] == check, name
        assert workflow._EFFECT_FAILURE_CHECKS[expected] == check


def test_supported_judgment_and_disabled_jev_do_not_raise_a_gate() -> None:
    # Given a supported Jev memory judgment, When the gate labels the outcome,
    # Then no failure label exists. Jev mode "off" never gates on Jev.
    supported = receipt(
        {"phase": "memory", "attempt": 0, "outcome": "applied", "durationMs": 1, "operations": 1, "jev": SUPPORTED_JEV}
    )
    assert workflow.memory_gate_failure(supported, "on") is None
    assert workflow.memory_gate_failure(supported, "off") is None
    stopped = receipt({"phase": "memory", "attempt": 0, "outcome": "failed", "durationMs": 1, "operations": 0})
    assert workflow.memory_gate_failure(stopped, "off") is None

def test_an_unavailable_judge_that_applied_memory_is_not_a_missing_judgment() -> None:
    # Requirement: an optional judge that cannot run must not change Memory. An
    # enabled judge that was unavailable leaves the parent's own validated plan to
    # apply, exactly as with Jev off, so the runner reports the availability
    # observation instead of a missing judgment. A judged hold stays its own class,
    # and a preflight refusal stays its own class.
    applied_when_unavailable = [{"attempts": [{"phase": "memory", "outcome": "applied", "operations": 3,
        "jev": {"stage": "memory", "status": "disabled", "reason": "unavailable"}}]}]
    applied_after_timeout = [{"attempts": [{"phase": "memory", "outcome": "applied", "operations": 3,
        "jev": {"stage": "memory", "status": "disabled", "reason": "timeout"}}]}]
    applied_with_no_judgment = [{"attempts": [{"phase": "memory", "outcome": "applied", "operations": 3}]}]
    refused_preflight = [{"attempts": [{"phase": "memory", "outcome": "proposed",
        "jev": {"stage": "memory", "status": "propose", "reason": "bounds"}}]}]
    judged_hold = [{"attempts": [{"phase": "memory", "outcome": "proposed",
        "jev": {"stage": "memory", "status": "propose", "reason": "uncertain"}}]}]

    assert workflow.memory_gate_failure(applied_when_unavailable, "on") is None
    assert workflow.memory_gate_failure(applied_after_timeout, "on") is None
    assert workflow.memory_gate_failure(applied_with_no_judgment, "on") == "Memory was applied without a Jev judgment"
    assert workflow.memory_gate_failure(refused_preflight, "on") == "Jev memory review was refused by a preflight guard"
    assert workflow.memory_gate_failure(judged_hold, "on") == "No successful real Jev memory judgment"
    assert workflow.memory_gate_failure(applied_when_unavailable, "off") is None
