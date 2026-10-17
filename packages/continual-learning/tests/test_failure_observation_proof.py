"""Given actual failed v18 feedback, distinguish task failure from safe evidence."""
from support import run_bun


def successful_proof(mutation=''):
    return run_bun('''
      import fs from 'node:fs';
      import {successfulFailureObservationReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-successful-verifier-feedback.json','utf8'));
    '''+mutation+'''console.log(JSON.stringify(successfulFailureObservationReady(input)));''')


def test_actual_successful_feedback_proves_observation_without_retry_authorization():
    # Given the retained v28 session, When proving its successful feedback read,
    # Then bind original bytes and pending slice without promoting the failed task.
    value = successful_proof()
    assert value['ready'], value
    assert value['reason'] == 'complete-successful-failure-observation'


@__import__('pytest').mark.parametrize('mutation',[
    "input.originalSession+=' ';",
    "input.sourceAfter={'index.js':'changed'};",
    "const o=JSON.parse(input.verifierText);o.verification.afterRecovery={passed:true};input.verifierText=JSON.stringify(o);",
    "input.currentSession=input.currentSession.replace(input.verifierPath,input.verifierPath+'other');",
    "input.queued.to--;",
    "input.queued.digest='different';",
    "input.explicitBackfills=1;",
    "input.currentSession=input.currentSession.replace('tools-removed','other');",
    "input.currentSession=input.currentSession.replace('\\\"stopReason\\\":\\\"stop\\\"','\\\"stopReason\\\":\\\"error\\\"');",
])
def test_successful_feedback_rejects_changed_report_source_slice_or_failed_summary(mutation):
    assert not successful_proof(mutation)['ready']


@__import__('pytest').mark.parametrize('edit',[
    "rows.at(-1).message.errorMessage='provider failed';",
    "rows.find(row=>row.message?.role==='assistant').message.stopReason='error';",
    "rows.find(row=>row.message?.role==='assistant').message.stopReason='aborted';",
])
def test_successful_feedback_rejects_errors_stripped_by_context_projection(edit):
    assert not successful_proof(r'''
      const rows=input.currentSession.slice(input.originalSession.length).trimEnd().split('\n').map(JSON.parse);
    '''+edit+r'''
      input.currentSession=input.originalSession+rows.map(JSON.stringify).join('\n')+'\n';
    ''')['ready']


def test_successful_feedback_rejects_an_extra_continue_even_with_valid_backlog():
    assert not successful_proof(r'''
      const {parseSessionEntries,buildContextEntries}=await import('@earendil-works/pi-coding-agent');
      const {currentTaskSlice}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
      const {backlogIdentity}=await import('./packages/continual-learning/extensions/learning-backlog.ts');
      const {createHash}=await import('node:crypto');
      const rows=input.currentSession.trimEnd().split('\n').map(JSON.parse);
      const last=rows.pop();const id='extra-continue';
      rows.push({type:'message',id,parentId:last.parentId,timestamp:last.timestamp,
        message:{role:'user',content:[{type:'text',text:'continue'}],timestamp:0}});
      rows.push({...last,parentId:id});input.currentSession=rows.map(JSON.stringify).join('\n')+'\n';
      const context=buildContextEntries(parseSessionEntries(input.currentSession).filter(row=>row.type!=='session'));
      input.queued.to=context.length-1;
      input.queued.digest=createHash('sha256').update(JSON.stringify(currentTaskSlice(context.slice(input.queued.from)))).digest('hex');
      input.queued.id=backlogIdentity(input.queued.scopeKey,input.queued);
    ''')['ready']


def proof(mutation=''):
    return run_bun('''
      import fs from 'node:fs';
      import {failureObservationReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-failed-verifier-feedback.json','utf8'));
    '''+mutation+'''console.log(JSON.stringify(failureObservationReady(input)));''')


def test_actual_failed_feedback_is_complete_evidence_without_promoting_task_success():
    value=proof()
    assert value['ready'], value
    from continuous_project_evidence import feedback_accepted, task_outcome
    failed={'exitCode':0,'modelErrors':1,'toolBudgetExceeded':True}
    assert not task_outcome(failed,{'passed':True})['passed']
    assert not feedback_accepted({**failed,'originalObservationsPreserved':True,'verifierObserved':True,
                                  'taskSourceUnchanged':True,'queuedFailure':{'id':'original'}})


@__import__('pytest').mark.parametrize('mutation',[
    "input.originalSession+=' ';",
    "input.sourceAfter={'index.js':'changed'};",
    "const o=JSON.parse(input.verifierText);o.logs.upstream+='changed';input.verifierText=JSON.stringify(o);",
    "input.currentSession=input.currentSession.replace(input.verifierPath,input.verifierPath+'other');",
    "input.currentSession=input.currentSession.replace('Tool read not found','read completed');",
    "input.currentSession=input.currentSession.replace('summary-tool-loop-stopped','other');",
    "input.queued.to--;",
    "input.queued.digest='different';",
    "input.explicitBackfills=1;",
    "input.currentSession=input.currentSession.trimEnd().split('\\n').slice(0,-1).join('\\n')+'\\n';",
])
def test_incomplete_changed_unsafe_or_consumed_feedback_is_rejected(mutation):
    assert not proof(mutation)['ready']


