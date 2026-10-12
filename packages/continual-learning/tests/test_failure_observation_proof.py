"""Given actual failed v18 feedback, distinguish task failure from safe evidence."""
from support import run_bun


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
