"""Regression: the Harness probe must not crash on a missing project Harness file.

The iniconfig-on arm failed its Harness phase with FileNotFoundError, because the
probe read `.pi/harness.json` even though no Harness rule had been applied. A
missing file means "no rule", and the acceptance gate must report that, not a
probe error.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import live_docker_projects as workflow


def test_missing_harness_file_means_no_rules(tmp_path) -> None:
    # Given a project with no .pi/harness.json, When the probe reads its rules,
    # Then it reports no rules instead of raising FileNotFoundError.
    assert workflow.read_harness_rules(tmp_path) == []


def test_present_harness_file_returns_its_rules(tmp_path) -> None:
    # Given a project Harness file, When the probe reads its rules, Then it
    # returns exactly the recorded rules.
    harness = tmp_path / ".pi"
    harness.mkdir()
    (harness / "harness.json").write_text(json.dumps({"rules": [{"bash": "git push", "action": "block"}]}))
    assert workflow.read_harness_rules(tmp_path) == [{"bash": "git push", "action": "block"}]


def test_malformed_harness_file_still_raises(tmp_path) -> None:
    # Given a malformed project Harness file, When the probe reads its rules,
    # Then the integrity problem still surfaces.
    harness = tmp_path / ".pi"
    harness.mkdir()
    (harness / "harness.json").write_text("{ not json")
    with pytest.raises(json.JSONDecodeError):
        workflow.read_harness_rules(tmp_path)

def test_coverage_repair_is_accepted_only_when_valid_and_non_empty() -> None:
    # Given a coverage-repaired Harness plan, When the parent decides whether to adopt
    # it, Then it is adopted only when validation passed and at least one rule exists.
    # Measured need: a weak generator produced an empty Harness plan while the task
    # stated a durable prohibition, and the enforcement gate then failed with no rule
    # to apply. Keeping the previous plan on a failed repair is what makes the new
    # path safe.
    from support import run_bun

    value = run_bun(
        """
        import { coverageRepairAccepted } from './packages/continual-learning/extensions/harness-consolidation.ts';
        console.log(JSON.stringify([
          coverageRepairAccepted([], 1),
          coverageRepairAccepted([], 0),
          coverageRepairAccepted(['a rule is missing or protected by another layer'], 1),
          coverageRepairAccepted(['identity-mismatch'], 0),
        ]));
        """
    )
    assert value == [True, False, False, False]


def test_coverage_repair_is_wired_for_both_arms_and_before_the_semantic_gate() -> None:
    # Given the Harness phase wiring, When a screened constraint yields no rule, Then
    # the coverage repair is enabled by the harness policy alone, so it fires whether
    # or not Jev is enabled, and its trigger runs before the semantic gate because an
    # empty plan has no operations for a judge to see.
    source = (Path(__file__).resolve().parents[1] / "extensions" / "inject-memory.ts").read_text(encoding="utf-8")
    coverage_spread = '...(policies.harness === "apply" && screen.harness === true\n            && process.env.PI_COVERAGE_REPAIR === "1" ? { coverageRepair: true } : {}),'
    assert coverage_spread in source
    # Enabled outside the Jev-only spread on purpose, so it cannot be read as a Jev benefit.
    assert source.index(coverage_spread) > source.index("...(jevJudge.enabled ? { validateSemantics:")
    harness = (Path(__file__).resolve().parents[1] / "extensions" / "harness-consolidation.ts").read_text(encoding="utf-8")
    trigger = harness.index("if (opts.coverageRepair && attempts.length === 1")
    assert trigger < harness.index("semanticDecision = verdict.decision;")
    window = harness[trigger:trigger + 2200]
    assert "allowOmissions: false" in window
    assert "coverageRepairAccepted(coverageValidation.errors, coverageOperations)" in window
