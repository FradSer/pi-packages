from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_agents_md_consolidation import js, prepare_extraction_roots, extraction_ops, apply_plan_script

MODULE = './packages/continual-learning/extensions/harness-consolidation.ts'


@pytest.mark.parametrize('asset_only', [False, True])
def test_native_path_aliases_enforce_gates(tmp_path: Path, asset_only: bool) -> None:
    source = r'''
      import register from './packages/continual-learning/extensions/guardrails.ts';
      import path from 'node:path'; import {pathToFileURL} from 'node:url';
      import {createWriteTool} from '@earendil-works/pi-coding-agent';
      const hooks={};
      register({on:(n,f)=>hooks[n]=f,registerCommand(){},registerEntryRenderer(){},getCommands:()=>[]});
      const ctx={cwd:process.env.HOME,hasUI:false};
      const results=[];
      const nativePaths=[];
      const native=createWriteTool(ctx.cwd,{operations:{mkdir:async()=>{},writeFile:async(p)=>nativePaths.push(p)}});
      for(const file of ['harness.local.json','harness.json']) {
        const absolute=path.join(process.env.HOME,'.pi/agent',file);
        for(const alias of ['~/.pi/agent/'+file,'@~/.pi/agent/'+file,'@'+absolute,absolute,'.pi/agent/'+file,'@./.pi/agent/../agent/'+file,pathToFileURL(absolute).href,'@'+pathToFileURL(absolute).href]) {
          await native.execute('probe',{path:alias,content:'{}'});
          if(nativePaths.at(-1)!==absolute) throw new Error('native path mismatch');
          for(const toolName of ['write','edit','read']) {
            const result=await hooks.tool_call({toolName,input:{path:alias,content:'{}',edits:[]}},ctx);
            results.push({file,alias,toolName,result:result??null});
          }
        }
      }
      const spacedCwd=path.join(ctx.cwd,'with space');
      const spacedTarget=path.join(spacedCwd,'.pi/harness.json');
      const spacedNative=createWriteTool(spacedCwd,{operations:{mkdir:async()=>{},writeFile:async(p)=>nativePaths.push(p)}});
      for(const space of ['\u00a0','\u2000','\u200a','\u202f','\u205f','\u3000']) {
        const alias='@'+spacedTarget.replace('with space','with'+space+'space');
        await spacedNative.execute('probe',{path:alias,content:'{}'});
        if(nativePaths.at(-1)!==spacedTarget) throw new Error('native Unicode space mismatch');
        const result=await hooks.tool_call({toolName:'write',input:{path:alias,content:'{}'}},{...ctx,cwd:spacedCwd});
        if(!result?.block) throw new Error('Unicode-space harness alias bypassed gate');
      }
      for(const toolName of ['write','edit']) {
        const result=await hooks.tool_call({toolName,input:{path:'ordinary.txt',content:'plain text',edits:[]}},ctx);
        if(result?.block) throw new Error('unrelated mutation blocked');
      }
      console.log(JSON.stringify(results));
    '''
    env = {'HOME': str(tmp_path), 'PI_CODING_AGENT_DIR': str(tmp_path / '.pi/agent')}
    if asset_only:
        assets = tmp_path / 'assets'
        assets.mkdir()
        (assets / 'README.md').write_text('Asset-only installation fixture')
        env['PI_PACKAGE_DIR'] = str(assets)
    results = js(source, env)
    for row in results:
        if row['toolName'] == 'read':
            assert row['result'] is None
        else:
            assert row['result'] and row['result']['block'], row
            assert ('Use ~/.pi/agent/harness.json for global configuration.' if row['file'] == 'harness.local.json' else ('validated' if row['toolName'] == 'edit' else 'Invalid')) in row['result']['reason']


MALFORMED = [None, [], 'retained', {'skillPrompts': ['retained']}, {'skillPrompts': None}, {'policies': {'retained': True}}, {'disabled': 'retained'}]


@pytest.mark.parametrize('base', MALFORMED)
def test_harness_apply_preserves_malformed_bytes(tmp_path: Path, base: object) -> None:
    target = tmp_path / 'harness.json'
    before = '  ' + json.dumps(base) + '\n'
    target.write_text(before)
    result = js(f"""
      import {{applyHarnessOps}} from '{MODULE}';
      console.log(JSON.stringify(await applyHarnessOps({json.dumps(str(target))}, [{{op:'addSkillPrompt',name:'known',prompt:'guidance',target:'system'}}],new Set(['known']))));
    """)
    assert result['ok'] is False
    assert 'object' in result['error'] or 'array' in result['error']
    assert target.read_text() == before


@pytest.mark.parametrize('base', MALFORMED)
def test_harness_orchestration_rejects_before_receipts(tmp_path: Path, base: object) -> None:
    target = tmp_path / 'harness.json'
    before = '  ' + json.dumps(base) + '\n'
    target.write_text(before)
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    result = js(f"""
      import {{applyHarnessConsolidationPlan}} from '{MODULE}';
      const planning={{
        target:{json.dumps(str(target))},
        run:{{manifest:{{runDir:{json.dumps(str(run_dir))},runId:'test',scopeDigest:'scope',snapshotDigest:'snapshot'}}}},
        plan:{{kind:'harness-consolidation-plan',operations:[{{op:'addSkillPrompt',name:'known',prompt:'guidance',target:'system'}}]}},
        validationOptions:{{availableSkills:new Set(['known']),requireEvidence:false,requireCases:false}}
      }};
      console.log(JSON.stringify(await applyHarnessConsolidationPlan(planning)));
    """)
    assert result['outcome'] == 'rejected'
    assert 'object' in result['error'] or 'array' in result['error']
    assert target.read_text() == before
    assert list(run_dir.iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ['harness.json', 'run']


@pytest.mark.parametrize('base', MALFORMED)
def test_agents_extraction_preserves_malformed_bytes(tmp_path: Path, base: object) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    target = project / '.pi/harness.json'
    before = '  ' + json.dumps(base) + '\n'
    target.write_text(before)
    doc = (project / 'AGENTS.md').read_bytes()
    result = js(apply_plan_script(project, agent, run_dir, [extraction_ops()[1]]), {'PI_CODING_AGENT_DIR': str(agent)})
    assert result['result']['outcome'] == 'failed'
    assert 'object' in result['result']['detail'] or 'array' in result['result']['detail']
    assert target.read_text() == before
    assert (project / 'AGENTS.md').read_bytes() == doc
    assert result['preReceiptExists'] is False


def test_summary_filters_unknown_skills(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    (project / '.pi').mkdir(parents=True)
    (project / '.pi/harness.json').write_text(json.dumps({'skillPrompts': {name: {'prompt': 'guidance', 'target': 'system'} for name in ['known', 'unknown']}}))
    result = js(f"""
      import {{harnessSurfaceSummary}} from '{MODULE}';
      console.log(JSON.stringify(JSON.parse(await harnessSurfaceSummary({json.dumps(str(project))},{json.dumps(str(tmp_path / 'agent'))},new Set(['known'])))));
    """)
    assert result['skillPrompts'] == ['known']
    assert any('unknown' in error for error in result['errors'])
