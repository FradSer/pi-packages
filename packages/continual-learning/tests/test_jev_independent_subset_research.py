from support import isolated_run_bun


SETUP = r'''
import {simulateIndependentMemorySubset} from './packages/continual-learning/tests/independent-memory-subset-bounded-replay.ts';
import {createHash} from 'node:crypto';
const digest=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
const evidence={contextEnabled:true,entries:[{role:'user',content:'Use pnpm. Report in Chinese.'}]};
const candidates=[
 {name:'tools.md',kind:'project',classification:'safe',content:'---\nname: tools\ndescription: Use pnpm.\ntype: project\n---\nUse pnpm.',evidence:[{index:0,role:'user',quote:'Use pnpm.'}]},
 {name:'report.md',kind:'preference',classification:'private',content:'---\nname: report\ndescription: Report in Chinese.\ntype: preference\n---\nReport in Chinese.',evidence:[{index:0,role:'user',quote:'Report in Chinese.'}]}
];
const existing=[];
const checks=i=>[`supported_${i}`,`supported_description_${i}`,`counter_${i}_0`,`counter_description_${i}_0`];
const review={version:1,purpose:'diagnostic-only',complete:true,sameBatchIndependenceReviewed:false,maxRequestBytes:64000,
 evidenceDigest:digest(evidence),existingDigest:digest(existing),candidatesDigest:digest(candidates),model:'jev-1.13.0',
 candidates:candidates.map((c,index)=>({index,candidateDigest:digest(c),outcome:index?'held':'passed',
 passedChecks:checks(index).filter(k=>!index||k!==`supported_description_${index}`),heldChecks:index?[`supported_description_${index}`]:[]}))};
const answer=label=>({type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(['independent','duplicate','conflict','dependent','unclear'].map(k=>[k,k===label?1:0]))});
const pair={a:0,b:1,model:'jev-1.13.0',evidenceDigest:digest(evidence),existingDigest:digest(existing),
 candidatesDigest:digest(candidates),candidateDigests:[digest(candidates[0]),digest(candidates[1])],answer:answer('independent')};
const input={evidence,candidates,existing,operations:[],review,pairs:[pair],windows:1,allowPrivateMemory:true};
'''


def test_independent_supported_candidate_is_only_a_simulation() -> None:
    value = isolated_run_bun(SETUP + r'''
      const before=JSON.stringify(input);const result=await simulateIndependentMemorySubset(input);
      console.log(JSON.stringify({result,unchanged:before===JSON.stringify(input)}));
    ''')
    assert value['result']['recoverable'] == [0]
    assert value['result']['held'] == [1]
    assert value['result']['purpose'] == 'research-only'
    assert value['result']['writeAuthorized'] is False
    assert value['unchanged']
    assert set(value['result']) == {'purpose', 'writeAuthorized', 'recoverable', 'held', 'reason'}


def test_nonindependent_or_uncertain_pairs_hold_both_candidates() -> None:
    rows = isolated_run_bun(SETUP + r'''
      const rows=[];
      for(const label of ['dependent','duplicate','conflict','unclear'])
        rows.push(await simulateIndependentMemorySubset({...input,pairs:[{...pair,answer:answer(label)}]}));
      rows.push(await simulateIndependentMemorySubset({...input,pairs:[{...pair,answer:{...answer('independent'),confidence:.79}}]}));
      console.log(JSON.stringify(rows));
    ''')
    assert all(row['recoverable'] == [] and row['held'] == [0, 1] for row in rows)


def test_missing_repeated_stale_or_wrong_model_pairs_hold_whole_plan() -> None:
    rows = isolated_run_bun(SETUP + r'''
      const pairs=[[],[pair,pair],[{...pair,a:1,b:0}],[{...pair,model:'jev-1.12.0'}],
        [{...pair,evidenceDigest:'stale'}],[{...pair,candidateDigests:['stale',pair.candidateDigests[1]]}],
        [{...pair,answer:{type:'choice',choice:'independent'}}]];
      console.log(JSON.stringify(await Promise.all(pairs.map(pairs=>simulateIndependentMemorySubset({...input,pairs})))));
    ''')
    assert all(row['recoverable'] == [] and row['held'] == [0, 1] for row in rows)


def test_incomplete_review_or_mutated_source_never_becomes_permission() -> None:
    rows = isolated_run_bun(SETUP + r'''
      const inputs=[{...input,review:undefined},{...input,windows:2},
       {...input,review:{...review,candidates:review.candidates.slice(0,1)}},
       {...input,review:{...review,candidates:review.candidates.map((c,i)=>i?c:{...c,passedChecks:[]})}},
       {...input,review:{...review,model:'jev-1.12.0'}},
       {...input,evidence:{...evidence,entries:[{role:'assistant',content:evidence.entries[0].content}]}},
       {...input,existing:[{name:'prior.md',content:'prior'}]},
       {...input,candidates:candidates.map((c,i)=>i?c:{...c,content:c.content+' changed'})}];
      console.log(JSON.stringify(await Promise.all(inputs.map(simulateIndependentMemorySubset))));
    ''')
    assert all(row['recoverable'] == [] and row['held'] == [0, 1] for row in rows)


