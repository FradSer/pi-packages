from support import isolated_run_bun
from test_jev_subset_parent_transaction_research import ACTUAL_PARENT


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
