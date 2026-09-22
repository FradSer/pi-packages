from __future__ import annotations

import json
from pathlib import Path

import pytest

from support import CONSOLIDATION, ENGINE, cases, evidence, isolated_run_bun as run_bun, rule, snapshot


def test_legacy_layers_have_read_only_adapter_and_non_error_notices() -> None:
    result = run_bun(f'''
      import {{mergeLayers,evaluateBash}} from '{ENGINE}';
      const config=mergeLayers([{{source:'old',policies:[{{name:'old',pattern:'x',reason:'old'}}],disabled:['inherited'],skillPrompts:{{known:{{prompt:'old',target:'system'}}}}}}]);
      console.log(JSON.stringify({{config,decision:evaluateBash(config,'safe')}}));
    ''')
    assert 'policies' not in result['config'] and 'skillPrompts' not in result['config']
    assert result['config']['rules'] == []
    assert result['config']['errors'] == []
    assert any('legacy' in notice for notice in result['config']['notices'])
    assert result['config']['legacy']['policies'][0]['name'] == 'old'
    assert result['decision']['decision'] == 'execute'


def test_automatic_flat_add_writes_revision_bound_provenance(tmp_path: Path) -> None:
    target = tmp_path / '.pi/harness.json'
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(tmp_path / 'agent'))};
      import fs from 'node:fs';
      const {{applyHarnessOps}} = await import('{CONSOLIDATION}');
      import {{ruleRevision}} from '{ENGINE}';
      const rule={json.dumps(rule())};
      const result=await applyHarnessOps({json.dumps(str(target))},[{{op:'addRule',rule,cases:{json.dumps(cases())}}}],{{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}});
      const config=fs.existsSync({json.dumps(str(target))})?JSON.parse(fs.readFileSync({json.dumps(str(target))},'utf8')):null;
      console.log(JSON.stringify({{result,config,revision:ruleRevision(rule)}}));
    ''')
    assert result['result']['ok'] is True
    assert result['config']['rules'] == [rule()]
    assert set(result['config']) == {'rules', 'learnedRules'}
    assert result['config']['learnedRules']['learned']['revision'] == result['revision']


@pytest.mark.parametrize('declaration', [{'id': 'taken', 'enabled': False}, {'id': 'taken', 'bash': '('}, {'id': 'taken', 'skill': 'unknown', 'instructions': 'manual'}])
def test_auto_add_conflicts_with_disabled_and_invalid_ids_in_any_layer(declaration: dict) -> None:
    result = run_bun(f'''
      import {{validateHarnessPlan}} from '{CONSOLIDATION}';
      console.log(JSON.stringify(validateHarnessPlan({{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{json.dumps(rule('taken'))},cases:{json.dumps(cases())}}}],evidence:{json.dumps(evidence())}}},{{automatic:true,snapshot:{json.dumps(snapshot())},layers:[{{source:'user',rules:[{json.dumps(declaration)}]}}]}})));
    ''')
    assert any('already' in error or 'conflict' in error for error in result)


def test_manual_edit_does_not_inherit_old_automatic_ownership(tmp_path: Path) -> None:
    target = tmp_path / 'harness.json'
    result = run_bun(f'''
      import fs from 'node:fs';
      import {{applyHarnessOps}} from '{CONSOLIDATION}';
      import {{ruleRevision}} from '{ENGINE}';
      const original={json.dumps(rule())};
      const edited={{...original,message:'User-owned manual revision'}};
      const before=JSON.stringify({{rules:[edited],learnedRules:{{learned:{{origin:'consolidation',revision:ruleRevision(original)}}}}}});
      fs.writeFileSync({json.dumps(str(target))},before);
      const result=await applyHarnessOps({json.dumps(str(target))},[{{op:'updateRule',rule:{{...original,message:'Overwrite manual'}},cases:{json.dumps(cases())}}}],{{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}});
      console.log(JSON.stringify({{result,unchanged:fs.readFileSync({json.dumps(str(target))},'utf8')===before}}));
    ''')
    assert result['result']['ok'] is False and result['unchanged']
    assert 'revision' in result['result']['error'] or 'manually' in result['result']['error']
