# --- Merged from test_independent_memory_partition.py ---
import pytest
from support import isolated_run_bun
LEGACY_SETUP = r'''
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
const input={evidence,candidates,existing,operations:[],review,pairs:[pair],windows:1};
'''

# Current production review adds body coherence; preserve the frozen research setup.
SETUP = LEGACY_SETUP.replace("const checks=i=>[", "const checks=i=>[`coherence_${i}`,")


BASE = SETUP + r'''
import {partitionReviewedNewMemory} from './packages/continual-learning/extensions/independent-memory-partition.ts';
const relations={version:1,purpose:'diagnostic-only',complete:true,evidenceDigest:review.evidenceDigest,
 existingDigest:review.existingDigest,candidatesDigest:review.candidatesDigest,model:review.model,
 pairs:[{a:0,b:1,candidateDigests:pair.candidateDigests,status:'decided',relation:'independent',answer:pair.answer}]};
'''


@pytest.mark.parametrize("model", ["jev-1.13.0", "jev-1.14.0"])
def test_original_supported_indexes_are_partitioned_without_write_authority(model: str) -> None:
    value = isolated_run_bun(BASE.replace('jev-1.13.0', model) + r'''
      console.log(JSON.stringify({bound:partitionReviewedNewMemory(evidence,candidates,existing,review,relations,undefined,'__MODEL__'),
        legacy:partitionReviewedNewMemory(evidence,candidates,existing,review,relations),
        foreign:partitionReviewedNewMemory(evidence,candidates,existing,review,relations,undefined,'jev-1.15.0')}));
    '''.replace('__MODEL__', model))
    assert value['bound']['eligible'] == [0] and value['bound']['held'] == [1]
    assert value['legacy']['eligible'] == ([0] if model == 'jev-1.13.0' else [])
    assert value['foreign']['eligible'] == []
    assert all(row['writeAuthorized'] is False for row in value.values())


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


def test_passed_new_fact_can_be_partitioned_beside_a_frozen_noop_rewrite():
    # Given a complete mixed review where a byte-identical rewrite stays held,
    # When the new record is proved independent and self-contained, Then only
    # the new index is eligible; the existing record and whole hold remain.
    value = isolated_run_bun(BASE + r'''
      const known=[{name:candidates[0].name,classification:'safe',type:'project',
        description:'Use pnpm.',content:candidates[0].content}];
      const mixed=[{...candidates[0],kind:'rewrite'},candidates[1]];
      const mixedChecks=i=>[`supported_${i}`,`coherence_${i}`,`supported_description_${i}`,
        ...(i?[`relation_${i}`,`relation_description_${i}`]:[]),
        `counter_${i}_0`,`counter_description_${i}_0`,
        ...(!i?[`counter_preservation_${i}_0`,`counter_permission_${i}_0`]:[])];
      const bound={...review,existingDigest:digest(known),candidatesDigest:digest(mixed),
        candidates:mixed.map((c,index)=>({index,candidateDigest:digest(c),outcome:index?'passed':'held',
          passedChecks:mixedChecks(index).filter(k=>index||k!=='coherence_0'),
          heldChecks:index?[]:['coherence_0']}))};
      const pairProof={...relations,existingDigest:digest(known),candidatesDigest:digest(mixed),
        pairs:[{...relations.pairs[0],candidateDigests:mixed.map(digest)}]};
      const readiness={version:1,purpose:'diagnostic-only',complete:true,model:review.model,
        evidenceDigest:digest(evidence),existingDigest:digest(known),candidatesDigest:digest(mixed),
        candidates:mixed.map((c,index)=>({index,candidateDigest:digest(c),answer:{type:'choice',
          choice:'selfContained',confidence:1,probabilities:{selfContained:1,needsOther:0,unresolved:0}}}))};
      const before=JSON.stringify({mixed,known,bound,pairProof,readiness});
      const selected=partitionReviewedNewMemory(evidence,mixed,known,bound,pairProof,readiness,
        'jev-1.13.0',{allowFrozenNoopComparators:true});
      const legacy=partitionReviewedNewMemory(evidence,mixed,known,bound,pairProof,readiness);
      console.log(JSON.stringify({selected,legacy,unchanged:before===JSON.stringify({mixed,known,bound,pairProof,readiness})}));
    ''')
    assert value['selected'] == {'eligible':[1], 'held':[0], 'writeAuthorized':False}
    assert value['legacy']['eligible'] == []
    assert value['unchanged']


