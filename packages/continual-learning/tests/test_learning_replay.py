from __future__ import annotations
from support import isolated_run_bun


def test_failed_replay_remains_pending_success_acknowledges_once_and_checks_original_digest() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog,beginBacklogAttempt,claimLearningLease} from './packages/continual-learning/extensions/learning-replay.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'cl-replay-'));const cwd=path.join(root,'project');fs.mkdirSync(cwd);
      const agent=process.env.PI_CODING_AGENT_DIR; const dir=path.join(agent,'sessions','project');fs.mkdirSync(dir,{recursive:true});
      const manager=SessionManager.create(cwd,dir);
      manager.appendMessage({role:'user',content:'The scheduler uses reserved slots.',timestamp:1});
      manager.appendMessage({role:'assistant',content:[{type:'text',text:'Observed source.'}],api:'openai-completions',provider:'fixture',model:'fixture',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:2});
      const entries=manager.buildContextEntries();const slice=currentTaskSlice(entries);
      const ref={cwd,agentDir:agent,sessionFile:manager.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(slice)),reason:'learning-failed'};
      enqueueBacklog({...ref,digest:'bad-first'});enqueueBacklog(ref);enqueueBacklog(ref);
      for(let i=0;i<513;i++)fs.writeFileSync(path.join(dir,`irrelevant-${i}`),'');
      let calls=0;const receipt=(outcome)=>({kind:'learning-pipeline-receipt',version:1,mode:'automatic',screen:{memory:true,harness:true,agents:true,reasons:[]},attempts:[{phase:'memory',attempt:0,outcome:outcome==='partial'?'applied':outcome,...(outcome==='partial'?{pendingOperations:1}:{}),operations:outcome==='applied'||outcome==='partial'?1:0,durationMs:1},{phase:'harness',attempt:0,outcome:'applied',operations:1,durationMs:1},{phase:'agents',attempt:0,outcome:'noop',operations:0,durationMs:1}],totals:{input:10,output:1,cacheRead:0,cacheWrite:0,totalTokens:11,cost:0},costAvailable:false,operations:outcome==='applied'?1:0,retries:0});
      const run=(outcome)=>replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async(input)=>{calls++;if(JSON.stringify(input.entries)!==JSON.stringify(slice.entries))throw Error('changed evidence');return receipt(outcome)}});
      const failed=await run('failed');const afterFailure=backlogStatus(cwd,agent);
      const partial=await run('partial');const afterPartial=backlogStatus(cwd,agent);
      const release=claimLearningLease(cwd,agent);const mayRetry=beginBacklogAttempt(cwd,ref,agent);release();const afterShortcut=backlogStatus(cwd,agent);
      const succeeded=await run('applied');const afterSuccess=backlogStatus(cwd,agent);await run('applied');
      enqueueBacklog({...ref,digest:'wrong-digest'});const invalid=await run('applied');
      console.log(JSON.stringify({calls,failed,partial,afterPartial,mayRetry,afterShortcut,succeeded,afterFailure,afterSuccess,invalid}));
      fs.rmSync(root,{recursive:true,force:true});
    ''')
    assert result['afterFailure']['pending'] == 2
    assert result['afterSuccess']['pending'] == 1, result
    assert result['calls'] == 3
    assert result['afterPartial']['pending'] == result['afterShortcut']['pending'] == 2
    assert result['mayRetry'] is True
    assert result['partial']['outcomes'][1]['outcome'] == 'failed'
    assert result['failed']['outcomes'][1]['outcome'] == 'failed'
    assert result['succeeded']['outcomes'][1]['outcome'] == 'completed'
    assert result['invalid']['outcomes'][0]['outcome'] == 'source-changed'


def test_shared_learning_lease_releases_during_unrelated_backlog_contention() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {claimLearningLease,replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      import {backlogFile} from './packages/continual-learning/extensions/learning-backlog.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'cl-lease-'));const agent=process.env.PI_CODING_AGENT_DIR;
      const release=claimLearningLease(cwd,agent);
      const busy=await replayLearningBacklog({cwd,agentDir:agent,learn:async()=>{throw Error('duplicate learning')}});
      const lock=path.join(path.dirname(backlogFile(cwd,agent)),'backlog.lock');
      fs.writeFileSync(lock,JSON.stringify({pid:process.pid}));release();fs.unlinkSync(lock);
      const next=claimLearningLease(cwd,agent);const released=Boolean(next);next?.();
      console.log(JSON.stringify({busy,released}));fs.rmSync(cwd,{recursive:true,force:true});
    ''')
    assert value['busy']['busy'] is True
    assert value['released'] is True


