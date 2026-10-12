from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from test_e2e_package import PACKAGE, PREAMBLE, REPO, run_typescript


def test_goal_seed_adapter_proves_each_clause_from_command_observations() -> None:
    # Given the project adapter and a fresh no-goal session, when /goal receives
    # a seed, then all three clauses have fresh run-bound deterministic checks.
    result = run_typescript(PREAMBLE + r'''
      const runner = JSON.parse(readFileSync(".e2e/runner.json", "utf8"));
      const result = await executeE2EVerify({
        feature: "packages/goal/features/goal.feature",
        scenario: "/goal hands the model a seed rather than creating a goal",
        runner, offline: true,
      }, undefined, {cwd: process.cwd()});
      if (result.details?.status === "error") throw new Error(JSON.stringify(result));
      out({status: result.details?.status, verified: result.details?.verifiedRun,
        clauses: result.details?.clauses?.map(c => [c.clause, c.status, c.source])});
    ''')
    assert result == {
        "status": "fulfilled", "verified": True,
        "clauses": [[1, "met", "deterministic"], [2, "met", "deterministic"], [3, "met", "deterministic"]],
    }


def test_continual_learning_sensitive_material_adapter_proves_each_clause() -> None:
    # Given the registered learning-controls binding, when the changed scenario
    # is verified, then every Then clause has a fresh deterministic check.
    result = run_typescript(PREAMBLE + r'''
      const runner = JSON.parse(readFileSync(".e2e/runner.json", "utf8"));
      const result = await executeE2EVerify({
        feature: "packages/continual-learning/features/learning-controls.feature",
        scenario: "Sensitive detection refuses credentials instead of ordinary text",
        runner, offline: true,
      }, undefined, {cwd: process.cwd()});
      if (result.details?.status === "error") throw new Error(JSON.stringify(result));
      out({status: result.details?.status, verified: result.details?.verifiedRun,
        clauses: result.details?.clauses?.map(c => [c.clause, c.status, c.source])});
    ''')
    assert result == {
        "status": "fulfilled", "verified": True,
        "clauses": [[1, "met", "deterministic"], [2, "met", "deterministic"], [3, "met", "deterministic"],
                    [4, "met", "deterministic"], [5, "met", "deterministic"]],
    }


