from support import isolated_run_bun


def test_parent_extracts_line_locations_without_transcription_or_evidence_changes() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations,locatedMemoryEvidence} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      const text='49:\t// Node.js 20 has a bug\r\n50:\tconst check = enabled ? run : skip;\r\n51:\treturn check;';
      const snapshot={contextEnabled:true,entries:[{role:'assistant',content:'not evidence'},{id:'original',message:{role:'toolResult',content:[{type:'text',text},{type:'image',data:'not text'},{type:'text',text:'Later correction: disabled.'}]}}]};
      const original=JSON.stringify(snapshot);
      const raw={operations:[],newMemories:[{name:'a.md',content:'unchanged',evidence:[{index:1,lines:{block:0,start:1,end:2},role:'toolResult'}]}]};
      const resolved=resolveMemoryPlanCitations(raw,snapshot);
      const shown=locatedMemoryEvidence(snapshot);
      console.log(JSON.stringify({resolved,shown,unchanged:JSON.stringify(snapshot)===original,rawUnchanged:!raw.newMemories[0].evidence[0].quote,problems:candidateCitationProblems(snapshot,resolved.newMemories)}));
    ''')
    citation = value['resolved']['newMemories'][0]['evidence'][0]
    assert citation == {'index': 1, 'quote': '49:\t// Node.js 20 has a bug\r\n50:\tconst check = enabled ? run : skip;\r', 'role': 'toolResult'}
    assert value['unchanged'] and value['rawUnchanged'] and not value['problems']
    entries = value['shown']['entries']
    assert entries[0]['entry']['content'] == 'not evidence'
    blocks = entries[1]['entry']['message']['content']
    assert blocks[0]['citationLines']['block'] == 0
    assert blocks[0]['citationLines']['lines'][0] == {'line': 1, 'text': '49:\t// Node.js 20 has a bug\r'}
    assert blocks[1] == {'type': 'image', 'data': 'not text'}
    assert blocks[2]['citationLines']['block'] == 2
    assert blocks[2]['citationLines']['lines'][0]['text'] == 'Later correction: disabled.'


def test_locations_cannot_add_authority_change_roles_or_evade_quote_bounds() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'assistant',content:'invented'},{role:'toolResult',content:[{text:'one\ntwo'},{text:'three'}]},{role:'user',content:'x'.repeat(2001)}]};
      const bad=[{index:0,lines:{block:0,start:1,end:1}},
        {index:1,lines:{block:0,start:0,end:1}},{index:1,lines:{block:0,start:2,end:1}},
        {index:1,lines:{block:0,start:1,end:3}},{index:1,lines:{block:9,start:1,end:1}},
        {index:1,lines:{block:0,start:1.5,end:2}},{index:1,lines:{block:0,start:1,end:1,omit:[1]}},
        {index:1,lines:{block:0,start:1,end:1},role:'user'},
        {index:1,lines:{block:0,start:1,end:1},quote:'not one'},
        {index:2,lines:{block:0,start:1,end:1}},{index:99,lines:{block:0,start:1,end:1}}];
      const rejected=bad.map(c=>{try{resolveMemoryPlanCitations({operations:[{evidence:[c]}]},snapshot);return false;}catch{return true;}});
      const legacy={operations:[{evidence:[{index:1,quote:'one'}]}]};
      const good=resolveMemoryPlanCitations({newMemories:[{evidence:[{index:1,lines:{block:0,start:1,end:1},quote:'one'}]}]},snapshot);
      console.log(JSON.stringify({rejected,legacyUnchanged:resolveMemoryPlanCitations(legacy,snapshot)===legacy,good}));
    ''')
    assert all(value['rejected'])
    assert value['legacyUnchanged']
    assert value['good']['newMemories'][0]['evidence'][0]['quote'] == 'one'


