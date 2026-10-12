from __future__ import annotations

import json
import tempfile

from support import PKG_DIR, isolated_run_bun


def test_selector_parent_binds_positions_without_transcribed_identity() -> None:
    fixture = json.loads((PKG_DIR / 'tests/fixtures/real-selector-transcription-rejection.json').read_text())
    with tempfile.TemporaryDirectory() as root:
        result = isolated_run_bun(r'''
          import {mock} from 'bun:test';
          import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
          const cwd=path.join(process.env.TEST_ROOT,'project');fs.mkdirSync(cwd,{recursive:true});execFileSync('git',['init','-q',cwd]);
          fs.mkdirSync(path.join(cwd,'.memory'));
          fs.writeFileSync(path.join(cwd,'.memory','contract.md'),'---\nname: contract\ndescription: Actual contract\ntype: project\n---\nEXACT_ORIGINAL_BODY\n');
          fs.writeFileSync(path.join(cwd,'.memory','z-other.md'),'---\nname: other\ndescription: Other contract\ntype: project\n---\nOTHER_BODY\n');
          const kit=await import('./packages/kit/src/index.ts');let reply;let calls=[];
          mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{calls.push(input);return {text:reply,exitCode:0,stderr:'',cancelled:false}}}));
          const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const decision={selectedIndices:[0],memory:true,harness:false,agents:false,reason:'Relevant contract.'};
          const fixture=JSON.parse(process.env.REAL_REJECTION);
          const legacy={kind:'incremental-memory-selection',version:1,contextDigest:fixture.contextDigest,selected:['contract.md'],memory:true,harness:false,agents:false,reason:'Relevant contract.'};
          const cases=[decision,{...decision,selectedIndices:[2]},{...decision,selectedIndices:[-1]},
            {...decision,selectedIndices:[0.5]},{...decision,selectedIndices:['0']},{...decision,selectedIndices:[0,0]},
            {...decision,contextDigest:'stale'},{...decision,selected:['contract.md']},{...decision,memory:'yes'},
            {...decision,reason:'api_key=sk-'+'x'.repeat(48)}, {...decision,agents:undefined},
            {...legacy,contextDigest:'stale'},legacy,{...decision,selectedIndices:[1,0]}];
          const taskSlice={kind:'learning-task-slice',version:1,entries:[{message:{role:'user',content:'Observed current declaration changes.'}}]};
          const results=[];
          for(let i=0;i<cases.length+1;i++){
            reply=i===cases.length?fixture.output:JSON.stringify(cases[i]);calls=[];
            const outputDir=path.join(process.env.TEST_ROOT,'out-'+i);
            const out=await selectIncrementalLearning({cwd,outputDir,contextDigest:fixture.contextDigest,taskSlice,jevJudge:{select:async()=>({telemetry:{status:'disabled'}})}});
            const file=path.join(outputDir,'incremental-learning-dossier.json');
            results.push({out,calls:calls.length,prompt:calls[0]?.prompt,tools:calls[0]?.tools,dossier:fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):null});
          }
          console.log(JSON.stringify({results,taskSlice}));
        ''', env={'TEST_ROOT': root, 'REAL_REJECTION': json.dumps(fixture)})
    rows = result['results']
    assert rows[0]['out']['outcome'] == 'selected'
    dossier = rows[0]['dossier']
    assert dossier['contextDigest'] == fixture['contextDigest']
    assert dossier['selection']['selected'] == ['contract.md']
    assert dossier['taskSlice'] == result['taskSlice']
    assert 'EXACT_ORIGINAL_BODY' in dossier['selectedMemories'][0]['content']
    assert 'selectedIndices' in rows[0]['prompt'] and '"index":0' in rows[0]['prompt']
    assert rows[0]['calls'] == 1 and rows[0]['tools'] == []
    for row in rows[1:12] + rows[14:]:
        assert row['out']['outcome'] == 'failed'
        assert row['calls'] == (2 if row is rows[10] else 1) and row['dossier'] is None
    assert rows[12]['out']['outcome'] == 'selected'  # Existing strict legacy envelope.
    assert rows[13]['dossier']['selection']['selected'] == ['z-other.md', 'contract.md']
