import pytest

from support import isolated_run_bun


COVERAGE_FEEDBACK_SETUP = r'''
  import fs from 'node:fs';
  import {buildMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
  import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
  import {memoryCoverageReviewDigest,prepareMemoryCoverageJudgment} from './packages/continual-learning/extensions/memory-knowledge-coverage.ts';
  const f=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-replay-coverage-feedback-v105.json','utf8'));
  const snapshot=JSON.parse(f.snapshotText), state=f.wireRequest.state;
  const artifact=structuredClone(f.semanticRecord);
  artifact.coverageContext={protocol:'memory-knowledge-coverage-v2',plan:state.completeCurrentPlan,
    review:f.coverageReview,expectedReviewDigest:memoryCoverageReviewDigest(f.coverageReview)};
  artifact.existingMemories=state.existingMemories;
  artifact.coverageQuestions=prepareMemoryCoverageJudgment(snapshot,state.originalCandidates,state.existingMemories,artifact.coverageContext).questions;
  artifact.coverageIssueBindings=state.namedIssueBindings;
  // Original service distributions, not a new judgment or invented confidence.
  for(const check of artifact.reviewed.coverageReview.checks) {
    const answer=f.wireResponse.answers[check.key];
    if(answer.choice!==check.choice || answer.confidence!==check.confidence
      || answer.probabilities[check.choice]!==check.probability)throw Error('Frozen wire mismatch');
    check.probabilities=answer.probabilities;
  }
  const file='memory-coverage-semantic-ae36b024-27f9-4ed8-a1fb-b104a7acff15.json';
  const text=JSON.stringify(artifact), ref={file,sha256:sha256Digest(text),reviewedPlanDigest:artifact.planDigest};
  // Simulate the prospective parent's receipt binding. Historical files stay unchanged.
  const receipt=structuredClone(f.receipt), proposal=structuredClone(f.history.proposal);
  receipt.attempts.find(a=>a.usageLedgerId===f.coverageReview.usageLedgerId).coverageReviewArtifact=structuredClone(ref);
  proposal.rejectedCoverageReviews=[structuredClone(ref)];
  const input={receipt,backlogId:receipt.input.backlogId,entries:snapshot.entries,
    proposal,snapshotText:f.snapshotText,rejectedCoverageArtifacts:[{file,text}]};
'''


def test_real_coverage_omission_survives_failed_learning_feedback() -> None:
    # Given V105's actual omitted maintenance baseline and complete original wire,
    # When the next learning task receives the bound failed-plan feedback,
    # Then it receives the questions, classifications and complete claim-condition relations.
    value = isolated_run_bun(COVERAGE_FEEDBACK_SETUP + r'''
      const before=JSON.stringify(input.entries), feedback=buildMemoryReplayFeedback(input);
      const result=feedback?.rejectedCoverageQuestions?.[0];
      console.log(JSON.stringify({result,originalQuestions:f.wireRequest.questions,
        originalOccurrences:state.namedIssueBindings,originalAnswers:f.wireResponse.answers,
        originalTargets:state.targets,originalPlan:state.completeCurrentPlan,
        originalPlanAccount:f.coverageReview.plan,originalRecordAccounts:f.coverageReview.accounts,
        entriesUnchanged:before===JSON.stringify(input.entries),eligible:feedback?.eligibleIndexes}));
    ''')
    result = value.get('result')
    assert result is not None, 'The concrete rejected coverage question was dropped'
    assert result['purpose'] == 'rejected-questions-only'
    assert result['sourceSnapshotDigest']
    assert result['occurrences'] == value['originalOccurrences']
    assert result['targets'] == value['originalTargets']
    assert result['rejectedPlan'] == value['originalPlan']
    assert result['planAccount'] == value['originalPlanAccount']
    assert result['recordAccounts'] == value['originalRecordAccounts']
    assert all(account['claims'] for account in result['recordAccounts'])
    assert any(claim['conditions'] for account in result['recordAccounts'] for claim in account['claims'])
    assert 'priorPlanAccount' not in result and 'priorRecordAccounts' not in result
    assert len(result['questions']) == len(value['originalQuestions']) == 6
    for question in result['questions']:
        original = value['originalQuestions'][question['key']]
        assert question['question'] == original['instructions']
        assert question['criteria'] == original['criteria']
    for check in result['checks']:
        original = value['originalAnswers'][check['key']]
        assert check['choice'] == original['choice']
        assert check['confidence'] == original['confidence']
        assert check['probabilities'] == original['probabilities']
    assert '42 tests' in str(result['occurrences'])
    assert 'originalEvidence' not in result
    assert 'coverageContext' not in result
    assert value['entriesUnchanged'] is True
    assert value['eligible'] == []