def test_observation_bindings_fail_closed_and_unbound_suites_stay_unjudged(tmp_path) -> None:
    # Given a passing linked suite, no producer may turn it into clause proof.
    tests = tmp_path / "packages/e2e/tests"
    tests.mkdir(parents=True)
    shutil.copy(PACKAGE / "tests/run-feature-suites.mjs", tests)
    (tests.parent / "src").symlink_to(PACKAGE / "src", target_is_directory=True)
    (tmp_path / "node_modules").symlink_to(REPO / "node_modules", target_is_directory=True)
    (tmp_path / "package.json").write_text('{"type":"module"}')
    (tests / "test_link.py").write_text("def test_link():\n    assert True\n")
    feature = tmp_path / "test.feature"
    feature.write_text("Feature: Test\nScenario: Observed\nThen actual condition holds\n")
    (tests / "scenario-behavior-map.json").write_text(json.dumps({"test.feature": {"Observed": ["packages/e2e/tests/test_link.py::test_link"]}}))
    producer = "packages/e2e/tests/observe-negative.mts"
    (tmp_path / producer).write_text('console.log(JSON.stringify({observations:{value:false},checks:[{clause:1,path:"value",op:"equals",value:true}]}));')
    (tmp_path / ".e2e").mkdir()
    evidence = tmp_path / "evidence.json"
    env = {**os.environ, "PI_E2E_EVIDENCE_PATH": str(evidence), "PI_E2E_FEATURE_PATH": str(feature), "PI_E2E_SCENARIO_NAME": "Observed"}
    cases = []
    for mode in ("unbound", "unregistered", "changed-clause", "changed-given", "changed-when", "observed-failure"):
        steps = [{"kind": "then", "text": "old condition" if mode == "changed-clause" else "actual condition holds"}]
        if mode in ("changed-given", "changed-when"):
            steps.insert(0, {"kind": mode.removeprefix("changed-"), "text": "a different precondition or action"})
        binding = {} if mode == "unbound" else {"test.feature": {"Observed": {"producer": producer, "steps": steps}}}
        (tests / "scenario-observation-map.json").write_text(json.dumps(binding))
        (tmp_path / ".e2e/runner.json").write_text(json.dumps({"adapterFiles": [] if mode == "unregistered" else [producer]}))
        if evidence.exists():
            evidence.unlink()
        result = subprocess.run(["node", "--import", "tsx", str(tests / "run-feature-suites.mjs")], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
        if mode == "unbound":
            assert result.returncode == 0, result.stderr
            assert "checks" not in json.loads(evidence.read_text())
        elif mode in ("unregistered", "changed-clause", "changed-given", "changed-when"):
            assert result.returncode != 0
            assert not evidence.exists()
        else:
            assert result.returncode == 0, result.stderr
            data = json.loads(evidence.read_text())
            assert data["run"]["observations"]["command"]["value"] is False
            assert data["checks"] == [{"clause": 1, "path": "command.value", "op": "equals", "value": True}]
            verdict = run_typescript(PREAMBLE + f'''
              const targetScenario = firstScenario(parseFeature({json.dumps(feature.read_text())}));
              const observedEvidence = JSON.parse(readFileSync({json.dumps(str(evidence))}, "utf8"));
              const result = await verifyScenario({{scenario: targetScenario, evidence: observedEvidence, offline: true}});
              out({{status: result.verdict.status}});
            ''')
            assert verdict["status"] == "not_fulfilled"
        cases.append(mode)
    assert len(cases) == 6


@pytest.mark.parametrize("mutation", ["creates-goal", "creates-then-releases", "raw-seed", "seed-is-objective", "transcript-only"])
def test_real_command_regressions_are_vetoed_by_observed_checks(tmp_path, mutation) -> None:
    # Given a faulty copy of the real command, when the producer observes it,
    # then its declared checks fail instead of reporting suite-level success.
    goal = tmp_path / "packages/goal/src"
    shutil.copytree(REPO / "packages/goal/src", goal)
    producer = tmp_path / "packages/e2e/tests/observe-goal-seed.mts"
    producer.parent.mkdir(parents=True)
    shutil.copy(PACKAGE / "tests/observe-goal-seed.mts", producer)
    (tmp_path / "node_modules").symlink_to(REPO / "node_modules", target_is_directory=True)
    (tmp_path / "package.json").write_text('{"type":"module"}')
    command = goal / "commands.ts"
    source = command.read_text()
    original = "const request=goalRequest(input);"
    assert source.count(original) == 1
    replacements = {
        "creates-goal": original + '\ncore.store.create({id:"bad",owner:"e2e-seed-observer",objective:input});',
        "creates-then-releases": original + '\ncore.store.create({id:"bad",owner:"e2e-seed-observer",objective:input}); core.store.apply({expectedGoalId:"bad",finish:true,mutate:d=>d});',
        "raw-seed": "const request=input;",
        "seed-is-objective": 'const request=goalRequest(input) + "\\nThe objective must be exactly these typed words: " + input;',
        "transcript-only": original,
    }
    command.write_text(source.replace(original, replacements[mutation]))
    if mutation == "transcript-only":
        procedure = goal / "procedure.ts"
        original_delivery = '{ deliverAs: "followUp", triggerTurn: true }'
        assert procedure.read_text().count(original_delivery) == 1
        procedure.write_text(procedure.read_text().replace(original_delivery, '{ triggerTurn: false }'))
    observed = subprocess.run(["node", "--import", "tsx", str(producer)], cwd=tmp_path,
                              capture_output=True, text=True, timeout=30)
    assert observed.returncode == 0, observed.stderr
    evidence = {"run": {"observations": json.loads(observed.stdout)["observations"]},
                "checks": json.loads(observed.stdout)["checks"]}
    result = run_typescript(PREAMBLE + f'''
      const targetScenario = firstScenario(parseFeature(readFileSync("packages/goal/features/goal.feature", "utf8")));
      const result = await verifyScenario({{scenario: targetScenario, evidence: {json.dumps(evidence)}, offline: true}});
      out({{status: result.verdict.status, unmet: result.verdict.clauses.filter(c => c.status === "unmet").map(c => c.clause)}});
    ''')
    assert result["status"] == "not_fulfilled"
    assert (1 if mutation.startswith("creates-") else 2 if mutation == "transcript-only" else 3) in result["unmet"]
