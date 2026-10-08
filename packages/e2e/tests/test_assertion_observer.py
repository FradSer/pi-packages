from __future__ import annotations

import json

from test_e2e_package import REPO, run_typescript


def test_assertion_observer_records_operands_not_suite_success() -> None:
    # Given two named behavior cases in one harness, when only one is observed,
    # then its exact assertion operands are kept and unrelated cases are absent.
    module = (REPO / "tests/e2e/support/assertion-observer.ts").as_uri()
    result = run_typescript(f'''
      import {{ observedAssert as assert, observeScenario, observedScenarios }} from {json.dumps(module)};
      await observeScenario("registered tools", async () => {{
        const registered = ["create_goal", "get_goal", "update_goal"];
        assert.deepEqual(registered, ["create_goal", "get_goal", "update_goal"]);
        assert.equal(registered.length, 3);
        assert.match(registered.join(","), /get_goal/);
      }});
      const cases = observedScenarios();
      console.log(JSON.stringify({{names: cases.map(c => c.name), assertions: cases[0].assertions}}));
    ''')
    assert result["names"] == ["registered tools"]
    assertions = result["assertions"]
    assert [a["operator"] for a in assertions] == ["deepEqual", "equal", "match"]
    assert assertions[0]["actual"] == ["create_goal", "get_goal", "update_goal"]
    assert assertions[0]["expected"] == ["create_goal", "get_goal", "update_goal"]
    assert assertions[1]["actual"] == 3
    assert all(a["matched"] for a in assertions)


def test_assertion_observer_keeps_failure_and_async_exception_evidence() -> None:
    # Given a mismatching assertion and a rejected operation, when observed,
    # then a failing predicate is retained and assertions still throw normally.
    module = (REPO / "tests/e2e/support/assertion-observer.ts").as_uri()
    result = run_typescript(f'''
      import {{ observedAssert as assert, observeScenario, observedScenarios }} from {json.dumps(module)};
      let failed = false;
      try {{ await observeScenario("bad registration", () => assert.equal(4, 3)); }} catch {{ failed = true; }}
      await observeScenario("refused operation", async () => {{
        await assert.rejects(async () => {{ throw new Error("stale generation"); }}, /stale/);
        assert.throws(() => {{ throw new TypeError("missing value"); }}, TypeError);
      }});
      console.log(JSON.stringify({{failed, cases: observedScenarios()}}));
    ''')
    assert result["failed"] is True
    assert result["cases"][0]["assertions"][0]["matched"] is False
    rejected = result["cases"][1]["assertions"][0]
    assert rejected["operator"] == "rejects"
    assert rejected["actual"]["message"] == "stale generation"
    assert rejected["matched"] is True


def test_assertion_observer_preserves_scenario_identity_across_awaits() -> None:
    module = (REPO / "tests/e2e/support/assertion-observer.ts").as_uri()
    result = run_typescript(f'''
      import {{ observedAssert as assert, observeScenario, observedScenarios }} from {json.dumps(module)};
      let release;
      const ready = new Promise(resolve => release = resolve);
      const first = observeScenario("first", async () => {{ await ready; assert.equal("a", "a"); }});
      await observeScenario("second", () => {{ assert.equal("b", "b"); release(); }});
      await first;
      console.log(JSON.stringify({{cases: observedScenarios().map(c => [c.name, c.assertions.map(a => a.actual)])}}));
    ''')
    assert result["cases"] == [["first", ["a"]], ["second", ["b"]]]