def test_real_corrected_versions_keep_each_complete_rejected_body_and_all_occurrences() -> None:
    value = isolated_run_bun(r"""
      import fs from 'node:fs';
      import {buildMemoryReplayFeedback} from './packages/continual-learning/extensions/learning-replay-feedback.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {prepareMemoryCoverageJudgment,memoryCoverageReviewDigest} from './packages/continual-learning/extensions/memory-knowledge-coverage.ts';
      const f=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-replay-coverage-feedback-v105.json','utf8')).backfill;
      const snapshot=JSON.parse(f.snapshotText),receipt=f.receipt,proposal=f.history.proposal,artifacts=[];
      let prior;proposal.rejectedCoverageReviews=[];
      for(const row of f.rows){
        const state=row.wire.state,context={protocol:'memory-knowledge-coverage-v2',plan:state.completeCurrentPlan,
          review:row.review,expectedReviewDigest:memoryCoverageReviewDigest(row.review),...(prior?{prior}:{})};
        const prepared=prepareMemoryCoverageJudgment(snapshot,state.originalCandidates,state.existingMemories,context);
        const a=row.semantic;Object.assign(a,{coverageContext:context,existingMemories:state.existingMemories,
          coverageQuestions:prepared.questions,coverageIssueBindings:prepared.state.namedIssueBindings});
        for(const c of a.reviewed.coverageReview.checks)c.probabilities=row.response.answers[c.key].probabilities;
        const text=JSON.stringify(a),ref={file:row.file,sha256:sha256Digest(text),reviewedPlanDigest:a.planDigest};
        proposal.rejectedCoverageReviews.push(ref);artifacts.push({file:row.file,text});
        receipt.attempts.find(a=>a.usageLedgerId===row.review.usageLedgerId).coverageReviewArtifact=structuredClone(ref);
        prior=context;
      }
      const input={receipt,proposal,backlogId:receipt.input.backlogId,entries:snapshot.entries,snapshotText:f.snapshotText,
        rejectedCoverageArtifacts:artifacts},feedback=buildMemoryReplayFeedback(input);
      const reversed=structuredClone(input);reversed.proposal.rejectedCoverageReviews.reverse();
      const dropped=structuredClone(input);dropped.proposal.rejectedCoverageReviews.pop();
      // A legacy parent can retain only the final artifact, whose validated
      // context still includes the complete predecessor account.
      const standalone=structuredClone(input),last=standalone.proposal.rejectedCoverageReviews.at(-1);
      standalone.proposal.rejectedCoverageReviews=[last];
      standalone.rejectedCoverageArtifacts=standalone.rejectedCoverageArtifacts.filter(a=>a.file===last.file);
      for(const attempt of standalone.receipt.attempts){
        if(attempt.coverageReviewArtifact?.file!==last.file)delete attempt.coverageReviewArtifact;
      }
      console.log(JSON.stringify({feedback,versions:f.rows.map(row=>({plan:row.wire.state.completeCurrentPlan,
        targets:row.wire.state.targets,occurrences:row.wire.state.namedIssueBindings,answers:row.response.answers,
        planAccount:row.review.plan,recordAccounts:row.review.accounts})),
        standalone:buildMemoryReplayFeedback(standalone),
        reversed:buildMemoryReplayFeedback(reversed),dropped:buildMemoryReplayFeedback(dropped)}));
    """)
    feedback = value['feedback']
    assert feedback is not None
    versions = feedback['rejectedCoverageQuestions']
    assert len(versions) == 2
    assert versions[0]['rejectedPlan'] != versions[1]['rejectedPlan']
    for actual, expected in zip(versions, value['versions'], strict=True):
        assert actual['rejectedPlan'] == expected['plan']
        assert actual['targets'] == expected['targets']
        assert actual['occurrences'] == expected['occurrences']
        assert actual['planAccount'] == expected['planAccount']
        assert actual['recordAccounts'] == expected['recordAccounts']
        for check in actual['checks']:
            assert check['probabilities'] == expected['answers'][check['key']]['probabilities']
    assert 'priorRejectedPlan' not in versions[1] and 'priorTargets' not in versions[1]
    assert versions[1]['priorAccountArtifact'] == versions[0]['artifact']
    prior = next(row for row in versions if row['artifact'] == versions[1]['priorAccountArtifact'])
    assert prior['planAccount'] == value['versions'][0]['planAccount']
    assert prior['recordAccounts'] == value['versions'][0]['recordAccounts']
    assert 'priorPlanAccount' not in versions[1] and 'priorRecordAccounts' not in versions[1]
    standalone = value['standalone']['rejectedCoverageQuestions'][0]
    assert 'priorAccountArtifact' not in standalone
    assert standalone['priorRejectedPlan'] == versions[0]['rejectedPlan']
    assert standalone['priorTargets'] == versions[0]['targets']
    assert standalone['priorPlanAccount'] == versions[0]['planAccount']
    assert standalone['priorRecordAccounts'] == versions[0]['recordAccounts']
    assert value['reversed'] is None and value['dropped'] is None


