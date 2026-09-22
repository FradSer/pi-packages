from __future__ import annotations

import json
from pathlib import Path

import pytest

from support import CONSOLIDATION, ENGINE, cases, evidence, isolated_run_bun as run_bun, rule, snapshot


@pytest.mark.parametrize('change', [{'action': 'confirm'}, {'action': None}, {'bash': '^different$'}, {'enabled': False}, {'skill': 'known', 'instructions': 'changed'}])
def test_learned_update_cannot_weaken_or_change_selector(change: dict) -> None:
    result = run_bun(f'''
      import {{validateHarnessPlan}} from '{CONSOLIDATION}';import {{ruleRevision}} from '{ENGINE}';
      const original={json.dumps(rule())};const changed={{...original,...{json.dumps(change)}}};
      if(changed.action===null)delete changed.action;
      console.log(JSON.stringify(validateHarnessPlan({{kind:'harness-consolidation-plan',operations:[{{op:'updateRule',rule:changed,cases:{json.dumps(cases())}}}],evidence:{json.dumps(evidence())}}},{{automatic:true,snapshot:{json.dumps(snapshot())},availableSkills:['known'],layers:[{{source:'project',rules:[original]}}],learnedRules:{{learned:ruleRevision(original)}}}})));
    ''')
    assert any('cannot weaken' in error or 'cannot disable' in error for error in result)


def test_auto_update_guidance_only_preserves_match_and_advances_revision(tmp_path: Path) -> None:
    target = tmp_path/'harness.json'
    result = run_bun(f'''
      import fs from 'node:fs';import {{applyHarnessOps,learnedRuleRevisionsFromConfig}} from '{CONSOLIDATION}';import {{ruleRevision}} from '{ENGINE}';
      const target={json.dumps(str(target))},original={json.dumps(rule())};
      fs.writeFileSync(target,JSON.stringify({{rules:[original],learnedRules:{{learned:{{origin:'consolidation',revision:ruleRevision(original)}}}}}}));
      const changed={{...original,message:'Use the validated safe fixture instead.'}};
      const result=await applyHarnessOps(target,[{{op:'updateRule',rule:changed,cases:{json.dumps(cases())}}}],{{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}});
      const config=JSON.parse(fs.readFileSync(target,'utf8'));
      console.log(JSON.stringify({{result,config,revisions:learnedRuleRevisionsFromConfig(config),expected:ruleRevision(changed)}}));
    ''')
    assert result['result']['ok'] and result['result']['applied'] == ['updateRule:learned']
    assert result['revisions']['learned'] == result['expected']
    assert result['config']['rules'][0]['bash'] == rule()['bash']


@pytest.mark.parametrize('selector, positive, negative, quote', [
    ({'skill':'known','instructions':'Use the skill checklist.'}, {'skill':'known'}, {'skill':'other'}, 'For known, use the skill checklist.'),
    ({'text':'Project A','instructions':'Project A is retired.'}, {'text':['Project A status']}, {'text':['Project B status']}, 'Project A is retired.'),
])
def test_automatic_guidance_requires_narrow_evidence_and_executed_cases(selector: dict, positive: dict, negative: dict, quote: str) -> None:
    result = run_bun(f'''
      import {{validateHarnessPlan}} from '{CONSOLIDATION}';
      const make=(quote,negative)=>{{const snapshot={{entries:[{{message:{{role:'user',content:quote}}}}]}};const plan={{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{{id:'guide',...{json.dumps(selector)}}},cases:{{positive:[{json.dumps(positive)}],negative:[negative]}}}}],evidence:[{{index:0,source:'user',quote,count:1}}]}};return validateHarnessPlan(plan,{{automatic:true,snapshot,availableSkills:['known']}})}};
      console.log(JSON.stringify({{valid:make({json.dumps(quote)},{json.dumps(negative)}),broad:make('Apply all conventions everywhere.',{json.dumps(negative)}),badCase:make({json.dumps(quote)},{json.dumps(positive)})}}));
    ''')
    assert result['valid'] == []
    assert any('narrow quoted evidence' in error for error in result['broad'])
    assert any('must remain unmatched' in error for error in result['badCase'])


