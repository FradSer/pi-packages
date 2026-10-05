from __future__ import annotations

import tempfile

from support import isolated_run_bun


def test_empty_memory_routes_explicit_evidence_without_model_and_preserves_dossier() -> None:
    with tempfile.TemporaryDirectory(prefix='empty-memory-routing-') as temporary:
        result = isolated_run_bun(r'''
          import {mock} from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import {execFileSync} from 'node:child_process';
          const cwd=path.join(process.env.TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
          let calls=0;
          const kit=await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{
            calls++;return {text:'INVALID_SELECTOR',exitCode:0,stderr:'',cancelled:false};
          }}));
          const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const slice={kind:'learning-task-slice',version:1,entries:[{message:{role:'user',content:
            'Remember for future tasks: the verified command is pnpm test. Never run git push.'}}]};
          const run=(name,taskSlice=slice,extra={})=>selectIncrementalLearning({cwd,taskSlice,contextDigest:'frozen-digest',
            outputDir:path.join(process.env.TEST_ROOT,name),allowEmptyIndexRouting:true,...extra});
          const cold=await run('cold');
          const dossier=cold.dossierPath?JSON.parse(fs.readFileSync(cold.dossierPath,'utf8')):null;
          const coldCalls=calls;
          const requested=await run('requested',{...slice,entries:[{message:{role:'user',content:'A means B.'}}]},{memoryOnly:true});
          const requestCalls=calls;
          const ambiguous=await run('ambiguous',{...slice,entries:[{message:{role:'user',content:'Inspect this task.'}}]});
          fs.mkdirSync(path.join(cwd,'.memory'));
          fs.writeFileSync(path.join(cwd,'.memory','known.md'),'---\nname: known\ndescription: Known project fact\ntype: project\n---\nBody\n');
          const existing=await run('existing');
          const cancelled=await run('cancelled',slice,{signal:AbortSignal.abort()});
          console.log(JSON.stringify({cold:cold.outcome,coldCalls,dossier,coldUsage:cold.usage??null,
            diagnostic:cold.diagnostic,requestCalls,requested:requested.selection,
            ambiguous:ambiguous.outcome,existing:existing.outcome,calls,cancelled:cancelled.outcome}));
        ''', {"TEST_ROOT": temporary})
    assert result['cold'] == 'selected'
    assert result['coldCalls'] == 0 and result['requestCalls'] == 0
    assert result['coldUsage'] is None
    assert result['dossier']['contextDigest'] == 'frozen-digest'
    assert result['dossier']['selectedMemories'] == []
    selection = result['dossier']['selection']
    assert selection['selected'] == [] and selection['memory'] and selection['harness'] and not selection['agents']
    assert result['requested']['memory'] and not result['requested']['harness'] and not result['requested']['agents']
    assert result['ambiguous'] == result['existing'] == 'failed'
    assert result['cancelled'] == 'cancelled' and result['calls'] == 2
    assert result['diagnostic'] == 'empty Memory index; parent-routed explicit evidence'
