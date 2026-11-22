from support import isolated_run_bun
from test_independent_memory_partition import LEGACY_SETUP

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