FROZEN_NOOP = BASE + r'''
      const known=[{name:candidates[0].name,classification:'safe',type:'project',
        description:'Use pnpm.',content:candidates[0].content}];
      const mixed=[{...candidates[0],kind:'rewrite'},candidates[1]];
      const mixedChecks=i=>[`supported_${i}`,`coherence_${i}`,`supported_description_${i}`,
        ...(i?[`relation_${i}`,`relation_description_${i}`]:[]),
        `counter_${i}_0`,`counter_description_${i}_0`,
        ...(!i?[`counter_preservation_${i}_0`,`counter_permission_${i}_0`]:[])];
      const bound={...review,existingDigest:digest(known),candidatesDigest:digest(mixed),
        candidates:mixed.map((c,index)=>({index,candidateDigest:digest(c),outcome:index?'passed':'held',
          passedChecks:mixedChecks(index).filter(k=>index||k!=='coherence_0'),
          heldChecks:index?[]:['coherence_0']}))};
      const pairProof={...relations,existingDigest:digest(known),candidatesDigest:digest(mixed),
        pairs:[{...relations.pairs[0],candidateDigests:mixed.map(digest)}]};
      const readiness={version:1,purpose:'diagnostic-only',complete:true,model:review.model,
        evidenceDigest:digest(evidence),existingDigest:digest(known),candidatesDigest:digest(mixed),
        candidates:mixed.map((c,index)=>({index,candidateDigest:digest(c),answer:{type:'choice',
          choice:'selfContained',confidence:1,probabilities:{selfContained:1,needsOther:0,unresolved:0}}}))};

'''


@pytest.mark.parametrize('change', [
    "mixed[0].content+=' ';",
    "mixed[0].content=mixed[0].content.replace('name: tools','name: other');",
    "mixed[0].classification='private';",
    "mixed[0].observations=[];",
    "mixed[0].preservedIn=['report.md'];",
    "mixed[0].contentSha256='invalid';",
    "mixed[0].kind='delete';",
    "mixed[0].name='Tools.md';",
    "known.length=0;",
    "known.push({...known[0]});",
    "known[0].content+=' ';",
    "known[0].name='other.md';",
    "mixed[1].evidence=[{index:0,role:'user',quote:'absent'}];",
    "mixed[0].evidence=[{index:0,role:'user',quote:'absent'}];",
])
def test_frozen_noop_admission_rejects_mutation_or_missing_exact_predecessor(change):
    value = isolated_run_bun(FROZEN_NOOP + change + r'''
      // Rebind all digests: changed data must fail admission with fresh hashes.
      for(const proof of [bound,pairProof,readiness]){
        proof.existingDigest=digest(known);proof.candidatesDigest=digest(mixed);
      }
      for(const proof of [bound,readiness])proof.candidates.forEach((c,i)=>c.candidateDigest=digest(mixed[i]));
      pairProof.pairs[0].candidateDigests=mixed.map(digest);
      console.log(JSON.stringify(partitionReviewedNewMemory(evidence,mixed,known,bound,pairProof,readiness,
        'jev-1.13.0',{allowFrozenNoopComparators:true})));
    ''')
    assert value == {'eligible':[], 'held':[0,1], 'writeAuthorized':False}


