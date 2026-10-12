"""Given real passing checks but an aborted task, preserve the task failure."""
from continuous_project_evidence import task_outcome, verifier_observation


def clean_inference():
    return {'exitCode':0,'modelErrors':0,'malformedSessionRows':0,
            'temporaryInstructionLeaked':False,'toolBudgetExceeded':False,
            'timedOut':False,'interrupted':False}


def test_real_budget_abort_is_a_failure_even_when_all_code_checks_pass(tmp_path):
    # Actual v17 idle learning arm: checks passed, model kept calling removed tools.
    inference={**clean_inference(),'modelErrors':1,'toolBudgetExceeded':True}
    verification={'passed':True,'behavior':{'passed':True},'types':{'passed':True},'upstream':{'passed':True}}
    outcome=task_outcome(inference,verification)
    assert outcome=={'passed':False,'failures':['model-error','tool-budget-exceeded']}
    observed=verifier_observation('idle',verification,tmp_path,{'index.js':'source'},b'actual session',inference=inference)
    assert observed['verification']==verification
    assert observed['taskOutcome']==outcome
    assert 'errorMessage' not in str(observed)


def test_success_and_check_failure_remain_distinct(tmp_path):
    inference=clean_inference()
    assert task_outcome(inference,{'passed':True})=={'passed':True,'failures':[]}
    assert task_outcome(inference,{'passed':False})=={'passed':False,'failures':['verification-failed']}
    assert 'taskOutcome' not in verifier_observation('old',{'passed':False},tmp_path,{},b'old')


def test_transport_exit_and_interruption_are_retained_without_provider_prose():
    inference={**clean_inference(),'exitCode':124,'timedOut':True,'interrupted':True,
               'errorMessage':'private provider text'}
    assert task_outcome(inference,{'passed':True})=={'passed':False,'failures':['process-exit','timeout','interrupted']}


def test_successful_read_followed_by_aborted_model_is_not_valid_feedback():
    from continuous_project_evidence import feedback_accepted
    feedback={**clean_inference(),'originalObservationsPreserved':True,'verifierObserved':True,
              'taskSourceUnchanged':True,'queuedFailure':{'id':'original'}}
    assert feedback_accepted(feedback)
    assert not feedback_accepted({**feedback,'modelErrors':1,'toolBudgetExceeded':True})
    assert not feedback_accepted({**feedback,'queuedFailure':None})


def test_exact_failure_confirmation_is_required_before_dependent_tasks():
    from continuous_project_evidence import exact_failure_processed
    from test_continuous_learning_coverage import full_evidence
    arm=full_evidence()['stages'][1]['arms']['with-learning']
    assert exact_failure_processed(arm['verifierFeedback'],arm['learning'])
    arm['learning']['completedBacklog']['failure-job']='wrong-ack'
    assert not exact_failure_processed(arm['verifierFeedback'],arm['learning'])
    arm['learning']['completedBacklog']['failure-job']='receipt-digest'
    arm['learning']['dossiers'][0]['observations'][0]['sessionDigest']='wrong-session'
    assert not exact_failure_processed(arm['verifierFeedback'],arm['learning'])
