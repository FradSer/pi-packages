from support import isolated_run_bun
from test_jev_independent_subset_research import SETUP


TRANSACTION = SETUP + r'''
import {runSubsetParentTransactionResearch} from './packages/continual-learning/tests/subset-parent-transaction-research.ts';
const original={runId:'run_subset',scopeDigest:'scope',artifactHash:'snapshot',inventory:[],selected:[],operations:[],newMemories:candidates};
const events=[];
const parent={applyChanges:true,
 persistOriginal:async plan=>{events.push({step:'persist',plan});return 'parent-proposal';},
 validateSubset:async plan=>{events.push({step:'validate',plan});},
 applySubset:async plan=>{events.push({step:'apply',plan});return {created:plan.newMemories.map(c=>c.name)};}};
'''


def test_partial_transaction_preserves_original_before_unchanged_parent_apply() -> None:
    value = isolated_run_bun(TRANSACTION + r'''
      const before=JSON.stringify({original,input});
      const result=await runSubsetParentTransactionResearch(original,input,parent);
      console.log(JSON.stringify({result,events,unchanged:before===JSON.stringify({original,input})}));
    ''')
    assert value['result']['outcome'] == 'applied'
    assert value['result']['appliedIndexes'] == [0]
    assert value['result']['heldIndexes'] == [1]
    assert value['result']['proposalId'] == 'parent-proposal'
    assert value['unchanged']
    assert [event['step'] for event in value['events']] == ['persist', 'validate', 'apply']
    assert len(value['events'][0]['plan']['newMemories']) == 2
    subset = value['events'][2]['plan']
    full = value['events'][0]['plan']
    assert subset['newMemories'] == full['newMemories'][:1]
    assert {k: v for k, v in subset.items() if k != 'newMemories'} == {k: v for k, v in full.items() if k != 'newMemories'}


def test_denied_permission_and_incomplete_proof_preserve_all_intent() -> None:
    value = isolated_run_bun(TRANSACTION + r'''
      const results=[];
      results.push(await runSubsetParentTransactionResearch(original,input,{...parent,applyChanges:false}));
      results.push(await runSubsetParentTransactionResearch(original,{...input,pairs:[]},parent));
      console.log(JSON.stringify({results,events}));
    ''')
    assert all(result['outcome'] == 'proposed' and result['appliedIndexes'] == [] for result in value['results'])
    assert all(result['heldIndexes'] == [0, 1] for result in value['results'])
    assert [event['step'] for event in value['events']] == ['persist', 'persist']
    assert all(len(event['plan']['newMemories']) == 2 for event in value['events'])


def test_original_candidate_mapping_cannot_change_text_privacy_or_operations() -> None:
    value = isolated_run_bun(TRANSACTION + r'''
      const variants=[{...original,newMemories:[...candidates].reverse()},
        {...original,newMemories:candidates.map((c,i)=>i?c:{...c,content:c.content+' changed'})},
        {...original,newMemories:candidates.map((c,i)=>i?{...c,classification:'safe'}:c)},
        {...original,operations:[{kind:'delete',name:'prior.md'}]}];
      const results=[];
      for(const plan of variants)try{await runSubsetParentTransactionResearch(plan,input,parent);results.push('bad');}catch{results.push('rejected');}
      console.log(JSON.stringify({results,events}));
    ''')
    assert value['results'] == ['rejected'] * 4
    assert value['events'] == []


def test_preservation_failure_or_mutation_across_await_cannot_apply() -> None:
    value = isolated_run_bun(TRANSACTION + r'''
      const failures=[];
      try{await runSubsetParentTransactionResearch(original,input,{...parent,persistOriginal:async()=>{throw Error('disk full');}});}catch{failures.push('preservation');}
      try{await runSubsetParentTransactionResearch(original,input,{...parent,persistOriginal:async plan=>{events.push({step:'persist',plan});input.evidence.entries[0].content+=' changed';return 'proposal';}});}catch{failures.push('stale');}
      console.log(JSON.stringify({failures,events}));
    ''')
    assert value['failures'] == ['preservation', 'stale']
    assert [event['step'] for event in value['events']] == ['persist']