@pytest.mark.parametrize('label', ['conflict','dependent','duplicate','unclear','independent-low-confidence','independent-low-probability'])
def test_standalone_answer_cannot_override_persisted_noop_pair(label):
    value = isolated_run_bun(FROZEN_NOOP + r'''
      const label='__LABEL__'; const relation=label.startsWith('independent-')?'independent':label;
      const confidence=label==='independent-low-confidence'?.79:1;
      const probabilities=Object.fromEntries(['independent','duplicate','conflict','dependent','unclear'].map(k=>[k,k===relation?1:0]));
      if(label==='independent-low-probability'){probabilities.independent=.89;probabilities.unclear=.11;}
      pairProof.pairs[0]={...pairProof.pairs[0],relation,status:relation==='unclear'||label.startsWith('independent-')?'uncertain':'decided',
        answer:{type:'choice',choice:relation,confidence,probabilities}};
      console.log(JSON.stringify(partitionReviewedNewMemory(evidence,mixed,known,bound,pairProof,readiness,
        'jev-1.13.0',{allowFrozenNoopComparators:true})));
    '''.replace('__LABEL__',label))
    assert value['eligible'] == [] and value['held'] == [0,1]


@pytest.mark.parametrize('change', [
    'readiness.complete=false;',
    'readiness.candidates.pop();',
    'readiness.candidates[1].answer.confidence=.79;',
    "readiness.candidates[1].answer={type:'choice',choice:'needsOther',confidence:1,probabilities:{selfContained:0,needsOther:1,unresolved:0}};",
    "readiness.candidates[0].candidateDigest='stale';",
    "bound.candidates[0].passedChecks=bound.candidates[0].passedChecks.filter(k=>!k.startsWith('counter_permission'));",
    "bound.candidates[0].passedChecks=bound.candidates[0].passedChecks.filter(k=>!k.startsWith('counter_preservation'));",
    "bound.candidates[1].passedChecks=bound.candidates[1].passedChecks.filter(k=>k!=='coherence_1');bound.candidates[1].heldChecks=['coherence_1'];bound.candidates[1].outcome='held';",
    'bound.counterWindows=[[99]];',
])
def test_mixed_subset_requires_complete_original_checks_and_standalone_proof(change):
    value = isolated_run_bun(FROZEN_NOOP + change + r'''
      console.log(JSON.stringify(partitionReviewedNewMemory(evidence,mixed,known,bound,pairProof,readiness,
        'jev-1.13.0',{allowFrozenNoopComparators:true})));
    ''')
    assert value['eligible'] == [] and value['held'] == [0,1]


# --- Merged from test_composed_memory_partition.py ---
from support import isolated_run_bun

_m1_SETUP = BASE + r'''
const standaloneAnswer=(label='selfContained',confidence=1)=>({type:'choice',choice:label,confidence,
 probabilities:Object.fromEntries(['selfContained','needsOther','unresolved'].map(k=>[k,k===label?1:0]))});
const standalone={version:1,purpose:'diagnostic-only',complete:true,model:review.model,
 evidenceDigest:review.evidenceDigest,existingDigest:review.existingDigest,candidatesDigest:review.candidatesDigest,
 candidates:candidates.map((candidate,index)=>({index,candidateDigest:digest(candidate),answer:standaloneAnswer()}))};
const related=label=>({...relations,pairs:[{...relations.pairs[0],relation:label,
 status:label==='unclear'?'uncertain':'decided',answer:answer(label)}]});
'''


def test_supported_complete_record_is_recovered_only_with_bound_extra_review() -> None:
    rows = isolated_run_bun(_m1_SETUP + r'''
      console.log(JSON.stringify(['conflict','dependent','duplicate','unclear'].map(label=>
        partitionReviewedNewMemory(evidence,candidates,existing,review,related(label),standalone))));
    ''')
    assert all(row['eligible'] == [0] and row['held'] == [1] for row in rows)
    assert all(row['writeAuthorized'] is False for row in rows)


