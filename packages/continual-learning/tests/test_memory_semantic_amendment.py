from support import isolated_run_bun


def test_frozen_real_repair_keeps_candidate_identity_parent_owned() -> None:
    # Given the real v31 new->rewrite failure, When correcting held content,
    # Then the parent binds patches to the original proposal and still rejects
    # the actual failed response, foreign IDs, privacy changes and stale input.
    result = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {semanticMemoryRepairCandidates,bindSemanticMemoryAmendment,mergeSemanticMemoryRepairDelta,candidateCitationProblems} from './packages/continual-learning/extensions/inject-memory.ts';
      import {containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      const fixture=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-memory-repair-intent-failure.json','utf8'));
      const original=fixture.files['semantic-rejected-plan.json'].value;
      const failed=JSON.parse(fixture.files['repair-response.json'].value.output);
      const snapshot=fixture.files['snapshot.json'].value;
      const identity=Object.fromEntries(['runId','scopeKey','scopeDigest','artifactHash','snapshotDigest'].map(k=>[k,original[k]]));
      const candidates=semanticMemoryRepairCandidates(original);
      const prior=original.newMemories[0];
      const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:candidates[0].candidateId,content:prior.content,evidence:prior.evidence}]};
      const bound=bindSemanticMemoryAmendment(original,amendment,identity);
      const merged=mergeSemanticMemoryRepairDelta(original,bound);
      const rejects=value=>{try{bindSemanticMemoryAmendment(original,value,identity);return false;}catch{return true;}};
      let oldRejected=false;try{mergeSemanticMemoryRepairDelta(original,failed)}catch{oldRejected=true}
      const invalid=[{...amendment,runId:'other'}, {...amendment,operations:[]},
        {...amendment,replacements:[{...amendment.replacements[0],classification:'safe'}]},
        {...amendment,replacements:[{...amendment.replacements[0],candidateId:'foreign'}]},
        {...amendment,replacements:[amendment.replacements[0],amendment.replacements[0]]}];
      let staleRejected=false;try{bindSemanticMemoryAmendment({...original,newMemories:[{...prior,content:'changed'},...original.newMemories.slice(1)]},amendment,identity)}catch{staleRejected=true}
      let unheldRejected=false;try{bindSemanticMemoryAmendment(original,amendment,identity,[])}catch{unheldRejected=true}
      console.log(JSON.stringify({oldRejected,invalid:invalid.map(rejects),staleRejected,unheldRejected,
        unchanged:JSON.stringify(merged)===JSON.stringify(original),boundOperations:bound.operations,
        candidates,sensitive:containsSensitiveMemoryMaterial(JSON.stringify(fixture)),
        citations:candidateCitationProblems(snapshot,merged.newMemories)}));
    ''')
    assert result['oldRejected']
    assert all(result['invalid'])
    assert result['staleRejected'] and result['unheldRejected']
    assert result['unchanged']
    assert result['boundOperations'] == []
    assert len(result['candidates']) == 2
    assert not result['sensitive']
    assert result['citations'] == []


def test_semantic_worker_uses_bound_amendments_and_preserves_omitted_candidates() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let prompt,tools;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const a={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[a,{...a,name:'b.md',content:'B'}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        prompt=input.prompt;tools=input.tools;
        const context=JSON.parse(prompt.split('\n').at(-1));
        return {exitCode:0,stderr:'',cancelled:false,text:JSON.stringify({kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:context.repairCandidates[0].candidateId,content:'correct A',evidence:a.evidence}]})};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['a held'],selectedNames:[],repairableNames:['a.md'],semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}});
      console.log(JSON.stringify({result,prompt,tools}));
    ''')
    assert result['result']['outcome'] == 'repaired'
    assert [x['content'] for x in result['result']['plan']['newMemories']] == ['correct A', 'B']
    assert result['tools'] == []
    assert 'incremental-memory-amendment' in result['prompt']
    assert 'Candidate identity, operation kind and privacy are parent-owned' in result['prompt']


def test_actual_pi_receives_parent_bound_amendment_prompt_without_tools(tmp_path) -> None:
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import {spawnSync} from 'node:child_process';import fs from 'node:fs';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');const root=ROOT;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{
        const env={PATH:process.env.PATH,HOME:root,PI_CODING_AGENT_DIR:path.join(root,'agent'),PI_OFFLINE:'1'};
        const native=spawnSync('node',[path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/cli.js'),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),'--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json',input.prompt],{cwd:root,env,encoding:'utf8',timeout:40000});
        fs.writeFileSync(path.join(root,'native-pi-output.jsonl'),native.stdout);
        if(native.status!==0)throw new Error(native.stderr+'\n'+native.stdout);
        return {...kit.parsePiWorkerOutput(native.stdout),exitCode:0,stderr:'',cancelled:false};
      }}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const candidate={name:'a.md',kind:'project',classification:'private',content:'Old claim',evidence:[{index:0,quote:'Correct claim'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[candidate]};
      const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['held'],selectedNames:[],repairableNames:['a.md'],semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Correct claim'}]},existingMemories:[]}});
      console.log(JSON.stringify({result,wroteMemory:fs.existsSync(path.join(root,'.memory'))}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert result['result']['outcome'] == 'repaired'
    assert result['result']['plan']['newMemories'][0]['content'] == 'Correct claim'
    assert not result['wroteMemory']


def test_empty_or_sensitive_amendments_do_not_acknowledge_correction(tmp_path) -> None:
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';
      const kit=await import('./packages/kit/src/index.ts');let output;let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {exitCode:0,stderr:'',text:JSON.stringify(output),cancelled:false}}}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const a={name:'a.md',kind:'project',classification:'private',content:'A',evidence:[{index:0,quote:'A'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[a]};
      const input={identity,rejectedPlan:original,errors:['held'],selectedNames:[],repairableNames:['a.md'],outputDir:ROOT,semanticContext:{frozenEvidence:{entries:[]},existingMemories:[]}};
      output={kind:'incremental-memory-amendment',version:1,...identity,replacements:[]};
      const empty=await repairIncrementalMemoryPlan(input);
      output.replacements=[{candidateId:semanticMemoryRepairCandidates(original)[0].candidateId,content:'api_key=sk-'+'x'.repeat(40),evidence:a.evidence}];
      await repairIncrementalMemoryPlan(input);
      const saved=JSON.parse(fs.readFileSync(path.join(input.outputDir,'repair-response.json'),'utf8'));
      console.log(JSON.stringify({empty,saved,calls}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert result['empty']['failureKind'] == 'no-correction'
    assert 'plan' not in result['empty']
    assert result['saved']['sensitive']
    assert 'output' not in result['saved']
    assert result['calls'] == 2
