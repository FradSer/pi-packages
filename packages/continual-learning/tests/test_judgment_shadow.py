"""Judgment shadow mode: opt-in activation, a bounded projection, an
authoritative selector, and an observation record that carries no user content.

The Judgment transport is exercised over a real loopback server; only the
selector's worker call is stubbed, through the package's established harness
seam. See ``judgment-shadow-harness.ts``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from support import run_bun_script

HARNESS = Path(__file__).with_name("judgment-shadow-harness.ts")


def run(scenario: str) -> dict:
    return run_bun_script(HARNESS, scenario)


# ── Activation ───────────────────────────────────────────────────────────


def test_no_configuration_leaves_judgment_inactive() -> None:
    value = run("inactive")
    assert value["active"] is False, value
    assert value["hits"] == 0, value
    assert value["observationCount"] == 0, value
    assert value["outcome"] == "selected", value


@pytest.mark.parametrize("scenario", ["active-env", "active-file"])
def test_a_resolved_key_activates_judgment(scenario: str) -> None:
    value = run(scenario)
    assert value["active"] is True, value
    assert value["hits"] >= 1, value
    assert value["observationCount"] == 1, value


def test_the_environment_key_takes_precedence_over_the_configured_key() -> None:
    value = run("env-precedence")
    assert value["active"] is True, value
    assert value["auth"] == ["Bearer env-key"], value


@pytest.mark.parametrize(
    ("scenario", "fragment"),
    [
        ("config-unknown-field", "unsupported"),
        ("config-no-key", "api key"),
        ("config-unreadable", "not a regular file"),
    ],
)
def test_a_faulty_configuration_fails_closed_with_a_diagnostic(scenario: str, fragment: str) -> None:
    value = run(scenario)
    assert value["active"] is False, value
    assert fragment in (value["configReason"] or "").lower(), value
    assert value["hits"] == 0, value
    assert value["observationCount"] == 0, value
    # A configuration fault must not change what the run produces.
    assert value["outcome"] == "selected", value


# ── Projection ───────────────────────────────────────────────────────────


def test_only_a_bounded_projection_is_sent() -> None:
    value = run("agreement")
    assert value["wireHasRawToolOutput"] is False, value
    assert value["stateKeys"], value


def test_memory_entries_are_identified_opaquely() -> None:
    value = run("agreement")
    question_ids = value["questionIds"]
    assert "memory_alpha.md" not in question_ids, value
    assert "memory_beta.md" not in question_ids, value
    # The filename may appear as projection data, but never as an answer key.
    assert all(not key.endswith(".md") for key in question_ids), value


def test_an_oversized_request_is_clipped_and_the_index_survives() -> None:
    value = run("projection-bounds")
    assert value["requestTextBytes"] <= 4096, value
    assert value["indexSurvived"] == 2, value


def test_the_projection_carries_a_missing_request_text_well_formed() -> None:
    value = run("agreement")
    assert value["stateKeys"] == [
        "request",
        "harness_events",
        "touched_paths",
        "memory_index",
        "registered_skills",
    ], value


def test_the_projection_carries_no_tool_result_content() -> None:
    value = run("agreement")
    # Absent from the wire, not merely clipped: the untrusted half of a Task
    # Slice is never projected in the first place.
    assert value["wireHasRawToolOutput"] is False, value


# ── Containment ──────────────────────────────────────────────────────────


def test_an_instruction_embedded_in_the_task_slice_is_carried_as_data() -> None:
    value = run("containment-slice")
    # The text is present as inert projection data and nothing more: no question
    # key derives from it, and the run's authoritative answer is unaffected.
    assert value["wireHasEmbedded"] is True, value
    assert value["selected"] is None or value["selected"] == [], value
    assert all("confirm" not in key for key in value["questionIds"]), value


def test_a_memory_description_cannot_act_as_an_instruction() -> None:
    value = run("containment-memory")
    assert value["wireHasHostile"] is True, value
    assert all(not key.endswith(".md") for key in value["questionIds"]), value


# ── Shadow authority ─────────────────────────────────────────────────────


def test_a_disagreement_does_not_change_the_selector_decision() -> None:
    value = run("selector-picks")
    assert value["selected"] == ["memory_beta.md"], value
    observation = value["observation"]
    assert observation["selectorSelected"] == ["memory_beta.md"], observation
    assert observation["judgmentSelected"] == ["memory_alpha.md"], observation
    assert observation["agrees"] is False, observation


def test_an_agreement_is_recorded() -> None:
    value = run("agreement")
    observation = value["observation"]
    assert observation["agrees"] is True, observation
    assert observation["judged"] is True, observation


# ── Robustness ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", ["unreachable", "throttled", "malformed"])
def test_a_failing_endpoint_leaves_the_pipeline_unchanged(scenario: str) -> None:
    value = run(scenario)
    assert value["outcome"] == "selected", value
    assert value["error"] is None, value
    observation = value["observation"]
    assert observation["judged"] is False, observation
    assert observation["outcome"] == "failed", observation
    assert observation["reason"], observation


def test_a_single_throttle_is_retried_and_recovers() -> None:
    value = run("throttled-recovers")
    assert value["hits"] == 2, value
    assert value["observation"]["outcome"] == "observed", value
    assert value["observation"]["judged"] is True, value


def test_cancellation_is_recorded_and_leaves_the_run_unchanged() -> None:
    value = run("cancelled")
    observation = value["observation"]
    assert observation["outcome"] == "cancelled", observation
    assert observation["judged"] is False, observation
    assert observation["reason"], observation
    # The observed work is untouched: the run still produced its selection.
    assert value["outcome"] == "selected", value
    assert value["error"] is None, value


# ── Observation record ───────────────────────────────────────────────────


def test_an_observation_carries_judgments_and_agreement_but_no_content() -> None:
    value = run("agreement")
    observation = value["observation"]
    assert observation["contextDigest"] == "a" * 64, observation
    assert observation["model"] == "jev-1.13.0", observation
    assert observation["values"]["scope::m0"] == 0.82, observation
    # A noul carries no confidence of its own, and inventing one would imply a
    # certainty the primitive never stated.
    assert observation["confidences"] == {}, observation
    assert observation["selectorSelected"] == ["memory_alpha.md"], observation
    assert observation["selectorRouted"] == {"memory": True, "harness": False, "agents": False}, observation
    assert "Fix the failing build." not in json_text(observation), observation
    assert "raw tool output" not in json_text(observation), observation


def test_an_observation_reaches_the_caller_without_becoming_authoritative() -> None:
    value = run("agreement")
    assert value["resultJudgment"] == {"model": "jev-1.13.0", "outcome": "observed", "agrees": True}, value


def json_text(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def test_an_observation_is_written_only_under_the_private_agent_root() -> None:
    value = run("agreement")
    assert value["observationUnderPrivateRoot"] is True, value
    assert value["publicMirror"] is None, value
    assert value["publicMirrorJudgmentDir"] is None, value


def test_an_observation_never_lands_inside_a_memory_root() -> None:
    # A Memory root admits only regular `.md` children. A sibling log fails
    # consolidation's privacy validation and aborts the run, which is how this
    # was found: shadow telemetry placed in the Memory root broke learning.
    value = run("agreement")
    assert value["insidePrivateMemoryRoot"] is False, value


# ── Promotion gate ──────────────────────────────────────────────────────


def test_an_empty_log_is_reported_as_unmeasured() -> None:
    value = run("promotion")
    report = value["emptyReport"]
    assert report["observations"] == 0, report
    assert report["agreementRate"] is None, report
    assert report["coverage"] is None, report
    assert report["threshold"] is None, report


def test_the_log_stays_within_its_cap_and_retains_the_newest_records() -> None:
    value = run("rotation")
    rotation = value["rotation"]
    assert rotation["bytes"] <= value["logCapBytes"], rotation
    # The oldest records are the ones dropped, and the newest is the one kept.
    assert rotation["firstIndex"] > 0, rotation
    assert rotation["lastIndex"] == rotation["written"] - 1, rotation
    assert rotation["records"] == rotation["written"] - rotation["firstIndex"], rotation


def test_a_report_proposes_no_threshold() -> None:
    value = run("promotion")
    # A threshold chosen by the reporter would be a guess wearing a number's
    # clothes; the whole point of shadow mode is to replace the guess.
    assert value["emptyReport"]["threshold"] is None, value


# ── Suite hermeticity ───────────────────────────────────────────────────


def test_a_selector_run_cannot_touch_the_callers_real_agent_directory() -> None:
    """Pin the bug this file's sibling shipped.

    Judgment resolves the agent directory. The selector tests run with the
    caller's real one unless they isolate it, so wiring Judgment into the
    selector made ``pytest`` write observation scopes into real ``~/.pi/agent``
    and make live billed calls. Both are asserted here, not assumed.
    """
    import os
    from pathlib import Path

    agent_dir = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
    judgment_dir = agent_dir / "judgment"
    before = set(judgment_dir.glob("*")) if judgment_dir.is_dir() else set()

    value = run("active-env")

    after = set(judgment_dir.glob("*")) if judgment_dir.is_dir() else set()
    assert after == before, f"a unit test added scopes to the real agent directory: {after - before}"
    # The run still produced its own observation, under the isolated directory
    # the harness set, so this asserts isolation rather than mere absence.
    assert value["observationCount"] == 1, value
    assert value["active"] is True, value