def test_pending_latest_phase_cannot_ack_even_when_applied_or_noop() -> None:
    value = isolated_run_bun(r'''
      import {buildLearningReceipt,learningSummarySubject,learningSummaryTone} from './packages/continual-learning/extensions/learning-efficiency.ts';
      import {learningReceiptComplete} from './packages/continual-learning/extensions/learning-replay.ts';
      const attempt=(outcome,pendingOperations)=>({phase:'memory',attempt:0,outcome,operations:outcome==='applied'?1:0,durationMs:1,...(pendingOperations===undefined?{}:{pendingOperations})});
      const inspect=attempts=>{const r=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},attempts);return {complete:learningReceiptComplete(r),tone:learningSummaryTone(r),subject:learningSummarySubject(r)}};
      console.log(JSON.stringify({partial:inspect([attempt('applied',1)]),empty:inspect([attempt('noop',2)]),resolved:inspect([attempt('applied',2),attempt('applied',0)]),otherPhase:inspect([attempt('applied',2),{phase:'harness',attempt:0,outcome:'noop',operations:0,durationMs:1}])}));
    ''')
    assert value['partial']['complete'] is False
    assert value['partial']['tone'] == 'warning'
    assert value['empty'] == {'complete': False, 'tone': 'warning', 'subject': 'no durable changes; 2 pending review'}
    assert value['resolved']['complete'] is True
    assert 'pending' not in value['resolved']['subject']
    assert value['resolved']['tone'] == 'success'
    assert value['otherPhase']['complete'] is False