def test_parent_validation_or_write_failure_retains_proposal_and_never_reports_applied() -> None:
    value = isolated_run_bun(TRANSACTION + r'''
      const failures=[];
      for(const step of ['validateSubset','applySubset'])try{
        await runSubsetParentTransactionResearch(original,input,{...parent,[step]:async()=>{throw Error(step);}});
      }catch{failures.push(step);}
      console.log(JSON.stringify({failures,events}));
    ''')
    assert value['failures'] == ['validateSubset', 'applySubset']
    assert [event['step'] for event in value['events']] == ['persist', 'persist', 'validate']


ACTUAL_PARENT = TRANSACTION + r'''
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


def test_actual_parent_subset_writes_only_original_supported_file_and_preserves_full_proposal() -> None:
    value = isolated_run_bun(ACTUAL_PARENT + r'''
      const cancelAt=Infinity;
      let result;
      try{result=await runSubsetParentTransactionResearch(plan,proof,actualParent);}finally{await lock.release();}
      const history=await listLearningHistory(cwd);
      console.log(JSON.stringify({result,history,
        privateBody:await readFile(join(manifest.harnessDir,'tools.md'),'utf8'),
        publicBody:await readFile(join(manifest.publicDir,'tools.md'),'utf8'),
        heldPrivateExists:await Bun.file(join(manifest.harnessDir,'report.md')).exists(),
        heldPublicExists:await Bun.file(join(manifest.publicDir,'report.md')).exists()}));
    ''')
    assert value['result']['appliedIndexes'] == [0]
    assert value['privateBody'] == value['publicBody']
    assert value['heldPrivateExists'] is False and value['heldPublicExists'] is False
    proposal = next(record for record in value['history'] if record['status'] == 'proposed')
    assert [item['name'] for item in proposal['proposal']['newMemories']] == ['tools.md', 'report.md']
    assert any(record['status'] == 'applied' for record in value['history'])


def test_actual_parent_cancellation_rolls_back_both_roots_and_keeps_original_proposal() -> None:
    value = isolated_run_bun(ACTUAL_PARENT + r'''
      const cancelAt=3;let error;
      try{await runSubsetParentTransactionResearch(plan,proof,actualParent);}catch(e){error=e.message;}finally{await lock.release();}
      console.log(JSON.stringify({error,activeChecks,observedFirstWrite,privateRootExists:existsSync(manifest.harnessDir),publicRootExists:existsSync(manifest.publicDir),history:await listLearningHistory(cwd),
        privateExists:await Bun.file(join(manifest.harnessDir,'tools.md')).exists(),
        publicExists:await Bun.file(join(manifest.publicDir,'tools.md')).exists(),
        privateIndexExists:await Bun.file(join(manifest.harnessDir,'MEMORY.md')).exists(),
        publicIndexExists:await Bun.file(join(manifest.publicDir,'MEMORY.md')).exists()}));
    ''')
    assert 'cancelled' in value['error']
    assert 'rollback failed' not in value['error']
    assert value['activeChecks'] == 3
    assert value['observedFirstWrite'] is True
    assert value['privateRootExists'] is False and value['publicRootExists'] is False
    assert all(value[key] is False for key in ['privateExists', 'publicExists', 'privateIndexExists', 'publicIndexExists'])
    assert len(value['history']) == 1
    assert value['history'][0]['status'] == 'proposed'
    assert len(value['history'][0]['proposal']['newMemories']) == 2


def test_revoked_permission_after_validation_preserves_request_without_writing() -> None:
    value = isolated_run_bun(TRANSACTION + r'''
      const revocable={...parent,validateSubset:async plan=>{events.push({step:'validate',plan});revocable.applyChanges=false;}};
      const result=await runSubsetParentTransactionResearch(original,input,revocable);
      console.log(JSON.stringify({result,events}));
    ''')
    assert value['result']['outcome'] == 'proposed'
    assert value['result']['heldIndexes'] == [0, 1]
    assert [event['step'] for event in value['events']] == ['persist', 'validate']


def test_incomplete_or_wrong_parent_write_result_cannot_claim_applied() -> None:
    value = isolated_run_bun(TRANSACTION + r'''
      const outcomes=[];
      for(const result of [undefined,{outcome:'rejected'},{created:[]},{created:['extra.md']},{created:['tools.md','tools.md']},
        {created:['tools.md'],outcome:'rejected'}])try{
        await runSubsetParentTransactionResearch(original,input,{...parent,applySubset:async()=>result});outcomes.push('bad');
      }catch{outcomes.push('rejected');}
      console.log(JSON.stringify(outcomes));
    ''')
    assert value == ['rejected'] * 6