def test_rewrites_bad_citations_and_changed_privacy_are_not_subset_eligible() -> None:
    rows = isolated_run_bun(SETUP + r'''
      const variants=[{...input,operations:[{op:'delete',name:'prior.md'}]},
       {...input,candidates:candidates.map((c,i)=>i?c:{...c,op:'rewrite'})},
       {...input,candidates:candidates.map((c,i)=>i?c:{...c,evidence:[{index:0,role:'user',quote:'not present'}]})},
       {...input,candidates:candidates.map((c,i)=>i?{...c,classification:'safe'}:c)}];
      // Rebind every synthetic digest to ensure structural gates, not merely
      // stale hashes, reject attempts to change the original contract.
      const results=variants.map(async v=>{const r={...review,candidatesDigest:digest(v.candidates),candidates:review.candidates.map((c,i)=>({...c,candidateDigest:digest(v.candidates[i])}))};
       const p={...pair,candidatesDigest:digest(v.candidates),candidateDigests:v.candidates.map(digest)};
       return simulateIndependentMemorySubset({...v,review:r,pairs:[p]});});
      console.log(JSON.stringify(await Promise.all(results)));
    ''')
    assert all(row['recoverable'] == [] and row['held'] == [0, 1] for row in rows)


def test_three_candidate_boundary_needs_all_original_pairs() -> None:
    value = isolated_run_bun(SETUP + r'''
      const third={...candidates[0],name:'other.md',content:'---\nname: other\ndescription: Use pnpm.\ntype: project\n---\nUse pnpm.'};
      const all=[...candidates,third];
      const r={...review,candidatesDigest:digest(all),candidates:[...review.candidates,
        {index:2,candidateDigest:digest(third),outcome:'passed',passedChecks:checks(2),heldChecks:[]}]};
      const p=(a,b,label)=>({...pair,a,b,candidatesDigest:digest(all),candidateDigests:[digest(all[a]),digest(all[b])],answer:answer(label)});
      const v={...input,candidates:all,review:r,pairs:[p(0,1,'independent'),p(0,2,'dependent'),p(1,2,'independent')]};
      const first=await simulateIndependentMemorySubset(v);
      const second=await simulateIndependentMemorySubset({...v,pairs:[p(0,1,'dependent'),p(0,2,'independent'),p(1,2,'independent')]});
      const incomplete=await simulateIndependentMemorySubset({...v,pairs:v.pairs.slice(1)});
      console.log(JSON.stringify([first,second,incomplete]));
    ''')
    assert value[0]['recoverable'] == []
    assert value[1]['recoverable'] == [2] and value[1]['held'] == [0, 1]
    assert value[2]['recoverable'] == [] and value[2]['held'] == [0, 1, 2]


def test_malformed_review_is_held_without_throwing_or_echoing_source() -> None:
    rows = isolated_run_bun(SETUP + r'''
      const variants=[{...review,candidates:undefined},{...review,candidates:[null,review.candidates[1]]},
       {...review,candidates:review.candidates.map((c,i)=>i?c:{...c,passedChecks:null})},
       {...review,candidates:review.candidates.map((c,i)=>i?c:{...c,heldChecks:undefined})}];
      console.log(JSON.stringify(await Promise.all(variants.map(review=>simulateIndependentMemorySubset({...input,review})))));
    ''')
    assert all(row['recoverable'] == [] and row['held'] == [0, 1] for row in rows)
    assert 'Use pnpm' not in str(rows) and 'Report in Chinese' not in str(rows)


def test_complete_original_evidence_privacy_bounds_and_windows_use_production_preflight() -> None:
    rows = isolated_run_bun(SETUP + r'''
      const variants=[
       {...input,evidence:{...evidence,api_key:'synthetic-secret-only'}},
       {...input,evidence:{...evidence,entries:[...evidence.entries,{role:'toolResult',content:'x'.repeat(65000)}]}},
       // This fits bounds but requires two original windows; rebinding hashes
       // alone must not legitimize a caller-supplied one-window checklist.
       {...input,evidence:{...evidence,entries:[...evidence.entries,{role:'toolResult',content:'Verified fixture observation. '.repeat(1000)}]}},
       {...input,allowPrivateMemory:false},
       {...input,existing:[{name:'prior.md',classification:'safe',type:'project',description:'prior',content:'api_key: "synthetic-secret-only"'}]}
      ];
      const results=await Promise.all(variants.map(v=>{
       const r={...review,evidenceDigest:digest(v.evidence),existingDigest:digest(v.existing)};
       // Existing Memory adds relationship checks. Preserve that checklist to
       // isolate the sensitive-dossier preflight from missing check failures.
       if(v.existing.length)r.candidates=r.candidates.map(c=>({...c,passedChecks:[...c.passedChecks,`relation_${c.index}`,`relation_description_${c.index}`]}));
       const p={...pair,evidenceDigest:r.evidenceDigest,existingDigest:r.existingDigest};
       return simulateIndependentMemorySubset({...v,review:r,pairs:[p]});
      }));
      console.log(JSON.stringify(results));
    ''')
    assert all(row['recoverable'] == [] and row['held'] == [0, 1] for row in rows)
