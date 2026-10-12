from support import isolated_run_bun
from test_jev_independent_subset_research import SETUP as LEGACY_SETUP

# Current production review adds body coherence; preserve the frozen research setup.
SETUP = LEGACY_SETUP.replace("const checks=i=>[", "const checks=i=>[`coherence_${i}`,")


BASE = SETUP + r'''
import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
import {structuredMemoryPairQuestion as frozenQuestion} from './packages/continual-learning/tests/jev-memory-pair-structured.ts';
let calls=[],mode='independent',active=0,maxActive=0;
const transport=async(_url,init)=>{
 const request=JSON.parse(String(init.body));calls.push(request);active++;maxActive=Math.max(active,maxActive);
 await Promise.resolve();active--;
 if(mode==='unavailable')throw Error('PRIVATE PROVIDER ERROR');
 if(mode==='mutation')evidence.entries[0].content+=' changed';
 const label=['dependent','conflict','duplicate','unclear'].includes(mode)?mode:'independent';
 return new Response(JSON.stringify({model:mode==='model-mismatch'?'jev-1.12.0':'jev-1.13.0',
  answers:{relation:mode==='missing-answer'?undefined:answer(label)},usage:{input_tokens:10,output_tokens:3}}));
};
const judge=createJevJudge({enabled:true,apiKey:'fixture-only',defaultModel:'jev-1.13.0',scopes:['memory'],allowPrivateMemory:true,fetch:transport});
'''


def test_relation_observation_uses_frozen_question_and_never_grants_write_authority() -> None:
    value = isolated_run_bun(BASE + r'''
      const result=await judge.reviewMemoryRelations(evidence,candidates,existing,review);
      console.log(JSON.stringify({result,calls,questionSame:JSON.stringify(calls[0].questions.relation)===JSON.stringify(frozenQuestion())}));
    ''')
    assert value['questionSame']
    result = value['result']
    assert 'decision' not in result
    assert result['review']['purpose'] == 'diagnostic-only'
    assert result['review']['complete'] is True
    assert result['review']['model'] == 'jev-1.13.0'
    assert result['review']['pairs'][0]['a'] == 0 and result['review']['pairs'][0]['b'] == 1
    assert result['review']['pairs'][0]['relation'] == 'independent'
    assert result['telemetry']['requestCount'] == result['telemetry']['completedRequests'] == 1
    assert result['telemetry']['inputTokens'] == 10
    state = value['calls'][0]['state']
    assert state['originalCandidates'][0]['name'] == 'tools.md'
    assert 'Use pnpm.' in state['originalEvidence']['entries'][0]['content']


def test_relation_transport_handles_every_original_pair_with_bounded_concurrency() -> None:
    value = isolated_run_bun(BASE + r'''
      const all=Array.from({length:5},(_,i)=>({...candidates[0],name:`fact-${i}.md`}));
      const r={...review,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),outcome:'passed',passedChecks:checks(index),heldChecks:[]}))};
      const result=await judge.reviewMemoryRelations(evidence,all,existing,r);
      console.log(JSON.stringify({result,calls:calls.length,maxActive}));
    ''')
    assert value['calls'] == 10
    assert 1 <= value['maxActive'] <= 4
    assert len(value['result']['review']['pairs']) == 10
    assert {(p['a'], p['b']) for p in value['result']['review']['pairs']} == {(a, b) for a in range(5) for b in range(a + 1, 5)}
    assert value['result']['telemetry']['inputTokens'] == 100


def test_invalid_or_stale_complete_review_never_sends_relationship_requests() -> None:
    value = isolated_run_bun(BASE + r'''
      const variants=[undefined,{...review,evidenceDigest:'stale'},{...review,candidates:review.candidates.slice(1)},
       {...review,candidates:review.candidates.map((c,i)=>i?c:{...c,passedChecks:[]})},
       {...review,model:'jev-1.12.0'},{...review,sameBatchIndependenceReviewed:true}];
      const results=[];for(const r of variants)results.push(await judge.reviewMemoryRelations(evidence,candidates,existing,r));
      console.log(JSON.stringify({results,calls:calls.length}));
    ''')
    assert value['calls'] == 0
    assert all('review' not in row for row in value['results'])