def test_replay_coalesces_only_verified_same_task_feedback_extensions() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      import {buildLearningReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'cl-feedback-replay-'));const cwd=path.join(root,'project');fs.mkdirSync(cwd);
      const agent=process.env.PI_CODING_AGENT_DIR;const dir=path.join(agent,'sessions','project');fs.mkdirSync(dir,{recursive:true});
      const manager=SessionManager.create(cwd,dir);
      manager.appendMessage({role:'user',content:'Inspect the scheduler.',timestamp:1});
      const enqueue=()=>{const entries=manager.buildContextEntries();const slice=currentTaskSlice(entries);
        const ref={cwd,agentDir:agent,sessionFile:manager.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(slice)),reason:'learning-failed'};enqueueBacklog(ref);return ref;};
      const first=enqueue();
      manager.appendMessage({role:'toolResult',toolCallId:'verifier',toolName:'read',content:[{type:'text',text:'Actual verifier: reserved slots were omitted; upstream fails.'}],isError:false,timestamp:2});
      const extended=enqueue();
      enqueueBacklog({...extended,digest:'a'.repeat(64)});
      manager.appendMessage({role:'user',content:'New substantive task: inspect another API.',timestamp:3});
      manager.appendMessage({role:'toolResult',toolCallId:'other',toolName:'read',content:[{type:'text',text:'Other API source.'}],isError:false,timestamp:4});
      enqueue();
      let mode='failed',seen=[];
      const run=()=>replayLearningBacklog({cwd,agentDir:agent,force:true,limit:1,learn:async input=>{
        seen.push(input);const r=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:mode==='failed'?'failed':'applied',operations:mode==='failed'?0:1,durationMs:1}],
          {source:'backlog-session',entryCount:input.entries.length,sessionId:input.sessionId,sourceDigest:input.sourceDigest,backlogId:input.id,...(input.backlogCoverage?{backlogCoverage:input.backlogCoverage}:{})});
        if(mode==='wrong-binding'&&r.input?.backlogCoverage)r.input.sourceDigest='0'.repeat(64);
        return r;
      }});
      const failed=await run();const afterFailure=backlogStatus(cwd,agent);
      mode='wrong-binding';const mismatch=await run();const afterMismatch=backlogStatus(cwd,agent);
      mode='applied';const success=await run();const afterSuccess=backlogStatus(cwd,agent);
      const files=fs.readdirSync(path.join(agent,'learning')).flatMap(n=>{
        const p=path.join(agent,'learning',n);return fs.statSync(p).isDirectory()?fs.readdirSync(p).filter(f=>f.startsWith('replay-')).map(f=>JSON.parse(fs.readFileSync(path.join(p,f),'utf8'))):[];
      });
      console.log(JSON.stringify({failed,mismatch,success,afterFailure,afterMismatch,afterSuccess,seen,files}));fs.rmSync(root,{recursive:true,force:true});
    ''')
    assert len(result['seen']) == 3
    assert all(any('Actual verifier' in str(entry) for entry in call['entries']) for call in result['seen'])
    assert all(len(call['backlogCoverage']) == 2 for call in result['seen'])
    assert all(call['id'] == max(call['backlogCoverage'], key=lambda ref: ref['to'])['id'] for call in result['seen'])
    assert result['afterFailure']['pending'] == result['afterMismatch']['pending'] == 4
    assert result['afterSuccess']['pending'] == 2
    assert result['failed']['outcomes'][0]['outcome'] == 'failed'
    assert result['mismatch']['outcomes'][0]['outcome'] == 'failed'
    assert result['success']['outcomes'][0]['outcome'] == 'completed'
    assert any(len(ledger['attempts']) == 3 for ledger in result['files'])


def test_coalesced_receipt_recovers_all_ack_breakpoints_without_duplicate_usage() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      import {buildLearningReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'cl-replay-crash-'));const agent=process.env.PI_CODING_AGENT_DIR;const cwd=path.join(root,'project');fs.mkdirSync(cwd);
      const dir=path.join(agent,'sessions','crash');fs.mkdirSync(dir,{recursive:true});const m=SessionManager.create(cwd,dir);
      m.appendMessage({role:'user',content:'Inspect scheduling.',timestamp:1});
      for(let i=0;i<3;i++) {
        if(i)m.appendMessage({role:'toolResult',toolCallId:`read-${i}`,toolName:'read',content:[{type:'text',text:`Verifier feedback ${i}`}],isError:false,timestamp:i+1});
        const entries=m.buildContextEntries();enqueueBacklog({cwd,agentDir:agent,sessionFile:m.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(currentTaskSlice(entries))),reason:'learning-failed'});
      }
      let calls=0;const controller=new AbortController();
      const learn=async input=>{calls++;return buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'applied',operations:1,durationMs:1,usage:{input:10,output:1,cacheRead:0,cacheWrite:0,totalTokens:11,cost:.1}}],
        {source:'backlog-session',entryCount:input.entries.length,sessionId:input.sessionId,sourceDigest:input.sourceDigest,backlogId:input.id,backlogCoverage:input.backlogCoverage},'batch_'+'a'.repeat(32));};
      const cancelled=await replayLearningBacklog({cwd,agentDir:agent,force:true,signal:controller.signal,learn:async input=>{const receipt=await learn(input);controller.abort();return receipt;}});
      const afterCancel=backlogStatus(cwd,agent);
      const completed=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn});
      const scope=resolveMemoryPaths(cwd,agent).scopeKey;const storage=path.join(agent,'learning',scope);const ack=path.join(storage,'backlog-completed.json');const all=JSON.parse(fs.readFileSync(ack,'utf8'));
      const files=fs.readdirSync(storage).filter(n=>n.startsWith('replay-'));const ledger=JSON.parse(fs.readFileSync(path.join(storage,files[0]),'utf8'));
      const receipt=ledger.attempts.at(-1).receipt;const coverage=receipt.input.backlogCoverage;const siblings=coverage.filter(c=>c.id!==receipt.input.backlogId);
      const recovered=[];
      for(let retained=0;retained<=siblings.length;retained++) {
        fs.writeFileSync(ack,JSON.stringify(Object.fromEntries(siblings.slice(0,retained).map(c=>[c.id,all[c.id]]))));
        const before=calls;const replay=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn});
        recovered.push({calls:calls-before,pending:backlogStatus(cwd,agent).pending,acks:JSON.parse(fs.readFileSync(ack,'utf8')),replay});
      }
      console.log(JSON.stringify({calls,cancelled,afterCancel,completed,recovered,files,all,ledger}));fs.rmSync(root,{recursive:true,force:true});
    ''')
    assert result['afterCancel']['pending'] == 3
    assert result['cancelled']['outcomes'][0]['outcome'] == 'failed'
    assert result['calls'] == 2
    assert len(result['files']) == 1
    assert len(result['ledger']['attempts']) == 2
    assert len(result['recovered']) == 3
    assert all(row['calls'] == 0 and row['pending'] == 0 and row['acks'] == result['all'] for row in result['recovered'])


