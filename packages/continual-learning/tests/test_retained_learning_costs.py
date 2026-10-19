import json
import pytest
from continuous_failure_retention import retained_learning_costs


def usage(cost, tokens=5):
    return dict(input=2, output=3, cacheRead=0, cacheWrite=0, totalTokens=tokens, cost=cost)


def put(root, name, data):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


def test_retained_receipts_and_body_source_workers_are_counted_once(tmp_path):
    # Given interrupted recovery and a duplicate replay receipt, When costs
    # are recovered, Then count known calls once and keep missing cost unknown.
    u = usage(.25)
    receipt = dict(kind='learning-pipeline-receipt', batchId='batch', totals=u,
                   attempts=[dict(usageLedgerId='worker', usage=u)], costAvailable=True)
    put(tmp_path, 'memory/runs/scope/run/learning-pipeline-receipt.json', receipt)
    put(tmp_path, 'learning/scope/replay-fixture.json', {'attempts': [{'receipt': receipt}]})
    put(tmp_path, 'memory/runs/scope/run/memory-task-usage.json', dict(ledgerId='worker', knownUsage=u, complete=True))
    put(tmp_path, 'memory/runs/scope/unfinished/memory-body-usage-id.json', dict(ledgerId='body', knownUsage=usage(.1), complete=True))
    put(tmp_path, 'memory/runs/scope/audit/source-audit-usage.json', dict(ledgerId='source', knownUsage=usage(.05), complete=True))
    result = retained_learning_costs(tmp_path)
    assert result['knownLearningCost'] == pytest.approx(.4)
    assert result['knownLearningTokens'] == 15
    assert result['receiptBatches'] == ['batch']
    assert len(result['additionalWorkerLedgers']) == 2
    assert result['unknownCosts'] is True


def test_conflicting_usage_identity_is_not_accepted(tmp_path):
    for i, cost in enumerate((.1, .2)):
        put(tmp_path, f'memory/runs/scope/run{i}/memory-body-usage-id.json', dict(ledgerId='same', knownUsage=usage(cost), complete=True))
    with pytest.raises(ValueError, match='Conflicting'):
        retained_learning_costs(tmp_path)


def test_historical_source_audit_is_not_deduplicated_by_numeric_equality(tmp_path):
    receipt = dict(kind='learning-pipeline-receipt', batchId='batch', totals=usage(.1),
                   attempts=[dict(usage=usage(.1))])
    put(tmp_path, 'memory/runs/scope/run/learning-pipeline-receipt.json', receipt)
    put(tmp_path, 'memory/runs/scope/audit/source-audit-usage.json', dict(knownUsage=usage(.1), complete=True))
    result = retained_learning_costs(tmp_path)
    assert result['knownLearningCost'] == .1
    assert result['unresolvedLegacySourceAudits'] == ['memory/runs/scope/audit/source-audit-usage.json']


def test_project_model_and_snapshot_objects_cannot_inject_receipts(tmp_path):
    fake = dict(kind='learning-pipeline-receipt', batchId='fake', totals=usage(99), attempts=[])
    for name in ('project/fake.json', 'sessions/fake.json', 'memory/runs/scope/run/snapshot.json',
                 'memory/runs/scope/run/plan.json'):
        put(tmp_path, name, fake)
    result = retained_learning_costs(tmp_path)
    assert result['knownLearningCost'] == 0 and result['receiptBatches'] == []


def test_duplicate_worker_identity_inside_one_receipt_is_rejected(tmp_path):
    for equal in (False, True):
        put(tmp_path, 'memory/runs/scope/run/learning-pipeline-receipt.json', dict(
            kind='learning-pipeline-receipt', batchId='batch', totals=usage(.3), attempts=[
                dict(usageLedgerId='same', usage=usage(.1)),
                dict(usageLedgerId='same', usage=usage(.1 if equal else .2))]))
        with pytest.raises(ValueError, match='duplicate'):
            retained_learning_costs(tmp_path)


def test_live_receipt_and_worker_copies_count_once_and_keep_failures():
    from continuous_failure_retention import learning_cost_summary
    u=usage(.4,41)
    receipt=dict(kind='learning-pipeline-receipt',batchId='early',totals=u,
        attempts=[dict(usageLedgerId='worker',usage=u,outcome='applied')],
        usageAvailable=True,costAvailable=True,operations=1)
    ledger=dict(ledgerId='worker',knownUsage=u,complete=True)
    result=learning_cost_summary([receipt,receipt],[dict(receipt=receipt,outcome='completed')],[ledger,ledger])
    assert result['knownLearningCost']==.4 and result['knownLearningTokens']==41
    assert result['actualLearningOperations']==1 and result['interruptedUnknownUsage']==0
    assert result['allLearningCostsPriced'] and result['learningFailedAttempts']==0
    failed={**receipt,'batchId':'failed','totals':{k:0 for k in usage(0)},'attempts':[dict(outcome='failed')],
            'usageAvailable':False,'costAvailable':False,'operations':0}
    result=learning_cost_summary([receipt,failed],[],[ledger])
    assert result['knownLearningCost']==.4 and result['learningFailedAttempts']==1
    assert result['interruptedUnknownUsage']==1 and not result['allLearningCostsPriced']