def test_relation_privacy_checks_full_evidence_existing_and_all_jobs_before_any_call() -> None:
    value = isolated_run_bun(BASE + r'''
      const results=[];
      const secret='ghp_'+'a'.repeat(40);
      const snapshots=[{...evidence,entries:[...evidence.entries,{role:'toolResult',content:secret}]}];
      for(const snapshot of snapshots)results.push(await judge.reviewMemoryRelations(snapshot,candidates,existing,{...review,evidenceDigest:digest(snapshot)}));
      const prior=[{name:'private.md',classification:'safe',type:'project',description:'prior',content:secret}];
      results.push(await judge.reviewMemoryRelations(evidence,candidates,prior,{...review,existingDigest:digest(prior)}));
      const denied=createJevJudge({enabled:true,apiKey:'fixture-only',scopes:['memory'],allowPrivateMemory:false,fetch:transport});
      results.push(await denied.reviewMemoryRelations(evidence,candidates,existing,review));
      console.log(JSON.stringify({results,calls:calls.length}));
    ''')
    assert value['calls'] == 0
    assert [row['telemetry']['reason'] for row in value['results']] == ['sensitive', 'sensitive', 'private-memory-denied']


def test_unavailable_missing_answer_wrong_model_and_mutation_cannot_supply_complete_proof() -> None:
    value = isolated_run_bun(BASE + r'''
      const original=evidence.entries[0].content,results=[];
      for(mode of ['unavailable','missing-answer','model-mismatch','mutation']){
        evidence.entries[0].content=original;results.push(await judge.reviewMemoryRelations(evidence,candidates,existing,review));
      }
      console.log(JSON.stringify({results,calls:calls.length,leaks:JSON.stringify(results).includes('PRIVATE PROVIDER')}));
    ''')
    # Justification: the unavailable mode fails at the connection level and is now
    # retried once, so four modes cost five attempts. The other three modes still
    # send exactly one request each, and only the first pair request is retried.
    assert value['calls'] == 5
    assert not value['leaks']
    assert all('review' not in row for row in value['results'])
    assert value['results'][0]['telemetry']['reason'] == 'unavailable'
    assert all(row['telemetry']['reason'] == 'invalid-response' for row in value['results'][1:])


def test_relation_answers_preserve_dependency_conflict_duplicate_and_uncertainty() -> None:
    value = isolated_run_bun(BASE + r'''
      const rows=[];for(mode of ['dependent','conflict','duplicate','unclear'])rows.push(await judge.reviewMemoryRelations(evidence,candidates,existing,review));
      console.log(JSON.stringify(rows));
    ''')
    assert [row['review']['pairs'][0]['relation'] for row in value] == ['dependent', 'conflict', 'duplicate', 'unclear']
    assert [row['review']['pairs'][0]['status'] for row in value] == ['decided', 'decided', 'decided', 'uncertain']
    assert all('decision' not in row for row in value)


def test_relation_scope_disable_bounds_and_precancel_make_no_calls() -> None:
    value = isolated_run_bun(BASE + r'''
      const rows=[];
      for(const config of [{enabled:false,scopes:['memory']},{enabled:true,scopes:['harness']}]){
        const j=createJevJudge({...config,apiKey:'fixture-only',allowPrivateMemory:true,fetch:transport});rows.push(await j.reviewMemoryRelations(evidence,candidates,existing,review));
      }
      const controller=new AbortController();controller.abort();rows.push(await judge.reviewMemoryRelations(evidence,candidates,existing,review,controller.signal));
      const all=Array.from({length:6},(_,i)=>({...candidates[0],name:`fact-${i}.md`}));
      const r={...review,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),outcome:'passed',passedChecks:checks(index),heldChecks:[]}))};
      rows.push(await judge.reviewMemoryRelations(evidence,all,existing,r));
      console.log(JSON.stringify({rows,calls:calls.length}));
    ''')
    assert value['calls'] == 0
    assert [row['telemetry']['reason'] for row in value['rows']] == ['disabled', 'scope-denied', 'cancelled', 'bounds']


