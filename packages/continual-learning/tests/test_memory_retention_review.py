import pytest
from support import isolated_run_bun


def test_real_noop_cannot_skip_review_of_retained_outdated_memory() -> None:
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const {snapshot,existing}=await Bun.file('./packages/continual-learning/tests/fixtures/real-memory-correction-relations.json').json();
      const requests=[];let mode='contradicts';
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const r=JSON.parse(init.body);requests.push(r);
        const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>[key,{type:'choice',choice:mode,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===mode?1:0]))}]));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      }});
      const before=JSON.stringify({snapshot,existing});
      const held=await judge.validate('memory',snapshot,[],existing);const first=requests.splice(0);
      mode='compatible';const allowed=await judge.validate('memory',snapshot,[],existing);
      console.log(JSON.stringify({held,allowed,rows:first.map(r=>({keys:Object.keys(r.questions),existingExact:existing.every((item,index)=>{const bodyQuestions=Object.entries(r.questions).filter(([key])=>new RegExp(`^counter_${index}_\\d+$`).test(key));return bodyQuestions.length===1&&bodyQuestions.every(([,q])=>q.instructions.candidate.content===item.content.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, ""))}),indexes:(typeof r.state === "string" ? JSON.parse(r.state) : r.state).reviewEvidence.entries.map(e=>e.index)})),entries:snapshot.entries.length,evidenceIndexes:snapshot.entries.flatMap((e,i)=>(e.customType??'').startsWith('continual-learning-')?[]:[i]),injected:snapshot.entries.filter(e=>(e.customType??'').startsWith('continual-learning-')).length,unchanged:before===JSON.stringify({snapshot,existing})}));
    ''')
    assert result['held']['decision'] == 'propose'
    assert result['held']['telemetry']['reason'] == 'conflict'
    assert result['allowed']['decision'] == 'allow'
    assert result['rows'] and result['unchanged'] and result['injected'] == 1
    covered = set()
    for row in result['rows']:
        assert all(k.startswith('counter_') for k in row['keys'])
        covered.update(row['indexes'])
        assert row['existingExact']
    # Every original session entry is reviewed. The extension's own injected
    # reference is routed and revisited, never judged as evidence.
    assert result['entries'] == 42
    assert covered == set(range(42)) - {1}


def test_retention_amendment_is_bounded_to_reviewed_existing_names_and_privacy() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let next;let calls=0;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{calls++;return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a'};
      const original={...identity,operations:[],newMemories:[]};
      const old={name:'contract.md',classification:'safe',content:'---\nname: contract\ndescription: Old declaration\ntype: project\n---\nOld declaration.'};
      const snapshot={entries:[{role:'user',content:'The wrapper now declares onIdle and clearQueue.'}]};
      const operation={name:'contract.md',kind:'rewrite',classification:'safe',content:'---\nname: contract\ndescription: The wrapper declares onIdle and clearQueue.\ntype: project\n---\nThe wrapper declares onIdle and clearQueue.',evidence:[{index:0,lines:{block:0,start:1,end:1}}]};
      const input={identity,rejectedPlan:original,errors:['retained claim conflicts'],selectedNames:['contract.md'],retainedRepairNames:['contract.md'],semanticContext:{frozenEvidence:snapshot,existingMemories:[old]}};
      const outputs=[{...original,operations:[operation]},original,{...original,operations:[{...operation,name:'other.md'}]},
        {...original,operations:[{...operation,classification:'private'}]},{...original,newMemories:[{...operation,kind:'project'}]}];
      const results=[];
      for(const value of outputs){next=value;results.push(await repairIncrementalMemoryPlan(input));}
      next=outputs[0];const partial=await repairIncrementalMemoryPlan({...input,selectedNames:['contract.md','other.md'],retainedRepairNames:['contract.md','other.md'],semanticContext:{...input.semanticContext,existingMemories:[old,{...old,name:'other.md'}]}});
      const other={...operation,name:'other.md',content:operation.content+'\nPreserve this original proposal exactly.'};
      const proposed={...operation,name:'new.md',kind:'project'};
      const mixed=await repairIncrementalMemoryPlan({...input,rejectedPlan:{...original,operations:[other],newMemories:[proposed]},selectedNames:['contract.md','other.md'],semanticContext:{...input.semanticContext,existingMemories:[old,{...old,name:'other.md'}]}});
      const before=calls;const invalid=await repairIncrementalMemoryPlan({...input,retainedRepairNames:['outside.md']});
      console.log(JSON.stringify({results,partial,mixed,other,proposed,invalid,invalidCalls:calls-before}));
    ''')
    assert result['results'][0]['outcome'] == 'repaired'
    assert result['results'][0]['plan']['operations'][0]['evidence'][0]['quote'] == 'The wrapper now declares onIdle and clearQueue.'
    assert result['results'][1]['outcome'] == 'failed'
    assert result['results'][1]['failureKind'] == 'no-correction'
    for row in result['results'][2:]:
        assert row['outcome'] == 'failed' and row['failureKind'] == 'intent'
    assert result['invalid']['outcome'] == 'failed' and result['invalidCalls'] == 0
    assert result['partial']['outcome'] == 'failed' and result['partial']['failureKind'] == 'intent'
    assert result['mixed']['outcome'] == 'repaired'
    assert result['mixed']['plan']['operations'][0]['content'] == result['other']['content']
    assert result['mixed']['plan']['operations'][0]['evidence'][0]['quote'] == 'The wrapper now declares onIdle and clearQueue.'
    assert result['mixed']['plan']['newMemories'][0]['content'] == result['proposed']['content']


