from __future__ import annotations

import json
from pathlib import Path

from test_e2e_package import PREAMBLE, run_typescript


def test_all_scenarios_runs_fresh_and_does_not_hide_later_failure(tmp_path: Path) -> None:
    (tmp_path / '.e2e').mkdir()
    (tmp_path / 'test.feature').write_text('Feature: Complete\nScenario: First\nThen value is true\nScenario: Second\nThen value is true\n')
    (tmp_path / 'adapter.mjs').write_text('''
import {writeFileSync,appendFileSync} from 'node:fs';
const scenario = process.env.PI_E2E_SCENARIO_NAME;
appendFileSync('calls.txt', scenario + '\\n');
writeFileSync(process.env.PI_E2E_EVIDENCE_PATH, JSON.stringify({run:{observations:{value:scenario === 'First'}},checks:[{clause:1,path:'value',op:'equals',value:true,step:'save',location:'src/save.ts:12'}]}));
''')
    runner = {'executable': 'node', 'args': ['adapter.mjs'], 'adapterFiles': ['adapter.mjs']}
    (tmp_path / '.e2e/runner.json').write_text(json.dumps(runner))
    result = run_typescript(PREAMBLE + f'''
const result = await executeE2EVerify({{feature:'test.feature', allScenarios:true, runner:{{executable:'node',args:['adapter.mjs']}},offline:true}},undefined,{{cwd:{json.dumps(str(tmp_path))}}});
out(result.structuredContent);
''')
    assert result['status'] == 'not_fulfilled'
    assert result['coverage'] == {'total': 2, 'evaluated': 2, 'passed': 1, 'remaining': ['Second']}
    assert result['nextAction'] == 'repair_code'
    scenarios = result['scenarios']
    assert len(scenarios) == 2 and all(s['verifiedRun'] for s in scenarios)
    finding = scenarios[1]['findings'][0]
    assert finding['action'] == 'repair_code'
    assert finding['check']['observed'] == 'false'
    assert finding['check']['expected'] == 'true'
    assert finding['check']['location'] == 'src/save.ts:12'
    assert (tmp_path / 'calls.txt').read_text().splitlines() == ['First', 'Second']


def test_missing_observation_routes_to_evidence_not_code_repair() -> None:
    result = run_typescript(PREAMBLE + '''
out((await executeE2EVerify({feature:''' + json.dumps(str(Path(__file__).resolve().parents[1] / 'examples/billing.feature')) + ''',offline:true,
evidence:{run:{observations:{}},checks:[{clause:1,path:'plan',op:'equals',value:'Pro'}]}})).structuredContent);
''')
    assert result['nextAction'] == 'collect_evidence'
    finding = result['findings'][0]
    assert finding['action'] == 'collect_evidence'
    assert finding['check']['failureKind'] == 'missing_observation'


def test_all_scenarios_rejects_unscoped_supplied_evidence() -> None:
    result = run_typescript(PREAMBLE + '''
out((await executeE2EVerify({feature:''' + json.dumps(str(Path(__file__).resolve().parents[1] / 'examples/billing.feature')) + ''',allScenarios:true,offline:true,evidence})).structuredContent);
''')
    assert result['status'] == 'error'
    assert 'runner' in result['error']


def test_batch_drift_delivers_no_acceptance_callbacks(tmp_path: Path) -> None:
    (tmp_path / '.e2e').mkdir()
    (tmp_path / 'test.feature').write_text('Feature: Stable\nScenario: First\nThen true\nScenario: Second\nThen true\n')
    (tmp_path / 'adapter.mjs').write_text('''
import {writeFileSync,appendFileSync} from 'node:fs';
if(process.env.PI_E2E_SCENARIO_NAME === 'Second') appendFileSync('adapter.mjs','\\n// drift');
writeFileSync(process.env.PI_E2E_EVIDENCE_PATH, JSON.stringify({run:{observations:{v:true}},checks:[{clause:1,path:'v',op:'equals',value:true}]}));
''')
    (tmp_path / '.e2e/runner.json').write_text(json.dumps({'executable':'node','args':['adapter.mjs'],'adapterFiles':['adapter.mjs']}))
    result = run_typescript(PREAMBLE + f'''
let callbacks=0;
const r=await executeE2EVerify({{feature:'test.feature',allScenarios:true,runner:{{executable:'node',args:['adapter.mjs']}},offline:true}},()=>{{callbacks++}},{{cwd:{json.dumps(str(tmp_path))}}});
out({{...r.structuredContent,callbacks}});
''')
    assert result['status'] == 'error'
    assert 'changed' in result['error']
    assert result['callbacks'] == 0


