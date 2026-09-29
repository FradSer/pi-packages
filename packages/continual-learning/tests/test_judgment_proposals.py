"""Judging a validated Memory plan's proposals.

The parent applies every proposal exactly as it does today. What is new is that
a decision surface is asked what it makes of each one, and the answers are
recorded — the baseline needed before anyone can ask whether a planner should
produce several candidates and pick one.
"""

from __future__ import annotations

from pathlib import Path

HARNESS = Path(__file__).with_name("judgment-proposal-harness.ts")


def run(scenario: str) -> dict:
    from support import run_bun_script

    return run_bun_script(HARNESS, scenario)


def test_a_validated_plan_is_judged_on_durability_and_generality() -> None:
    value = run("judged")
    assert value["hits"] == 1, value
    ids = value["questionIds"]
    assert "durable::c0" in ids and "durable::c1" in ids, value
    assert "general::c0" in ids and "general::c1" in ids, value
    assert value["stateProposalCount"] == 2, value
    assert value["stateIndexCount"] == 2, value


def test_a_duplicate_question_offers_every_indexed_entry_and_a_no_match() -> None:
    value = run("judged")
    options = value["duplicateOptions"]
    # Opaque ids plus an explicit no-match: without it, "none of these" would
    # have to be expressed by picking the least similar entry.
    assert options == ["m0", "m1", "none"], value
    assert value["filenameAsAnswerKey"] is False, value


def test_proposal_judgments_carry_a_confidence() -> None:
    value = run("judged")
    observation = value["observation"]
    assert observation["judged"] is True, value
    assert observation["model"] == "jev-1.13.0", value
    # A noul has none, so `durable::` is absent; the score and the choice do.
    confidences = observation["confidences"]
    assert confidences.get("general::c0") == 0.71, confidences
    assert confidences.get("duplicate::c1") == 0.64, confidences
    assert "durable::c0" not in confidences, confidences


def test_the_record_reports_what_would_be_kept_without_changing_it() -> None:
    value = run("judged")
    observation = value["observation"]
    assert observation["phase"] == "proposals", value
    assert observation["proposed"] == 2, value
    # c0 is durable (0.82) and general (2.4 >= 2); c1 is neither.
    assert observation["kept"] == ["c0"], value
    assert observation["duplicates"] == ["c1=m0"], value


def test_a_plan_with_no_proposals_makes_no_request() -> None:
    value = run("no-proposals")
    assert value["hits"] == 0, value
    assert value["recordCount"] == 0, value
    assert value["observation"]["judged"] is False, value
    assert value["observation"]["proposed"] == 0, value


def test_an_inactive_judgment_makes_no_request_and_writes_no_record() -> None:
    value = run("inactive")
    assert value["hits"] == 0, value
    assert value["recordCount"] == 0, value
    assert value["observation"]["judged"] is False, value


def test_a_persisted_api_block_activates_proposal_judging_too() -> None:
    value = run("config-file")
    assert value["hits"] == 1, value
    assert value["observation"]["judged"] is True, value
    assert value["recordCount"] == 1, value


def test_a_failing_endpoint_leaves_the_plan_untouched() -> None:
    value = run("unreachable")
    observation = value["observation"]
    assert observation["judged"] is False, value
    assert observation["outcome"] == "failed", value
    # The record still exists, because a lost measurement and a broken service
    # are different facts and only one of them is actionable.
    assert value["recordCount"] == 1, value


def test_proposal_content_is_carried_as_bounded_data() -> None:
    value = run("containment")
    # Present as inert data, absent from the record: proposal content is
    # model-generated and therefore untrusted exactly like a Task Slice.
    assert value["wireHasHostile"] is True, value
    assert value["rawHasHostile"] is False, value
    assert value["rawHasUserQuote"] is False, value