def test_parent_keeps_failed_retention_as_failure_and_applies_valid_amendment() -> None:
    from pathlib import Path
    from support import run_bun_script

    for mode in ('retention-held', 'retention-fixed'):
        result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared', env={'CL_JEV_FIXTURE': mode})
        receipt = result['registryReceipt']
        attempts = [row for row in receipt['attempts'] if row['phase'] == 'memory']
        assert result['semanticRepairs'] == 1 and not result['lock']
        errors = result['repairErrors'][-1]
        assert len(errors) == len(set(errors))
        assert any(error == 'Retained existing records: known.md' for error in errors)
        if mode == 'retention-held':
            assert result['receiptComplete'] is False
            assert receipt['operations'] == 0
            assert all(row['outcome'] not in ('noop', 'applied') for row in attempts)
            assert 'Existing knowledge.' in result['knownMemory']
            assert attempts[-1]['diagnostic'] == 'Retained Memory review remains unresolved; no corrective operation was proposed. No files changed.'
        else:
            assert result['receiptComplete'] is True
            assert receipt['operations'] == 1
            assert attempts[-1]['outcome'] == 'applied'
            assert 'CL_MANUAL_SHARED' in result['knownMemory']


def test_nonzero_plan_cannot_hide_outdated_retained_knowledge() -> None:
    from pathlib import Path
    from support import run_bun_script

    for mode in ('retention-mixed-held', 'retention-mixed-fixed'):
        result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared', env={'CL_JEV_FIXTURE': mode})
        receipt = result['registryReceipt']
        assert result['semanticRepairs'] == 1 and not result['lock']
        if mode.endswith('-held'):
            assert result['receiptComplete'] is False
            assert receipt['operations'] == 0
            assert 'Existing knowledge.' in result['knownMemory']
        else:
            assert result['receiptComplete'] is True
            assert receipt['operations'] == 2
            assert 'CL_MANUAL_SHARED' in result['knownMemory']
            assert result['memoryMirrored'] is True


def test_retained_deletion_uses_complete_protocol_and_same_plan_preservation() -> None:
    from pathlib import Path
    from support import run_bun_script

    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared', env={'CL_JEV_FIXTURE': 'retention-delete'})
    assert result['receiptComplete'] is True
    assert result['semanticRepairs'] == 1 and not result['lock']
    assert result['registryReceipt']['operations'] == 2
    assert result.get('knownMemory') is None
    assert 'CL_MANUAL_SHARED' in result['replacementMemory']


