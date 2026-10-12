from support import isolated_run_bun
from test_jev_independent_subset_research import SETUP as LEGACY_SETUP

# Current production review adds body coherence; preserve the frozen research setup.
SETUP = LEGACY_SETUP.replace("const checks=i=>[", "const checks=i=>[`coherence_${i}`,")


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


def test_only_the_composed_self_containment_proof_recovers_a_proven_candidate() -> None:
    # Given a reviewed plan whose third candidate is held, and relation pairs that
    # stay undecided wherever that held candidate is a member, the strict pair
    # gate holds every member on its own. When the parent also has a valid
    # composed proof, only a candidate that passed its own checks and stands
    # alone is recovered.
    value = isolated_run_bun(BASE + r'''
      const third={name:'build.md',kind:'project',classification:'safe',
       content:'---\nname: build\ndescription: Run make build.\ntype: project\n---\nRun make build.',
       evidence:[{index:0,role:'user',quote:'Use pnpm.'}]};
      const all=[...candidates,third];
      const own=i=>[`coherence_${i}`,`supported_${i}`,`supported_description_${i}`,`counter_${i}_0`,`counter_description_${i}_0`];
      const held=2;
      const review3={...review,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),
       outcome:index===held?'held':'passed',passedChecks:own(index).filter(k=>index!==held||k!==`supported_${index}`),
       heldChecks:index===held?[`supported_${index}`]:[]}))};
      const relation=(a,b,label,confidence)=>({a,b,status:label==='unclear'||confidence<.8?'uncertain':'decided',relation:label,
       candidateDigests:[digest(all[a]),digest(all[b])],
       answer:{type:'choice',choice:label,confidence,probabilities:Object.fromEntries(['independent','duplicate','conflict','dependent','unclear'].map(k=>[k,k===label?1:0]))}});
      const relations3={...relations,candidatesDigest:digest(all),
       pairs:[relation(0,1,'independent',1),relation(0,2,'unclear',1),relation(1,2,'independent',.7)]};
      const standalone=label=>({type:'choice',choice:label,confidence:1,
       probabilities:Object.fromEntries(['selfContained','needsOther','unresolved'].map(k=>[k,k===label?1:0]))});
      const readiness={version:1,purpose:'diagnostic-only',complete:true,model:'jev-1.13.0',
       evidenceDigest:digest(evidence),existingDigest:digest(existing),candidatesDigest:digest(all),
       candidates:all.map((c,index)=>({index,candidateDigest:digest(c),answer:standalone(index===held?'needsOther':'selfContained')}))};
      console.log(JSON.stringify({pairs:partitionReviewedNewMemory(evidence,all,existing,review3,relations3),
       composed:partitionReviewedNewMemory(evidence,all,existing,review3,relations3,readiness)}));
    ''')
    assert value['pairs'] == {'eligible': [], 'held': [0, 1, 2], 'writeAuthorized': False}
    assert value['composed'] == {'eligible': [0, 1], 'held': [2], 'writeAuthorized': False}


def test_a_candidate_without_a_description_line_is_not_denied() -> None:
    # Given two proven candidates whose frontmatter has no description line, the
    # judge generates no description checks. The parent must expect that same
    # checklist, or a description-less record can never enter the subset.
    value = isolated_run_bun(BASE + r'''
      const all=[{...candidates[0],content:'---\nname: tools\ntype: project\n---\nUse pnpm.'},
        {...candidates[1],content:'---\nname: report\ntype: preference\n---\nReport in Chinese.'}];
      const own=i=>[`coherence_${i}`,`supported_${i}`,`counter_${i}_0`];
      const r={...review,candidatesDigest:digest(all),candidates:all.map((c,index)=>({index,candidateDigest:digest(c),
        outcome:'passed',passedChecks:own(index),heldChecks:[]}))};
      const p={...relations,candidatesDigest:digest(all),
        pairs:[{...relations.pairs[0],candidateDigests:[digest(all[0]),digest(all[1])]}]};
      console.log(JSON.stringify(partitionReviewedNewMemory(evidence,all,existing,r,p)));
    ''')
    assert value == {'eligible': [0, 1], 'held': [], 'writeAuthorized': False}


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


def test_missing_or_held_body_coherence_cannot_authorize_subset() -> None:
    value = isolated_run_bun(BASE + r'''
      const legacy=structuredClone(review);for(const c of legacy.candidates)c.passedChecks=c.passedChecks.filter(key=>!key.startsWith('coherence_'));
      const held=structuredClone(review);held.candidates[0].passedChecks=held.candidates[0].passedChecks.filter(key=>key!=='coherence_0');held.candidates[0].heldChecks=['coherence_0'];held.candidates[0].outcome='held';
      console.log(JSON.stringify({legacy:partitionReviewedNewMemory(evidence,candidates,existing,legacy,relations),held:partitionReviewedNewMemory(evidence,candidates,existing,held,relations)}));
    ''')
    for row in value.values():
        assert row['eligible'] == [] and row['held'] == [0, 1]
        assert row['writeAuthorized'] is False
