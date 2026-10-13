from __future__ import annotations

import tempfile

from support import isolated_run_bun


def test_real_selector_schema_recovery_preserves_independent_phase_routing() -> None:
    with tempfile.TemporaryDirectory() as root:
        result = isolated_run_bun(r'''
          import {mock} from 'bun:test';
          import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
          const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-exposed-memory-selector-rejection.json','utf8'));
          const kit=await import('./packages/kit/src/index.ts');let calls=0, localCalls=0;
          mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;localCalls++;return {text:localCalls===1?fixture.rejection.output:JSON.stringify({kind:'incremental-memory-selection',version:1,contextDigest:fixture.rejection.contextDigest,selected:[],memory:true,harness:true,agents:true,reason:'Independent semantic routing after schema correction'}),exitCode:0,stderr:'',cancelled:false,usage:{input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:0.01}}}}));
          const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const {containsSensitiveMemoryMaterial}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
          const {deliveredMemoryNames}=await import('./packages/continual-learning/extensions/memory-retrieval.ts');
          const rows=[];
          for(const mode of ['complete','partial','unexposed','memory-only']){
            const cwd=path.join(process.env.TEST_ROOT,mode);fs.mkdirSync(path.join(cwd,'.memory'),{recursive:true});execFileSync('git',['init','-q',cwd]);
            for(const memory of fixture.memories)fs.writeFileSync(path.join(cwd,'.memory',memory.name),memory.content);
            if(mode==='partial')fs.writeFileSync(path.join(cwd,'.memory','unexposed.md'),'---\ndescription: Unexposed established knowledge\ntype: project\n---\nKeep this original body.\n');
            const entries=mode==='unexposed'?fixture.snapshot.entries.filter(entry=>!(entry.message??entry).customType):fixture.snapshot.entries;
            const taskSlice={kind:'learning-task-slice',version:1,entries};
            const outputDir=path.join(process.env.TEST_ROOT,'out-'+mode);const before=calls;localCalls=0;
            const out=await selectIncrementalLearning({cwd,taskSlice,outputDir,contextDigest:fixture.rejection.contextDigest,memoryOnly:mode==='memory-only',
              jevJudge:{select:async()=>({selection:null,telemetry:{stage:'selection',status:'fallback',reason:'uncertain',durationMs:1}})}});
            const dossier=out.dossierPath?JSON.parse(fs.readFileSync(out.dossierPath,'utf8')):null;
            rows.push({mode,out,calls:calls-before,hasDossier:!!dossier,
              evidenceUnchanged:JSON.stringify(dossier?.taskSlice.entries)===JSON.stringify(entries),
              selectedBodies:dossier?.selectedMemories ?? [],
              sourceBodiesUnchanged:fixture.memories.every(old=>fs.readFileSync(path.join(cwd,'.memory',old.name),'utf8')===old.content)});
          }
          console.log(JSON.stringify({rows,
            exposed:deliveredMemoryNames(fixture.snapshot.entries),sensitive:containsSensitiveMemoryMaterial(JSON.stringify(fixture))}));
        ''', env={'TEST_ROOT': root})
    assert result['sensitive'] is False
    complete, partial, unexposed, explicit = result['rows']
    assert complete['out']['outcome'] == 'selected'
    assert complete['calls'] == 2
    assert complete['out']['selection']['harness'] is True
    assert complete['out']['selection']['agents'] is True
    assert [a['outcome'] for a in complete['out']['attempts']] == ['failed', 'applied']
    assert complete['out']['usage']['cost'] == 0.02
    # Historical retrieved[] metadata is discovery, not actual read provenance.
    # Schema recovery still preserves independent routing, evidence, and usage.
    assert result['exposed']
    assert complete['out']['selection']['selected'] == []
    assert complete['out']['selection']['memory'] is True
    assert complete['evidenceUnchanged'] is True
    assert complete['selectedBodies'] == []
    assert complete['sourceBodiesUnchanged'] is True
    for row in (partial, unexposed, explicit):
        assert row['out']['outcome'] == 'selected'
        assert row['calls'] == 2
        assert row['hasDossier'] is True
        assert row['out']['selection']['selected'] == []
        assert row['selectedBodies'] == []
        assert row['sourceBodiesUnchanged'] is True
    assert explicit['out']['selection']['harness'] is False
    assert explicit['out']['selection']['agents'] is False