@pytest.mark.parametrize('mutation', [
    'delete proposal.rejectedCoverageReviews',
    'proposal.rejectedCoverageReviews=[]',
    'proposal.rejectedCoverageReviews.push(structuredClone(ref))',
    'input.rejectedCoverageArtifacts=[]',
    'input.rejectedCoverageArtifacts.push({file,text})',
    "proposal.rejectedCoverageReviews[0].file='../outside.json'",
    "proposal.rejectedCoverageReviews[0].sha256='0'.repeat(64)",
    "artifact.runId='run_foreign_0123456789abcdef';rehash()",
    "artifact.coverageQuestions[0].question+='Changed';rehash()",
    "artifact.coverageIssueBindings=[];rehash()",
    "artifact.reviewed.coverageReview.checks[0].confidence=1;rehash()",
])
def test_coverage_replay_rejects_changed_reference_without_parent_receipt(mutation: str) -> None:
    # Given the immutable original receipt, even a rehashed new projection must
    # not replace its actual historical questions or classifications.
    value = isolated_run_bun(COVERAGE_FEEDBACK_SETUP + r"""
      function rehash(){input.rejectedCoverageArtifacts[0].text=JSON.stringify(artifact);
        proposal.rejectedCoverageReviews[0].sha256=sha256Digest(input.rejectedCoverageArtifacts[0].text);}
    """ + mutation + r""";
      console.log(JSON.stringify({result:buildMemoryReplayFeedback(input),usage:input.receipt.totals,
        originalUsage:f.receipt.totals,entriesUnchanged:JSON.stringify(input.entries)===JSON.stringify(snapshot.entries)}));
    """)
    assert value['result'] is None
    assert value['usage'] == value['originalUsage']
    assert value['entriesUnchanged'] is True


@pytest.mark.parametrize('mutation', [
    "artifact.runId='run_foreign_0123456789abcdef'",
    "artifact.planDigest='0'.repeat(64)",
    "artifact.expectedAccountDigest='0'.repeat(64)",
    "artifact.expectedContextDigest='0'.repeat(64)",
    "artifact.coverageContext.plan.selected.push('foreign.md')",
    "artifact.coverageContext.review.targets[0].content+='Changed'",
    "artifact.coverageQuestions[0].question+='Changed'",
    'artifact.coverageIssueBindings.pop()',
    'artifact.reviewed.coverageReview.checks.pop()',
    "artifact.reviewed.coverageReview.checks[0].key='unknown'",
    'artifact.reviewed.coverageReview.checks[0].candidateIndex=999',
    'delete artifact.reviewed.coverageReview.checks[0].probabilities',
    'artifact.reviewed.coverageReview.checks[0].probability=0.001',
    'artifact.reviewed.coverageReview.checks[0].confidence=2',
    'artifact.reviewed.coverageReview.checks[0].probabilities.unknown=0.1',
    'artifact.coverageContext.review.usage.totalTokens++',
    'artifact.coverageContext.questionContractVersion=3',
    'artifact.coverageContext.questionContractVersion=2',
    'artifact.writeAuthorized=true',
])
def test_coverage_replay_rejects_malformed_parent_artifact(mutation: str) -> None:
    # Given a malformed prospective producer record, even a matching synthetic
    # receipt hash cannot bypass exact source, plan, question or answer binding.
    value = isolated_run_bun(COVERAGE_FEEDBACK_SETUP + mutation + r""";
      input.rejectedCoverageArtifacts[0].text=JSON.stringify(artifact);
      const digest=sha256Digest(input.rejectedCoverageArtifacts[0].text);
      proposal.rejectedCoverageReviews[0].sha256=digest;
      receipt.attempts.find(a=>a.coverageReviewArtifact).coverageReviewArtifact.sha256=digest;
      console.log(JSON.stringify({result:buildMemoryReplayFeedback(input)}));
    """)
    assert value['result'] is None