def test_semantic_uncertainty_and_invalid_checks_never_request_code_repair() -> None:
    result = run_typescript(PREAMBLE + '''
const {findings,nextAction}=await import(''' + json.dumps((Path(__file__).resolve().parents[1] / 'src/guidance.ts').as_uri()) + ''');
const v=(await verifyScenario({scenario,evidence:{run:{observations:{value:'abc'}},checks:[{clause:1,path:'value',op:'matches',value:'['}]},offline:true})).verdict;
const invalid=findings(v,true);
const uncertain=findings({...v,status:'needs_review',clauses:[{clause:1,kind:'then',text:'uncertain',status:'unmet',source:'jev',score:0.56}]},true);
out({invalid,uncertain,action:nextAction(uncertain)});
''')
    assert result['invalid'][0]['check']['failureKind'] == 'invalid_check'
    assert result['invalid'][0]['action'] == 'collect_evidence'
    assert result['uncertain'][0]['action'] == result['action'] == 'collect_evidence'


def test_failed_batch_rerun_withdraws_old_scene_pass(tmp_path: Path) -> None:
    (tmp_path / '.e2e').mkdir()
    (tmp_path / 'test.feature').write_text('Feature: Stable\nScenario: First\nThen true\nScenario: Second\nThen true\n')
    (tmp_path / 'adapter.mjs').write_text('''
import {writeFileSync,existsSync} from 'node:fs';
if(existsSync('fail-marker') && process.env.PI_E2E_SCENARIO_NAME === 'First') process.exit(1);
writeFileSync(process.env.PI_E2E_EVIDENCE_PATH, JSON.stringify({run:{observations:{v:true}},checks:[{clause:1,path:'v',op:'equals',value:true}]}));
''')
    (tmp_path / '.e2e/runner.json').write_text(json.dumps({'executable':'node','args':['adapter.mjs'],'adapterFiles':['adapter.mjs']}))
    result = run_typescript(PREAMBLE + f'''
const {{writeFileSync}}=await import('node:fs');
const gate=new E2EGate();gate.beginTurn('verify test.feature',{json.dumps(str(tmp_path))});
const observer=gate.verificationObserver();
const args={{feature:'test.feature',runner:{{executable:'node',args:['adapter.mjs']}},offline:true}};
await executeE2EVerify({{...args,scenario:'First'}},observer.onVerdict,{{...observer,cwd:{json.dumps(str(tmp_path))}}});
writeFileSync({json.dumps(str(tmp_path / 'fail-marker'))},'fail');
const r=await executeE2EVerify({{...args,allScenarios:true}},observer.onVerdict,{{...observer,cwd:{json.dumps(str(tmp_path))}}});
out({{...r.structuredContent,accepted:gate.isAccepted()}});
''')
    assert result['status'] == 'error'
    assert result['coverage']['remaining'] == ['First']
    assert result['accepted'] is False


def test_illegal_expected_value_is_evidence_problem() -> None:
    result = run_typescript(PREAMBLE + '''
const {findings}=await import(''' + json.dumps((Path(__file__).resolve().parents[1] / 'src/guidance.ts').as_uri()) + ''');
const rows=[];
for(const value of [null,{},[]]) {
 const v=(await verifyScenario({scenario,evidence:{run:{observations:{v:1}},checks:[{clause:1,path:'v',op:'equals',value}]},offline:true})).verdict;
 rows.push(findings(v,true)[0]);
}
out({rows});
''')
    assert all(row['action'] == 'collect_evidence' and row['check']['failureKind'] == 'invalid_check' for row in result['rows'])
