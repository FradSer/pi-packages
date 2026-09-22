from __future__ import annotations

import json
from pathlib import Path

import pytest

from support import CONSOLIDATION, cases, evidence, isolated_run_bun as run_bun, rule, snapshot


@pytest.mark.parametrize('pipeline', [False, True])
@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('external_change', [False, True])
def test_readback_failure_restores_only_identifiable_parent_write(tmp_path: Path, pipeline: bool, existing: bool, external_change: bool) -> None:
    project=tmp_path/'project'; (project/'.pi').mkdir(parents=True)
    target=project/'.pi/harness.json'; run=tmp_path/'run'; run.mkdir()
    before='  {"rules": []}\n'
    if existing: target.write_text(before)
    external=' {"rules":[{"id":"external","text":"topic","instructions":"External edit"}]}\n'
    result=run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import {{mock}} from 'bun:test';import fs from 'node:fs';import fsp from 'node:fs/promises';
      const target={json.dumps(str(target))};let written=false,failed=false;
      const realRename=fsp.rename.bind(fsp),realReadFile=fsp.readFile.bind(fsp);
      const patched={{...fsp,
        rename:async(from,to)=>{{await realRename(from,to);if(String(to)===target)written=true}},
        readFile:async(file,...args)=>{{
          if(String(file)===target&&written&&!failed){{
            failed=true;
            if({json.dumps(external_change)})fs.writeFileSync(target,{json.dumps(external)});
            throw new Error('injected post-replacement readback failure');
          }}
          return realReadFile(file,...args);
        }}
      }};
      mock.module('node:fs/promises',()=>({{...patched,default:patched}}));
      const {{applyHarnessOps,applyHarnessConsolidationPlan}}=await import('{CONSOLIDATION}');
      const operations=[{{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(cases())}}}];
      const validationOptions={{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}};
      const result={json.dumps(pipeline)}?await applyHarnessConsolidationPlan({{
        target,run:{{manifest:{{cwd:{json.dumps(str(project))},runDir:{json.dumps(str(run))},runId:'r',scopeDigest:'s',snapshotDigest:'d'}}}},
        plan:{{kind:'harness-consolidation-plan',operations,evidence:validationOptions.evidence}},validationOptions
      }}):await applyHarnessOps(target,operations,validationOptions);
      console.log(JSON.stringify({{result,failed,bytes:fs.existsSync(target)?fs.readFileSync(target,'utf8'):null,postReceipt:fs.existsSync({json.dumps(str(run/'harness-post-receipt.json'))})}}));
    ''')
    assert result['failed'] is True
    assert (result['result'].get('outcome') == 'rejected') if pipeline else result['result']['ok'] is False
    assert 'injected post-replacement readback failure' in result['result']['error']
    assert result['bytes'] == (external if external_change else before if existing else None)
    assert result['postReceipt'] is False
