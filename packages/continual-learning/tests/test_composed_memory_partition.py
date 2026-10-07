from support import isolated_run_bun
from test_independent_memory_partition import BASE

SETUP = BASE + r'''
const standaloneAnswer=(label='selfContained',confidence=1)=>({type:'choice',choice:label,confidence,
 probabilities:Object.fromEntries(['selfContained','needsOther','unresolved'].map(k=>[k,k===label?1:0]))});
const standalone={version:1,purpose:'diagnostic-only',complete:true,model:review.model,
 evidenceDigest:review.evidenceDigest,existingDigest:review.existingDigest,candidatesDigest:review.candidatesDigest,
 candidates:candidates.map((candidate,index)=>({index,candidateDigest:digest(candidate),answer:standaloneAnswer()}))};
const related=label=>({...relations,pairs:[{...relations.pairs[0],relation:label,
 status:label==='unclear'?'uncertain':'decided',answer:answer(label)}]});
'''


def test_supported_complete_record_is_recovered_only_with_bound_extra_review() -> None:
    rows = isolated_run_bun(SETUP + r'''
      console.log(JSON.stringify(['conflict','dependent','duplicate','unclear'].map(label=>
        partitionReviewedNewMemory(evidence,candidates,existing,review,related(label),standalone))));
    ''')
    assert all(row['eligible'] == [0] and row['held'] == [1] for row in rows)
    assert all(row['writeAuthorized'] is False for row in rows)


def test_selected_supported_pairs_still_require_independence() -> None:
    rows = isolated_run_bun(SETUP + r'''
      const both={...review,candidates:review.candidates.map(c=>({...c,outcome:'passed',passedChecks:checks(c.index),heldChecks:[]}))};
      console.log(JSON.stringify(['conflict','dependent','duplicate','unclear'].map(label=>
        partitionReviewedNewMemory(evidence,candidates,existing,both,related(label),standalone))));
    ''')
    assert all(row['eligible'] == [] for row in rows)


def test_invalid_or_uncertain_extra_review_falls_back_to_original_selection() -> None:
    value = isolated_run_bun(SETUP + r'''
      const variants=[undefined,{...standalone,model:'jev-1.12.0'},
        {...standalone,evidenceDigest:'stale'},{...standalone,candidates:[]},
        {...standalone,candidates:standalone.candidates.map(c=>({...c,answer:standaloneAnswer('selfContained',.79)}))},
        {...standalone,candidates:standalone.candidates.map(c=>({...c,answer:standaloneAnswer('needsOther')}))},
        {...standalone,candidates:standalone.candidates.map(c=>({...c,answer:{type:'choice'}}))}];
      console.log(JSON.stringify({old:variants.map(s=>partitionReviewedNewMemory(evidence,candidates,existing,review,relations,s)),
        held:variants.map(s=>partitionReviewedNewMemory(evidence,candidates,existing,review,related('conflict'),s))}));
    ''')
    assert all(row['eligible'] == [0] for row in value['old'])
    assert all(row['eligible'] == [] for row in value['held'])


def test_original_invalid_proof_never_recovers_from_extra_answers() -> None:
    value = isolated_run_bun(SETUP + r'''
      const variants=[undefined,{...review,evidenceDigest:'stale'},
        {...review,candidates:review.candidates.map(c=>({...c,passedChecks:[]}))}];
      const rows=variants.map(r=>partitionReviewedNewMemory(evidence,candidates,existing,r,related('conflict'),standalone));
      rows.push(partitionReviewedNewMemory(evidence,candidates,existing,review,{...relations,pairs:[]},standalone));
      console.log(JSON.stringify(rows));
    ''')
    assert all(row['eligible'] == [] for row in value)


def test_deletion_order_cannot_erase_another_tentative_pair_obligation() -> None:
    value = isolated_run_bun(SETUP + r'''
      const third={...candidates[0],name:'third.md'};
      const all=[...candidates,third];
      const r={...review,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,
        candidateDigest:digest(c),outcome:'passed',passedChecks:checks(index),heldChecks:[]}))};
      const p={...relations,candidatesDigest:digest(all),pairs:[[0,1,'conflict'],[0,2,'dependent'],[1,2,'independent']].map(([a,b,label])=>({
        a,b,candidateDigests:[digest(all[a]),digest(all[b])],status:'decided',relation:label,answer:answer(label)}))};
      const s={...standalone,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),answer:standaloneAnswer()}))};
      console.log(JSON.stringify([partitionReviewedNewMemory(evidence,all,existing,r,p,s),
        partitionReviewedNewMemory(evidence,all,existing,r,{...p,pairs:[...p.pairs].reverse()},s)]));
    ''')
    assert all(row['eligible'] == [] and row['held'] == [0, 1, 2] for row in value)


def test_runtime_standalone_interpreter_matches_frozen_research_contract() -> None:
    value = isolated_run_bun(SETUP + r'''
      import {interpretStandaloneMemory as runtime} from './packages/continual-learning/extensions/jev-memory-readiness.ts';
      import {interpretStandaloneMemory as research} from './packages/continual-learning/tests/jev-standalone-memory-research.ts';
      const answers=['selfContained','needsOther','unresolved'].flatMap(label=>[0,.79,.8,1].map(conf=>standaloneAnswer(label,conf)));
      answers.push(undefined,null,{}, {...standaloneAnswer(),probabilities:{selfContained:.89,needsOther:.11,unresolved:0}},
        {...standaloneAnswer(),confidence:NaN},{...standaloneAnswer(),probabilities:{selfContained:1,needsOther:0,unresolved:0,extra:0}});
      console.log(JSON.stringify(answers.map(a=>JSON.stringify(runtime(a))===JSON.stringify(research(a)))));
    ''')
    assert all(value)