def test_relation_output_strips_provider_extra_text_and_rejects_support_review_mutation() -> None:
    value = isolated_run_bun(BASE + r'''
      const leaking=createJevJudge({enabled:true,apiKey:'fixture-only',scopes:['memory'],allowPrivateMemory:true,fetch:async()=>
       new Response(JSON.stringify({model:'jev-1.13.0',answers:{relation:{...answer('independent'),explanation:'PRIVATE CANDIDATE RAW TEXT'}},usage:{input_tokens:10,output_tokens:3}}))});
      const safe=await leaking.reviewMemoryRelations(evidence,candidates,existing,review);
      const mutating=createJevJudge({enabled:true,apiKey:'fixture-only',scopes:['memory'],allowPrivateMemory:true,fetch:async()=>{
       review.candidates[1].outcome='passed';review.candidates[1].passedChecks=checks(1);review.candidates[1].heldChecks=[];
       return new Response(JSON.stringify({model:'jev-1.13.0',answers:{relation:answer('independent')},usage:{input_tokens:10,output_tokens:3}}));
      }});
      const stale=await mutating.reviewMemoryRelations(evidence,candidates,existing,review);
      console.log(JSON.stringify({safe,stale,leaks:JSON.stringify(safe).includes('PRIVATE CANDIDATE RAW TEXT')}));
    ''')
    assert not value['leaks']
    assert set(value['safe']['review']['pairs'][0]['answer']) == {'type', 'choice', 'confidence', 'probabilities'}
    assert 'review' not in value['stale']
    assert value['stale']['telemetry']['reason'] == 'invalid-response'


def test_later_pair_bounds_is_detected_before_first_request() -> None:
    value = isolated_run_bun(BASE + r'''
      const all=[candidates[0],{...candidates[0],name:'second.md'},
        {...candidates[0],name:'long.md',content:candidates[0].content+' context'.repeat(5000)}];
      const r={...review,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),outcome:'passed',passedChecks:checks(index),heldChecks:[]}))};
      const result=await judge.reviewMemoryRelations(evidence,all,existing,r);
      console.log(JSON.stringify({result,calls:calls.length}));
    ''')
    assert value['calls'] == 0
    assert value['result']['telemetry']['reason'] == 'bounds'


def test_partial_service_failure_keeps_lower_bound_usage_and_returns_no_proof() -> None:
    value = isolated_run_bun(BASE + r'''
      const all=[...candidates,{...candidates[0],name:'third.md'}];
      const r={...review,candidatesDigest:digest(all),candidates:[...review.candidates,{index:2,candidateDigest:digest(all[2]),outcome:'passed',passedChecks:checks(2),heldChecks:[]}]};
      let attempts=0;const faulty=createJevJudge({enabled:true,apiKey:'fixture-only',scopes:['memory'],allowPrivateMemory:true,fetch:async()=>{
       if(++attempts===3)return new Response('PRIVATE RESPONSE ERROR',{status:503});
       return new Response(JSON.stringify({model:'jev-1.13.0',answers:{relation:answer('independent')},usage:{input_tokens:10,output_tokens:3}}));
      }});
      const result=await faulty.reviewMemoryRelations(evidence,all,existing,r);
      console.log(JSON.stringify({result,attempts,leaks:JSON.stringify(result).includes('PRIVATE RESPONSE ERROR')}));
    ''')
    assert value['attempts'] == 3
    assert not value['leaks'] and 'review' not in value['result']
    telemetry = value['result']['telemetry']
    assert telemetry['reason'] == 'unavailable' and telemetry['httpStatus'] == 503
    assert telemetry['requestCount'] == 3 and telemetry['completedRequests'] == 2
    assert telemetry['knownInputTokens'] == 20
    assert 'inputTokens' not in telemetry and 'estimatedCostUsd' not in telemetry


def test_relation_timeout_and_inflight_cancellation_return_no_proof() -> None:
    value = isolated_run_bun(BASE + r'''
      const abortingFetch=async(_url,init)=>new Promise((_resolve,reject)=>{
       if(init.signal.aborted)reject(new DOMException('PRIVATE ERROR','AbortError'));
       else init.signal.addEventListener('abort',()=>reject(new DOMException('PRIVATE ERROR','AbortError')),{once:true});
      });
      const timed=createJevJudge({enabled:true,apiKey:'fixture-only',scopes:['memory'],allowPrivateMemory:true,timeout:10,fetch:abortingFetch});
      const timeout=await timed.reviewMemoryRelations(evidence,candidates,existing,review);
      const controller=new AbortController();
      const cancelled=createJevJudge({enabled:true,apiKey:'fixture-only',scopes:['memory'],allowPrivateMemory:true,fetch:async(_url,init)=>{
       controller.abort();return abortingFetch(_url,init);
      }});
      const cancellation=await cancelled.reviewMemoryRelations(evidence,candidates,existing,review,controller.signal);
      console.log(JSON.stringify({timeout,cancellation}));
    ''')
    assert 'review' not in value['timeout'] and 'review' not in value['cancellation']
    assert value['timeout']['telemetry']['reason'] == 'timeout'
    assert value['cancellation']['telemetry']['reason'] == 'cancelled'


