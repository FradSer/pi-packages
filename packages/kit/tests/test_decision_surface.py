"""Five transport contracts; cases share one fixture process per contract."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FIXTURE = Path(__file__).with_name("decision-surface-fixture.ts")


def run(*scenarios: str) -> dict[str, dict[str, object]]:
    result = subprocess.run(["bun", str(FIXTURE), *scenarios], cwd=REPO, capture_output=True,
                            text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    return {value["scenario"]: value for line in result.stdout.splitlines() if line.strip()
            for value in [json.loads(line)]}


def test_typed_answers_and_preflight_validation() -> None:
    cases = run("answers", "empty-questions")
    value = cases["answers"]
    assert value["ok"] is True and value["model"] == "jev-1.13.0", value
    assert value["answers"]["a"] == {"type": "noul", "noul": 0.9}
    assert value["answers"]["b"]["probabilities"] == {"yes": 0.9, "no": 0.1}
    assert value["answers"]["b"]["confidence"] == 0.8
    assert "confidence" not in value["answers"]["a"]
    assert value["usage"] == {"inputTokens": 12, "outputTokens": 5}
    assert value["hits"] == 1
    rejected = cases["empty-questions"]
    assert rejected["failure"] == "rejected" and rejected["isDecisionError"] is True
    assert rejected["hits"] == 0


def test_malformed_and_oversized_response_classes() -> None:
    cases = run("missing-answer", "non-object-answer", "no-answers", "not-json", "oversize")
    for scenario, value in cases.items():
        assert value["failure"] == "malformed", (scenario, value)
        assert value["hits"] == 1, (scenario, value)
    assert "omits 1 of 2" in cases["missing-answer"]["message"]


def test_retry_budget_and_nonretryable_credentials() -> None:
    cases = run("unauthorized", "throttled-once", "throttled", "unreachable")
    assert cases["unauthorized"]["failure"] == "unauthorized"
    assert cases["unauthorized"]["hits"] == 1
    assert cases["throttled-once"]["ok"] is True and cases["throttled-once"]["hits"] == 2
    for scenario, failure in (("throttled", "throttled"), ("unreachable", "unreachable")):
        assert cases[scenario]["failure"] == failure and cases[scenario]["hits"] == 3


def test_cancellation_before_and_during_transport() -> None:
    cases = run("pre-aborted", "cancelled")
    assert cases["pre-aborted"]["failure"] == "cancelled" and cases["pre-aborted"]["hits"] == 0
    assert cases["cancelled"]["failure"] == "cancelled" and cases["cancelled"]["hits"] == 1


def test_request_deadline_is_not_an_outage() -> None:
    value = run("timeout")["timeout"]
    assert value["failure"] == "timeout", value