def test_selected_supported_pairs_still_require_independence() -> None:
    rows = isolated_run_bun(_m1_SETUP + r'''
      const both={...review,candidates:review.candidates.map(c=>({...c,outcome:'passed',passedChecks:checks(c.index),heldChecks:[]}))};
      console.log(JSON.stringify(['conflict','dependent','duplicate','unclear'].map(label=>
        partitionReviewedNewMemory(evidence,candidates,existing,both,related(label),standalone))));
    ''')
    assert all(row['eligible'] == [] for row in rows)


def test_invalid_or_uncertain_extra_review_falls_back_to_original_selection() -> None:
    value = isolated_run_bun(_m1_SETUP + r'''
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
    value = isolated_run_bun(_m1_SETUP + r'''
      const variants=[undefined,{...review,evidenceDigest:'stale'},
        {...review,candidates:review.candidates.map(c=>({...c,passedChecks:[]}))}];
      const rows=variants.map(r=>partitionReviewedNewMemory(evidence,candidates,existing,r,related('conflict'),standalone));
      rows.push(partitionReviewedNewMemory(evidence,candidates,existing,review,{...relations,pairs:[]},standalone));
      console.log(JSON.stringify(rows));
    ''')
    assert all(row['eligible'] == [] for row in value)


def test_deletion_order_cannot_erase_another_tentative_pair_obligation() -> None:
    value = isolated_run_bun(_m1_SETUP + r'''
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
    value = isolated_run_bun(_m1_SETUP + r'''
      import {interpretStandaloneMemory as runtime} from './packages/continual-learning/extensions/jev-memory-readiness.ts';
      import {interpretStandaloneMemory as research} from './packages/continual-learning/tests/jev-standalone-memory-research.ts';
      const answers=['selfContained','needsOther','unresolved'].flatMap(label=>[0,.79,.8,1].map(conf=>standaloneAnswer(label,conf)));
      answers.push(undefined,null,{}, {...standaloneAnswer(),probabilities:{selfContained:.89,needsOther:.11,unresolved:0}},
        {...standaloneAnswer(),confidence:NaN},{...standaloneAnswer(),probabilities:{selfContained:1,needsOther:0,unresolved:0,extra:0}});
      console.log(JSON.stringify(answers.map(a=>JSON.stringify(runtime(a))===JSON.stringify(research(a)))));
    ''')
    assert all(value)


# --- Merged from test_memory_final_verification_transaction.py ---
from support import isolated_run_bun

ACTUAL_PARENT = LEGACY_SETUP + r'''
const original={runId:'run_subset',scopeDigest:'scope',artifactHash:'snapshot',inventory:[],selected:[],operations:[],newMemories:candidates};
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {resolveConsolidationRunPaths,acquireConsolidationLock,applyConsolidationPlan,
 normalizeNewMemoryProposals,validatePlanIdentity} from './packages/continual-learning/extensions/consolidation-run.ts';
import {recordLearningProposal,recordLearningMutation,memoryMutationFiles,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
const cwd=join(process.env.PI_CODING_AGENT_DIR,'project');await mkdir(cwd,{recursive:true});
execFileSync('git',['init','--quiet',cwd]);
const paths=resolveConsolidationRunPaths(cwd,'run_subset');await mkdir(paths.runDir,{recursive:true});
const snapshot={...evidence,schemaVersion:1,runId:'run_subset',scopeKey:paths.memory.scopeKey};
const snapshotBytes=JSON.stringify(snapshot);await writeFile(paths.snapshotFile,snapshotBytes);
const manifest={runId:'run_subset',scopeKey:paths.memory.scopeKey,scopeDigest:'b'.repeat(64),
 snapshotDigest:createHash('sha256').update(snapshotBytes).digest('hex'),harnessDir:paths.memory.harnessDir,
 publicDir:paths.memory.publicDir,sourceHashes:{harness:{},public:{}}};
const run={manifest,paths,released:false};
const proof={...input,evidence:snapshot,review:{...review,evidenceDigest:digest(snapshot)},pairs:[{...pair,evidenceDigest:digest(snapshot)}]};
const plan={...original,scopeDigest:manifest.scopeDigest,artifactHash:manifest.snapshotDigest};
const lock=await acquireConsolidationLock(paths,{runId:'run_subset',cwd});
const actualParent={applyChanges:true,
 persistOriginal:plan=>recordLearningProposal(cwd,'memory',plan),
 validateSubset:async plan=>{
   const errors=validatePlanIdentity(plan,manifest);if(errors.length)throw Error(errors.join(';'));
   normalizeNewMemoryProposals(plan,snapshot,[]);
 },
 applySubset:async plan=>recordLearningMutation(cwd,'memory',memoryMutationFiles(cwd,plan.newMemories.map(c=>c.name)),
  ()=>applyConsolidationPlan(run,plan,()=>{activeChecks++;if(activeChecks===3)observedFirstWrite=existsSync(join(manifest.harnessDir,'tools.md'));return activeChecks<cancelAt;}),plan)};
let activeChecks=0,observedFirstWrite=false;
'''


def test_final_verification_rejection_and_cancellation_roll_back_real_writes() -> None:
    for mode in ['reject', 'cancel']:
        value = isolated_run_bun(ACTUAL_PARENT + r'''
          const cancelAt=Infinity;
          const subset={...plan,newMemories:[plan.newMemories[0]]};
          await recordLearningProposal(cwd,'memory',plan);
          let active=true,observed=false,error;
          try {
            await recordLearningMutation(cwd,'memory',memoryMutationFiles(cwd,['tools.md']),
              ()=>applyConsolidationPlan(run,subset,()=>active,async applied=>{
                observed=existsSync(join(manifest.harnessDir,'tools.md')) && existsSync(join(manifest.publicDir,'tools.md'))
                  && existsSync(join(manifest.harnessDir,'MEMORY.md')) && applied.created[0]==='tools.md';
                await Promise.resolve();
                if (MODE==='reject') throw Error('Final receipt rejected');
                active=false;
              }),subset);
          } catch(e) {error=e.message;} finally {await lock.release();}
          console.log(JSON.stringify({observed,error,privateRootExists:existsSync(manifest.harnessDir),
            publicRootExists:existsSync(manifest.publicDir),history:await listLearningHistory(cwd)}));
        '''.replace('MODE', repr(mode)))
        assert value['observed'] is True
        assert 'rejected' in value['error'] if mode == 'reject' else 'cancelled' in value['error']
        assert value['privateRootExists'] is False and value['publicRootExists'] is False
        assert len(value['history']) == 1 and value['history'][0]['status'] == 'proposed'
        assert len(value['history'][0]['proposal']['newMemories']) == 2


# --- Merged from test_independent_memory_parent_pipeline.py ---
from pathlib import Path
import re
import pytest
from typing import Any
from support import run_bun_script

FIXTURE = Path(__file__).with_name('learning-policy-harness.ts')


def run_case(reason: str, model: str = 'jev-1.13.0') -> dict[str, Any]:
    return run_bun_script(FIXTURE, 'remember-subset', env={'CL_JEV_FIXTURE': reason, 'CL_JEV_MODEL': model})


@pytest.mark.parametrize("model", ["jev-1.13.0", "jev-1.14.0"])
def test_parent_applies_supported_original_subset_and_preserves_all_original_intent(model: str) -> None:
    value = run_case('subset-independent', model)
    assert value['relationValidations'] == 1
    assert {'tools.md', 'license.md'} <= set(value['privateFiles'])
    assert {'tools.md', 'license.md'} <= set(value['publicFiles'])
    assert 'cache.md' not in value['privateFiles'] and 'cache.md' not in value['publicFiles']
    assert value['registryReceipt']['operations'] == 2
    assert any(a['outcome'] == 'applied' and a.get('pendingOperations') == 1 for a in value['registryReceipt']['attempts'])
    preserved = [r['proposal'] for r in value['history'] if r['status'] == 'proposed' and r.get('proposal', {}).get('kind') == 'independent-memory-review']
    assert len(preserved) == 1
    assert [m['name'] for m in preserved[0]['originalPlan']['newMemories']] == ['tools.md', 'cache.md', 'license.md']
    assert preserved[0]['eligibleIndexes'] == [0, 2] and preserved[0]['heldIndexes'] == [1]
    assert value['requestCaptured'] and value['agentsUnchanged'] and not value['harnessExists'] and not value['lock']


def test_partial_success_does_not_skip_the_bounded_correction() -> None:
    # Given one held claim alongside independently supported knowledge, When
    # correction removes its unsupported generalization, Then review the entire
    # corrected plan before any partial application can end the learning run.
    value = run_case('subset-repair-complete')
    assert value['semanticRepairs'] == 1
    assert value['registryReceipt']['operations'] == 3
    assert {'tools.md', 'cache.md', 'license.md'} <= set(value['privateFiles'])
    assert not any(a.get('pendingOperations') for a in value['registryReceipt']['attempts'])


def test_failed_correction_retains_original_subset_and_accounts_for_its_writes() -> None:
    value = run_case('subset-repair-invalid')
    assert value['semanticRepairs'] == 1
    assert value['registryReceipt']['operations'] == 2
    attempts = value['registryReceipt']['attempts']
    assert any(a['attempt'] == 0 and a['outcome'] == 'applied'
               and a['operations'] == 2 and a['pendingOperations'] == 1 for a in attempts)
    assert any(a['attempt'] == 1 and a['outcome'] == 'failed' and a['operations'] == 0 for a in attempts)
    assert 'cache.md' not in value['privateFiles']


def test_original_subset_cannot_borrow_the_corrected_plans_retention_gate() -> None:
    # Given original unchanged knowledge was held, When a still-held correction
    # touches it, Then its absence from the corrected retained set does not clear
    # the original plan's independent-application gate.
    value = run_case('subset-retention-fallback')
    assert value['semanticRepairs'] == 1
    assert value['registryReceipt']['operations'] == 0
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['privateFiles']))
    assert any(r['status'] == 'proposed' for r in value['history'])