@pytest.mark.parametrize('field,value', [('totals',usage(.9)), ('operations',2),
    ('input',{'source':'backlog-session'}), ('attempts',[{'outcome':'failed'}])])
def test_live_conflicting_same_batch_snapshots_block_instead_of_picking_max(field,value):
    from continuous_failure_retention import learning_cost_summary
    receipt=dict(kind='learning-pipeline-receipt',batchId='same',totals=usage(.1),attempts=[],operations=0)
    with pytest.raises(ValueError,match='Conflicting'):
        learning_cost_summary([receipt,{**receipt,field:value}],[],[])


def test_live_worker_mismatch_or_duplicate_receipt_identity_blocks():
    from continuous_failure_retention import learning_cost_summary
    receipt=dict(kind='learning-pipeline-receipt',batchId='one',totals=usage(.1),
                 attempts=[dict(usageLedgerId='worker',usage=usage(.1))])
    with pytest.raises(ValueError,match='Conflicting'):
        learning_cost_summary([receipt],[],[dict(ledgerId='worker',knownUsage=usage(.2),complete=True)])
    with pytest.raises(ValueError,match='duplicate'):
        learning_cost_summary([receipt,{**receipt,'batchId':'two'}],[],[])
    with pytest.raises(ValueError,match='Conflicting'):
        learning_cost_summary([],[],[dict(ledgerId='worker',knownUsage=usage(.1),complete=True),
                                    dict(ledgerId='worker',knownUsage=usage(.1),complete=False)])


@pytest.mark.parametrize('outcome', ['noop','declined','screened','skipped','applied'])
def test_standalone_settled_nonfailure_outcomes_do_not_count_as_failures(outcome):
    from continuous_failure_retention import learning_cost_summary
    receipt=dict(kind='learning-pipeline-receipt',batchId='settled',totals={k:0 for k in usage(0)},
                 attempts=[dict(outcome=outcome)],operations=0,usageAvailable=True,costAvailable=True)
    result=learning_cost_summary([receipt],[],[])
    assert result['learningFailedAttempts']==0


def test_receipt_total_cannot_hide_matching_known_worker_usage():
    from continuous_failure_retention import learning_cost_summary
    u=usage(.4,41)
    receipt=dict(kind='learning-pipeline-receipt',batchId='understated',totals=usage(0,0),
                 attempts=[dict(usageLedgerId='worker',usage=u,outcome='applied')],
                 usageAvailable=True,costAvailable=True,operations=1)
    with pytest.raises(ValueError,match='totals'):
        learning_cost_summary([receipt],[],[dict(ledgerId='worker',knownUsage=u,complete=True)])



def test_replay_link_does_not_erase_a_failed_phase_before_repair():
    from continuous_failure_retention import learning_cost_summary
    receipt=dict(kind='learning-pipeline-receipt',batchId='repaired',totals={k:0 for k in usage(0)},
                 attempts=[dict(outcome='failed'),dict(outcome='applied')],operations=1,
                 usageAvailable=False,costAvailable=False)
    standalone=learning_cost_summary([receipt],[],[])
    linked=learning_cost_summary([receipt],[dict(receipt=receipt,outcome='completed')],[])
    assert standalone['learningFailedAttempts']==linked['learningFailedAttempts']==1
    failed_job=learning_cost_summary([receipt],[dict(receipt=receipt,outcome='failed')],[])
    assert failed_job['learningFailedAttempts']==1
    assert failed_job['learningFailedReplayAttempts']==1
    assert standalone['learningFailedReplayAttempts']==0
    missing=learning_cost_summary([],[dict(outcome='failed')],[])
    assert missing['learningFailedAttempts']==1 and missing['learningFailedReplayAttempts']==1



def test_retained_worker_completion_conflict_is_not_overwritten(tmp_path):
    for index, complete in enumerate((True,False)):
        put(tmp_path,f'memory/runs/scope/run{index}/memory-task-usage.json',
            dict(ledgerId='same',knownUsage=usage(.1),complete=complete))
    with pytest.raises(ValueError,match='Conflicting'):
        retained_learning_costs(tmp_path)


def test_retained_receipt_totals_must_match_known_attempts(tmp_path):
    put(tmp_path,'memory/runs/scope/run/learning-pipeline-receipt.json',
        dict(kind='learning-pipeline-receipt',batchId='hidden',totals={k:0 for k in usage(0)},
             attempts=[dict(usage=usage(.4),usageLedgerId='known')]))
    with pytest.raises(ValueError,match='totals'):
        retained_learning_costs(tmp_path)
