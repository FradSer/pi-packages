from support import isolated_run_bun


def test_real_failed_memory_plan_is_bound_to_unchanged_original_evidence() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {buildMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const f=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-replay-held-feedback.json','utf8'));
      const entries=JSON.parse(f.snapshotText).entries;
      const input={receipt:f.receipt,backlogId:f.receipt.input.backlogId,entries,proposal:f.proposal,snapshotText:f.snapshotText};
      const result=buildMemoryReplayFeedback(input);
      const altered=structuredClone(input);altered.entries[0].message.content='Changed task';
      const foreign=structuredClone(input);foreign.backlogId='another-task';
      const stale=structuredClone(input);stale.snapshotText+=' ';
      const oversized=structuredClone(input);oversized.proposal.originalPlan.newMemories[0].content='x'.repeat(128001);
      const bound=structuredClone(input);Object.assign(bound.proposal,{reviewedPlanDigest:sha256Digest(JSON.stringify(bound.proposal.originalPlan)),candidateFailures:bound.receipt.attempts.filter(a=>a.jev?.candidateFailures?.length).at(-1).jev.candidateFailures});
      const boundResult=buildMemoryReplayFeedback(bound);
      const invalidHint=structuredClone(bound);invalidHint.proposal.candidateFailures[0].reason='ARBITRARY_DIAGNOSTIC';
      const wrongPlan=structuredClone(bound);wrongPlan.proposal.originalPlan.newMemories[0].content+='Changed';
      console.log(JSON.stringify({result,boundResult,wrongPlan:buildMemoryReplayFeedback(wrongPlan),changed:buildMemoryReplayFeedback(altered),foreign:buildMemoryReplayFeedback(foreign),stale:buildMemoryReplayFeedback(stale),oversized:buildMemoryReplayFeedback(oversized),invalidHint:buildMemoryReplayFeedback(invalidHint),entriesUnchanged:JSON.stringify(entries)===JSON.stringify(JSON.parse(f.snapshotText).entries)}));
    ''')
    feedback = value['result']
    assert feedback['kind'] == 'memory-replay-feedback'
    assert feedback['heldIndexes'] == [0, 1]
    assert feedback['eligibleIndexes'] == [2, 3]
    assert feedback['candidates'][1]['name'] == 'p-limit-concurrency-reservation.md'
    assert feedback['failures'] == []
    assert feedback['diagnosticsStatus'] == 'unavailable'
    assert value['boundResult']['diagnosticsStatus'] == 'bound'
    assert value['wrongPlan'] is None
    assert value['boundResult']['failures'][1] == {
        'candidateIndex': 1, 'dimension': 'support', 'field': 'description',
        'reason': 'uncertain',
    }
    assert value['changed'] is None
    assert value['foreign'] is None
    assert value['stale'] is None
    assert value['oversized'] is None
    assert value['invalidHint'] is None
    assert value['entriesUnchanged'] is True


def test_replay_delivers_prior_failed_fields_and_bound_proposal_without_diagnostic_prose() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'cl-feedback-')),agent=process.env.PI_CODING_AGENT_DIR;
      const dir=path.join(agent,'sessions','project');fs.mkdirSync(dir,{recursive:true});const manager=SessionManager.create(cwd,dir);
      manager.appendMessage({role:'user',content:'Remember source behavior only when a slot is available.',timestamp:1});
      manager.appendMessage({role:'assistant',content:[{type:'text',text:'Observed the conditional source branch.'}],api:'openai-completions',provider:'fixture',model:'fixture',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:2});
      const entries=manager.buildContextEntries(),slice=currentTaskSlice(entries),paths=resolveMemoryPaths(cwd,agent);
      enqueueBacklog({cwd,agentDir:agent,sessionFile:manager.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(slice)),reason:'learning-failed'});
      const batchId='batch_'+ 'a'.repeat(32),runId='run_fixture_'+ 'b'.repeat(16),historyId='change_fixture_'+ 'c'.repeat(16);
      const snapshotText=JSON.stringify({runId,scopeKey:paths.scopeKey,entries:slice.entries});
      const run=path.join(paths.runsDir,runId);fs.mkdirSync(run,{recursive:true});fs.writeFileSync(path.join(run,'snapshot.json'),snapshotText);
      const candidate={name:'reservation.md',kind:'project',classification:'safe',content:'---\nname: reservation\ndescription: A conditional source behavior\ntype: project\n---\nEarlier proposed claim.'};
      const proposal={kind:'independent-memory-review',version:1,originalPlan:{kind:'memory-consolidation-plan',runId,scopeKey:paths.scopeKey,snapshotDigest:sha256Digest(snapshotText),operations:[],newMemories:[candidate]},eligibleIndexes:[],heldIndexes:[0]};
      const history=path.join(agent,'memory','history',paths.scopeKey);fs.mkdirSync(history,{recursive:true});
      fs.writeFileSync(path.join(history,historyId+'.json'),JSON.stringify({version:1,batchId,id:historyId,cwd:paths.cwd,agentDir:paths.agentDir,phase:'memory',createdAt:new Date().toISOString(),status:'proposed',changes:[],proposal}));
      const failure={kind:'learning-pipeline-receipt',version:1,mode:'automatic',batchId,screen:{memory:true,harness:false,agents:false,reasons:[]},attempts:[{phase:'memory',attempt:1,outcome:'proposed',operations:0,pendingOperations:1,durationMs:1,diagnostic:'ARBITRARY_CHILD_PROSE',jev:{stage:'memory',status:'propose',reason:'uncertain',durationMs:1,candidateFailures:[{candidateIndex:0,dimension:'support',field:'description',reason:'uncertain'}]}}],totals:{input:10,output:1,cacheRead:0,cacheWrite:0,totalTokens:11,cost:0},costAvailable:false,operations:0,retries:1};
      Object.assign(proposal,{reviewedPlanDigest:sha256Digest(JSON.stringify(proposal.originalPlan)),candidateFailures:failure.attempts[0].jev.candidateFailures});
      fs.writeFileSync(path.join(history,historyId+'.json'),JSON.stringify({version:1,batchId,id:historyId,cwd:paths.cwd,agentDir:paths.agentDir,phase:'memory',createdAt:new Date().toISOString(),status:'proposed',changes:[],proposal}));
      const first=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async input=>({...failure,input:{source:'backlog-session',entryCount:input.entries.length,backlogId:input.id}})});
      for(let i=0;i<50;i++) {
        const id='change_zz'+i.toString(36)+'_'+'f'.repeat(16);
        fs.writeFileSync(path.join(history,id+'.json'),JSON.stringify({version:1,batchId:'batch_'+'f'.repeat(32),id,cwd:paths.cwd,agentDir:paths.agentDir,phase:'harness',createdAt:new Date().toISOString(),status:'proposed',changes:[],proposal:{kind:'unrelated'}}));
      }
      const snapshotFile=path.join(run,'snapshot.json'),outside=path.join(cwd,'outside-snapshot');fs.writeFileSync(outside,snapshotText);
      fs.unlinkSync(snapshotFile);fs.symlinkSync(outside,snapshotFile);let unsafeCalls=0;
      const unsafe=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async()=>{unsafeCalls++;return undefined;}});
      const outsideUnchanged=fs.readFileSync(outside,'utf8')===snapshotText;fs.unlinkSync(snapshotFile);fs.writeFileSync(snapshotFile,snapshotText);
      let seen;const second=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async input=>{seen=input;return {...failure,batchId:'batch_'+'d'.repeat(32),attempts:[{phase:'selector',attempt:0,outcome:'failed',operations:0,durationMs:1}],input:{source:'backlog-session',entryCount:input.entries.length,backlogId:input.id}};}});
      let afterSelectorFailure;await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async input=>{afterSelectorFailure=input.memoryReplayFeedback;return {...failure,batchId:'batch_'+'e'.repeat(32),screen:{memory:true,harness:true,agents:false,reasons:[]},attempts:[{phase:'memory',attempt:0,outcome:'noop',operations:0,durationMs:1},{phase:'harness',attempt:0,outcome:'failed',operations:0,pendingOperations:1,durationMs:1}],input:{source:'backlog-session',entryCount:input.entries.length,backlogId:input.id}};}});
      let afterMemoryResolved;await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async input=>{afterMemoryResolved=input.memoryReplayFeedback??null;return undefined;}});
      console.log(JSON.stringify({first,second,unsafe,unsafeCalls,outsideUnchanged,feedback:seen?.memoryReplayFeedback,afterSelectorFailure,afterMemoryResolved,entriesUnchanged:JSON.stringify(seen?.entries)===JSON.stringify(slice.entries),pending:backlogStatus(cwd,agent).pending,hasProse:(JSON.stringify(seen)??'').includes('ARBITRARY_CHILD_PROSE')}));
      fs.rmSync(cwd,{recursive:true,force:true});
    ''')
    assert value.get('feedback', {}).get('heldIndexes') == [0], value
    assert value['feedback']['candidates'][0]['name'] == 'reservation.md'
    assert value['feedback']['failures'][0]['field'] == 'description'
    assert value['entriesUnchanged'] is True
    assert value['pending'] == 1
    assert value['hasProse'] is False
    assert value.get('afterSelectorFailure') == value['feedback'], value
    assert value['afterMemoryResolved'] is None
    assert value['unsafe']['error'] == 'Learning replay could not complete safely'
    assert value['unsafeCalls'] == 0
    assert value['outsideUnchanged'] is True