@pytest.mark.parametrize('mutation', [
    "fact.evidence[0].role='assistant'",
    "fact.evidence[0].quote='Not present in the original task'",
    "fact.statement='x'.repeat(2001)",
    "fact.statement='   '",
])
def test_coverage_replay_revalidates_facts_after_all_projection_hashes_change(mutation: str) -> None:
    value = isolated_run_bun(COVERAGE_FEEDBACK_SETUP + r"""
      const fact=artifact.coverageContext.review.accounts[1].uncovered[0];
    """ + mutation + r""";
      artifact.coverageContext.expectedReviewDigest=memoryCoverageReviewDigest(artifact.coverageContext.review);
      const prepared=prepareMemoryCoverageJudgment(snapshot,state.originalCandidates,state.existingMemories,artifact.coverageContext);
      artifact.expectedAccountDigest=artifact.coverageContext.expectedReviewDigest;
      artifact.expectedContextDigest=prepared.contextDigest;
      artifact.reviewed.coverageReview.contextDigest=prepared.contextDigest;
      artifact.coverageQuestions=prepared.questions;
      artifact.coverageIssueBindings=prepared.state.namedIssueBindings;
      input.rejectedCoverageArtifacts[0].text=JSON.stringify(artifact);
      const digest=sha256Digest(input.rejectedCoverageArtifacts[0].text);
      proposal.rejectedCoverageReviews[0].sha256=digest;
      receipt.attempts.find(a=>a.coverageReviewArtifact).coverageReviewArtifact.sha256=digest;
      console.log(JSON.stringify({result:buildMemoryReplayFeedback(input)}));
    """)
    assert value['result'] is None


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


@pytest.mark.parametrize('mutation', [
    'delete artifact.coverageContext.questionContractVersion',
    'artifact.coverageContext.questionContractVersion=3',
    "artifact.coverageContext.questionContractVersion='2'",
])
def test_scoped_coverage_feedback_rejects_contract_downgrade(mutation: str) -> None:
    # Controlled prospective framing only: the recorded historical service result
    # is never rejudged or promoted. Marker changes cannot replay scoped questions
    # under the historical contract, even after an artifact/receipt rehash.
    value = isolated_run_bun(COVERAGE_FEEDBACK_SETUP + r"""
      artifact.coverageContext.questionContractVersion=2;
      const prepared=prepareMemoryCoverageJudgment(snapshot,state.originalCandidates,state.existingMemories,artifact.coverageContext);
      artifact.coverageQuestions=prepared.questions;
      artifact.expectedContextDigest=prepared.contextDigest;
      artifact.reviewed.coverageReview.contextDigest=prepared.contextDigest;
      function bind(){
        input.rejectedCoverageArtifacts[0].text=JSON.stringify(artifact);
        const digest=sha256Digest(input.rejectedCoverageArtifacts[0].text);
        proposal.rejectedCoverageReviews[0].sha256=digest;
        receipt.attempts.find(a=>a.coverageReviewArtifact).coverageReviewArtifact.sha256=digest;
      }
      bind();const valid=buildMemoryReplayFeedback(input);
    """ + mutation + r""";
      bind();console.log(JSON.stringify({valid:!!valid,changed:buildMemoryReplayFeedback(input)}));
    """)
    assert value['valid'] is True
    assert value['changed'] is None
