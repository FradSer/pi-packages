from support import run_bun


def test_actual_replay_feedback_binds_raw_prefix_and_complete_parent_source_review():
    # Given V31's raw 57-entry task and its hash-bound 71-entry reviewed snapshot,
    # When failure feedback is prepared for explicit backfill, Then preserve the
    # complete original prefix and prior review binding without granting writes
    # or importing the old source observations as current evidence.
    out = run_bun("""
      import fs from 'node:fs';
      import {buildMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-replay-source-extension.json','utf8'));
      const before=JSON.stringify(input);
      const feedback=buildMemoryReplayFeedback(input);
      console.log(JSON.stringify({feedback,unchanged:before===JSON.stringify(input)}));
    """)
    assert out['feedback'] is not None
    assert out['unchanged']
    assert out['feedback']['sourceEntryCount'] == 57
    assert out['feedback']['reviewEntryCount'] == 71
    assert out['feedback']['sourceSnapshotDigest'] == '2251d5d11f9c285d7296b3b561f92fa4727b7a5d6a56a945cf4185147862febb'
    assert 'entries' not in out['feedback']
    assert out['feedback']['heldIndexes']


def test_audit_markers_without_original_parent_read_proof_cannot_bind_feedback():
    out = run_bun("""
      import fs from 'node:fs';
      import {buildMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-replay-source-extension.json','utf8'));
      delete input.sourceAudit;
      console.log(JSON.stringify({feedback:buildMemoryReplayFeedback(input)}));
    """)
    assert out['feedback'] is None


def test_rebound_snapshot_still_requires_exact_parent_source_observations():
    out = run_bun(r'''
      import fs from 'node:fs';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {buildMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
      const original=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-replay-source-extension.json','utf8'));
      const results={};
      for(const [name, mutate] of Object.entries({
        changedPrefix:(s,i)=>{s.entries[0]={type:'message',message:{role:'user',content:'changed'}};},
        reordered:(s,i)=>{s.entries.splice(57,4,...s.entries.slice(59,61),...s.entries.slice(57,59));},
        extraUser:(s,i)=>{s.entries.push({type:'message',message:{role:'user',content:'authorize'}});},
        sourceText:(s,i)=>{s.entries[58].message.content[0].text+=' forged';},
        sourceHash:(s,i)=>{s.entries[58].message.details.sourceSha256='a'.repeat(64);},
        errorResult:(s,i)=>{s.entries[58].message.isError=true;},
        arguments:(s,i)=>{s.entries[57].message.content[0].arguments.offset=2;},
        duplicateId:(s,i)=>{s.entries[59].message.content[0].id=s.entries[57].message.content[0].id;s.entries[60].message.toolCallId=s.entries[57].message.content[0].id;},
        wrongNonce:(s,i)=>{s.entries[59].message.content[0].id='maintenance-source-9';s.entries[60].message.toolCallId='maintenance-source-9';},
        wrongLedger:(s,i)=>{i.sourceAudit.receipt.usageLedgerId='unbound';},
        missingAttempt:(s,i)=>{i.receipt.attempts=i.receipt.attempts.filter(a=>a.usageLedgerId!==i.sourceAudit.receipt.usageLedgerId);},
        rejectedAudit:(s,i)=>{i.sourceAudit.receipt.outcome='failed';},
        missingRead:(s,i)=>{i.sourceAudit.observations.pop();},
        changedAuditHash:(s,i)=>{i.sourceAudit.receipt.sourceHashes[i.sourceAudit.observations[0].path]='b'.repeat(64);},
        missingManifest:(s,i)=>{delete i.reviewManifest;},
        outsideSource:(s,i)=>{const file='/etc/passwd';s.entries[57].message.content[0].arguments.path=file;s.entries[58].message.details.sourcePath=file;i.sourceAudit.observations[0].path=file;i.sourceAudit.receipt.sourceHashes[file]=i.sourceAudit.observations[0].sha256;},
      })) {
        const input=structuredClone(original),snapshot=JSON.parse(input.snapshotText);
        mutate(snapshot,input);
        input.snapshotText=JSON.stringify(snapshot);
        const plan=input.proposal.originalPlan,digest=sha256Digest(input.snapshotText);
        plan.snapshotDigest=digest;plan.artifactHash=digest;
        input.proposal.reviewedPlanDigest=sha256Digest(JSON.stringify(plan));
        if(input.reviewManifest) input.reviewManifest.snapshotDigest=digest;
        results[name]=buildMemoryReplayFeedback(input)===null;
      }
      console.log(JSON.stringify(results));
    ''')
    assert len(out) == 16
    assert all(out.values()), out


