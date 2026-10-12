from support import isolated_run_bun


def test_actual_repaired_failure_body_and_sources_survive_optional_distillation() -> None:
    # Given a real correction scopes failure to the last observed source state,
    # When optional distillation runs with the original description's checklist,
    # Then the corrected body and citations survive rather than reverting to
    # the original causal description. This proves preservation, not semantics.
    result = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {distillReviewedNewMemory} from './packages/continual-learning/extensions/inject-memory.ts';
      import {normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-failure-distillation-overwrite.json').json();
      const candidates=[...f.originalPlan.operations,...normalizeNewMemoryProposals(f.originalPlan,f.snapshot)];
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const name='onidle_absent_from_index_d_ts.md';
      const repaired=resolveMemoryPlanCitations(f.repairResponse,f.snapshot).newMemories.find(x=>x.name===name);
      const original=candidates.find(x=>x.name===name);
      const run=item=>distillReviewedNewMemory({operations:[],newMemories:[item]},candidates,f.review,f.snapshot,f.existingMemories,11);
      const changed=run(repaired), unchanged=run(original);
      const citationOnly=run({...original,evidence:repaired.evidence});
      console.log(JSON.stringify({boundCandidates:digest(candidates)===f.review.candidatesDigest,
        boundEvidence:digest(f.snapshot)===f.review.evidenceDigest,boundExisting:digest(f.existingMemories)===f.review.existingDigest,
        repaired,changed,unchanged,citationOnly,actual:f.actualDistilledPlan.newMemories.find(x=>x.name===name)}));
    ''')
    assert result['boundCandidates'] and result['boundEvidence'] and result['boundExisting']
    assert 'last observed state' in result['repaired']['content']
    assert 'last observed state' not in result['actual']['content']
    assert result['changed']['names'] == []
    assert result['changed']['plan']['newMemories'][0] == result['repaired']
    assert result['citationOnly']['names'] == []
    assert result['citationOnly']['plan']['newMemories'][0]['evidence'] == result['repaired']['evidence']
    assert result['unchanged']['names'] == ['onidle_absent_from_index_d_ts.md']


def test_complete_corrected_failure_plan_fits_without_dropping_source_or_preservation_context() -> None:
    # Given the actual corrected v14 response, When the full parent path reviews
    # it, Then all source entries, exact replacement bodies and each proposal's
    # original citations remain reviewable within the unchanged wire bounds.
    # All-positive transport answers below prove coverage only, not correctness.
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';
      const kit=await import('./packages/kit/src/index.ts');
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-failure-distillation-overwrite.json').json();
      mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>({text:JSON.stringify(f.repairResponse),exitCode:0,stderr:'',cancelled:false})}));
      const {repairIncrementalMemoryPlan,semanticMemoryRepairFields,distillReviewedNewMemory}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const {normalizeNewMemoryProposals,normalizeSnapshotEvidence}=await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {createJevJudge}=await import('./packages/continual-learning/extensions/jev-learning.ts');
      const candidates=[...f.originalPlan.operations,...normalizeNewMemoryProposals(f.originalPlan,f.snapshot)];
      const repair=await repairIncrementalMemoryPlan({identity:f.originalRawPlan,rejectedPlan:f.originalRawPlan,selectedNames:f.existingMemories.map(x=>x.name),errors:['Actual original review held candidates and retained record'],repairableNames:['limit_function_type_contract.md','onidle_absent_from_index_d_ts.md','onidle_method_in_index_js.md'],retainedRepairNames:['clear_queue_pending_only.md'],repairableFields:semanticMemoryRepairFields(candidates,f.review),semanticContext:{frozenEvidence:f.snapshot,existingMemories:f.existingMemories}});
      const plan=distillReviewedNewMemory(repair.plan,candidates,f.review,f.snapshot,f.existingMemories,11).plan;
      const next=[...plan.operations,...normalizeNewMemoryProposals(plan,f.snapshot)];
      const before=JSON.stringify(next);
      const {createHash}=await import('node:crypto');
      const digest=x=>createHash('sha256').update(x).digest('hex');
      const calls=[];
      const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_u,init)=>{
        const r=JSON.parse(init.body);calls.push(r);
        const answers=Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{
          const keys=Object.keys(q.criteria),choice=keys.find(k=>['grounded','compatible','unrelated','same'].includes(k))??keys[0];
          return [key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(keys.map(k=>[k,k===choice?1:0]))}];
        }));
        return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
      }});
      const verdict=await judge.validate('memory',f.snapshot,next,f.existingMemories);
      const entries=new Map(),cited=new Set();let exactBodies=true,exactCitations=true,exactAssociations=true;
      for(const r of calls){
        const s=r.state;
        for(const x of s.reviewEvidence?.entries??[])entries.set(x.index,x.entry);
        for(const [key,refs] of Object.entries(s.originalCitationsByCandidate??{})){
          cited.add(Number(key));
          exactCitations &&= JSON.stringify(refs)===JSON.stringify(normalizeSnapshotEvidence(next[Number(key)].evidence,f.snapshot));
        }
        if(s.proposedMemoryOperations)exactAssociations &&= s.mutationComparison.evidenceDigest===digest(JSON.stringify(f.snapshot))&&s.proposedMemoryOperations.every((x,i)=>x.candidateIndex===i&&JSON.stringify(x.originalCitationSources)===JSON.stringify(normalizeSnapshotEvidence(next[i].evidence,f.snapshot).map(ref=>({snapshotIndex:ref.index,role:ref.role,quoteSha256:digest(ref.quote)}))));
        if(s.proposedMemoryOperations)exactBodies &&= s.proposedMemoryOperations.length===next.length && s.proposedMemoryOperations.every((x,i)=>x.name===next[i].name&&x.kind===next[i].kind&&x.content===next[i].content&&JSON.stringify(x.preservedIn)===JSON.stringify(next[i].preservedIn));
      }
      console.log(JSON.stringify({telemetry:verdict.telemetry,requests:calls.length,maxBytes:Math.max(0,...calls.map(r=>Buffer.byteLength(JSON.stringify(r)))),
        covered:entries.size,sourceExact:f.snapshot.entries.every((x,i)=>JSON.stringify(entries.get(i))===JSON.stringify(x)),exactBodies,exactCitations,exactAssociations,inputUnchanged:JSON.stringify(next)===before,cited:cited.size,candidates:next.length}));
    ''')
    assert result['telemetry']['reason'] != 'bounds'
    assert 0 < result['requests'] <= 68
    assert result['maxBytes'] <= 64_000
    assert result['covered'] == 51 and result['sourceExact']
    assert result['exactBodies'] and result['exactCitations']
    assert result['exactAssociations'] and result['inputUnchanged']
    assert result['cited'] == result['candidates']