def test_one_correction_reviews_retained_and_proposed_failures_before_worker() -> None:
    from pathlib import Path
    from support import run_bun_script

    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared', env={'CL_JEV_FIXTURE': 'retention-mixed-both-fixed'})
    assert result['semanticRepairs'] == 1
    assert result['receiptComplete'] is True
    assert result['registryReceipt']['operations'] == 2
    assert result['memoryMirrored'] is True
    assert 'CL_MANUAL_SHARED' in result['knownMemory']
    assert not result['lock']


def test_actual_mixed_failure_scopes_allow_only_held_replacements_and_retained_amendments() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let next,prompt;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async input=>{prompt=input.prompt;return {text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false}}}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const fixture=await Bun.file('./packages/continual-learning/tests/fixtures/real-retained-and-proposed-repair.json').json();
      const original=fixture.original, retained=fixture.retainedDelta.operations[0];
      // The fixture retains actual rejected bodies; this controlled replacement
      // tests the parent boundary only, never semantic validity or learning efficacy.
      const rewrite={...original.operations[0],content:original.operations[0].content.split("This is a type-level")[0]};
      const proposal={...original.newMemories[0],content:original.newMemories[0].content.split('A consequence')[0]};
      next={...fixture.retainedDelta,operations:[retained,rewrite],newMemories:[proposal]};
      const input={identity:original,rejectedPlan:original,errors:['Retained clear_queue; proposed active_count support held'],selectedNames:fixture.existingMemories.map(x=>x.name),retainedRepairNames:[retained.name],repairableNames:[proposal.name,rewrite.name],repairableFields:{[proposal.name]:['body'],[rewrite.name]:['body']},semanticContext:{frozenEvidence:{entries:[]},existingMemories:fixture.existingMemories}};
      const good=await repairIncrementalMemoryPlan(input), payload=JSON.parse(prompt.split('\n').at(-1));
      const instructions=prompt.includes('each retained-record operation') && !prompt.includes('every operation requires name (one exact retainedRepairName)');
      const errors=[];
      for(const bad of [
        {...next,operations:[retained,{...rewrite,kind:'delete'}]},
        {...next,newMemories:[{...proposal,classification:'private'}]},
        {...next,newMemories:[{...proposal,name:'unexpected.md'}]},
        {...next,newMemories:[proposal,{...proposal,name:'unexpected.md'}]},
        {...next,operations:[retained,retained]},
        {...next,operations:[]}
      ]) {next=bad;errors.push(await repairIncrementalMemoryPlan(input));}
      console.log(JSON.stringify({good,errors,original,proposal,rewrite,retained,payload,instructions}));
    ''')
    assert result['good']['outcome'] == 'repaired'
    operations = result['good']['plan']['operations']
    assert operations[0] == result['rewrite']
    assert result['instructions'] is True
    assert operations[1] == result['retained']
    assert result['good']['plan']['newMemories'][0] == result['proposal']
    assert result['payload']['repairableNames'] == [result['proposal']['name'], result['rewrite']['name']]
    assert result['payload']['retainedRepairNames'] == [result['retained']['name']]
    assert all(row['outcome'] == 'failed' and row['failureKind'] == 'intent' for row in result['errors'][:-1])
    assert result['errors'][-1]['outcome'] == 'failed'
    assert result['errors'][-1]['failureKind'] == 'intent'  # New proposal remains in this malformed mixed delta.


def test_each_retained_and_mutation_review_is_recorded_once_when_only_retention_holds() -> None:
    from pathlib import Path
    from support import run_bun_script
    from collections import Counter

    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared', env={'CL_JEV_FIXTURE': 'retention-mixed-fixed'})
    assert result['receiptComplete'] is True
    actual = [row['jev'] for row in result['registryReceipt']['attempts'] if 'jev' in row and row['jev'].get('stage') == 'memory']
    assert Counter(row['requestCount'] for row in actual) == Counter(row['requestCount'] for row in result['reviewTelemetry'])


def test_semantic_worker_restores_indentation_and_keeps_only_nonredundant_new_sources() -> None:
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');
      const old={name:'fact.md',kind:'project',classification:'private',content:'---\nname: fact\ndescription: A fact\ntype: project\n---\nOld body.',evidence:[{index:0,role:'toolResult',quote:'\tFirst fact.\n\tSecond fact.'}]};
      const delta={...old,content:old.content.replace('Old body.','First fact.'),evidence:[{index:0,role:'toolResult',quote:'Second fact.'},{index:1,role:'toolResult',quote:'Second fact.'}]};
      const identity={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a'};
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({text:JSON.stringify({...identity,operations:[],newMemories:[delta]}),exitCode:0,stderr:'',cancelled:false})}));
      const {repairIncrementalMemoryPlan,mergeSemanticMemoryRepairDelta}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const original={...identity,operations:[],newMemories:[old]};
      const snapshot={entries:[{role:'toolResult',content:'\tFirst fact.\n\tSecond fact.'},{role:'toolResult',content:'Second fact.'}]};
      const repaired=await repairIncrementalMemoryPlan({identity,rejectedPlan:original,errors:['support held'],selectedNames:[],repairableNames:['fact.md'],repairableFields:{'fact.md':['body']},semanticContext:{frozenEvidence:snapshot,existingMemories:[]}});
      const roles=mergeSemanticMemoryRepairDelta(original,{...original,newMemories:[{...delta,evidence:[{index:0,role:'user',quote:'Second fact.'}]}]},['fact.md'],{'fact.md':['body']});
      console.log(JSON.stringify({repaired,roles,old}));
    ''')
    assert result['repaired']['outcome'] == 'repaired'
    sources = result['repaired']['plan']['newMemories'][0]['evidence']
    assert sources == [result['old']['evidence'][0], {'index': 1, 'role': 'toolResult', 'quote': 'Second fact.'}]
    assert len(result['roles']['newMemories'][0]['evidence']) == 2


