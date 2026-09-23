"""Reach the shipped engineering instructions through the real catalog resolver."""

from __future__ import annotations

import re

import pytest

from test_package import run_typescript


@pytest.fixture(scope="module")
def instructions() -> dict[str, object]:
    return run_typescript('''
        import { resolveProcedureBundle } from "./packages/matt-pocock/src/resolver.ts";
        import { routeEntryState, workflowGuidance, workflowRoutes } from "./packages/matt-pocock/src/workflow.ts";
        const bundles = Object.fromEntries(["implement", "code-review"].map(id => [id, resolveProcedureBundle(id)]));
        const guidance = workflowRoutes().map(({ route }) => workflowGuidance(routeEntryState(route, "test-work"), []));
        console.log(JSON.stringify({ bundles, guidance }));
    ''')


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_every_active_workflow_drives_to_completion_and_yields_only_when_blocked(instructions: dict[str, object]) -> None:
    for text in instructions["guidance"]:
        guidance = normalized(text)
        for rule in ("integrated candidate", "blocking reviews", "findings resolved"):
            assert rule in guidance
        # Reaching the end of the work, not the end of one slice, is the finish line.
        assert "Drive the current procedure to its end" in guidance
        assert "Do not end the turn to ask whether to continue" in guidance
        # The old text told the agent to stop whenever only teammate results were out;
        # that instruction is what ended a long task partway through.
        assert "yield with the workflow still active" not in guidance
        assert "Yield only when the remaining work genuinely depends" in guidance


def test_implementation_bundle_scopes_checks_and_freezes_a_candidate(instructions: dict[str, object]) -> None:
    bundle = instructions["bundles"]["implement"]
    text = normalized(bundle["content"])
    for rule in ("one integration owner", "local checks", "safe", "same candidate", "affected evidence", "blocking reviews"):
        assert rule in text
    assert "Run typechecking regularly, single test files regularly" not in text
    assert bundle["byteLength"] <= 64 * 1024


def test_review_only_bundle_returns_findings_without_owning_repairs(instructions: dict[str, object]) -> None:
    text = normalized(instructions["bundles"]["code-review"]["content"])
    for rule in ("Review-only", "return the report", "including REWORK", "without editing", "without waiting for repairs", "Leader or implementation owner"):
        assert rule in text, rule


def test_recheck_bundle_refreshes_brief_before_work_assignment(instructions: dict[str, object]) -> None:
    text = normalized(instructions["bundles"]["code-review"]["content"])
    for rule in ("preserve the prior findings", "authoritative brief", "before reopening", "does not update the description", "candidate fingerprint", "correction delta", "bounded follow-up", "dependsOn"):
        assert rule in text, rule
    assert "with the original brief and findings" not in text


def test_review_bundle_supports_local_spec_and_proportional_review(instructions: dict[str, object]) -> None:
    bundle = instructions["bundles"]["code-review"]
    text = normalized(bundle["content"])
    for rule in ("confirmed conversation", "untracked", "unrelated", "candidate", "one fresh reviewer", "REWORK", "reopen", "root cause"):
        assert rule in text
    for obsolete in (
        "delegate the two independent axes to separate teammates",
        "If they didn't specify one, ask for it",
        "If the teammate facility is available, give each teammate one brief",
    ):
        assert obsolete not in text
    assert "Standards" in text and "Spec" in text and "Refute-before-PASS" in text
    assert bundle["byteLength"] <= 64 * 1024
