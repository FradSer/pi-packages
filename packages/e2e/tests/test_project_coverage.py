from __future__ import annotations

import json

from test_e2e_package import PREAMBLE, REPO, run_typescript


def test_goal_contract_has_no_unbound_or_partial_clause_evidence() -> None:
    # Given the current Goal contract, when coverage is audited, then every
    # atomic Then has a registered observation (suite links alone do not count).
    result = run_typescript(PREAMBLE + r'''
      const contract = parseFeature(readFileSync("packages/goal/features/goal.feature", "utf8"));
      const bindings = JSON.parse(readFileSync("packages/e2e/tests/scenario-observation-map.json", "utf8"))["packages/goal/features/goal.feature"];
      const missing = contract.scenarios.filter(s => !bindings[s.name]).map(s => s.name);
      const changed = contract.scenarios.filter(s => bindings[s.name] && JSON.stringify(bindings[s.name].steps) !== JSON.stringify([...s.background, ...s.clauses].map(({kind,text}) => ({kind,text})))).map(s => s.name);
      const partial = contract.scenarios.filter(s => bindings[s.name]?.cases && thenClauses(s).some(c => !bindings[s.name].cases.some(input => input.assertions.some(a => a.clause === c.index)))).map(s => s.name);
      out({missing, changed, partial});
    ''')
    assert result == {"missing": [], "changed": [], "partial": []}


def test_every_legacy_goal_scenario_has_an_explicit_migration() -> None:
    legacy = json.loads((REPO / "packages/e2e/tests/legacy-goal-scenarios.json").read_text())
    migration = json.loads((REPO / "packages/e2e/tests/goal-scenario-migration.json").read_text())
    assert len(legacy["scenarios"]) == 106
    assert {item["legacy"] for item in migration} == {item["name"] for item in legacy["scenarios"]}
    assert all(item["reason"] and item["targets"] for item in migration)
    current = run_typescript(PREAMBLE + r'''
      out({names: parseFeature(readFileSync("packages/goal/features/goal.feature", "utf8")).scenarios.map(s => s.name)});
    ''')["names"]
    assert all(target in current for item in migration for target in item["targets"])


def test_goal_contract_never_certifies_a_constant_assertion() -> None:
    # Given independent expectations, when their assertion expressions are
    # bound, then literal-only comparisons cannot masquerade as observations.
    import re

    bindings = json.loads((REPO / "packages/e2e/tests/scenario-observation-map.json").read_text())["packages/goal/features/goal.feature"]
    constant = re.compile(r"assert\.(?:equal|strictEqual|deepEqual)\(\s*(?:false|true|\d+|\"[^\"]*\")\s*,\s*(?:false|true|\d+|\"[^\"]*\")\s*\)")
    invalid = [name for name, binding in bindings.items() for case in binding.get("cases", []) for check in case["assertions"] if constant.fullmatch(check["source"])]
    assert invalid == []


def test_goal_observation_bindings_freeze_current_harness_expectations() -> None:
    import hashlib

    bindings = json.loads((REPO / "packages/e2e/tests/scenario-observation-map.json").read_text())["packages/goal/features/goal.feature"]
    for binding in bindings.values():
        for case in binding.get("cases", []):
            source = (REPO / case["harness"]).read_bytes()
            assert case["harnessHash"] == hashlib.sha256(source).hexdigest(), case["harness"]
            for predicate in case["assertions"]:
                assert predicate["count"] > 0
                assert predicate["source"] in source.decode()
                assert predicate["assertionId"] == hashlib.sha256(predicate["source"].encode()).hexdigest()


def test_goal_contract_sync_is_read_only_and_current(tmp_path) -> None:
    import os
    import subprocess

    # Given the reviewed bindings, when maintenance runs without --write,
    # then every fresh fixture expectation matches and no contract is rewritten.
    targets = [REPO / "packages/goal/features/goal.feature", REPO / "packages/e2e/tests/scenario-observation-map.json", REPO / "packages/e2e/tests/scenario-behavior-map.json"]
    before = [target.read_bytes() for target in targets]
    run = subprocess.run(["node", "--import", "tsx", "packages/e2e/tests/sync-goal-contracts.mts"], cwd=REPO, env={**os.environ, "TMPDIR": str(tmp_path)}, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr + run.stdout
    assert json.loads(run.stdout) == {"scenarios": 179, "clauses": 718}
    assert [target.read_bytes() for target in targets] == before
