import pytest
from support import isolated_run_bun


def test_combined_repair_binds_existing_and_new_proposals_without_transcribing_intent() -> None:
    """Given held proposed+retained claims, When ID patches arrive, Then identity stays parent-owned."""
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let next,payload,prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async options=>{prompt=options.prompt;payload=JSON.parse(options.prompt.split('\n').at(-1));return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false,usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:.01}}}}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a'};
      const content=body=>'---\nname: claim\ndescription: Current claim\ntype: project\n---\n'+body;
      const evidence=[{index:0,quote:'Verified current implementation.'}];
      const old={name:'old.md',kind:'rewrite',classification:'private',content:content('Old proposed body.'),evidence};
      const fresh={name:'new.md',kind:'project',classification:'safe',content:content('New proposed body.'),evidence};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[old],newMemories:[fresh]};
      const retained={name:'retained.md',kind:'rewrite',classification:'private',content:content('Corrected retained body.'),evidence};
      const input={identity,rejectedPlan:original,selectedNames:['old.md','retained.md'],retainedRepairNames:['retained.md'],repairableNames:['old.md','new.md'],repairableFields:{'old.md':['body'],'new.md':['body']},errors:['held proposed and retained fields'],semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:'Verified current implementation.'}]},existingMemories:[{...old,type:'project',description:'Current claim'},{...retained,type:'project',description:'Current claim',content:content('Old retained body.')}]}};
      const ids=semanticMemoryRepairCandidates(original,input.repairableNames);const amendment={kind:'incremental-memory-amendment',version:1,...identity,replacements:ids.map(c=>({candidateId:c.candidateId,content:content('Corrected '+c.name+' body.'),evidence})),operations:[retained]};
      next=amendment;const good=await repairIncrementalMemoryPlan(input);const supplied=payload.repairCandidates;const exampleStart=prompt.indexOf('{\n  "kind": "incremental-memory-amendment"');const examples=[JSON.parse(prompt.slice(exampleStart,prompt.indexOf("\n}",exampleStart)+2))];
      const bad=[];
      for(const mutate of [a=>a.replacements[0].candidateId+='stale',a=>a.replacements.push(a.replacements[0]),a=>a.replacements[0].kind='rewrite',a=>a.replacements[0].classification='safe',a=>a.operations[0].name='outside.md',a=>a.operations[0].classification='safe',a=>a.replacements.pop(),a=>a.operations=[],a=>a.operations.push(a.operations[0]),a=>{a.replacements.shift();a.operations.push({...old,content:content('Corrected old.md body.')})},a=>a.newMemories=[]]){next=structuredClone(amendment);mutate(next);bad.push(await repairIncrementalMemoryPlan(input));}
      next={...amendment,replacements:[],operations:[]};const refusal=await repairIncrementalMemoryPlan(input);
      next={...amendment,scopeDigest:'foreign',replacements:[],operations:[]};const foreignRefusal=await repairIncrementalMemoryPlan(input);
      const deleted={name:'obsolete.md',kind:'delete',classification:'private',verdict:'SUBSUMED',preservedIn:['retained.md'],evidence};
      const deletionOriginal={...original,operations:[deleted]};const deletionInput={...input,rejectedPlan:deletionOriginal,selectedNames:['obsolete.md','retained.md'],repairableNames:['obsolete.md','new.md'],repairableFields:{'obsolete.md':['body'],'new.md':['body']}};
      const deletionIds=semanticMemoryRepairCandidates(deletionOriginal,deletionInput.repairableNames);
      next={...amendment,replacements:deletionIds.map(c=>({candidateId:c.candidateId,...(c.contentAllowed?{content:content('Corrected '+c.name+' body.')}:{}),evidence}))};
      await repairIncrementalMemoryPlan(deletionInput);const deleteStart=prompt.indexOf('{\n  "kind": "incremental-memory-amendment"');const deletionExample=JSON.parse(prompt.slice(deleteStart,prompt.indexOf("\n}",deleteStart)+2));
      const retainedOriginal={...original,operations:[],newMemories:[]};next={...retainedOriginal,operations:[retained]};
      const retainedOnly=await repairIncrementalMemoryPlan({...input,rejectedPlan:retainedOriginal,repairableNames:undefined,repairableFields:undefined});
      const retainedStart=prompt.indexOf('{\n  "kind": "incremental-memory-plan"');const retainedExample=JSON.parse(prompt.slice(retainedStart,prompt.indexOf("\n}",retainedStart)+2));
      // Exact real failure family: a newly proposed Memory is regenerated as an
      // existing rewrite, sometimes also duplicated in newMemories. Never coerce it.
      next={...original,operations:[old,retained,{...fresh,kind:'rewrite'}],newMemories:[fresh]};const misplaced=await repairIncrementalMemoryPlan(input);
      console.log(JSON.stringify({good,supplied,examples,ids,bad,misplaced,old,fresh,retained,refusal,foreignRefusal,deletionExample,deletionIds,retainedOnly,retainedExample}));
    ''')
    assert value['good']['outcome'] == 'repaired'
    plan = value['good']['plan']
    assert len(plan['operations']) == 2 and len(plan['newMemories']) == 1
    assert plan['operations'][0]['name'] == 'old.md'
    assert plan['operations'][0]['kind'] == 'rewrite'
    assert plan['operations'][0]['classification'] == 'private'
    assert plan['newMemories'][0]['name'] == 'new.md'
    assert plan['newMemories'][0]['kind'] == 'project'
    assert plan['newMemories'][0]['classification'] == 'safe'
    assert 'Corrected new.md body.' in plan['newMemories'][0]['content']
    assert plan['operations'][1] == value['retained']
    assert [{k:v for k,v in c.items() if k!='reuseOriginalEvidence'} for c in value['supplied']] == value['ids']
    assert all(c['reuseOriginalEvidence'] is False for c in value['supplied'])  # This legacy synthetic snapshot has no bound digest.
    assert all(row['outcome'] == 'failed' for row in value['bad'])
    assert value['misplaced']['outcome'] == 'failed'
    assert value['misplaced']['failureKind'] == 'intent'

    assert len(value['examples']) == 1
    example = value['examples'][0]
    assert [op['name'] for op in example['operations']] == ['retained.md']
    assert example['operations'][0]['kind'] == 'rewrite'
    assert example['operations'][0]['classification'] == 'private'
    assert [patch['candidateId'] for patch in example['replacements']] == [c['candidateId'] for c in value['ids']]

    assert value['bad'][7]['failureKind'] == 'no-correction'
    assert value['refusal']['outcome'] == 'failed' and value['refusal']['failureKind'] == 'no-correction'
    assert value['refusal']['usage']['cost'] == 0.01
    assert value['foreignRefusal']['outcome'] == 'failed' and value['foreignRefusal']['failureKind'] == 'intent'
    delete_patch = next(patch for patch in value['deletionExample']['replacements'] if patch['candidateId'] == value['deletionIds'][0]['candidateId'])
    assert 'content' not in delete_patch, 'A deletion may repair citations but must not acquire a body or change kind'
    assert value['retainedOnly']['outcome'] == 'repaired'
    assert [op['name'] for op in value['retainedExample']['operations']] == ['retained.md']
    assert value['retainedExample']['newMemories'] == []


@pytest.mark.parametrize('native', [False, True])
def test_retained_evidence_only_repair_preserves_frozen_real_contract(tmp_path, native) -> None:
    """Given V89's retyping error, When evidence alone changes, Then reuse exact prior bytes."""
    import json
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import {spawnSync} from 'node:child_process';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const kit=await import('./packages/kit/src/index.ts');let next,mutate=()=>{},payload,args,nativeEnabled=NATIVE,nativeCalls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async options=>{
        payload=JSON.parse(options.prompt.split('\n').at(-1));args=options.extraArgs;mutate();
        if(nativeEnabled){
          const cli=path.resolve('node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js');
          const version=spawnSync('node',[cli,'--version'],{encoding:'utf8'});if(version.status!==0||version.stdout.trim()!=='1.3.0')throw Error('Pi1.3 required');
          const response=structuredClone(next);
          if(response.replacements)response.replacements=response.replacements.map(patch=>{
            const candidate=payload.repairCandidates.find(c=>c.candidateId===patch.candidateId);
            const {candidateId,...rest}=patch;return {...rest,candidateRef:candidate.candidateRef};
          });
          const r=spawnSync('node',[cli,'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-tools','-e',path.resolve('packages/continual-learning/tests/memory-amendment-live-fixture.ts'),
            '--provider','amendment-fixture','--model','fixed','--thinking','off','--no-session','--print','--mode','json','--bound-candidate-response',JSON.stringify(response),options.prompt],
            {cwd:ROOT,env:{PATH:process.env.PATH,HOME:ROOT,PI_CODING_AGENT_DIR:path.join(ROOT,'agent'),PI_OFFLINE:'1'},encoding:'utf8',timeout:40000,maxBuffer:32*1024*1024});
          fs.writeFileSync(path.join(ROOT,'native-retained-'+(++nativeCalls)+'.jsonl'),r.stdout);
          if(r.status!==0)throw Error(r.stderr+'\n'+r.stdout);
          return {...kit.parsePiWorkerOutput(r.stdout),exitCode:0,stderr:'',cancelled:false};
        }
        return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false,usage:{input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:.1}};
      }}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairCandidates}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {learningOutputSchema}=await import('./packages/continual-learning/extensions/planner-output-schema.ts');
      const real=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-retained-and-proposed-repair.json','utf8')).retainedBodyRetyping;
      const snapshot={contextEnabled:true,runId:'r',scopeKey:'s',scopeDigest:'d',entries:[{role:'toolResult',content:'readonly rejectOnClear?: boolean;'}]};
      const h=sha256Digest(JSON.stringify(snapshot,null,2)+'\n'),identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:h,snapshotDigest:h};
      const evidence=[{ref:'e0.b0.l1'}],name='limit_function_contract.md';
      const prior={name,classification:'private',type:'project',description:'Declared contract',content:real.predecessor};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[]};
      const input={identity,rejectedPlan:original,selectedNames:[name],retainedRepairNames:[name],errors:['source support held'],semanticContext:{frozenEvidence:snapshot,existingMemories:[prior]}};
      const reply={...original,operations:[{name,kind:'rewrite',classification:'private',evidence}]};
      next=reply;const good=await repairIncrementalMemoryPlan(input),contract=payload.retainedOperationContract,nativeArgs=args;
      nativeEnabled=false;const bad=[];
      for(const change of [v=>v.operations[0].content=null,v=>v.operations[0].content='',v=>v.operations[0].content=42,
        v=>v.runId='foreign',v=>delete v.artifactHash,v=>delete v.kind,v=>v.version=2,v=>v.schemaVersion=2,
        v=>v.operations[0].classification='safe',v=>v.operations.push(v.operations[0]),v=>v.operations[0].contentSha256='forged',v=>v.operations[0].foreign=true,
        v=>v.operations[0].evidence=[{ref:'e0.b0.l9'}]]){
        next=structuredClone(reply);change(next);bad.push(await repairIncrementalMemoryPlan(input));
      }
      for(const changes of [{requiredTextChanges:{[name]:['body']}},{requiredTextChanges:{[name]:['description']}},
        {semanticContext:{...input.semanticContext,frozenEvidence:{...snapshot,runId:'foreign'}}},
        {semanticContext:{...input.semanticContext,existingMemories:[prior,prior]}}]){
        next=reply;bad.push(await repairIncrementalMemoryPlan({...input,...changes}));
      }
      next=reply;mutate=()=>{prior.content=real.rejectedReplacement};const changed=await repairIncrementalMemoryPlan(input);prior.content=real.predecessor;mutate=()=>{};
      next=reply;mutate=()=>{snapshot.entries[0].content='changed after generation'};const sourceChanged=await repairIncrementalMemoryPlan(input);snapshot.entries[0].content='readonly rejectOnClear?: boolean;';mutate=()=>{};
      next=reply;mutate=()=>{input.requiredTextChanges={[name]:['body']}};const textRequirementChanged=await repairIncrementalMemoryPlan(input);delete input.requiredTextChanges;mutate=()=>{};
      next=reply;mutate=()=>{original.newMemories.push({name:'race.md'})};const proposalChanged=await repairIncrementalMemoryPlan(input);original.newMemories=[];mutate=()=>{};
      const fresh={name:'failure.md',kind:'project',classification:'private',content:'---\nname: failure\ndescription: Observed failure\ntype: project\n---\nThe observed task failed.',evidence};
      const combinedOriginal={...original,newMemories:[fresh]},ids=semanticMemoryRepairCandidates(combinedOriginal,['failure.md']);
      next={kind:'incremental-memory-amendment',version:1,...identity,replacements:[{candidateId:ids[0].candidateId,evidence}],operations:reply.operations};
      nativeEnabled=NATIVE;const combined=await repairIncrementalMemoryPlan({...input,rejectedPlan:combinedOriginal,repairableNames:['failure.md'],repairableFields:{'failure.md':['body']}});
      const delta=learningOutputSchema('memory-delta'),retained=learningOutputSchema('memory-retained-amendment');
      console.log(JSON.stringify({good,bad,changed,sourceChanged,textRequirementChanged,proposalChanged,combined,contract,nativeArgs,nativeCalls,originalUnchanged:original.operations.length===0,
        predecessorUnchanged:prior.content===real.predecessor,body:real.predecessor,
        deltaContentRequired:delta.properties.operations.items.anyOf[0].required.includes('content'),
        retainedContentOptional:retained&&!retained.properties.operations.items.anyOf[0].required.includes('content')}));
    '''.replace('ROOT', json.dumps(str(tmp_path))).replace('NATIVE', str(native).lower()))
    assert result['good']['outcome'] == 'repaired', result['good']
    operation = result['good']['plan']['operations'][0]
    assert operation['content'] == result['body']
    assert operation['evidence'] == [{'index': 0, 'quote': 'readonly rejectOnClear?: boolean;'}]
    assert result['contract']['records'][0]['reuseFrozenContent'] is True
    assert result['retainedContentOptional'] and result['deltaContentRequired']
    assert all(row['outcome'] == 'failed' for row in result['bad']), result['bad']
    assert all(result[name]['outcome'] == 'failed' for name in ['changed', 'sourceChanged', 'textRequirementChanged', 'proposalChanged'])
    assert result['combined']['outcome'] == 'repaired', result['combined']
    assert result['combined']['plan']['operations'][0]['content'] == result['body']
    assert result['originalUnchanged'] and result['predecessorUnchanged']

    assert result['nativeCalls'] == (2 if native else 0)