@pytest.mark.parametrize("model", ["jev-1.13.0", "jev-1.14.0"])
def test_distillation_requires_complete_bound_description_review_and_never_rewrites_old_memory(model: str) -> None:
    result = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      const {distillReviewedNewMemory}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const content='---\nname: fact\ndescription: Prefer concise task updates.\ntype: feedback\n---\nUnsupported timing explanation.';
      const candidate={name:'fact.md',kind:'preference',classification:'private',content,evidence:[{index:0,quote:'Prefer concise task updates.'}]};
      const candidates=[candidate], evidence={entries:[{role:'user',content:'Prefer concise task updates.'}]}, existing=[];
      const review={version:1,purpose:'diagnostic-only',complete:true,sameBatchIndependenceReviewed:false,model:'__MODEL__',evidenceDigest:digest(evidence),existingDigest:digest(existing),candidatesDigest:digest(candidates),candidates:[{index:0,candidateDigest:digest(candidate),outcome:'held',passedChecks:['supported_description_0','counter_0_0','counter_description_0_0'],heldChecks:['supported_0']}]};
      const plan={operations:[],newMemories:[candidate]};
      const run=(r=review,p=plan)=>distillReviewedNewMemory(p,candidates,r,evidence,existing,1,'__MODEL__');
      const good=run();
      const bad=[run({...review,model:'jev-1.15.0'}),run({...review,evidenceDigest:'wrong'}),run({...review,candidates:[{...review.candidates[0],passedChecks:['supported_description_0']}]}),run({...review,candidates:[{...review.candidates[0],heldChecks:['supported_0','counter_description_0_0']}]}),run(review,{operations:[{...candidate,kind:'rewrite'}],newMemories:[]})];
      const purpose={...candidate,content:content+'\n\n**Why**\nKeep updates useful.\n\n**How to apply**\nUse concise updates.'};
      const purposeReview={...review,candidatesDigest:digest([purpose]),candidates:[{...review.candidates[0],candidateDigest:digest(purpose)}]};
      const purposePlan={operations:[],newMemories:[purpose]};
      const purposeResult=distillReviewedNewMemory(purposePlan,[purpose],purposeReview,evidence,existing,1,'__MODEL__');
      console.log(JSON.stringify({good,bad,plan,purposePlan,purposeResult}));
    '''.replace('__MODEL__', model))
    assert result['good']['names'] == ['fact.md']
    item = result['good']['plan']['newMemories'][0]
    assert item['content'].endswith('\nPrefer concise task updates.\n')
    assert item['evidence'] == result['plan']['newMemories'][0]['evidence']
    assert result['purposeResult']['names'] == []
    assert result['purposeResult']['plan'] == result['purposePlan']
    for row in result['bad']:
        assert row['names'] == []


def test_subquote_union_uses_validated_snapshot_roles_without_rewriting_originals() -> None:
    result = isolated_run_bun(r'''
      const {mergeSemanticMemoryRepairDelta}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const snapshot={entries:[{role:'toolResult',content:'First fact. Second fact.'}]};
      const item={name:'fact.md',kind:'project',content:'---\nname: fact\ndescription: A fact\ntype: project\n---\nA fact.',evidence:[{index:0,quote:'First fact. Second fact.'}]};
      const before={operations:[],newMemories:[item]}, delta={operations:[],newMemories:[{...item,evidence:[{index:0,role:'toolResult',quote:'Second fact.'}]}]};
      const run=(a,b)=>mergeSemanticMemoryRepairDelta(a,b,['fact.md'],{'fact.md':['body']},snapshot);
      const good=run(before,delta), reverse=run({...before,newMemories:[{...item,evidence:[{...item.evidence[0],role:'toolResult'}]}]},{...delta,newMemories:[{...delta.newMemories[0],evidence:[{index:0,quote:'Second fact.'}]}]});
      const wrong=run(before,{...delta,newMemories:[{...delta.newMemories[0],evidence:[{index:0,role:'user',quote:'Second fact.'}]}]});
      console.log(JSON.stringify({good,reverse,wrong,item}));
    ''')
    assert result['good']['newMemories'][0]['evidence'] == result['item']['evidence']
    assert len(result['reverse']['newMemories'][0]['evidence']) == 1
    assert len(result['wrong']['newMemories'][0]['evidence']) == 2


def test_structural_then_semantic_correction_retains_both_costs_and_failure_scopes() -> None:
    from pathlib import Path
    from support import run_bun_script
    result = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), 'remember-shared', env={'CL_JEV_FIXTURE': 'structural-retention-mixed-both-fixed'})
    assert result['totalRepairs'] == 2 and result['semanticRepairs'] == 1
    assert result['receiptComplete'] is True and result['registryReceipt']['operations'] == 2
    attempts = [a for a in result['registryReceipt']['attempts'] if a['phase'] == 'memory' and a['attempt'] > 0]
    assert [a['attempt'] for a in attempts] == [1, 2]
    assert [a['usage']['cost'] for a in attempts] == [0.01, 0.01]
    assert [a['operations'] for a in attempts] == [0, 2]
    assert result['registryReceipt']['totals']['cost'] >= 0.02
    assert result['structuralRejectionRecorded'] and result['structuralResponseRetained']
    assert result['memoryMirrored'] and not result['lock']


def test_phase_corrections_stop_on_failure_cancellation_drift_and_second_hold() -> None:
    from pathlib import Path
    from support import run_bun_script
    fixture = Path(__file__).with_name('learning-policy-harness.ts')
    for reason in ('structural-failed', 'structural-held', 'structural-repair-cancel', 'structural-tamper-second'):
        result = run_bun_script(fixture, 'remember-shared', env={'CL_JEV_FIXTURE': reason})
        assert result['totalRepairs'] <= 2 and result['semanticRepairs'] <= 1
        assert not result['memoryMirrored'] and not result['lock'], reason
        if reason == 'structural-failed':
            assert result['totalRepairs'] == 1 and result['jevValidations'] == []
        elif reason == 'structural-repair-cancel':
            assert result['totalRepairs'] == 2 and 'registryReceipt' not in result
        elif reason == 'structural-held':
            assert result['totalRepairs'] == 2 and result['jevValidations'] == ['memory', 'memory']
            attempts = [a for a in result['registryReceipt']['attempts'] if a['phase'] == 'memory']
            assert [a['attempt'] for a in attempts] == [0, 1, 2]
            assert result['registryReceipt']['operations'] == 0
        else:
            assert result['totalRepairs'] == 2 and result['registryReceipt']['operations'] == 0


def test_correcting_both_held_claim_fields_does_not_union_rejected_citation_footprint() -> None:
    # Given the real failure topology: six original citations plus four replacements.
    result = isolated_run_bun(r'''
      import {mergeSemanticMemoryRepairDelta} from './packages/continual-learning/extensions/inject-memory.ts';
      import {normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      const snapshot={contextEnabled:true,entries:Array.from({length:10},(_,i)=>({role:'toolResult',content:`Observed fact ${i}.`}))};
      const refs=(start,end)=>Array.from({length:end-start},(_,i)=>({index:start+i,quote:`Observed fact ${start+i}.`}));
      const old={name:'gap.md',kind:'project',classification:'private',content:'---\nname: gap\ndescription: Old gap explanation\ntype: project\n---\nOld body.',evidence:refs(0,6)};
      const revised={...old,content:'---\nname: forbidden-new-name\ndescription: Corrected gap\ntype: project\n---\nCorrected body.',evidence:refs(6,10)};
      const original={operations:[],newMemories:[old]},delta={operations:[],newMemories:[revised]};
      const before=JSON.stringify(original);
      const full=mergeSemanticMemoryRepairDelta(original,delta,['gap.md'],{'gap.md':['body','description']},snapshot);
      const partial=['body','description'].map(field=>mergeSemanticMemoryRepairDelta(original,delta,['gap.md'],{'gap.md':[field]},snapshot));
      const accepted=plan=>{try {normalizeNewMemoryProposals(plan,snapshot,[]);return true;}catch{return false;}};
      const invalid=[[],refs(0,9),[{index:6,role:'user',quote:'Observed fact 6.'}],[{index:6,quote:'Invented fact.'}]].map(evidence=>mergeSemanticMemoryRepairDelta(original,{...delta,newMemories:[{...revised,evidence}]},['gap.md'],{'gap.md':['body','description']},snapshot));
      console.log(JSON.stringify({full,partial,valid:accepted(full),invalidValid:invalid.map(accepted),partialValid:partial.map(accepted),originalUnchanged:before===JSON.stringify(original),old,revised}));
    ''')
    # When both held claim fields are replaced, their new sources remain independently gated.
    assert result['full']['newMemories'][0]['evidence'] == result['revised']['evidence']
    assert result['valid'] and result['originalUnchanged']
    assert result['invalidValid'] == [False, False, False, False]
    assert 'name: gap\n' in result['full']['newMemories'][0]['content']
    assert result['full']['newMemories'][0]['classification'] == 'private'
    # Then preserving either original field also preserves every original source.
    assert result['partialValid'] == [False, False]
    for partial in result['partial']:
        assert partial['newMemories'][0]['evidence'][:6] == result['old']['evidence']


def test_injected_memory_reference_is_never_review_evidence() -> None:
    """The extension's own reference indexes the records under review, so it is
    context for routing, never factual support for a retained-record judgment."""
    result = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const reference={type:'custom_message',customType:'continual-learning-memory-reference',content:'# Active Project Memories\n- fact.md (harness) — A fact.'};
      const snapshot={contextEnabled:true,entries:[
        {type:'message',message:{role:'user',content:[{type:'text',text:'Review fact.md.'}]}},
        reference,
        {type:'message',message:{role:'assistant',content:[{type:'text',text:'Noted.'}]}},
        {type:'message',message:{role:'toolResult',content:[{type:'text',text:'Unrelated output.'}]}}]};
      const existing=[{name:'fact.md',classification:'safe',type:'project',description:'A fact',
        content:'---\nname: fact\ndescription: A fact\ntype: project\n---\nA fact.'}];
      const requests=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{
        const r=JSON.parse(init.body);requests.push(r);
        const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>[key,{type:'choice',choice:'compatible',confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k==='compatible'?1:0]))}]));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:1,output_tokens:1}}));
      }});
      const before=JSON.stringify({snapshot,existing});
      const verdict=await judge.validate('memory',snapshot,[],existing);
      const states=requests.map(r=>typeof r.state==='string'?JSON.parse(r.state):r.state);
      console.log(JSON.stringify({verdict,requests:requests.length,
        indexes:(states[0]?.reviewEvidence?.entries??[]).map(e=>e.index),totalEntries:states[0]?.reviewEvidence?.totalEntries,
        leaked:requests.some(r=>JSON.stringify(r).includes('Active Project Memories')),
        unchanged:before===JSON.stringify({snapshot,existing})}));
    ''')
    assert result['verdict']['decision'] == 'allow'
    assert result['requests'] >= 1
    assert result['indexes'] == [0, 2, 3]
    assert result['totalEntries'] == 3
    assert result['leaked'] is False and result['unchanged'] is True