def test_structurally_repaired_subset_is_not_credited_to_rejected_initial_attempt() -> None:
    value = run_case('structural-subset-repair-invalid')
    assert value['registryReceipt']['operations'] == 2
    attempts = [a for a in value['registryReceipt']['attempts'] if a['phase'] == 'memory']
    assert any(a['attempt'] == 0 and a['operations'] == 0 and a['outcome'] == 'rejected' for a in attempts)
    assert any(a['attempt'] == 1 and a['operations'] == 2 and a['outcome'] == 'applied' for a in attempts)
    assert any(a['attempt'] == 2 and a['operations'] == 0 and a['outcome'] == 'failed' for a in attempts)


def test_unrepairable_name_collision_does_not_spend_a_correction_or_review_call() -> None:
    value = run_case('subset-name-collision')
    assert value['totalRepairs'] == 0
    assert value['jevValidations'] == []
    assert value['registryReceipt']['operations'] == 0
    assert 'cache.md' in value['privateFiles']
    assert not ({'tools.md', 'license.md'} & set(value['privateFiles']))
    assert any(r['status'] == 'proposed' for r in value['history'])


def test_cancelled_collision_does_not_append_a_proposal_from_the_old_run() -> None:
    value = run_case('subset-name-collision-cancel')
    assert value['totalRepairs'] == 0
    assert value.get('registryReceipt', {}).get('operations', 0) == 0
    assert not any(r['status'] == 'proposed' for r in value['history'])
    assert not value['lock']


