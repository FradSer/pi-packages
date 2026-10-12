from __future__ import annotations

import tempfile

from support import isolated_run_bun


def test_selector_repairs_only_digest_bound_missing_fields_once() -> None:
    with tempfile.TemporaryDirectory() as root:
        result = isolated_run_bun(r'''
          import { mock } from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import { execFileSync } from 'node:child_process';
          const cwd = path.join(process.env.TEST_ROOT, 'project');
          fs.mkdirSync(cwd, {recursive:true});
          execFileSync('git', ['init', '-q', cwd]);
          const kit = await import('./packages/kit/src/index.ts');
          let replies = [], calls = [];
          const usage = {input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:0.01};
          mock.module('./packages/kit/src/index.ts', () => ({...kit, runPiWorker:async input => {
            calls.push(input); return {text:replies.shift(),exitCode:0,stderr:'',cancelled:false,usage};
          }}));
          const {selectIncrementalLearning} = await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const identity = {kind:'incremental-memory-selection',version:1,contextDigest:'current'};
          const valid = {...identity,selected:[],memory:true,harness:false,agents:false,reason:'metadata only'};
          const cases = [
            [JSON.stringify(identity), JSON.stringify(valid)],
            [JSON.stringify({...identity,selectedEntries:['invented.md']}), JSON.stringify(valid)],
            [JSON.stringify({...identity,contextDigest:'stale'}), JSON.stringify(valid)],
            [JSON.stringify(identity)+'\n'+JSON.stringify(identity), JSON.stringify(valid)],
            [JSON.stringify({...identity,selected:['unknown.md']}), JSON.stringify(valid)],
            [JSON.stringify({...identity,memory:'yes'}), JSON.stringify(valid)],
            [JSON.stringify(identity), JSON.stringify(identity)],
            [JSON.stringify({...identity,api_key:'sk-'+'x'.repeat(48)}), JSON.stringify(valid)],
            [JSON.stringify(identity), JSON.stringify({...identity,api_key:'sk-'+'x'.repeat(48)})],
          ];
          const results = [];
          for (let i=0;i<cases.length;i++) {
            replies = [...cases[i]]; calls = [];
            const outputDir = path.join(process.env.TEST_ROOT, `out-${i}`);
            const out = await selectIncrementalLearning({cwd,outputDir,contextDigest:'current',
              taskSlice:{kind:'learning-task-slice',version:1,entries:[{original:'COMPLETE_ORIGINAL_TASK'}]},
              jevJudge:{select:async()=>({telemetry:{status:'disabled'}})}});
            results.push({out,count:calls.length,unchanged:calls.length===2 && calls[1].prompt.startsWith(calls[0].prompt),
              noTools:calls.every(c=>c.minimal===true && c.tools.length===0),
              dossier:fs.existsSync(path.join(outputDir,'incremental-learning-dossier.json')),
              rejected:fs.existsSync(path.join(outputDir,'selector-rejected.json')),
              sensitiveStored:fs.readdirSync(outputDir).filter(n=>n.startsWith('selector-')).some(n=>fs.readFileSync(path.join(outputDir,n),'utf8').includes('sk-'+'x'.repeat(48)))});
          }
          console.log(JSON.stringify(results));
        ''', env={"TEST_ROOT": root})
    for item in result[:2]:
        assert item["out"]["outcome"] == "selected"
        assert item["count"] == 2 and item["unchanged"] and item["noTools"]
        assert item["rejected"] and item["dossier"]
        assert [a["outcome"] for a in item["out"]["attempts"]] == ["failed", "applied"]
        assert sum(a["usage"]["cost"] for a in item["out"]["attempts"]) == 0.02
        assert item["out"]["usage"]["totalTokens"] == 24
    for item in result[2:6]:
        assert item["out"]["outcome"] == "failed" and item["count"] == 1
        assert not item["dossier"]
    assert result[6]["out"]["outcome"] == "failed" and result[6]["count"] == 2
    assert not result[6]["dossier"]

    assert result[7]["count"] == 1 and result[7]["out"]["outcome"] == "failed"
    assert result[8]["count"] == 2 and result[8]["out"]["outcome"] == "failed"
    assert not result[7]["sensitiveStored"] and not result[8]["sensitiveStored"]


def test_real_position_response_requires_independent_missing_phase_correction() -> None:
    with tempfile.TemporaryDirectory() as root:
        result = isolated_run_bun(r'''
          import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
          const fixture=await Bun.file('./packages/continual-learning/tests/fixtures/real-selector-missing-phase.json').json();
          const cwd=path.join(process.env.TEST_ROOT,'project');fs.mkdirSync(path.join(cwd,'.memory'),{recursive:true});execFileSync('git',['init','-q',cwd]);
          for(const name of ['a.md','b.md'])fs.writeFileSync(path.join(cwd,'.memory',name),'---\ndescription: Established fact\ntype: project\n---\nOriginal knowledge.');
          const kit=await import('./packages/kit/src/index.ts');let calls=0;let mode='corrected';
          const usage={input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:0.01};
          mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({text:++calls===1||mode==='still-missing'?fixture.rejection.output:JSON.stringify({selectedIndices:[0,1],memory:true,harness:true,agents:true,reason:'Independent phase decisions.'}),exitCode:0,stderr:'',cancelled:false,usage})}));
          const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const rows=[];
          for(const value of ['corrected','still-missing']){mode=value;calls=0;const out=await selectIncrementalLearning({cwd,outputDir:path.join(process.env.TEST_ROOT,value),contextDigest:fixture.rejection.contextDigest,taskSlice:{kind:'learning-task-slice',version:1,entries:[{role:'user',content:'Observed project change.'}]},jevJudge:{select:async()=>({telemetry:{status:'disabled'}})}});rows.push({out,calls});}
          console.log(JSON.stringify(rows));
        ''', env={'TEST_ROOT': root})
    corrected, missing = result
    assert corrected['calls'] == 2 and corrected['out']['outcome'] == 'selected'
    assert corrected['out']['selection']['agents'] is True
    assert corrected['out']['selection']['harness'] is True
    assert corrected['out']['usage']['cost'] == 0.02
    assert [a['outcome'] for a in corrected['out']['attempts']] == ['failed', 'applied']
    assert missing['calls'] == 2 and missing['out']['outcome'] == 'failed'