def test_only_known_owned_references_are_excluded_from_source_review() -> None:
    result = isolated_run_bun(r'''
      import {selfInjectedContextEntry} from './packages/continual-learning/extensions/memory-retrieval.ts';
      const types=['continual-learning-memory-reference','continual-learning-result','continual-learning-observed-failure'];
      const entries=types.flatMap(customType=>[{customType},{customType,role:'user'},
        {customType,message:{role:'toolResult'}},{message:{customType,role:'user'}},
        {message:{customType,role:'toolResult'}}]);
      console.log(JSON.stringify(entries.map(selfInjectedContextEntry)));
    ''')
    assert result == [True, False, False, False, False, True, False, False, False, False, False, False, False, False, False]


def test_real_empty_retention_repair_reports_missing_correction_not_intent_drift() -> None:
    # The reported manual run returned identical empty delta arrays twice.
    # Names/bodies are replaced; the parent boundary and response shape are exact.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');let next;
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({text:JSON.stringify(next),exitCode:0,stderr:'',cancelled:false})}));
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={kind:'incremental-memory-plan',version:1,schemaVersion:1,runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'a'};
      const original={...identity,operations:[],newMemories:[]};
      const names=['architecture.md','billing.md','deploy.md','runtime.md'];
      const input={identity,rejectedPlan:original,errors:['Retained records: uncertain counterevidence'],selectedNames:names,retainedRepairNames:names,semanticContext:{frozenEvidence:{entries:[]},existingMemories:names.map(name=>({name,classification:'private',content:'Existing knowledge'}))}};
      next=original;const empty=await repairIncrementalMemoryPlan(input);
      next={...original,operations:null};const malformed=await repairIncrementalMemoryPlan(input);
      next={...original,operations:[{name:'outside.md',kind:'delete',classification:'private'}]};const drift=await repairIncrementalMemoryPlan(input);
      next={...original,scopeDigest:'changed'};const identityDrift=await repairIncrementalMemoryPlan(input);
      console.log(JSON.stringify({empty,malformed,drift,identityDrift}));
    ''')
    assert result['empty']['outcome'] == 'failed'
    assert result['empty']['failureKind'] == 'no-correction'
    assert 'plan' not in result['empty']
    for key in ('malformed', 'drift', 'identityDrift'):
        assert result[key]['outcome'] == 'failed'
        assert result[key]['failureKind'] == 'intent'
