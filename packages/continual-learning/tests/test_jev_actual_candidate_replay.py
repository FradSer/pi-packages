from support import isolated_run_bun


def test_actual_replay_binds_original_files_before_using_candidates() -> None:
    # Given frozen actual-plan files, When any source changes, Then fail before
    # constructing inference input or treating a changed candidate as the original.
    rows = isolated_run_bun(r'''
      import {loadActualCandidateReplay} from './packages/continual-learning/tests/actual-candidate-replay.ts';
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {createHash} from 'node:crypto';
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'cl-actual-replay-'));const quote='This project uses pnpm.';
      const snapshot={contextEnabled:true,entries:[{role:'user',content:quote}]};const plan={operations:[],selected:[],newMemories:[{name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: '+quote+'\ntype: project\n---\n'+quote,evidence:[{index:0,quote,role:'user'}]}]};
      const input={id:'public-fixture',stage:'memory',format:'plan',plan:path.join(root,'plan.json'),snapshot:path.join(root,'snapshot.json'),planHash:'',snapshotHash:''};
      await fs.writeFile(input.plan,JSON.stringify(plan));await fs.writeFile(input.snapshot,JSON.stringify(snapshot));for(const k of ['plan','snapshot'])input[k+'Hash']=createHash('sha256').update(await fs.readFile(input[k])).digest('hex');
      const valid=await loadActualCandidateReplay(input);await fs.writeFile(input.plan,JSON.stringify({...plan,newMemories:[]}));let changedRejected=false;try{await loadActualCandidateReplay(input);}catch{changedRejected=true;}
      console.log(JSON.stringify({candidateCount:valid.candidates.length,evidenceUnchanged:JSON.stringify(valid.snapshot)===JSON.stringify(snapshot),changedRejected}));await fs.rm(root,{recursive:true,force:true});
    ''')
    assert rows == {'candidateCount': 1, 'evidenceUnchanged': True, 'changedRejected': True}


def test_actual_replay_retains_partial_usage_without_pricing_unknown_models() -> None:
    # Given incomplete responses with known usage, When summarizing the run,
    # Then retain known lower bounds and distinguish unverified model estimates.
    rows = isolated_run_bun(r'''
      import {summarizeActualReplayUsage} from './packages/continual-learning/tests/actual-candidate-replay.ts';
      console.log(JSON.stringify(summarizeActualReplayUsage([
       {model:'jev-1.13.0',reason:'supported',inputTokens:10,estimatedCostUsd:.00000042},
       {model:'jev-1.13.0',reason:'unavailable',knownInputTokens:20,knownEstimatedCostUsd:.00000084},
       {model:'unexpected-version',reason:'invalid-response',knownInputTokens:30,knownEstimatedCostUsd:999},
       {reason:'timeout',knownInputTokens:40,knownEstimatedCostUsd:.00000168}
      ],'jev-1.13.0')));
    ''')
    assert rows['knownInputTokens'] == 100
    assert rows['knownEstimatedCostUsd'] == 0.00000126
    assert rows['unpricedInputTokens'] == 70
    assert rows['unverifiedJudgeEstimatedCostUsd'] == 999.00000168
