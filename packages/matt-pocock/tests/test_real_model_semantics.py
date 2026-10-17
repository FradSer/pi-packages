"""Semantic acceptance checks for the procedures used by real-model runs."""

from __future__ import annotations

from matt_pocock_helpers import run_typescript


def delivered_procedure_bundles() -> dict[str, str]:
    result = run_typescript(
        """
        import { resolveProcedureDelta } from "./packages/matt-pocock/src/resolver.ts";
        const ids = ["domain-modeling", "code-review", "to-questionnaire", "prototype", "codebase-design", "deslop",
          "grilling", "grill-me", "grill-with-docs", "pr", "retro", "to-tickets", "improve-codebase-architecture"];
        const delivered = Object.fromEntries(ids.map((id) => [
          id, resolveProcedureDelta(id, [], []).content,
        ]));
        console.log(JSON.stringify(delivered));
        """
    )
    return {key: str(value) for key, value in result.items()}


def test_domain_delivery_separates_glossary_vocabulary_from_implementation_and_unknown_policy() -> None:
    bundle = delivered_procedure_bundles()["domain-modeling"]

    assert "totally devoid of implementation details" in bundle
    assert "implementation paths, function behavior, tests" in bundle
    assert "unresolved policy" in bundle
    assert "do not state a universal policy" in bundle.lower()
    assert "Do not add Open questions or Resolutions sections" in bundle


def test_code_review_delivery_blocks_spec_pass_for_unresolved_scope_creep() -> None:
    bundle = delivered_procedure_bundles()["code-review"]

    assert "scope creep" in bundle
    assert "Spec finding" in bundle
    assert "Spec PASS" in bundle
    assert "non-breaking" in bundle
    assert "explicit compatibility requirement" in bundle


def test_questionnaire_delivery_requires_verified_context_and_single_decision_questions() -> None:
    bundle = delivered_procedure_bundles()["to-questionnaire"]

    assert "observed current behavior" in bundle
    assert "target behavior" in bundle
    assert "unresolved decision" in bundle
    assert "one independent decision" in bundle
    assert "do not combine" in bundle.lower()


def test_prototype_delivery_limits_conclusions_to_measured_results() -> None:
    bundle = delivered_procedure_bundles()["prototype"]

    assert "measured results" in bundle
    assert "proposed production choices" in bundle
    assert "unresolved policy" in bundle
    assert "not tested" in bundle


def test_grilling_delivery_keeps_the_required_recommendation_policy() -> None:
    """The question policy is a local contract: a sync must not drop it silently."""
    for capability in ("grilling", "grill-me", "grill-with-docs"):
        bundle = delivered_procedure_bundles()[capability]
        assert "matt_pocock_ask" in bundle, capability
        assert "recommended" in bundle, capability
        assert "waits indefinitely" in bundle or "deadline" in bundle, capability

    grilling = delivered_procedure_bundles()["grilling"]
    assert "required `recommended` value" in grilling
    assert "recommend the option that does not act" in grilling


def test_delivered_procedures_keep_the_written_deliverable_policy() -> None:
    """A procedure whose deliverable is a file must keep that requirement after a sync."""
    bundles = delivered_procedure_bundles()

    assert "do not end the turn until that file exists" in bundles["pr"]
    assert "do not end the turn before it exists" in bundles["to-questionnaire"]
    assert "writes the report and nothing else" in bundles["improve-codebase-architecture"]


def test_design_delivery_separates_sourced_requirements_from_proposed_invariants() -> None:
    bundle = delivered_procedure_bundles()["codebase-design"]

    assert "sourced requirements" in bundle
    assert "proposed invariants" in bundle
    assert "assumptions or unresolved decisions" in bundle


def test_review_requires_reachable_interleaving_for_concurrency_claims() -> None:
    bundle = delivered_procedure_bundles()["code-review"]
    assert "reachable interleaving" in bundle
    assert "actual public API" in bundle
    assert "hypothetical future" in bundle


def test_cleanup_cannot_call_retained_findings_clean() -> None:
    bundle = delivered_procedure_bundles()["deslop"]
    assert "retained finding" in bundle
    assert "readability preference" in bundle
    assert "PARTIAL" in bundle


def test_review_judgement_calls_do_not_erase_unresolved_smells() -> None:
    bundle = delivered_procedure_bundles()["code-review"]
    assert "changes confidence, not the verdict" in bundle
    assert "no lint rule" in bundle


def test_cleanup_records_only_observed_command_failures() -> None:
    bundle = delivered_procedure_bundles()["deslop"]
    assert "actually failed command" in bundle
    assert "unexecuted alternative" in bundle


def test_cleanup_inert_predicate_removal_is_not_a_product_policy_change() -> None:
    bundle = delivered_procedure_bundles()["deslop"]
    assert "Removing a proven inert predicate" in bundle
    assert "does not require changing the spec" in bundle


def test_teaching_existing_application_requires_separate_repair_authorization() -> None:
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "procedures/teach.md").read_text()
    assert "do not modify application source" in text
    assert "separate implementation request" in text
    assert "ask the mission question and wait" in text