def test_replay_retains_omission_metadata_and_sibling_retry_limits() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {enqueueBacklog,backlogIdentity,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'cl-replay-bounds-'));const agent=process.env.PI_CODING_AGENT_DIR;const results=[];
      for(const mode of ['exhausted','backoff','invalid-extension','omitted','other-session']) {
        const cwd=path.join(root,mode);fs.mkdirSync(cwd);const dir=path.join(agent,'sessions',mode);fs.mkdirSync(dir,{recursive:true});const m=SessionManager.create(cwd,dir);
        m.appendMessage({role:'user',content:'Inspect scheduling.',timestamp:1});
        const enqueue=manager=>{const entries=manager.buildContextEntries();const slice=currentTaskSlice(entries);const ref={cwd,agentDir:agent,sessionFile:manager.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(slice)),reason:'learning-failed'};enqueueBacklog(ref);return ref;};
        if(mode!=='omitted')enqueue(m);
        for(let i=0;i<(mode==='omitted'?300:1);i++)m.appendMessage({role:'toolResult',toolCallId:`read-${i}`,toolName:'read',content:[{type:'text',text:`Observed source ${i}`}],isError:false,timestamp:i+2});
        const extension=enqueue(m);const scope=resolveMemoryPaths(cwd,agent).scopeKey;
        if(mode==='invalid-extension') {const file=path.join(agent,'learning','backlog.jsonl');const rows=fs.readFileSync(file,'utf8').trim().split('\n').map(JSON.parse);rows[rows.length-1].digest='0'.repeat(64);fs.writeFileSync(file,rows.map(x=>JSON.stringify(x)).join('\n')+'\n');}
        if(['exhausted','backoff'].includes(mode)) {
          const file=path.join(agent,'learning',scope,`replay-${backlogIdentity(scope,extension)}.json`);
          fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify({attempts:Array.from({length:mode==='exhausted'?16:1},()=>({at:new Date().toISOString(),outcome:'failed'})),nextAttemptAt:Date.now()+3600000}));
        }
        if(mode==='other-session') {const other=SessionManager.create(cwd,dir);other.appendMessage({role:'user',content:'Other session.',timestamp:1});enqueue(other);}
        const seen=[];const run=await replayLearningBacklog({cwd,agentDir:agent,force:mode!=='backoff',limit:1,learn:async input=>{seen.push({...input,entries:input.entries.map(e=>(e.message??e).content)});return undefined;}});
        results.push({mode,seen,run,pending:backlogStatus(cwd,agent).pending});
      }
      console.log(JSON.stringify(results));fs.rmSync(root,{recursive:true,force:true});
    ''')
    rows = {row['mode']: row for row in result}
    for mode in ('exhausted', 'backoff'):
        assert rows[mode]['seen'] == []
        assert rows[mode]['run']['outcomes'][0]['reason'] == 'newer-slice-deferred'
        assert rows[mode]['pending'] == 2
    assert len(rows['invalid-extension']['seen']) == 1
    assert rows['invalid-extension']['seen'][0].get('backlogCoverage') is None
    assert rows['omitted']['seen'][0]['omittedEntries'] > 0
    assert rows['omitted']['seen'][0]['omittedEvidenceEntries'] > 0
    assert rows['other-session']['pending'] == 3
    assert len(rows['other-session']['seen'][0]['backlogCoverage']) == 2


def test_completed_extension_recovers_before_older_deferred_reference_is_retried() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {enqueueBacklog,backlogIdentity} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      import {buildLearningReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'cl-recovery-order-'));const cwd=path.join(root,'project');fs.mkdirSync(cwd);const agent=process.env.PI_CODING_AGENT_DIR;
      const dir=path.join(agent,'sessions','order');fs.mkdirSync(dir,{recursive:true});const m=SessionManager.create(cwd,dir);
      m.appendMessage({role:'user',content:'Inspect scheduler.',timestamp:1});
      const enqueue=()=>{const entries=m.buildContextEntries();const ref={cwd,agentDir:agent,sessionFile:m.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(currentTaskSlice(entries))),reason:'learning-failed'};enqueueBacklog(ref);return ref;};
      const old=enqueue();m.appendMessage({role:'toolResult',toolCallId:'read',toolName:'read',content:[{type:'text',text:'New verifier feedback.'}],isError:false,timestamp:2});const extended=enqueue();
      const scope=resolveMemoryPaths(cwd,agent).scopeKey;const storage=path.join(agent,'learning',scope);fs.mkdirSync(storage,{recursive:true});
      fs.writeFileSync(path.join(storage,`replay-${backlogIdentity(scope,old)}.json`),JSON.stringify({attempts:[{at:new Date().toISOString(),outcome:'failed'}],nextAttemptAt:Date.now()+3600000}));
      const seen=[];const learn=async input=>{seen.push(input);return buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'applied',operations:1,durationMs:1}],
        {source:'backlog-session',entryCount:input.entries.length,sessionId:input.sessionId,sourceDigest:input.sourceDigest,backlogId:input.id,...(input.backlogCoverage?{backlogCoverage:input.backlogCoverage}:{})});};
      await replayLearningBacklog({cwd,agentDir:agent,learn});const ack=path.join(storage,'backlog-completed.json');const original=JSON.parse(fs.readFileSync(ack,'utf8'));fs.writeFileSync(ack,'{}');
      const recovered=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn});
      console.log(JSON.stringify({seen,original,after:JSON.parse(fs.readFileSync(ack,'utf8')),newId:backlogIdentity(scope,extended),recovered}));fs.rmSync(root,{recursive:true,force:true});
    ''')
    assert len(result['seen']) == 2
    assert any('New verifier feedback' in str(entry) for entry in result['seen'][0]['entries'])
    assert not any('New verifier feedback' in str(entry) for entry in result['seen'][1]['entries'])
    assert result['seen'][1].get('backlogCoverage') is None
    assert result['after'][result['newId']] == result['original'][result['newId']]


