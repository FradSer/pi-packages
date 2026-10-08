from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_e2e_package import PACKAGE, REPO


@pytest.mark.parametrize("mutation", ["none", "missing", "extra", "changed-source", "repeated", "changed-harness", "false"])
def test_goal_assertion_bindings_reject_mutated_witnesses(tmp_path: Path, mutation: str) -> None:
    # Given a frozen assertion contract, when individual witnesses change,
    # then missing/changed evidence fails closed and false remains false.
    producer = tmp_path / "packages/e2e/tests/observe-goal-harness.mts"
    producer.parent.mkdir(parents=True)
    shutil.copy(PACKAGE / "tests/observe-goal-harness.mts", producer)
    (tmp_path / "node_modules").symlink_to(REPO / "node_modules", target_is_directory=True)
    (tmp_path / "package.json").write_text('{"type":"module"}')
    harness = tmp_path / "packages/goal/tests/goal_fixture.mts"
    harness.parent.mkdir(parents=True)
    witness = {"assertionId": "frozen", "source": "assert.equal(actual, expected)", "matched": mutation != "false", "actual": 3, "expected": 3}
    assertions = [] if mutation == "missing" else [witness]
    if mutation == "extra":
        assertions += [{**witness, "assertionId": "unbound"}]
    if mutation == "changed-source":
        witness["source"] = "assert.ok(true)"
    if mutation == "repeated":
        assertions += [witness.copy()]
    harness.write_text('import {writeFileSync} from "node:fs";\nwriteFileSync(process.env.PI_E2E_ASSERTION_PATH, ' + json.dumps(json.dumps([{"name": "case", "assertions": assertions}])) + ');\n')
    binding = {"producer": str(producer), "cases": [{"harness": "packages/goal/tests/goal_fixture.mts", "case": "case", "harnessHash": hashlib.sha256(harness.read_bytes()).hexdigest(), "assertions": [{"clause": 1, "assertionId": "frozen", "source": "assert.equal(actual, expected)", "count": 1}]}]}
    (producer.parent / "scenario-observation-map.json").write_text(json.dumps({"goal.feature": {"case": binding}}))
    if mutation == "changed-harness":
        harness.write_text(harness.read_text() + "// unreviewed change\n")
    run = subprocess.run(["node", "--import", "tsx", str(producer)], cwd=tmp_path, env={**os.environ, "PI_E2E_FEATURE_PATH": str(tmp_path / "goal.feature"), "PI_E2E_SCENARIO_NAME": "case"}, capture_output=True, text=True, timeout=30)
    if mutation in ("none", "false"):
        assert run.returncode == 0, run.stderr
        observed = json.loads(run.stdout)
        assert observed["observations"]["cases"][0]["assertions"][0]["matched"] is (mutation == "none")
        assert observed["checks"] == [{"clause": 1, "path": "cases[0].assertions[0].matched", "op": "equals", "value": True}]
    else:
        assert run.returncode != 0, run.stdout
        assert not run.stdout.strip()


@pytest.mark.parametrize("mutation", ["symlink-guard", "report-escape", "claim-as-evidence"])
def test_current_contracts_detect_real_runtime_mutations(tmp_path: Path, mutation: str) -> None:
    # Given a copied real runtime, when an authorization/data boundary regresses,
    # then its independent behavior predicates fail instead of certifying it.
    goal = tmp_path / "packages/goal"
    shutil.copytree(REPO / "packages/goal/src", goal / "src")
    shutil.copytree(REPO / "packages/goal/tests", goal / "tests", ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    support = tmp_path / "tests/e2e/support"
    shutil.copytree(REPO / "tests/e2e/support", support)
    (tmp_path / "node_modules").symlink_to(REPO / "node_modules", target_is_directory=True)
    (tmp_path / "package.json").write_text('{"type":"module"}')
    if mutation == "symlink-guard":
        source = goal / "src/store.ts"
        original = "  private assertSafePath(file: string): void {"
        replacement = original + "\n    return;"
        harness = "goal_store.mts"
    elif mutation == "report-escape":
        source = goal / "src/prompt.ts"
        original = 'unmet.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")'
        replacement = "unmet"
        harness = "goal_scheduling.mts"
    else:
        source = goal / "src/core.ts"
        original = "        evidence,\n        cwd: ctx.cwd,"
        replacement = "        evidence: { ...evidence, executorClaim: claim },\n        cwd: ctx.cwd,"
        harness = "goal_completion.mts"
    text = source.read_text()
    assert text.count(original) == 1
    source.write_text(text.replace(original, replacement))
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    result = subprocess.run(["node", "--import", "tsx", str(goal / "tests" / harness)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0, result.stdout
    outcomes = json.loads(result.stdout)
    expected_case = {"symlink-guard": "linked paths refuse mutation", "report-escape": "goal prompts carry the unmet line", "claim-as-evidence": "completion receives recorded executions"}[mutation]
    assert any(line.startswith("FAIL ") and expected_case in line for line in outcomes), outcomes