def test_bound_failure_is_in_frozen_dossier_without_expanding_selection_or_evidence() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {buildMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
      import {selectIncrementalLearning} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const f=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-replay-held-feedback.json','utf8'));
      const entries=JSON.parse(f.snapshotText).entries;
      const feedback=buildMemoryReplayFeedback({receipt:f.receipt,backlogId:f.receipt.input.backlogId,entries,proposal:f.proposal,snapshotText:f.snapshotText});
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'cl-feedback-dossier-'));const taskSlice={kind:'learning-task-slice',version:1,entries};
      const outcome=await selectIncrementalLearning({cwd,taskSlice,contextDigest:sha256Digest(JSON.stringify(taskSlice)),outputDir:path.join(cwd,'private-run'),memoryOnly:true,allowEmptyIndexRouting:true,memoryReplayFeedback:feedback});
      const raw=fs.readFileSync(outcome.dossierPath,'utf8'),dossier=JSON.parse(raw);
      console.log(JSON.stringify({outcome:outcome.outcome,selected:outcome.selection.selected,evidenceUnchanged:JSON.stringify(dossier.taskSlice)===JSON.stringify(taskSlice),feedbackUnchanged:JSON.stringify(dossier.memoryReplayFeedback)===JSON.stringify(feedback),dossierDigestMatches:outcome.dossierDigest===sha256Digest(raw)}));
      fs.rmSync(cwd,{recursive:true,force:true});
    ''')
    assert value == {
        'outcome': 'selected', 'selected': [], 'evidenceUnchanged': True,
        'feedbackUnchanged': True, 'dossierDigestMatches': True,
    }


def test_verified_failure_extension_keeps_older_prefix_feedback_but_not_resolved_holds() -> None:
    # Given a held Memory plan and a byte-identical same-task verifier extension,
    # When replay changes the receipt owner to the longest slice,
    # Then prior bound diagnostics survive; later completed Memory suppresses them.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'cl-feedback-')),agent=process.env.PI_CODING_AGENT_DIR;
      const dir=path.join(agent,'sessions','project');fs.mkdirSync(dir,{recursive:true});const manager=SessionManager.create(cwd,dir);
      manager.appendMessage({role:'user',content:'Remember source behavior only when a slot is available.',timestamp:1});
      manager.appendMessage({role:'assistant',content:[{type:'text',text:'Observed the conditional source branch.'}],api:'openai-completions',provider:'fixture',model:'fixture',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:2});
      const entries=manager.buildContextEntries(),slice=currentTaskSlice(entries),paths=resolveMemoryPaths(cwd,agent);
      enqueueBacklog({cwd,agentDir:agent,sessionFile:manager.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(slice)),reason:'learning-failed'});
      const batchId='batch_'+ 'a'.repeat(32),runId='run_fixture_'+ 'b'.repeat(16),historyId='change_fixture_'+ 'c'.repeat(16);
      const snapshotText=JSON.stringify({runId,scopeKey:paths.scopeKey,entries:slice.entries});
      const run=path.join(paths.runsDir,runId);fs.mkdirSync(run,{recursive:true});fs.writeFileSync(path.join(run,'snapshot.json'),snapshotText);
      const candidate={name:'reservation.md',kind:'project',classification:'safe',content:'---\nname: reservation\ndescription: A conditional source behavior\ntype: project\n---\nEarlier proposed claim.'};
      const proposal={kind:'independent-memory-review',version:1,originalPlan:{kind:'memory-consolidation-plan',runId,scopeKey:paths.scopeKey,snapshotDigest:sha256Digest(snapshotText),operations:[],newMemories:[candidate]},eligibleIndexes:[],heldIndexes:[0]};
      const history=path.join(agent,'memory','history',paths.scopeKey);fs.mkdirSync(history,{recursive:true});
      fs.writeFileSync(path.join(history,historyId+'.json'),JSON.stringify({version:1,batchId,id:historyId,cwd:paths.cwd,agentDir:paths.agentDir,phase:'memory',createdAt:new Date().toISOString(),status:'proposed',changes:[],proposal}));
      const failure={kind:'learning-pipeline-receipt',version:1,mode:'automatic',batchId,screen:{memory:true,harness:false,agents:false,reasons:[]},attempts:[{phase:'memory',attempt:1,outcome:'proposed',operations:0,pendingOperations:1,durationMs:1,diagnostic:'ARBITRARY_CHILD_PROSE',jev:{stage:'memory',status:'propose',reason:'uncertain',durationMs:1,candidateFailures:[{candidateIndex:0,dimension:'support',field:'description',reason:'uncertain'}]}}],totals:{input:10,output:1,cacheRead:0,cacheWrite:0,totalTokens:11,cost:0},costAvailable:false,operations:0,retries:1};
      Object.assign(proposal,{reviewedPlanDigest:sha256Digest(JSON.stringify(proposal.originalPlan)),candidateFailures:failure.attempts[0].jev.candidateFailures});
      fs.writeFileSync(path.join(history,historyId+'.json'),JSON.stringify({version:1,batchId,id:historyId,cwd:paths.cwd,agentDir:paths.agentDir,phase:'memory',createdAt:new Date().toISOString(),status:'proposed',changes:[],proposal}));
      const first=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async input=>({...failure,input:{source:'backlog-session',entryCount:input.entries.length,backlogId:input.id}})});

      manager.appendMessage({role:'user',content:'continue',timestamp:3});
      manager.appendMessage({role:'toolResult',toolCallId:'verifier',toolName:'read',content:[{type:'text',text:'Actual verification failed: new regression file violates project lint.'}],isError:false,timestamp:4});
      const extended=manager.buildContextEntries(),extendedSlice=currentTaskSlice(extended);
      enqueueBacklog({cwd,agentDir:agent,sessionFile:manager.getSessionFile(),from:0,to:extended.length-1,digest:sha256Digest(JSON.stringify(extendedSlice)),reason:'learning-failed'});
      let seen;await replayLearningBacklog({cwd,agentDir:agent,force:true,limit:1,learn:async input=>{seen=input;return undefined;}});
      await replayLearningBacklog({cwd,agentDir:agent,force:true,limit:1,learn:async input=>({...failure,batchId:'batch_'+'e'.repeat(32),screen:{memory:true,harness:true,agents:false,reasons:[]},attempts:[{phase:'memory',attempt:0,outcome:'noop',operations:0,durationMs:1},{phase:'harness',attempt:0,outcome:'failed',operations:0,pendingOperations:1,durationMs:1}],input:{source:'backlog-session',entryCount:input.entries.length,sessionId:input.sessionId,sourceDigest:input.sourceDigest,backlogId:input.id,backlogCoverage:input.backlogCoverage}})});
      let afterCompletion;await replayLearningBacklog({cwd,agentDir:agent,force:true,limit:1,learn:async input=>{afterCompletion=input.memoryReplayFeedback??null;return undefined;}});
      const oldFile=path.join(agent,'learning',paths.scopeKey,`replay-${first.outcomes[0].id}.json`);
      const oldState=JSON.parse(fs.readFileSync(oldFile,'utf8'));
      oldState.attempts.push({...oldState.attempts[0],at:new Date(Date.now()+1000).toISOString()});
      fs.writeFileSync(oldFile,JSON.stringify(oldState));
      let latePrefixFeedback;await replayLearningBacklog({cwd,agentDir:agent,force:true,limit:1,learn:async input=>{latePrefixFeedback=input.memoryReplayFeedback;return undefined;}});
      console.log(JSON.stringify({feedback:seen?.memoryReplayFeedback,coverage:seen?.backlogCoverage,entries:seen?.entries,originalPrefixUnchanged:JSON.stringify(seen?.entries.slice(0,slice.entries.length))===JSON.stringify(slice.entries),afterCompletion,latePrefixFeedback}));
      fs.rmSync(cwd,{recursive:true,force:true});
    ''')
    assert value.get('feedback', {}).get('heldIndexes') == [0], value
    assert len(value['coverage']) == 2
    assert any('Actual verification failed' in str(e) for e in value['entries'])
    assert value['originalPrefixUnchanged'] is True
    assert value['afterCompletion'] is None
    assert value.get('latePrefixFeedback', {}).get('heldIndexes') == [0]