def test_single_replay_receipt_preserves_parent_range_after_pending_queue_closes() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      import {buildLearningReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'single-range-')),agent=process.env.PI_CODING_AGENT_DIR;
      const dir=path.join(agent,'sessions','project');fs.mkdirSync(dir,{recursive:true});const session=SessionManager.create(cwd,dir);
      session.appendMessage({role:'user',content:'Inspect an original source contract.',timestamp:1});
      session.appendMessage({role:'toolResult',toolName:'read',toolCallId:'source',content:[{type:'text',text:'Actual original source.'}],isError:false,timestamp:2});
      const entries=session.buildContextEntries(),slice=currentTaskSlice(entries);const range={from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(slice))};
      enqueueBacklog({cwd,agentDir:agent,sessionFile:session.getSessionFile(),...range,reason:'learning-failed'});
      const seen=[];const run=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async input=>{
        seen.push(input);return buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'noop',operations:0,durationMs:1}],
          {source:'backlog-session',entryCount:input.entries.length,sessionId:input.sessionId,sourceDigest:input.sourceDigest,backlogId:input.id,backlogRange:input.backlogRange});}});
      console.log(JSON.stringify({range,seen,run,pending:backlogStatus(cwd,agent).pending}));
    ''')
    assert result['seen'][0].get('backlogRange') == result['range']
    assert result['seen'][0].get('backlogCoverage') is None
    assert result['pending'] == 0 and result['run']['outcomes'][0]['outcome'] == 'completed'


def test_supplied_single_owner_range_and_source_binding_cannot_drift() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {enqueueBacklog,backlogStatus} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {replayLearningBacklog} from './packages/continual-learning/extensions/learning-replay.ts';
      import {buildLearningReceipt,isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'range-binding-')),out=[];
      for(const change of ['from','to','digest','owner','source','count','session']){
        const cwd=path.join(root,change);fs.mkdirSync(cwd);const agent=path.join(process.env.PI_CODING_AGENT_DIR,change),dir=path.join(agent,'sessions','project');fs.mkdirSync(dir,{recursive:true});
        const s=SessionManager.create(cwd,dir);s.appendMessage({role:'user',content:'Actual source task.',timestamp:1});
        const entries=s.buildContextEntries(),slice=currentTaskSlice(entries);enqueueBacklog({cwd,agentDir:agent,sessionFile:s.getSessionFile(),from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(slice)),reason:'learning-failed'});
        const replay=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async input=>{
          const metadata={source:'backlog-session',entryCount:input.entries.length,sessionId:input.sessionId,sourceDigest:input.sourceDigest,backlogId:input.id,backlogRange:{...input.backlogRange}};
          if(change==='from')metadata.backlogRange.from++;
          if(change==='to')metadata.backlogRange.to++;
          if(change==='digest')metadata.backlogRange.digest='0'.repeat(64);
          if(change==='owner')metadata.backlogId='0'.repeat(64);
          if(change==='source')metadata.sourceDigest='0'.repeat(64);
          if(change==='count')metadata.entryCount++;
          if(change==='session')metadata.sessionId='foreign';
          return buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'noop',operations:0,durationMs:1}],metadata);
        }});out.push({change,replay,pending:backlogStatus(cwd,agent).pending});
      }
      const base=buildLearningReceipt('manual',{memory:false,harness:false,agents:false,reasons:[]},[],{source:'backlog-session',entryCount:1,backlogId:'a'.repeat(64),backlogRange:{from:0,to:0,digest:'b'.repeat(64)}});
      const invalid=[null,[],{from:-1,to:0,digest:'b'.repeat(64)},{from:1,to:0,digest:'b'.repeat(64)},{from:0,to:0,digest:'bad'},{from:0,to:0,digest:'b'.repeat(64),extra:true}];
      console.log(JSON.stringify({out,valid:isLearningPipelineReceipt(base),invalid:invalid.map(backlogRange=>isLearningPipelineReceipt({...base,input:{...base.input,backlogRange}}))}));
    ''')
    assert result['valid'] and not any(result['invalid'])
    assert all(row['pending'] == 1 and row['replay']['outcomes'][0]['outcome'] == 'failed' for row in result['out'])


