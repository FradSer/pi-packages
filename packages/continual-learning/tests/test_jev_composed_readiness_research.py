from support import isolated_run_bun
from test_jev_independent_subset_research import SETUP


BASE = SETUP + r'''
import {simulateComposedMemoryReadiness} from './packages/continual-learning/tests/jev-composed-readiness-research.ts';
const standaloneAnswer=(label='selfContained',confidence=1)=>({type:'choice',choice:label,confidence,
 probabilities:Object.fromEntries(['selfContained','needsOther','unresolved'].map(k=>[k,k===label?1:0]))});
const standalone={version:1,purpose:'diagnostic-only',complete:true,model:review.model,
 evidenceDigest:review.evidenceDigest,existingDigest:review.existingDigest,candidatesDigest:review.candidatesDigest,
 candidates:candidates.map((candidate,index)=>({index,candidateDigest:digest(candidate),answer:standaloneAnswer()}))};
'''


def test_supported_self_contained_record_survives_held_pair_without_authority() -> None:
    value = isolated_run_bun(BASE + r'''
      const rows=[];
      for(const label of ['conflict','dependent','duplicate','unclear'])
        rows.push(await simulateComposedMemoryReadiness({...input,pairs:[{...pair,answer:answer(label)}]},standalone));
      console.log(JSON.stringify(rows));
    ''')
    assert all(row['recoverable'] == [0] and row['held'] == [1] for row in value)
    assert all(row['writeAuthorized'] is False for row in value)


def test_conflicting_supported_records_and_directional_references_are_held() -> None:
    value = isolated_run_bun(BASE + r'''
      const both={...review,candidates:review.candidates.map(c=>({...c,outcome:'passed',passedChecks:checks(c.index),heldChecks:[]}))};
      const rows=[];
      for(const label of ['conflict','dependent','duplicate','unclear'])
        rows.push(await simulateComposedMemoryReadiness({...input,review:both,pairs:[{...pair,answer:answer(label)}]},standalone));
      rows.push(await simulateComposedMemoryReadiness({...input,pairs:[{...pair,answer:answer('dependent')}]},
        {...standalone,candidates:standalone.candidates.map(c=>({...c,answer:standaloneAnswer('needsOther')}))}));
      console.log(JSON.stringify(rows));
    ''')
    assert all(row['recoverable'] == [] for row in value)


def test_standalone_uncertainty_cannot_add_readiness_and_original_success_is_preserved() -> None:
    value = isolated_run_bun(BASE + r'''
      const variants=[undefined,{...standalone,model:'jev-1.12.0'},
        {...standalone,evidenceDigest:'stale'},{...standalone,candidates:[]},
        {...standalone,candidates:standalone.candidates.map(c=>({...c,answer:standaloneAnswer('selfContained',.79)}))}];
      const conflict={...input,pairs:[{...pair,answer:answer('conflict')}]};
      console.log(JSON.stringify({original:await Promise.all(variants.map(s=>simulateComposedMemoryReadiness(input,s))),
        conflict:await Promise.all(variants.map(s=>simulateComposedMemoryReadiness(conflict,s)))}));
    ''')
    assert all(row['recoverable'] == [0] for row in value['original'])
    assert all(row['recoverable'] == [] for row in value['conflict'])


def test_original_invalid_proofs_never_gain_readiness_from_new_answers() -> None:
    value = isolated_run_bun(BASE + r'''
      const variants=[{...input,operations:[{op:'delete',name:'prior.md'}]},
        {...input,review:{...review,evidenceDigest:'stale'}},{...input,pairs:[]},
        {...input,allowPrivateMemory:false},{...input,windows:2},
        {...input,review:{...review,candidates:review.candidates.map(c=>({...c,passedChecks:[]}))}}];
      console.log(JSON.stringify(await Promise.all(variants.map(v=>simulateComposedMemoryReadiness(v,standalone)))));
    ''')
    assert all(row['recoverable'] == [] and row['held'] == [0, 1] for row in value)


def test_research_transport_redirect_policy_does_not_forward_to_another_server() -> None:
    # Given an HTTP redirect, When the research's actual transport option is
    # used with real local servers, Then the destination gets no request.
    value = isolated_run_bun(r'''
      import fs from 'node:fs/promises';
          import {historicalResearchPath} from './packages/continual-learning/tests/historical-research-source.ts';
      // This transport regression uses the preserved study's source bytes for
      // its historical hash check; it does not rewrite or rerun the paid study.
      const readFile=fs.readFile.bind(fs);
      fs.readFile=async(file,...args)=>{
        file=historicalResearchPath(file);
        const path=String(file);
        if(path.endsWith('/extensions/independent-memory-partition.ts'))
          return readFile(new URL('./packages/continual-learning/tests/fixtures/composed-partition-preintegration/independent-memory-partition.ts',`file://${process.cwd()}/`),...args);
        const legacyName=['jev-learning.ts','inject-memory.ts','learning-efficiency.ts','jev-memory-relations.ts'].find(name=>path.endsWith('/extensions/'+name));
        if(legacyName)return readFile(new URL('./packages/continual-learning/tests/fixtures/composed-parent-preintegration/'+legacyName,`file://${process.cwd()}/`),...args);
        return readFile(file,...args);
      };
      fs.open=async()=>({writeFile:async()=>{},close:async()=>{}});
      fs.writeFile=async()=>{};fs.rename=async()=>{};
      const realFetch=globalThis.fetch,redirects=[];
      globalThis.fetch=async(url,init)=>{redirects.push(init?.redirect);throw new Error('Offline blocked transport')};
      process.env.TYPESAFE_API_KEY='fixture-only';process.argv.push('--live');
      await import('./packages/continual-learning/tests/evaluate_jev_composed_readiness.ts');
      globalThis.fetch=realFetch;
      let destinationRequests=0,originRequests=0;
      const destination=Bun.serve({port:0,hostname:'127.0.0.1',fetch(){destinationRequests++;return new Response('unexpected destination')}});
      const origin=Bun.serve({port:0,hostname:'127.0.0.1',fetch(){originRequests++;return new Response(null,{status:307,headers:{Location:destination.url.href}})}});
      try{
        await realFetch(origin.url,{method:'POST',body:'public fixture',redirect:redirects[0]});
      }catch{}
      finally{origin.stop(true);destination.stop(true)}
      console.log(JSON.stringify({interceptedSdkCalls:redirects.length,originRequests,destinationRequests}));
    ''')
    assert value['interceptedSdkCalls'] > 0
    assert value['originRequests'] == 1
    assert value['destinationRequests'] == 0
