from support import run_bun


def test_real_duplicate_removes_no_unique_input_and_changes_no_rule_or_evidence() -> None:
    result = run_bun(r'''
      import fs from 'node:fs';
      import {repairDuplicateHarnessCases,previewHarnessRuleCases} from './packages/continual-learning/extensions/harness-consolidation.ts';
      const original=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-harness-duplicate-case.json','utf8')).rejectedPlan;
      const raw=JSON.stringify(original),fixed=repairDuplicateHarnessCases(original);
      const op=fixed.plan.operations[0],prior=original.operations[0];
      const originalInputs=[...prior.cases.positive,...prior.cases.negative].map(x=>x.bash);
      const fixedInputs=[...op.cases.positive,...op.cases.negative].map(x=>x.bash);
      const broad=structuredClone(original);broad.operations[0].rule.bash='.*';
      const noNegative=structuredClone(original);noNegative.operations[0].cases.negative=[{bash:'npm test'}];
      console.log(JSON.stringify({fixed,unchanged:raw===JSON.stringify(original),sameRule:JSON.stringify(prior.rule)===JSON.stringify(op.rule),sameEvidence:JSON.stringify(original.evidence)===JSON.stringify(fixed.plan.evidence),sameInputs:JSON.stringify([...new Set(originalInputs)].sort())===JSON.stringify([...new Set(fixedInputs)].sort()),preview:previewHarnessRuleCases(op.rule,op.cases),broad:repairDuplicateHarnessCases(broad),noNegative:repairDuplicateHarnessCases(noNegative)}));
    ''')
    assert result['unchanged'] and result['sameRule'] and result['sameEvidence'] and result['sameInputs']
    assert len(result['fixed']['corrections']) == 1
    assert result['preview']['passed']
    assert result['broad']['corrections'] == []
    assert result['noNegative']['corrections'] == []


def test_production_normalization_still_requires_semantic_approval_and_retains_failed_plan() -> None:
    from test_harness_plan_repair import run
    for scenario, decision, calls in [('semantic-duplicate-allow', 'allow', 1), ('semantic-duplicate-hold', 'propose', 2)]:
        value = run(scenario)
        assert value['ok'], value
        assert value['semanticDecision'] == decision, value
        assert value['semanticCalls'] == calls, value
        assert all(value['boundScopeChecks'])
        assert len(value['normalizations']) == calls, value
        for record in value['normalizations']:
            proof = record['proof']
            assert record['mode'] == 0o600
            assert len(proof['corrections']) == 1
            assert proof['beforeSha256'] != proof['afterSha256']
            assert proof['originalPlan']['operations'][0]['cases']['negative'][-1]['bash'] == 'retired-compiler build'
        if decision == 'propose':
            assert not value['targetExists']
            assert value['directApply']['outcome'] != 'applied'
