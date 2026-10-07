from support import isolated_run_bun
from test_jev_independent_subset_research import SETUP


BASE = SETUP + r'''
import {partitionReviewedNewMemory} from './packages/continual-learning/extensions/independent-memory-partition.ts';
const relations={version:1,purpose:'diagnostic-only',complete:true,evidenceDigest:review.evidenceDigest,
 existingDigest:review.existingDigest,candidatesDigest:review.candidatesDigest,model:review.model,
 pairs:[{a:0,b:1,candidateDigests:pair.candidateDigests,status:'decided',relation:'independent',answer:pair.answer}]};
'''


def test_original_supported_indexes_are_partitioned_without_write_authority() -> None:
    value = isolated_run_bun(BASE + r'''
      console.log(JSON.stringify(partitionReviewedNewMemory(evidence,candidates,existing,review,relations)));
    ''')
    assert value['eligible'] == [0] and value['held'] == [1]
    assert value['writeAuthorized'] is False


def test_stale_missing_or_forged_checks_cannot_authorize_subset() -> None:
    value = isolated_run_bun(BASE + r'''
      const results=[];
      for(const r of [undefined,{...relations,model:'jev-1.12.0'},{...relations,evidenceDigest:'stale'},
       {...relations,pairs:[]},{...relations,pairs:[{...relations.pairs[0],candidateDigests:['stale',pair.candidateDigests[1]]}]},
       {...relations,pairs:[{...relations.pairs[0],status:'decided',relation:'independent',answer:answer('conflict')}]}])
       results.push(partitionReviewedNewMemory(evidence,candidates,existing,review,r));
      results.push(partitionReviewedNewMemory(evidence,candidates,existing,{...review,candidates:review.candidates.map((c,i)=>i?c:{...c,passedChecks:[]})},relations));
      console.log(JSON.stringify(results));
    ''')
    assert all(row['eligible'] == [] and row['held'] == [0, 1] for row in value)


def test_dependency_conflict_duplicate_and_uncertainty_hold_affected_candidates() -> None:
    value = isolated_run_bun(BASE + r'''
      const results=[];for(const label of ['dependent','conflict','duplicate','unclear'])
       results.push(partitionReviewedNewMemory(evidence,candidates,existing,review,{...relations,pairs:[{...relations.pairs[0],relation:label,status:label==='unclear'?'uncertain':'decided',answer:answer(label)}]}));
      console.log(JSON.stringify(results));
    ''')
    assert all(row['eligible'] == [] and row['held'] == [0, 1] for row in value)


def test_operations_or_bad_original_citations_never_become_subset_permission() -> None:
    value = isolated_run_bun(BASE + r'''
      const rows=[];for(const change of [{op:'rewrite'},{evidence:[{index:0,role:'user',quote:'not in evidence'}]},{kind:'preference',classification:'safe'}]){
       const all=candidates.map((c,i)=>i?c:{...c,...change});
       const r={...review,candidatesDigest:digest(all),candidates:review.candidates.map((c,i)=>({...c,candidateDigest:digest(all[i])}))};
       const p={...relations,candidatesDigest:digest(all),pairs:relations.pairs.map(p=>({...p,candidateDigests:all.map(digest)}))};
       rows.push(partitionReviewedNewMemory(evidence,all,existing,r,p));
      }console.log(JSON.stringify(rows));
    ''')
    assert all(row['eligible'] == [] for row in value)