def test_auto_apply_reloads_all_layers_and_rejects_new_personal_conflict(tmp_path: Path) -> None:
    project=tmp_path/'project'; (project/'.pi').mkdir(parents=True)
    target=project/'.pi/harness.json'
    (project/'.pi/harness.local.json').write_text(json.dumps({'rules':[{'id':'learned','enabled':False}]}))
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{applyHarnessOps}}=await import('{CONSOLIDATION}');
      console.log(JSON.stringify(await applyHarnessOps({json.dumps(str(target))},[{{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(cases())}}}],{{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())},layers:[]}})));
    ''')
    assert not result['ok'] and 'project.local' in result['error']
    assert not target.exists()


@pytest.mark.parametrize('kind', ['symlink','bad-case','invalid-legacy'])
def test_rejected_automatic_application_changes_no_bytes_or_receipts(tmp_path: Path, kind: str) -> None:
    project=tmp_path/'project'; (project/'.pi').mkdir(parents=True)
    target=project/'.pi/harness.json'; run=tmp_path/'run';run.mkdir()
    before=' {"rules":[]}\n'
    if kind == 'invalid-legacy': before=' {"policies":[{"name":"invalid","pattern":"("}]}\n'
    if kind == 'symlink':
        outside=tmp_path/'outside.json';outside.write_text(before);target.symlink_to(outside)
    else: target.write_text(before)
    proposed_cases=cases()
    if kind == 'bad-case': proposed_cases['negative']=[{'bash':'dangerous-fixture'}]
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{applyHarnessConsolidationPlan}}=await import('{CONSOLIDATION}');
      console.log(JSON.stringify(await applyHarnessConsolidationPlan({{
        target:{json.dumps(str(target))},run:{{manifest:{{cwd:{json.dumps(str(project))},runDir:{json.dumps(str(run))},runId:'r',scopeDigest:'s',snapshotDigest:'d'}}}},
        plan:{{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(proposed_cases)}}}],evidence:{json.dumps(evidence())}}},
        validationOptions:{{automatic:true,snapshot:{json.dumps(snapshot())}}}
      }})));
    ''')
    assert result['outcome'] == 'rejected'
    assert target.read_text() == before
    assert list(run.iterdir()) == []


def test_successful_parent_apply_receipts_bind_exact_before_and_after(tmp_path: Path) -> None:
    project=tmp_path/'project';(project/'.pi').mkdir(parents=True)
    target=project/'.pi/harness.json';target.write_text('{"rules":[]}\n')
    run=tmp_path/'run';run.mkdir()
    result=run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';import {{createHash}} from 'node:crypto';
      const {{applyHarnessConsolidationPlan}}=await import('{CONSOLIDATION}');
      const target={json.dumps(str(target))},runDir={json.dumps(str(run))};
      const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');const before=hash(target);
      const result=await applyHarnessConsolidationPlan({{target,run:{{manifest:{{cwd:{json.dumps(str(project))},runDir,runId:'r',scopeDigest:'s',snapshotDigest:'d'}}}},plan:{{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(cases())}}}],evidence:{json.dumps(evidence())}}},validationOptions:{{automatic:true,snapshot:{json.dumps(snapshot())}}}}});
      console.log(JSON.stringify({{result,before,after:hash(target),pre:JSON.parse(fs.readFileSync(path.join(runDir,'harness-pre-receipt.json'),'utf8')),post:JSON.parse(fs.readFileSync(path.join(runDir,'harness-post-receipt.json'),'utf8'))}}));
    ''')
    assert result['result']['outcome'] == 'applied'
    assert result['pre']['digestBefore'] == result['before']
    assert result['post']['digestAfter'] == result['after']
    assert result['post']['applied'] == ['addRule:learned']


def test_automatic_validation_flags_cannot_skip_evidence_or_cases() -> None:
    result=run_bun(f'''
      import {{validateHarnessPlan}} from '{CONSOLIDATION}';
      console.log(JSON.stringify(validateHarnessPlan({{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{json.dumps(rule())}}}]}},{{automatic:true,requireEvidence:false,requireCases:false}})));
    ''')
    assert any('evidence' in error for error in result)
    assert any('positive and negative' in error for error in result)