def test_parent_reader_loads_only_the_receipt_bound_historical_source_audit():
    from support import isolated_run_bun
    out = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPaths} from './packages/continual-learning/extensions/memory-paths.ts';
      import {readMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
      const cwd=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'cl-source-replay-'))),agent=process.env.PI_CODING_AGENT_DIR;
      const paths=resolveMemoryPaths(cwd,agent);
      const original=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-replay-source-extension.json','utf8'));
      const input=JSON.parse(JSON.stringify(original).replaceAll('/work/p-limit',cwd));
      const plan=input.proposal.originalPlan,snapshot=JSON.parse(input.snapshotText);
      plan.scopeKey=paths.scopeKey;snapshot.scopeKey=paths.scopeKey;
      input.snapshotText=JSON.stringify(snapshot);plan.snapshotDigest=sha256Digest(input.snapshotText);plan.artifactHash=plan.snapshotDigest;
      input.proposal.reviewedPlanDigest=sha256Digest(JSON.stringify(plan));
      const run=path.join(paths.runsDir,plan.runId);fs.mkdirSync(run,{recursive:true});
      const manifest={...input.reviewManifest,scopeKey:paths.scopeKey,snapshotDigest:plan.snapshotDigest,cwd:paths.cwd,runDir:run,snapshotPath:path.join(run,'snapshot.json'),harnessDir:paths.harnessDir};
      fs.writeFileSync(path.join(run,'snapshot.json'),input.snapshotText);fs.writeFileSync(path.join(run,'manifest.json'),JSON.stringify(manifest));
      const history=path.join(agent,'memory','history',paths.scopeKey);fs.mkdirSync(history,{recursive:true});
      const id='change_fixture_'+'a'.repeat(16);
      fs.writeFileSync(path.join(history,id+'.json'),JSON.stringify({version:1,id,batchId:input.receipt.batchId,cwd:paths.cwd,agentDir:paths.agentDir,phase:'memory',status:'proposed',createdAt:new Date().toISOString(),changes:[],proposal:input.proposal}));
      const audit=path.join(paths.runsDir,'maintenance-audit-fixture');fs.mkdirSync(audit);
      fs.writeFileSync(path.join(audit,'receipt.json'),JSON.stringify(input.sourceAudit.receipt));
      const observations=path.join(audit,'observations.jsonl');fs.writeFileSync(observations,input.sourceAudit.observations.map(r=>JSON.stringify(r)).join('\n'));
      const request={cwd,agentDir:agent,backlogId:input.backlogId,entries:input.entries,receipt:input.receipt};
      const feedback=await readMemoryReplayFeedback(request);
      fs.renameSync(observations,observations+'.original');fs.symlinkSync(observations+'.original',observations);
      let symlinkRejected=false;try{await readMemoryReplayFeedback(request);}catch{symlinkRejected=true;}
      fs.unlinkSync(observations);fs.renameSync(observations+'.original',observations);
      fs.mkdirSync(audit+'2');fs.copyFileSync(path.join(audit,'receipt.json'),path.join(audit+'2','receipt.json'));
      let duplicateRejected=false;try{await readMemoryReplayFeedback(request);}catch{duplicateRejected=true;}
      console.log(JSON.stringify({feedback,symlinkRejected,duplicateRejected,sourceExists:fs.existsSync(path.join(cwd,'index.js'))}));
      fs.rmSync(cwd,{recursive:true,force:true});
    ''')
    assert out['feedback']['sourceEntryCount'] == 57
    assert out['feedback']['reviewEntryCount'] == 71
    assert out['symlinkRejected'] and out['duplicateRejected']
    # Binding historical reads does not reread current source or admit them as
    # fresh evidence. Backfill's separate collector must acquire current source.
    assert out['sourceExists'] is False