def test_actual_held_whole_maintenance_plan_can_supply_bound_correction_context() -> None:
    # Given the actual zero-write v24 maintenance rejection with no partition wrapper,
    # When binding its parent diagnostics, Then the whole plan remains held context.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {buildMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
      const f=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-replay-maintenance-feedback.json','utf8'));
      const entries=JSON.parse(f.snapshotText).entries;
      const input={receipt:f.receipt,backlogId:f.receipt.input.backlogId,entries,proposal:f.proposal,snapshotText:f.snapshotText};
      const feedback=buildMemoryReplayFeedback(input);
      const changed=structuredClone(input);changed.entries[0].id='changed';
      console.log(JSON.stringify({feedback,sourceEntries:entries.length,changed:buildMemoryReplayFeedback(changed)}));
    ''')
    assert value.get('feedback') is not None, value
    assert len(value['feedback']['candidates']) == 2
    assert value['feedback']['eligibleIndexes'] == []
    assert value['feedback']['heldIndexes'] == [0, 1]
    assert value['feedback']['sourceEntryCount'] == value['sourceEntries'] == 42
    assert value['feedback']['failures'] == []
    assert value['feedback']['diagnosticsStatus'] == 'unavailable'
    assert value['changed'] is None


def test_cancellation_during_attempt_save_does_not_start_learning() -> None:
    # Given an admitted task, When cancellation arrives during its durable
    # attempt save, Then no learning callback starts and the lease is released.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {mock} from 'bun:test';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import * as consolidation from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'cl-abort-save-')),agent=process.env.PI_CODING_AGENT_DIR;
      const directory=path.join(agent,'sessions','project');fs.mkdirSync(directory,{recursive:true});
      const manager=SessionManager.create(cwd,directory);
      manager.appendMessage({role:'user',content:'Remember the observed source contract.',timestamp:1});
      const entries=manager.buildContextEntries(),slice=currentTaskSlice(entries),paths=resolveMemoryPaths(cwd,agent);
      enqueueBacklog({cwd,agentDir:agent,sessionFile:manager.getSessionFile(),from:0,to:entries.length-1,digest:consolidation.sha256Digest(JSON.stringify(slice)),reason:'learning-failed'});
      const controller=new AbortController(),write=consolidation.writeFileAtomic;
      let cancelledDuringSave=false,calls=0;
      mock.module('./packages/continual-learning/extensions/consolidation-run.ts',()=>({...consolidation,
        writeFileAtomic:async(...args)=>{const result=await write(...args);
          if(path.basename(String(args[0])).startsWith('replay-')){cancelledDuringSave=true;controller.abort();}
          return result;}}));
      const result=await replayLearningBacklog({cwd,agentDir:agent,force:true,signal:controller.signal,
        learn:async()=>{calls++;return undefined;}});
      console.log(JSON.stringify({cancelledDuringSave,calls,result,pending:backlogStatus(cwd,agent).pending,
        lockLeft:fs.existsSync(path.join(agent,'learning',paths.scopeKey,'replay.lock'))}));
      fs.rmSync(cwd,{recursive:true,force:true});
    ''')
    assert value['cancelledDuringSave'] is True
    assert value['calls'] == 0, value
    assert value['pending'] == 1
    assert value['lockLeft'] is False


