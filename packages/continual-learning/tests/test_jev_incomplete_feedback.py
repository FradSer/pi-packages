import pytest
from support import isolated_run_bun


def test_incomplete_review_keeps_bound_holds_but_never_complete_permission() -> None:
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      import {incompleteMemoryRepairFields} from './packages/continual-learning/extensions/inject-memory.ts';
      const evidence={contextEnabled:true,entries:[{role:'user',content:'The project uses pnpm.'}]};
      const existing=Array.from({length:5},(_,i)=>({name:`note-${i}.md`,classification:'safe',type:'project',description:'Build convention',content:'The project uses pnpm.'}));
      const candidates=existing.map(x=>({kind:'rewrite',name:x.name,classification:'safe',content:'---\nname: note\ndescription: The project uses npm.\ntype: project\n---\nThe project uses npm.',evidence:[{index:0,quote:'The project uses pnpm.'}]}));
      const rows=[];
      for(const mode of ['held','coherence-held','positive','mutated','invalid','cancelled']) {
        const input=structuredClone(candidates);let calls=0;const controller=new AbortController();
        const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
          calls++;const r=JSON.parse(init.body);
          if(Object.hasOwn(r.questions,'supported_0'))return new Response('{}',{status:400});
          const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
            const label=key==='coherence_1'&&mode==='coherence-held'?'contradictory':(key==='supported_1'||key==='supported_description_1')&&mode!=='positive'?'unsupported':key.startsWith('coherence_')?'compatible':key.startsWith('counter_')?'compatible':key.startsWith('relation_')?'supplement':'grounded';
            return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))}];
          }));
          if(mode==='mutated')input[1].content+=' changed';
          if(mode==='cancelled')controller.abort();
          if(mode==='invalid')delete answers[Object.keys(answers)[0]];
          return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:10,output_tokens:0}}));
        }});
        const result=await judge.validate('memory',evidence,input,existing,controller.signal);
        const fields=incompleteMemoryRepairFields(input,result.incompleteReview,evidence,existing);
        const changed=incompleteMemoryRepairFields(input,result.incompleteReview,{...evidence,extra:true},existing);
        rows.push({mode,result,fields,changed,calls});
      } console.log(JSON.stringify(rows));
    ''')
    held, coherence_held, positive, mutated, invalid, cancelled = value
    assert held['result']['decision'] == 'propose'
    assert held['result']['telemetry']['reason'] == 'unavailable'
    assert held['result']['telemetry']['completedWindows'] == 0
    assert 'candidateReview' not in held['result']
    assert held['result']['incompleteReview']['complete'] is False
    assert held['fields'] == {'note-1.md': ['body', 'description']}
    assert 'changed' not in held
    assert held['result']['telemetry']['knownInputTokens'] == 30
    assert any(f.get('internalConsistency') for f in coherence_held['result']['incompleteReview']['failures'])
    assert not any(f.get('internalConsistency') for f in held['result']['incompleteReview']['failures'])
    for row in [positive, mutated, invalid, cancelled]:
        assert 'candidateReview' not in row['result']
        assert 'incompleteReview' not in row['result']
        assert 'fields' not in row


@pytest.mark.parametrize("model", ["jev-1.13.0", "jev-1.14.0"])
def test_incomplete_feedback_does_not_replace_complete_field_proof(model: str) -> None:
    value = isolated_run_bun(r'''
      import {incompleteMemoryRepairFields as rawIncomplete,semanticMemoryRepairFields} from './packages/continual-learning/extensions/inject-memory.ts';
      import {createHash} from 'node:crypto';const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const incompleteMemoryRepairFields=(c,r,e,x)=>rawIncomplete(c,r,e,x,'__MODEL__');
      const evidence={entries:[]},existing=[],candidates=[{name:'note.md',content:'Full original body.'}];
      const review={version:1,purpose:'diagnostic-only',complete:false,model:'__MODEL__',evidenceDigest:digest(evidence),existingDigest:digest(existing),candidatesDigest:digest(candidates),failures:[{candidateIndex:0,dimension:'support',reason:'uncertain',field:'description'}]};
      const fields=incompleteMemoryRepairFields(candidates,review,evidence,existing);
      const rejected=[];for(const patch of [{complete:true},{model:'wrong'},{candidatesDigest:'wrong'},{failures:[]},{failures:[{candidateIndex:9,dimension:'support',reason:'unsupported'}]},{failures:[{candidateIndex:0,dimension:'scope',reason:'scope-expansion'}]}])rejected.push(incompleteMemoryRepairFields(candidates,{...review,...patch},evidence,existing)===undefined);
      const preservation=incompleteMemoryRepairFields(candidates,{...review,failures:[{candidateIndex:0,dimension:'preservation',reason:'uncertain'}]},evidence,existing);
      const foreignExpected=rawIncomplete(candidates,review,evidence,existing,'jev-1.15.0');
      console.log(JSON.stringify({fields,preservation,rejected,foreignExpected,completeProof:semanticMemoryRepairFields(candidates,review)}));
    '''.replace('__MODEL__', model))
    assert value['fields'] == {'note.md': ['description']}
    assert value['preservation'] == {'note.md': ['body']}
    assert all(value['rejected'])
    assert 'completeProof' not in value
    assert 'foreignExpected' not in value


@pytest.mark.parametrize("model", ["jev-1.13.0", "jev-1.14.0"])
def test_parent_uses_one_correction_slot_then_keeps_failed_recheck_and_costs(model: str) -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    for mode, repairs in [('partial-review-held', 1), ('partial-review-stale', 0), ('partial-review-consistency', 1), ('partial-review-compatible', 1), ('partial-review-low-contradiction', 1)]:
        value = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': mode, 'CL_JEV_MODEL': model})
        assert value['semanticRepairs'] == value['totalRepairs'] == repairs
        assert len(value['jevValidations']) == (1 if mode == 'partial-review-consistency' else repairs + 1)
        assert not value['memoryMirrored']
        assert value['registryReceipt']['operations'] == 0
        if repairs:
            assert value['receivedFailureHints']
            assert any('Review incomplete:' in error for errors in value['repairErrors'] for error in errors)
            attempts = [a for a in value['registryReceipt']['attempts'] if a['phase'] == 'memory']
            assert attempts[-1]['usage']['cost'] == .01
            if mode == 'partial-review-consistency':
                assert value['requiredTextChangesReceived'] == {'concise.md': ['body']}
            if mode != 'partial-review-consistency':
                assert attempts[-1]['jev']['reason'] == 'timeout'
            if mode in ('partial-review-compatible', 'partial-review-low-contradiction'):
                assert not value.get('requiredTextChangesReceived')


def test_combined_repair_must_cover_held_proposals_as_well_as_retained_records() -> None:
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';const kit=await import('./packages/kit/src/index.ts');let payload;
      const identity={runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h'};
      const content='---\nname: original\ndescription: The project uses pnpm.\ntype: project\n---\nThe project uses pnpm.\n';
      const evidence={entries:[{role:'user',content:'The project uses pnpm.'}]};
      const original={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[{name:'original.md',kind:'rewrite',classification:'private',content,evidence:[{index:0,quote:'The project uses pnpm.'}]}],newMemories:[]};
      const response={...original,operations:[{name:'retained.md',kind:'rewrite',classification:'private',content,evidence:[{index:0,quote:'The project uses pnpm.'}]}]};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{payload=JSON.parse(input.prompt.split('\n').at(-1));return {exitCode:0,stderr:'',text:JSON.stringify(response),usage:{input:10,output:2,totalTokens:12,cost:.01}}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const input={identity,rejectedPlan:original,selectedNames:['original.md','retained.md'],retainedRepairNames:['retained.md'],repairableNames:['original.md'],repairableFields:{'original.md':['body']},requiredTextChanges:{'original.md':['body']},errors:['held original and retained fields'],semanticContext:{frozenEvidence:evidence,existingMemories:[{name:'original.md',classification:'private',type:'project',description:'Build',content},{name:'retained.md',classification:'private',type:'project',description:'Build',content}]}};const result=await repairIncrementalMemoryPlan(input);
      response.operations.unshift(original.operations[0]);
      const unchanged=await repairIncrementalMemoryPlan(input);
      const formattingOnly=[];
      for(const replacement of [content+'\n',content.replaceAll('\n','\r\n'),content.replace('description: The project uses pnpm.','description: This project uses pnpm.')+'\n']){
        response.operations[0]={...original.operations[0],content:replacement};
        formattingOnly.push(await repairIncrementalMemoryPlan({...input,repairableFields:{'original.md':['body','description']}}));
      }
      response.operations[0]={...original.operations[0],content:content.replace('\nThe project uses pnpm.\n','\nThis project uses pnpm.\n')};
      const both={...input,repairableFields:{'original.md':['body','description']},requiredTextChanges:{'original.md':['body','description']}};
      const unchangedDescription=await repairIncrementalMemoryPlan(both);
      response.operations[0].content=response.operations[0].content.replace('description: The project uses pnpm.','description: This project uses pnpm.');
      const changed=await repairIncrementalMemoryPlan(both);
      response.operations[0]=original.operations[0];
      const citationOnlyAllowed=await repairIncrementalMemoryPlan({...input,requiredTextChanges:undefined});
      console.log(JSON.stringify({result,unchanged,formattingOnly,unchangedDescription,changed,citationOnlyAllowed,coverage:payload.requiredRepairCoverage}));
    ''')
    assert value['result']['outcome'] == 'failed'
    assert value['result']['failureKind'] == 'no-correction'
    assert value['result']['usage']['cost'] == .01
    assert value['coverage'] == {'proposed': ['original.md'], 'retained': ['retained.md']}
    assert value['unchanged']['outcome'] == 'failed'
    assert value['unchanged']['failureKind'] == 'no-correction'
    assert all(row['outcome'] == 'failed' and row['failureKind'] == 'no-correction'
               and row['usage']['cost'] == .01 for row in value['formattingOnly'])

    assert value['unchangedDescription']['outcome'] == 'failed'
    assert value['unchangedDescription']['failureKind'] == 'no-correction'
    assert value['changed']['outcome'] == 'repaired'
    assert value['citationOnlyAllowed']['outcome'] == 'repaired'