def test_semantic_repair_resolves_locations_before_retaining_protected_candidates() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt='';let payload;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(payload),usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:.01}};}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const item={name:'fact.md',kind:'project',classification:'safe',content:'Project uses Vitest.',evidence:[{index:0,lines:{block:0,start:1,end:1}}]};
      const rejectedPlan={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[item]};
      payload={...rejectedPlan,newMemories:[{...item,evidence:[{index:0,quote:'Project uses Vitest.'}]}]};
      const semanticContext={frozenEvidence:{entries:[{role:'toolResult',content:'Project uses Vitest.'}]},existingMemories:[]};
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan,selectedNames:[],errors:['uncertain'],repairableNames:[],semanticContext});
      payload={...payload,newMemories:[{...item,evidence:[{index:0,lines:{block:0,start:1,end:9}}]}]};
      const invalid=await repairIncrementalMemoryPlan({identity,rejectedPlan,selectedNames:[],errors:['uncertain'],semanticContext});
      console.log(JSON.stringify({result,invalid,locatedProjection:prompt.includes('citationLines')}));
    ''')
    assert value['result']['outcome'] == 'repaired'
    assert value['result']['plan']['newMemories'][0]['evidence'] == [{'index': 0, 'quote': 'Project uses Vitest.'}]
    assert value['invalid']['outcome'] == 'failed' and value['invalid']['failureKind'] == 'citation'
    assert value['invalid']['usage']['cost'] == .01
    assert value['locatedProjection']


def test_parent_pipeline_applies_initial_and_repaired_locations_with_existing_gates() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    for reason in ['located-supported', 'located-repair']:
        value = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': reason})
        assert value['registryReceipt']['operations'] == 1
        assert 'concise.md' in value['privateFiles'] and 'concise.md' in value['publicFiles']
        assert value['semanticRepairs'] == (1 if reason == 'located-repair' else 0)
        assert not value['lock']


def test_locations_cannot_resolve_against_a_changed_frozen_snapshot() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {expandIncrementalMemoryPlan} from './packages/continual-learning/extensions/incremental-memory-plan.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'located-plan-'));
      try {
        const snapshotFile=path.join(root,'snapshot.json');const snapshot=JSON.stringify({schemaVersion:1,runId:'run_located',scopeKey:'s'.repeat(64),contextEnabled:true,entries:[{role:'toolResult',content:'Project uses Vitest.'}]});
        await fs.writeFile(snapshotFile,snapshot);
        const identity={runId:'run_located',scopeKey:'s'.repeat(64),scopeDigest:'d'.repeat(64),artifactHash:sha256Digest(snapshot),snapshotDigest:sha256Digest(snapshot)};
        const run={manifest:{schemaVersion:1,...identity,snapshotDigest:identity.snapshotDigest,cwd:root,harnessDir:root,publicDir:root,sourceHashes:{harness:{},public:{}}},paths:{snapshotFile}};
        const delta={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[{name:'fact.md',kind:'project',classification:'safe',content:'Project uses Vitest.',evidence:[{index:0,lines:{block:0,start:1,end:1}}]}]};
        const valid=await expandIncrementalMemoryPlan(run,[],delta);
        await fs.writeFile(snapshotFile,snapshot+' ');
        let refused=false;try{await expandIncrementalMemoryPlan(run,[],delta);}catch{refused=true;}
        console.log(JSON.stringify({valid,refused}));
      } finally {await fs.rm(root,{recursive:true,force:true});}
    ''')
    assert value['valid']['newMemories'][0]['evidence'][0]['quote'] == 'Project uses Vitest.'
    assert value['refused']


def test_location_repair_receives_all_controlled_failures_without_source_text() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const snapshot={entries:[{role:'toolResult',content:'one\ntwo'},{role:'toolResult',content:'private-marker-'.repeat(200)}]};
      const raw={operations:[{evidence:[{index:0,lines:{block:0,start:1,end:1}},{index:0,lines:{block:0,start:3,end:3}}]}],
        newMemories:[{evidence:[{index:1,lines:{block:0,start:1,end:1}},{index:0,lines:{block:99,start:1,end:1}},{index:0,lines:{block:0,start:1,end:1},quote:'different'}]}]};
      const before=JSON.stringify(raw);let error='';
      try {resolveMemoryPlanCitations(raw,snapshot);}catch(e){error=e.message;}
      console.log(JSON.stringify({error,unchanged:JSON.stringify(raw)===before}));
    ''')
    assert value['unchanged']
    assert 'operations[0].evidence[1]: line-range-out-of-bounds (availableLines=2)' in value['error']
    assert 'newMemories[0].evidence[0]: quote-length-out-of-bounds (maximumCharacters=2000)' in value['error']
    assert 'newMemories[0].evidence[1]: source-unavailable' in value['error']
    assert 'newMemories[0].evidence[2]: quote-mismatch' in value['error']
    assert 'private-marker' not in value['error'] and 'different' not in value['error']


def test_location_diagnostics_are_bounded_for_untrusted_plan_sizes() -> None:
    value = isolated_run_bun(r'''
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      let error='';try {resolveMemoryPlanCitations({operations:[{evidence:Array.from({length:1000},()=>({index:0,lines:{block:0,start:9,end:9}}))}]},{entries:[{role:'user',content:'one'}]});}catch(e){error=e.message;}
      console.log(JSON.stringify({error}));
    ''')
    assert value['error'].count('line-range-out-of-bounds') == 8
    assert len(value['error']) < 800