def test_uncertain_unavailable_and_default_gate_keep_original_proposal_without_subset_writes() -> None:
    for reason in ['subset-uncertain', 'subset-unavailable', 'subset-disabled']:
        value = run_case(reason)
        assert value['registryReceipt']['operations'] == 0
        assert 'tools.md' not in value['privateFiles'] and 'license.md' not in value['privateFiles']
        assert any(r['status'] == 'proposed' for r in value['history'])
        assert value['relationValidations'] == (0 if reason == 'subset-disabled' else 1)
        assert value['requestCaptured'] and not value['harnessExists']


def test_preservation_failure_and_evidence_tamper_prevent_all_subset_writes() -> None:
    for reason in ['subset-preservation-fails', 'subset-tamper-queue']:
        value = run_case(reason)
        assert value['registryReceipt']['operations'] == 0
        assert 'tools.md' not in value['privateFiles'] and 'license.md' not in value['publicFiles']
        assert any(a['outcome'] == 'failed' for a in value['registryReceipt']['attempts'])
        assert value['summarySubject'] in {'finished with issues: memory failed', 'finished with issues: memory rejected'}
        assert not value['lock']


def test_final_validator_failure_rolls_back_written_subset_and_preserves_original_proposal() -> None:
    value = run_case('subset-final-validator-fails')
    assert value['finalVerificationObservedWrites'] is True
    assert value['memoryFilesRestored'] is True
    assert value['registryReceipt']['operations'] == 0
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['privateFiles']))
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['publicFiles']))
    assert value['newAppliedHistoryRecords'] == 0
    assert any(r.get('proposal', {}).get('kind') == 'independent-memory-review' for r in value['history'])
    assert value['summarySubject'] == 'finished with issues: memory failed' and not value['lock']


