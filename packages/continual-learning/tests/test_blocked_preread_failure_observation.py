from support import run_bun


def proof(mutation=''):
    return run_bun('''
      import fs from 'node:fs';
      import {blockedPreReadFailureObservationReady,successfulFailureObservationReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      const input=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-blocked-preread-feedback.json','utf8'));
    ''' + mutation + '''console.log(JSON.stringify({proof:blockedPreReadFailureObservationReady(input),ordinary:successfulFailureObservationReady(input)}));''')


def test_actual_blocked_preread_retains_failed_feedback_but_proves_observation():
    value = proof()
    assert value['proof']['ready'], value
    assert value['proof']['reason'] == 'complete-observation-after-single-blocked-read'
    assert not value['ordinary']['ready']


@__import__('pytest').mark.parametrize('mutation', [
    "input.originalSession+=' ';",
    "input.sourceAfter={'index.js':'changed'};",
    "input.explicitBackfills=1;",
    "input.queued.digest='changed';",
    "input.queued.to--;",
    "input.currentSession=input.currentSession.replace('verifier-read-blocked','tools-removed');",
    "input.currentSession=input.currentSession.replace('This verification continuation only permits read of','untrusted model refusal of');",
    "const rows=input.currentSession.trimEnd().split('\\n').map(JSON.parse);const start=input.originalSession.trimEnd().split('\\n').length;const calls=rows.slice(start).filter(r=>r.message?.role==='assistant'&&r.message.content.some(p=>p.type==='toolCall'));calls[0].message.content.find(p=>p.type==='toolCall').name='bash';input.currentSession=rows.map(JSON.stringify).join('\\n')+'\\n';",
    "const rows=input.currentSession.trimEnd().split('\\n').map(JSON.parse);const start=input.originalSession.trimEnd().split('\\n').length;const result=rows.slice(start).find(r=>r.message?.role==='toolResult'&&r.message.isError===false);result.message.content[0].text+=' altered';input.currentSession=rows.map(JSON.stringify).join('\\n')+'\\n';",
    "const rows=input.currentSession.trimEnd().split('\\n').map(JSON.parse);rows.at(-1).message.stopReason='error';input.currentSession=rows.map(JSON.stringify).join('\\n')+'\\n';",
])
def test_changed_incomplete_repeated_or_unsafe_feedback_cannot_admit_recovery(mutation):
    assert not proof(mutation)['proof']['ready']


def test_boundary_denial_is_a_failed_feedback_task():
    from continuous_project_evidence import feedback_accepted, task_outcome
    feedback = dict(exitCode=0, originalObservationsPreserved=True, verifierObserved=True,
                    taskSourceUnchanged=True, queuedFailure={'id': 'bound'}, verifierReadBoundaryViolations=1)
    assert not feedback_accepted(feedback)
    assert 'verifier-read-boundary' in task_outcome(feedback, {'passed': True})['failures']
