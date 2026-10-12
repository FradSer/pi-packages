from support import isolated_run_bun
from test_jev_independent_subset_research import SETUP

BASE = SETUP + r'''
import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
import {standaloneMemoryQuestion as frozenQuestion} from './packages/continual-learning/tests/jev-standalone-memory-research.ts';
let calls=[],mode='ok',active=0,maxActive=0;
const transport=async(_url,init)=>{
 const req=JSON.parse(String(init.body));calls.push(req);active++;maxActive=Math.max(active,maxActive);
 await Promise.resolve();active--;
 const ready=!!req.questions.ready;
 if(ready && mode==='unavailable')throw Error('PRIVATE FAILURE');
 if(ready && mode==='mutation')evidence.entries[0].content+=' changed';
 const result=ready?{type:'choice',choice:'selfContained',confidence:1,probabilities:{selfContained:1,needsOther:0,unresolved:0}}:answer('unclear');
 return new Response(JSON.stringify({model:ready && mode==='wrong-model'?'jev-1.12.0':'jev-1.13.0',
  answers:{[ready?'ready':'relation']:result},usage:{input_tokens:10,output_tokens:3}}));
};
const make=(extra=true)=>createJevJudge({enabled:true,apiKey:'fixture-only',defaultModel:'jev-1.13.0',
 scopes:['memory'],allowPrivateMemory:true,independentMemoryApplication:true,composedMemoryApplication:extra,fetch:transport});
'''


def test_isolated_gate_collects_full_bound_readiness_and_frozen_question() -> None:
    value = isolated_run_bun(BASE + r'''
      const result=await make().reviewMemoryRelations(evidence,candidates,existing,review);
      console.log(JSON.stringify({result,calls,maxActive,questionSame:JSON.stringify(calls[1].questions.ready)===JSON.stringify(frozenQuestion())}));
    ''')
    assert value['questionSame']
    assert len(value['calls']) == 3
    assert value['result']['readiness']['purpose'] == 'diagnostic-only'
    assert len(value['result']['readiness']['candidates']) == 2
    assert value['result']['readinessTelemetry']['model'] == 'jev-1.13.0'
    assert value['result']['readinessTelemetry']['requestCount'] == 2
    for call in value['calls'][1:]:
        import json
        state = json.loads(call['state']) if isinstance(call['state'], str) else call['state']
        assert len(state['originalCandidates']) == 2
        assert state['otherNewRecordsAreWritten'] is False
    assert 'decision' not in value['result']


def test_default_path_does_not_collect_additional_observations() -> None:
    value = isolated_run_bun(BASE + r'''
      const result=await make(false).reviewMemoryRelations(evidence,candidates,existing,review);
      console.log(JSON.stringify({result,calls:calls.length}));
    ''')
    assert value['calls'] == 1 and 'readiness' not in value['result']


def test_failed_extra_requests_keep_original_review_without_extra_proof() -> None:
    for mode in ['unavailable', 'wrong-model', 'mutation']:
        value = isolated_run_bun(BASE + f"mode='{mode}';" + r'''
          const result=await make().reviewMemoryRelations(evidence,candidates,existing,review);
          console.log(JSON.stringify(result));
        ''')
        assert 'readiness' not in value
        assert value['readinessTelemetry']['reason'] in ['unavailable', 'invalid-response']
        if mode != 'mutation':
            assert value['review']['complete'] is True


def test_all_original_candidates_are_reviewed_with_bounded_concurrency() -> None:
    value = isolated_run_bun(BASE + r'''
      const all=Array.from({length:5},(_,i)=>({...candidates[0],name:`fact-${i}.md`}));
      const r={...review,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),outcome:'passed',passedChecks:checks(index),heldChecks:[]}))};
      const result=await make().reviewMemoryRelations(evidence,all,existing,r);
      console.log(JSON.stringify({result,calls:calls.length,maxActive,states:calls.filter(c=>c.questions.ready).map(c=>(typeof c.state === "string" ? JSON.parse(c.state) : c.state))}));
    ''')
    assert value['calls'] == 15 and value['maxActive'] <= 4
    assert len(value['result']['readiness']['candidates']) == 5
    assert all(len(s['originalCandidates']) == 5 for s in value['states'])


def test_stale_original_review_and_private_denial_send_no_extra_requests() -> None:
    value = isolated_run_bun(BASE + r'''
      const results=[await make().reviewMemoryRelations(evidence,candidates,existing,{...review,evidenceDigest:'stale'})];
      const denied=createJevJudge({enabled:true,apiKey:'fixture-only',defaultModel:'jev-1.13.0',scopes:['memory'],
        allowPrivateMemory:false,independentMemoryApplication:true,composedMemoryApplication:true,fetch:transport});
      results.push(await denied.reviewMemoryRelations(evidence,candidates,existing,review));
      console.log(JSON.stringify({results,calls:calls.length}));
    ''')
    assert value['calls'] == 0
    assert all('readiness' not in r for r in value['results'])


def test_extra_requests_cannot_expand_the_five_second_budget() -> None:
    value = isolated_run_bun(BASE + r'''
      const {TypeSafeClient}=await import('./packages/continual-learning/node_modules/@typesafe-ai/sdk/dist/index.mjs');
      const original=TypeSafeClient.prototype.systemOne,timeouts=[];
      TypeSafeClient.prototype.systemOne=function(request,options){timeouts.push(options?.timeout);return original.call(this,request,options)};
      const judge=createJevJudge({enabled:true,apiKey:'fixture-only',defaultModel:'jev-1.13.0',scopes:['memory'],
        allowPrivateMemory:true,independentMemoryApplication:true,composedMemoryApplication:true,timeout:90000,fetch:transport});
      await judge.reviewMemoryRelations(evidence,candidates,existing,review);
      console.log(JSON.stringify(timeouts));
    ''')
    assert value[1:] == [5000, 5000]
