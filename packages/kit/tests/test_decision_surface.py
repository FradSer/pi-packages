"""pi-kit's decision surface: typed answers, bounded responses, retry policy,
and failure classification. Driven against a real loopback endpoint, because the
behaviors under contract are the ones only a real endpoint exercises.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FIXTURE = Path(__file__).with_name("decision-surface-fixture.ts")


def run(scenario: str) -> dict[str, object]:
    result = subprocess.run(
        ["bun", str(FIXTURE), scenario],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_a_bounded_question_set_returns_typed_answers() -> None:
    value = run("answers")
    assert value["ok"] is True, value
    assert value["model"] == "jev-1.13.0", value
    answers = value["answers"]
    assert answers["a"] == {"type": "noul", "noul": 0.9}, answers
    assert answers["b"]["confidence"] == 0.8, answers
    assert answers["b"]["probabilities"] == {"yes": 0.9, "no": 0.1}, answers
    # A noul carries no confidence: none is invented for it.
    assert "confidence" not in answers["a"], answers
    assert value["usage"] == {"inputTokens": 12, "outputTokens": 5}, value
    assert value["hits"] == 1, value


def test_a_request_with_no_questions_is_refused_before_the_endpoint() -> None:
    value = run("empty-questions")
    assert value["ok"] is False, value
    assert value["isDecisionError"] is True, value
    assert value["failure"] == "rejected", value
    assert value["hits"] == 0, value


def test_a_silently_missing_answer_is_a_service_fault() -> None:
    value = run("missing-answer")
    assert value["failure"] == "malformed", value
    # The diagnostic names what was missing, so an operator can tell a partial
    # service response from a malformed one.
    assert "omits 1 of 2" in str(value["message"]), value


def test_a_non_object_answer_is_a_service_fault() -> None:
    value = run("non-object-answer")
    assert value["failure"] == "malformed", value


def test_a_response_carrying_no_answers_is_a_service_fault() -> None:
    value = run("no-answers")
    assert value["failure"] == "malformed", value


def test_an_unparseable_response_is_a_service_fault() -> None:
    value = run("not-json")
    assert value["failure"] == "malformed", value


def test_a_rejected_credential_is_not_retried() -> None:
    value = run("unauthorized")
    assert value["failure"] == "unauthorized", value
    assert value["hits"] == 1, value


def test_a_throttled_request_is_retried_and_can_recover() -> None:
    value = run("throttled-once")
    assert value["ok"] is True, value
    assert value["hits"] == 2, value


def test_a_persistently_throttled_request_gives_up_within_its_budget() -> None:
    value = run("throttled")
    assert value["failure"] == "throttled", value
    # One attempt plus the two-attempt retry budget.
    assert value["hits"] == 3, value


def test_an_unreachable_endpoint_is_retried_then_reported() -> None:
    value = run("unreachable")
    assert value["failure"] == "unreachable", value
    assert value["hits"] == 3, value


def test_an_oversized_declared_response_is_refused() -> None:
    value = run("oversize")
    assert value["failure"] == "malformed", value
    assert value["hits"] == 1, value


def test_a_pre_aborted_signal_never_reaches_the_endpoint() -> None:
    value = run("pre-aborted")
    assert value["failure"] == "cancelled", value
    assert value["hits"] == 0, value


def test_cancellation_in_flight_is_reported_as_cancelled() -> None:
    value = run("cancelled")
    assert value["failure"] == "cancelled", value
    # Cancellation is not an outage: it must not be reported as unreachable.
    assert value["failure"] != "unreachable", value


def test_a_slow_endpoint_is_reported_as_a_timeout() -> None:
    value = run("timeout")
    assert value["failure"] == "timeout", value