def test_composed_parent_recovers_only_supported_records_and_preserves_full_proposal() -> None:
    value = run_case('subset-composed')
    assert value['registryReceipt']['operations'] == 2
    assert {'tools.md', 'license.md'} <= set(value['privateFiles'])
    assert 'cache.md' not in value['privateFiles']
    preserved = [r['proposal'] for r in value['history'] if r.get('proposal', {}).get('kind') == 'independent-memory-review']
    assert len(preserved) == 1
    assert preserved[0]['eligibleIndexes'] == [0, 2] and preserved[0]['heldIndexes'] == [1]
    assert len(preserved[0]['originalPlan']['newMemories']) == 3
    assert any(a.get('jev', {}).get('strategy') == 'standalone-memory' and a['outcome'] == 'noop' for a in value['registryReceipt']['attempts'])
    assert any(a['outcome'] == 'applied' and a.get('pendingOperations') == 1 for a in value['registryReceipt']['attempts'])
    assert value['agentsUnchanged'] and not value['harnessExists'] and not value['lock']


def test_composed_proof_without_parent_gate_cannot_change_original_selection() -> None:
    value = run_case('subset-composed-default')
    assert value['registryReceipt']['operations'] == 0
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['privateFiles']))
    assert not value['harnessExists'] and value['agentsUnchanged']


@pytest.mark.parametrize("model", ["jev-1.13.0", "jev-1.14.0"])
def test_production_pipeline_keeps_verified_independent_knowledge_available_to_next_task(model: str) -> None:
    value = run_case('subset-production', model)
    assert value['registryReceipt']['operations'] == 2
    assert value['relationValidations'] == 1
    assert value['productionJudgeOptions']['independentMemoryApplication'] is True
    assert value['productionJudgeOptions']['composedMemoryApplication'] is True
    assert any(a.get('pendingOperations') == 1 for a in value['registryReceipt']['attempts'])
    delivered = [item for hook in value['nextMemory'] for item in hook.get('message', {}).get('details', {}).get('retrieved', [])]
    # The user-requested discovery contract exposes filenames, not bodies.
    # Independent admitted facts remain discoverable; the held fact stays absent.
    assert delivered == []
    assert all(hook['result'] is None for hook in value['nextMemory'])
    indexed = {name for hook in value['nextMemory'] for name in
               re.findall(r'^- ([^\n]+?\.md)(?: — |$)', hook['systemPromptOptions']['sections'].get('project_memory_discovery', ''), re.MULTILINE)}
    assert indexed == {'tools.md', 'license.md'}
    assert all('cache.md' not in str(hook) for hook in value['nextMemory'])
    assert any(record.get('proposal', {}).get('heldIndexes') == [1] for record in value['history'])