def test_foreign_completion_receipt_cannot_resolve_current_memory_feedback() -> None:
    # Given a schema-valid receipt belonging to a different backlog,
    # When replay encounters its Memory completion, Then reject its binding
    # before treating it as a completion barrier or starting another learner.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'cl-foreign-completion-')),agent=process.env.PI_CODING_AGENT_DIR;
      const directory=path.join(agent,'sessions','project');fs.mkdirSync(directory,{recursive:true});
      const manager=SessionManager.create(cwd,directory);
      manager.appendMessage({role:'user',content:'Remember the observed source contract.',timestamp:1});
      const entries=manager.buildContextEntries(),slice=currentTaskSlice(entries),paths=resolveMemoryPaths(cwd,agent);
      enqueueBacklog({cwd,agentDir:agent,sessionFile:manager.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(slice)),reason:'learning-failed'});
      const receipt={kind:'learning-pipeline-receipt',version:1,mode:'automatic',batchId:'batch_'+'a'.repeat(32),
        screen:{memory:true,harness:true,agents:false,reasons:[]},
        attempts:[{phase:'memory',attempt:0,outcome:'noop',operations:0,durationMs:1},
          {phase:'harness',attempt:0,outcome:'failed',operations:0,durationMs:1}],
        totals:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:0},
        costAvailable:false,operations:0,retries:0,
        input:{source:'current-session',entryCount:entries.length,backlogId:'f'.repeat(64)}};
      const first=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async()=>receipt});
      let calls=0;const second=await replayLearningBacklog({cwd,agentDir:agent,force:true,
        learn:async()=>{calls++;return undefined;}});
      const ledger=JSON.parse(fs.readFileSync(path.join(agent,'learning',paths.scopeKey,`replay-${first.outcomes[0].id}.json`),'utf8'));
      console.log(JSON.stringify({calls,second,retainedForeignReceipt:ledger.attempts.some(attempt=>attempt.receipt?.input?.backlogId==='f'.repeat(64)),
        pending:backlogStatus(cwd,agent).pending,lockLeft:fs.existsSync(path.join(agent,'learning',paths.scopeKey,'replay.lock'))}));
      fs.rmSync(cwd,{recursive:true,force:true});
    ''')
    assert value['retainedForeignReceipt'] is True
    assert value['calls'] == 0, value
    assert value['second'].get('error') == 'Learning replay could not complete safely'
    assert value['pending'] == 1
    assert value['lockLeft'] is False