def test_forced_text_changes_require_confirmed_negative_not_a_low_confidence_preference() -> None:
    value = isolated_run_bun(r'''
      import {isConfirmedMemoryContradiction} from './packages/continual-learning/extensions/jev-learning.ts';
      const confirmed={candidateIndex:0,dimension:'support',reason:'unsupported',choice:'contradictory',probability:.9,confidence:.8,internalConsistency:true};
      const actual=[{choice:'compatible',probability:.74,confidence:.61},{choice:'compatible',probability:.54,confidence:.31},{choice:'compatible',probability:.5,confidence:.25},{choice:'contradictory',probability:.64,confidence:.46},{choice:'contradictory',probability:.53,confidence:.3}];
      const rejected=[...actual.map(answer=>({...confirmed,...answer,reason:'uncertain'})),{...confirmed,probability:.899},{...confirmed,confidence:.799},{...confirmed,probability:1.1},{...confirmed,confidence:NaN},{...confirmed,internalConsistency:undefined},{...confirmed,field:'description'},{...confirmed,reason:'uncertain'},{...confirmed,choice:'compatible',probability:1,confidence:1}];
      console.log(JSON.stringify({boundary:isConfirmedMemoryContradiction(confirmed),strong:isConfirmedMemoryContradiction({...confirmed,probability:1,confidence:1}),rejected:rejected.map(isConfirmedMemoryContradiction)}));
    ''')
    assert value['boundary'] and value['strong']
    assert not any(value['rejected'])