def test_verified_repair_subset_is_applied_and_keeps_unresolved_work_pending() -> None:
    # Given a source-backed npm-to-pnpm correction, When full review admits only a
    # subset, Then apply that subset and preserve the still-held original work.
    value = run_case('subset-production-after-repair')
    assert value['registryReceipt']['operations'] == 2
    assert value['relationValidations'] == 1
    assert value['semanticRepairs'] == 1
    assert value['repairableFieldsReceived']['fields']['tools.md'] == ['body', 'description']
    assert 'tools.md' in value['repairableFieldsReceived']['names']
    assert {'tools.md', 'license.md'} <= set(value['privateFiles'])
    assert 'cache.md' not in value['privateFiles']
    assert any(a['attempt'] == 1 and a['outcome'] == 'applied' and a.get('pendingOperations') == 1
               for a in value['registryReceipt']['attempts'])
    assert any(r.get('proposal', {}).get('heldIndexes') == [1] for r in value['history'])


def test_cancellation_during_relationship_review_stops_after_bounded_repair_without_writes() -> None:
    value = run_case('subset-cancel-relations')
    assert value.get('registryReceipt', {}).get('operations', 0) == 0
    assert value['semanticRepairs'] == 1
    assert not ({'tools.md', 'license.md', 'cache.md'} & set(value['privateFiles']))
    assert not value['lock']


def test_whole_held_proposal_binds_diagnostics_to_its_exact_original_plan() -> None:
    # Given a held whole plan after bounded correction, When preserving it,
    # Then parent diagnostics bind that exact plan rather than a later repair.
    import hashlib
    import json
    value = run_case('subset-disabled')
    proposals = [r['proposal'] for r in value['history'] if r['status'] == 'proposed'
                 and r.get('proposal', {}).get('kind') == 'independent-memory-review']
    assert len(proposals) == 1
    proposal = proposals[0]
    expected = hashlib.sha256(json.dumps(proposal['originalPlan'], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    assert proposal['reviewedPlanDigest'] == expected
    assert proposal['eligibleIndexes'] == []
    assert proposal['heldIndexes'] == list(range(len(proposal['originalPlan']['newMemories'])))
    assert isinstance(proposal['candidateFailures'], list)
    assert value['registryReceipt']['operations'] == 0


def test_subset_audit_history_does_not_invalidate_selected_memory_origin() -> None:
    value = run_bun_script(FIXTURE, 'remember-subset', env={'CL_JEV_FIXTURE': 'subset-independent', 'CL_MEMORY_ORIGIN': '1'})
    assert value['registryReceipt']['operations'] == 2, value['registryReceipt']
    assert {'known.md', 'tools.md', 'license.md'} <= set(value['privateFiles'])
    assert 'cache.md' not in value['privateFiles']
    preserved = [r['proposal'] for r in value['history'] if r.get('proposal', {}).get('kind') == 'independent-memory-review']
    assert len(preserved) == 1
    assert preserved[0]['eligibleIndexes'] == [0, 2] and preserved[0]['heldIndexes'] == [1]
    assert not value['lock']


def test_cancelled_deferred_history_failure_keeps_the_only_complete_audit() -> None:
    value = run_bun_script(FIXTURE, 'remember-subset', env={'CL_JEV_FIXTURE': 'subset-independent', 'CL_MEMORY_ORIGIN': '1', 'CL_ORIGIN_AUDIT_FAIL': 'cancel'})
    assert value['originAuditArtifacts'], value
    assert not value['lock']