def test_actual_read_cannot_be_replaced_by_claims_partial_output_or_successful_extra_execution():
    mutations=[
      ("row.message.content[0].text=row.message.content[0].text.slice(0,-1)", 'eafd867c', 'incomplete-verifier-read'),
      ("row.message.isError=false", 'f5447231', 'unproven-tool-rejection'),
      ("row.message.content[0].arguments.offset=1", '41afb8f1', 'verifier-read-boundary'),
      ("row.message.toolCallId='unmatched'", 'eafd867c', 'incomplete-verifier-read'),
    ]
    for edit,id,reason in mutations:
        mutation="""
          const rows=input.currentSession.slice(input.originalSession.length).trimEnd().split('\\n').map(JSON.parse);
          const row=rows.find(row=>row.id===ID);
          EDIT;
          input.currentSession=input.originalSession+rows.map(JSON.stringify).join('\\n')+'\\n';
        """.replace('ID',repr(id)).replace('EDIT',edit)
        assert proof(mutation)=={'ready':False,'reason':reason}


def test_latest_actual_failed_summary_extension_is_preserved_before_backfill():
    value=run_bun(r'''import fs from 'node:fs';
      import {failureObservationExtensionReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      const prior=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-failed-verifier-feedback.json','utf8'));
      const extension=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-failed-summary-extension.json','utf8'));
      const input={...prior,...extension,originalSession:prior.currentSession};
      console.log(JSON.stringify(failureObservationExtensionReady(prior,input)));
    ''')
    assert value['ready'], value


@__import__('pytest').mark.parametrize('mutation',[
    "input.originalSession+=' ';",
    "input.sourceAfter={'index.js':'changed'};",
    "input.explicitBackfills=1;",
    "input.currentSession=input.currentSession.replace('Tool bash not found','executed');",
    "input.queued.to--;",
    "input.queued.digest='changed';",
    "prior.verifierText='{}';",
])
def test_latest_failed_diagnostic_requires_full_safe_extension(mutation):
    value=run_bun(r'''import fs from 'node:fs';
      import {failureObservationExtensionReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      const prior=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-failed-verifier-feedback.json','utf8'));
      const extension=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-failed-summary-extension.json','utf8'));
      const input={...prior,...extension,originalSession:prior.currentSession};
    '''+mutation+'''console.log(JSON.stringify(failureObservationExtensionReady(prior,input)));''')
    assert not value['ready']


def deadline_proof(mutation=''):
    return run_bun('''
      import fs from 'node:fs';
      import {successfulFailureObservationReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-deadline-verifier-feedback.json','utf8'));
    '''+mutation+'''console.log(JSON.stringify(successfulFailureObservationReady(input)));''')


def test_actual_successful_feedback_keeps_parent_settled_deadline_after_summary():
    # Given V30's complete read and successful summary followed by the parent's
    # settled marker, When admitting observed failure, Then keep every raw row
    # and require the complete deadline proof instead of assuming the last row
    # must be an assistant message. The original source task remains failed.
    value=deadline_proof()
    assert value['ready'],value
    assert value['reason']=='complete-successful-failure-observation'


@__import__('pytest').mark.parametrize('edit',[
    "rows.at(-1).data.stage='expired';",
    "rows.at(-1).data.stage='shutdown';",
    "rows.at(-1).data.elapsedMs=900001;",
    "rows.at(-1).data.elapsedMs=-1;",
    "rows.at(-1).data.elapsedMs=true;",
    "rows.at(-1).data.limitMs=900001;",
    "rows.at(-1).data.extra='untrusted';",
    "rows.at(-1).parentId='foreign';",
    "rows[0].parentId='foreign';",
    "rows[1].parentId='foreign';",
    "rows.find(r=>r.customType==='continuous-study-task-deadline').data.stage='settled';",
    "rows.find(r=>r.customType==='continuous-study-task-deadline').data.elapsedMs=99999;",
    "rows.shift();",
    "rows.push({...rows.at(-1),id:'extra-deadline'});",
    "rows.push({type:'custom',id:'unexpected-trailer',parentId:rows.at(-1).id,customType:'other',data:{}});",
    "rows.at(-2).message.stopReason='error';",
])
def test_deadline_feedback_does_not_admit_incomplete_failed_or_forged_lifecycle(edit):
    assert not deadline_proof(r'''
      const rows=input.currentSession.slice(input.originalSession.length).trimEnd().split('\n').map(JSON.parse);
    '''+edit+r'''
      input.currentSession=input.originalSession+rows.map(JSON.stringify).join('\n')+'\n';
    ''')['ready']


def rebound_deadline_proof(edit):
    return deadline_proof(r'''
      const {parseSessionEntries,buildContextEntries}=await import('@earendil-works/pi-coding-agent');
      const {currentTaskSlice}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
      const {backlogIdentity}=await import('./packages/continual-learning/extensions/learning-backlog.ts');
      const {createHash}=await import('node:crypto');
      let rows=input.currentSession.slice(input.originalSession.length).trimEnd().split('\n').map(JSON.parse);
    '''+edit+r'''
      input.currentSession=input.originalSession+rows.map(JSON.stringify).join('\n')+'\n';
      const context=buildContextEntries(parseSessionEntries(input.currentSession).filter(row=>row.type!=='session'));
      input.queued.to=context.length-1;
      input.queued.digest=createHash('sha256').update(JSON.stringify(currentTaskSlice(context.slice(input.queued.from)))).digest('hex');
      input.queued.id=backlogIdentity(input.queued.scopeKey,input.queued);
    ''')


def test_current_deadline_protocol_cannot_be_stripped_to_historical_after_rebinding():
    value=rebound_deadline_proof(r'''
      const predecessor=JSON.parse(input.originalSession.trimEnd().split('\n').at(-1)).id;
      rows=rows.filter(r=>r.customType!=='continuous-study-task-deadline');
      rows[0].parentId=predecessor;
    ''')
    assert not value['ready'],value


def test_started_lifecycle_cannot_be_detached_from_backlog_after_rebinding():
    value=rebound_deadline_proof("rows[2].parentId=rows[0].parentId;")
    assert not value['ready'],value
