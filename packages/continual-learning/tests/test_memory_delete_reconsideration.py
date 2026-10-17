from support import isolated_run_bun


def test_unvalidated_deletion_can_be_reconsidered_as_cited_rewrite_only_in_structural_slot() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let response,prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {exitCode:0,stderr:'',text:JSON.stringify(response)}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const source='The wrapper retains clearQueue and now exposes onIdle.';
      const old={name:'contract.md',classification:'safe',content:'---\nname: contract\ndescription: Queue contract\ntype: project\n---\nThe wrapper retains clearQueue.',description:'Queue contract',type:'project'};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:old.name,kind:'delete',classification:'safe',verdict:'SUPERSEDED',preservedIn:['missing.md'],evidence:[{index:1,quote:source}]}],newMemories:[]};
      const rewrite={name:old.name,kind:'rewrite',classification:'safe',content:'---\nname: contract\ndescription: Queue contract\ntype: project\n---\n'+source,evidence:[{index:0,quote:source}]};
      const input={identity,rejectedPlan:original,errors:['ineligible-source'],selectedNames:[old.name],structuralCorrection:true,allowDeleteReconsideration:true,semanticContext:{frozenEvidence:{entries:[{role:'toolResult',content:source},{role:'assistant',content:source}]},existingMemories:[old]}};
      const run=async(overrides={},operation=rewrite)=>{response={...original,operations:[operation]};return repairIncrementalMemoryPlan({...input,...overrides})};
      const good=await run();const framing=prompt;
      const held=[];
      held.push(await run({structuralCorrection:false}));
      held.push(await run({allowDeleteReconsideration:false}));
      held.push(await run({semanticContext:undefined}));
      held.push(await run({semanticContext:{...input.semanticContext,existingMemories:[]}}));
      held.push(await run({}, {...rewrite,classification:'private'}));
      held.push(await run({}, {...rewrite,content:''}));
      held.push(await run({}, {...rewrite,verdict:'SUPERSEDED'}));
      held.push(await run({}, {...rewrite,preservedIn:[]}));
      held.push(await run({}, {...rewrite,name:'other.md'}));
      held.push(await run({}, {...rewrite,evidence:[{index:1,lines:{block:0,start:1,end:1}}]}));
      held.push(await run({rejectedPlan:{...original,operations:[rewrite]}},original.operations[0]));
      console.log(JSON.stringify({good,held:held.map(x=>x.outcome),framing}));
    ''')
    assert value['good']['outcome'] == 'repaired'
    assert value['good']['plan']['operations'][0]['kind'] == 'rewrite'
    assert 'unvalidated deletion' in value['framing']
    assert all(outcome == 'failed' for outcome in value['held'])


def test_reconsideration_requires_complete_current_semantic_preservation_review() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {deletionReconsiderationReviewed} from './packages/continual-learning/extensions/inject-memory.ts';
      const evidence={contextEnabled:true,entries:[{role:'toolResult',content:'The wrapper now also exposes onIdle; retain clearQueue.'}]};
      const existing=[{name:'contract.md',classification:'safe',description:'contract',type:'project',content:'The wrapper retains clearQueue.'}];
      const candidates=[{name:'contract.md',kind:'rewrite',classification:'safe',content:'The wrapper exposes onIdle.',evidence:[{index:0,quote:evidence.entries[0].content}]}];
      let hold=false,sawPredecessor=false;const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);if(Object.keys(r.questions).some(k=>k.startsWith('counter_')))sawPredecessor ||=r.state.existingMemories.some(x=>x.name==='contract.md'&&x.content===existing[0].content);
        return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{const choice=key.startsWith('counter_')?(hold?'contradicts':'compatible'):key.startsWith('coherence_')?'compatible':'grounded';return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===choice?1:0]))}]}))}));
      }});
      const good=await judge.validate('memory',evidence,candidates,existing);
      const check=(v=good,e=evidence,c=candidates,x=existing)=>deletionReconsiderationReviewed(['contract.md'],e,c,x,v);
      const accepted=check();const rejected=[check({...good,telemetry:{...good.telemetry,status:'disabled'}}),check({...good,candidateReview:undefined}),check(good,{...evidence,entries:[]}),check(good,[{...candidates[0],content:'changed'}]),check(good,[]),check({...good,telemetry:{...good.telemetry,completedWindows:0}}),check({...good,candidateReview:{...good.candidateReview,candidates:good.candidateReview.candidates.map(x=>({...x,passedChecks:x.passedChecks.filter(k=>!k.startsWith('counter_'))}))}})];
      rejected.push(check({...good,candidateReview:{...good.candidateReview,candidates:good.candidateReview.candidates.map(x=>({...x,passedChecks:x.passedChecks.filter(k=>!k.startsWith('counter_preservation_'))}))}}));
      rejected.push(check({...good,candidateReview:{...good.candidateReview,candidates:good.candidateReview.candidates.map(x=>({...x,passedChecks:x.passedChecks.filter(k=>!k.startsWith('counter_permission_'))}))}}));
      hold=true;const bad=await judge.validate('memory',evidence,candidates,existing);rejected.push(check(bad));
      console.log(JSON.stringify({accepted,rejected,sawPredecessor,enabled:judge.memoryReviewEnabled,disabled:createJevJudge({enabled:false}).memoryReviewEnabled,scopeOff:createJevJudge({enabled:true,scopes:['selection']}).memoryReviewEnabled}));
    ''')
    assert value['accepted'] and value['sawPredecessor']
    assert not any(value['rejected'])
    assert value['enabled'] and not value['disabled'] and not value['scopeOff']


def test_reconsideration_parent_pipeline_requires_proof_before_history_or_file_writes() -> None:
    from pathlib import Path
    from support import run_bun_script
    for mode in ('valid', 'missing-proof', 'partial-proof', 'wrong-predecessor', 'wrong-evidence', 'scope-off', 'disabled'):
        value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared',
                               env={'CL_JEV_FIXTURE': 'delete-reconsideration-' + mode})
        assert value['totalRepairs'] == 1, value
        if mode not in ('scope-off', 'disabled'):
            assert value['reviewWireCalls'] > 0, value
        if mode == 'valid':
            assert value['registryReceipt']['operations'] > 0, value
            assert value['newAppliedHistoryRecords'] > 0 and not value['memoryFilesRestored'], value
        else:
            assert value['registryReceipt']['operations'] == 0, value
            assert value['newAppliedHistoryRecords'] == 0 and value['memoryFilesRestored'], value