def test_completed_range_receipt_recovery_requires_parent_source_binding() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {SessionManager} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {enqueueBacklog,backlogStatus,backlogIdentity,readBacklog} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      import {replayLearningBacklog,recordBacklogAttempt} from './packages/continual-learning/extensions/learning-replay.ts';
      import {buildLearningReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'range-recovery-')),out=[];
      for(const change of ['session','source','count','valid-append','missing-parent']){
        const cwd=path.join(root,change);fs.mkdirSync(cwd);const agent=path.join(process.env.PI_CODING_AGENT_DIR,change),dir=path.join(agent,'sessions','project');fs.mkdirSync(dir,{recursive:true});
        const session=SessionManager.create(cwd,dir);session.appendMessage({role:'user',content:'Actual original task.',timestamp:1});
        const entries=session.buildContextEntries(),range={from:0,to:entries.length-1,digest:sha256Digest(JSON.stringify(currentTaskSlice(entries)))};
        enqueueBacklog({cwd,agentDir:agent,sessionFile:session.getSessionFile(),...range,reason:'learning-failed'});
        const entry=readBacklog(cwd,agent).pendingEntries[0].entry,scope=resolveMemoryPaths(cwd,agent).scopeKey,id=backlogIdentity(scope,entry),storage=path.join(agent,'learning');
        const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'noop',operations:0,durationMs:1}],
          {source:'backlog-session',entryCount:entries.length,sessionId:session.getSessionId(),sourceDigest:sha256Digest(fs.readFileSync(session.getSessionFile())),backlogId:id,backlogRange:range});
        if(change==='missing-parent'){
          const recorded=recordBacklogAttempt(cwd,entry,receipt,agent);out.push({change,recorded,pending:backlogStatus(cwd,agent).pending});continue;
        }
        await replayLearningBacklog({cwd,agentDir:agent,learn:async()=>receipt});
        fs.writeFileSync(path.join(storage,scope,'backlog-completed.json'),'{}');
        const file=path.join(storage,scope,`replay-${id}.json`),state=JSON.parse(fs.readFileSync(file,'utf8'));
        const input=state.attempts.at(-1).receipt.input;
        if(change==='session')input.sessionId='foreign';
        if(change==='source')input.sourceDigest='0'.repeat(64);
        if(change==='count')input.entryCount=999;
        fs.writeFileSync(file,JSON.stringify(state));
        session.appendMessage({role:'user',content:'A later independent task may append legally.',timestamp:2});
        let calls=0;const restored=await replayLearningBacklog({cwd,agentDir:agent,force:true,learn:async()=>{calls++;return receipt;}});
        out.push({change,calls,restored,pending:backlogStatus(cwd,agent).pending});
      }
      console.log(JSON.stringify(out));
    ''')
    for row in result:
        if row['change'] == 'valid-append':
            assert row['pending'] == 0 and row['calls'] == 0
            assert row['restored']['outcomes'][0]['outcome'] == 'completed'
        elif row['change'] == 'missing-parent':
            assert not row['recorded'] and row['pending'] == 1
        else:
            assert row['pending'] == 1 and row['calls'] == 0 and row['restored'].get('error'), row
