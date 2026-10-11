"""Regression coverage for actual pilot prompt intent, not model-quality claims."""
from test_e2e_package import PREAMBLE, run_typescript


def test_behavior_constraints_preserve_explicit_verification_and_direct_opt_out() -> None:
    result = run_typescript(PREAMBLE + '''
const prompts = [
  "Do not change existing expected behavior merely to make tests pass. Run acceptance for acceptance.feature with e2e_verify.",
  "不要为了通过测试而修改预期行为。请运行 acceptance.feature 的端到端验证。",
  "Never invent test results. Verify acceptance.feature using e2e_verify.",
  "Run acceptance for acceptance.feature. Do not run tests.",
  "Do not run tests. Run acceptance for acceptance.feature.",
  "Review only; do not execute acceptance.feature tests.",
  "Without running tests, inspect acceptance.feature.",
  "只审查 acceptance.feature，不跑测试。",
  "Do not run unrelated unit tests; run acceptance for acceptance.feature.",
  "Run acceptance for acceptance.feature; do not run database migrations.",
  "No e2e tests; inspect acceptance.feature.",
  "No need to run e2e for acceptance.feature.",
  "Do not automatically run acceptance.feature tests.",
  "Do not re-run e2e for acceptance.feature.",
  "Without rerunning tests, inspect acceptance.feature.",
  "Run acceptance for acceptance.feature without executing the tests.",
  "Run acceptance for acceptance.feature. No tests should be changed.",
  "Run acceptance for acceptance.feature. Do not run unrelated unit tests.",
  "Do not run tests and instead run acceptance for acceptance.feature.",
];
const results=prompts.map(prompt=>{
  const gate=new E2EGate(); gate.recordUserPrompt(prompt,"/tmp/project");
  return Boolean(gate.checkBeforeSettle({outcome:"completed",continue:false,entries:[],context:{pendingMessages:[]}} as never,{cwd:"/tmp/project"} as never)?.continue);
}); out(results);
''')
    assert result == [True, True, True, False, True, False, False, False, True, True, False, False, False, False, False, False, True, True, True]


def test_injected_workflow_prioritizes_fresh_focused_checks_and_coverage_limits() -> None:
    result = run_typescript(PREAMBLE + '''
out({early:E2E_CAPABILITY_NOTE.includes("early"),duplicate:E2E_CAPABILITY_NOTE.includes("same suite"),
coverage:E2E_CAPABILITY_NOTE.includes("covered scenarios"),budget:E2E_CAPABILITY_NOTE.includes("budget"),
configured:E2E_CAPABILITY_NOTE.includes(".e2e/runner.json")});
''')
    assert result == dict(early=True, duplicate=True, coverage=True, budget=True, configured=True)


def test_workflow_requires_requirement_mapping_and_stagnation_exit() -> None:
    result = run_typescript(PREAMBLE + '''
out({mapping:E2E_CAPABILITY_NOTE.includes("each public requirement"),
missing:E2E_CAPABILITY_NOTE.includes("uncovered"),
stagnation:E2E_CAPABILITY_NOTE.includes("no new evidence"),
final:E2E_CAPABILITY_NOTE.includes("final changed code")});
''')
    assert result == dict(mapping=True, missing=True, stagnation=True, final=True)