def test_existing_memory_checklist_is_required_and_its_body_remains_bound() -> None:
    value = isolated_run_bun(BASE + r'''
      const prior=[{name:'prior.md',classification:'safe',type:'project',description:'prior',content:'Use pnpm with Node 20.'}];
      const r={...review,existingDigest:digest(prior),candidates:review.candidates.map(c=>({...c,passedChecks:[...c.passedChecks,`relation_${c.index}`,`relation_description_${c.index}`]}))};
      const invalid=await judge.reviewMemoryRelations(evidence,candidates,prior,{...review,existingDigest:digest(prior)});
      const valid=await judge.reviewMemoryRelations(evidence,candidates,prior,r);
      console.log(JSON.stringify({invalid,valid,calls:calls.length,expectedExistingDigest:digest(prior)}));
    ''')
    assert 'review' not in value['invalid']
    assert value['calls'] == 1
    assert value['valid']['review']['existingDigest'] == value['expectedExistingDigest']


def test_mixed_actual_models_and_candidate_or_existing_mutation_hold_complete_proof() -> None:
    value = isolated_run_bun(BASE + r'''
      const rows=[];
      for(const issue of ['mixed-model','candidate-mutation','existing-mutation']){
       const all=[...structuredClone(candidates),{...candidates[0],name:'third.md'}];
       const prior=issue==='existing-mutation'?[{name:'prior.md',classification:'safe',type:'project',description:'prior',content:'Use pnpm.'}]:[];
       const r={...review,existingDigest:digest(prior),candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),outcome:'passed',passedChecks:[...checks(index),...(prior.length?[`relation_${index}`,`relation_description_${index}`]:[])],heldChecks:[]}))};
       let n=0;const j=createJevJudge({enabled:true,apiKey:'fixture-only',scopes:['memory'],allowPrivateMemory:true,fetch:async()=>{
        n++;if(issue==='candidate-mutation')all[0].content+=' altered';if(issue==='existing-mutation')prior[0].content+=' altered';
        return new Response(JSON.stringify({model:issue==='mixed-model'&&n===2?'jev-1.12.0':'jev-1.13.0',answers:{relation:answer('independent')},usage:{input_tokens:10,output_tokens:3}}));
       }});rows.push({issue,result:await j.reviewMemoryRelations(evidence,all,prior,r)});
      }console.log(JSON.stringify(rows));
    ''')
    assert all('review' not in row['result'] and row['result']['telemetry']['reason'] == 'invalid-response' for row in value)
    assert 'model' not in value[0]['result']['telemetry']
    assert 'estimatedCostUsd' not in value[0]['result']['telemetry']


def test_inflight_cancellation_does_not_start_later_relation_batches() -> None:
    value = isolated_run_bun(BASE + r'''
      const all=Array.from({length:5},(_,i)=>({...candidates[0],name:`fact-${i}.md`}));
      const r={...review,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),outcome:'passed',passedChecks:checks(index),heldChecks:[]}))};
      const controller=new AbortController();let n=0;
      const j=createJevJudge({enabled:true,apiKey:'fixture-only',scopes:['memory'],allowPrivateMemory:true,fetch:async()=>{
       n++;controller.abort();return new Response(JSON.stringify({model:'jev-1.13.0',answers:{relation:answer('independent')},usage:{input_tokens:10,output_tokens:3}}));
      }});
      const result=await j.reviewMemoryRelations(evidence,all,existing,r,controller.signal);
      console.log(JSON.stringify({result,n}));
    ''')
    assert 1 <= value['n'] <= 4
    assert 'review' not in value['result']
    assert value['result']['telemetry']['reason'] == 'cancelled'
